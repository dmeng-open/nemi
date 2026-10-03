import logging
import uuid
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphInterrupt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.graph import compile_planning_graph
from app.agents.llm import (
    ConstraintParser,
    Explainer,
    OpenAIConstraintParser,
    OpenAIExplainer,
    OpenAIGateway,
    UnconfiguredParser,
)
from app.agents.nodes import EventLog, PlanningDeps, default_schedule, make_nodes
from app.agents.itinerary.routing import is_itinerary_request
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.exceptions import (
    AppError,
    ApprovalRequired,
    CalendarCreateUnconfirmed,
    CalendarNotConnected,
    CalendarReadFailed,
    InvalidSelection,
    PlanNotFound,
    PlanStateError,
    ProviderError,
    ScheduleConflictError,
)
from app.core.logging import safe_error_text
from app.core.messages import SAFE_MESSAGES
from app.domain.candidates import Candidate
from app.domain.ranking import RankedCandidate
from app.models.agent import AgentRun, AgentRunEvent, InteractionEvent
from app.models.planning import (
    PlanningConstraint,
    PlanningSession,
    Recommendation,
    RecommendationCandidate,
)
from app.models.user import LOCAL_USER_ID
from app.providers.factory import (
    build_calendar_provider,
    build_event_provider,
    build_restaurant_provider,
)
from app.providers.http import bind_plan_id, reset_plan_id
from app.repositories.users import ensure_local_user, get_preferences
from app.services.calendar.scheduling import schedule_approved_plan
from app.services.ranking.heuristic import HeuristicRanker
from app.services.recommendations.explanations import TemplateExplainer

logger = logging.getLogger(__name__)


class DbEventLog(EventLog):
    def __init__(self, session: AsyncSession, run_id: uuid.UUID, session_id: uuid.UUID) -> None:
        self.session = session
        self.run_id = run_id
        self.session_id = session_id

    async def emit(
        self,
        event_type: str,
        status: str,
        metadata: dict | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.session.add(
            AgentRunEvent(
                agent_run_id=self.run_id,
                session_id=self.session_id,
                event_type=event_type,
                status=status,
                duration_ms=duration_ms,
                safe_metadata=metadata or {},
                error_code=error_code,
            )
        )
        await self.session.commit()


class PlanningOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        parser: ConstraintParser | None = None,
        explainer: Explainer | None = None,
        clock: Clock | None = None,
        checkpointer=None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.parser = parser or _default_parser(settings)
        self.explainer = explainer or _default_explainer(settings)
        self.clock = clock or SystemClock()
        self.checkpointer = checkpointer or MemorySaver()

    async def create_plan(self, message: str) -> uuid.UUID:
        async with self.session_factory() as session:
            user = await ensure_local_user(session)
            plan = PlanningSession(
                user_id=user.id, user_request=message.strip(), status="processing"
            )
            session.add(plan)
            await session.flush()
            run = AgentRun(session_id=plan.id, user_id=user.id, status="running")
            session.add(run)
            await session.flush()
            _add_event(session, run, "request_received", "completed", {})
            await session.commit()
            return plan.id

    async def clarify(self, plan_id: uuid.UUID, message: str) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            if plan.status != "awaiting_clarification":
                raise PlanStateError("This plan is not waiting for a clarification.")
            extra = message.strip()
            plan.follow_up = f"{plan.follow_up}\n{extra}".strip() if plan.follow_up else extra
            plan.status = "processing"
            plan.clarification_question = None
            plan.error_code = None
            plan.error_message = None
            run = AgentRun(session_id=plan.id, user_id=plan.user_id, status="running")
            session.add(run)
            await session.flush()
            _add_event(session, run, "request_received", "completed", {})
            await session.commit()

    async def continue_plan(self, plan_id: uuid.UUID) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            if plan.status != "awaiting_location":
                raise PlanStateError("This plan is not waiting for a location.")
            plan.status = "processing"
            plan.error_code = None
            plan.error_message = None
            run = AgentRun(session_id=plan.id, user_id=plan.user_id, status="running")
            session.add(run)
            await session.flush()
            _add_event(session, run, "request_received", "completed", {})
            await session.commit()

    async def run_discovery(self, plan_id: uuid.UUID) -> None:
        if await self._request_is_itinerary(plan_id):
            from app.agents.itinerary.runtime import run_itinerary_discovery

            await run_itinerary_discovery(self, plan_id)
            return
        await self._discover_single(plan_id)

    async def _discover_single(self, plan_id: uuid.UUID) -> None:
        token = bind_plan_id(str(plan_id))
        try:
            async with self.session_factory() as session:
                plan = await _owned_plan(session, plan_id)
                run = await _latest_run(session, plan_id)
                if run is None:
                    raise PlanStateError("This plan has no agent run.")
                deps = await self._deps(session, run)
                preferences = await get_preferences(session, LOCAL_USER_ID)
                if preferences.timezone:
                    from zoneinfo import ZoneInfo

                    deps.zone = ZoneInfo(preferences.timezone)
                nodes = make_nodes(deps)
                deps.schedule = default_schedule(deps)
                graph = compile_planning_graph(nodes, MemorySaver())
                config: RunnableConfig = {"configurable": {"thread_id": str(plan_id)}}
                initial = {
                    "session_id": str(plan.id),
                    "user_id": str(plan.user_id),
                    "user_request": _compose_request(plan),
                    "approved": False,
                    "errors": [],
                    "status": "processing",
                }
                final = await _invoke(graph, initial, config)
                await self._persist(session, plan, run, final)
                await session.commit()
        except PlanNotFound:
            raise
        except Exception as exc:
            logger.error(
                "plan_failed",
                extra={"plan_id": str(plan_id), "detail": safe_error_text(exc)},
            )
            await self.mark_failed(plan_id, exc)
        finally:
            reset_plan_id(token)

    async def select(self, plan_id: uuid.UUID, candidate_id: str) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            if plan.status not in {"awaiting_selection", "awaiting_approval"}:
                raise PlanStateError("Choose an option once recommendations are ready.")
            rows = await _candidate_rows(session, plan.id)
            match = next(
                (row for row in rows if row.candidate_id == candidate_id and row.shown),
                None,
            )
            if match is None:
                raise InvalidSelection()
            for row in rows:
                row.selected = row.candidate_id == candidate_id
            plan.selected_candidate_id = candidate_id
            plan.status = "awaiting_approval"
            plan.approved = False
            plan.error_code = None
            plan.error_message = None
            run = await _latest_run(session, plan.id)
            if run is not None:
                _add_event(
                    session, run, "candidate_selected", "completed", {"candidate_id": candidate_id}
                )
                _add_event(session, run, "approval_requested", "started", {})
            _interact(
                session,
                plan,
                "recommendation_selected",
                candidate_id,
                properties=_interaction_properties(match),
            )
            await session.commit()

    async def reject(self, plan_id: uuid.UUID, candidate_id: str) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            if plan.status not in {"awaiting_selection", "awaiting_approval"}:
                raise PlanStateError("Not this is available while you are choosing.")
            rows = await _candidate_rows(session, plan.id)
            match = next(
                (row for row in rows if row.candidate_id == candidate_id and row.shown),
                None,
            )
            if match is None:
                raise InvalidSelection()
            if plan.status == "awaiting_approval" and plan.selected_candidate_id != candidate_id:
                raise PlanStateError("Not this is available while you are choosing.")
            already_rejected = match.rejected
            match.rejected = True
            if plan.selected_candidate_id == candidate_id:
                for row in rows:
                    row.selected = False
                plan.selected_candidate_id = None
                plan.approved = False
                plan.status = "awaiting_selection"
                plan.error_code = None
                plan.error_message = None
            if not already_rejected:
                _interact(
                    session,
                    plan,
                    "recommendation_rejected",
                    candidate_id,
                    properties=_interaction_properties(match),
                )
            await session.commit()

    async def clear_selection(self, plan_id: uuid.UUID) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            if plan.status != "awaiting_approval":
                raise PlanStateError("There is no selection to cancel.")
            for row in await _candidate_rows(session, plan.id):
                row.selected = False
            plan.selected_candidate_id = None
            plan.approved = False
            plan.status = "awaiting_selection"
            plan.error_code = None
            plan.error_message = None
            await session.commit()

    async def approve(
        self,
        plan_id: uuid.UUID,
        approved: bool,
        itinerary_id: str | None = None,
    ) -> None:
        if await self._plan_is_itinerary(plan_id):
            from app.agents.itinerary.runtime import resume_itinerary

            action = "approve" if approved else "cancel"
            await resume_itinerary(
                self,
                plan_id,
                {"action": action, "itinerary_id": itinerary_id},
            )
            return
        token = bind_plan_id(str(plan_id))
        try:
            await self._approve(plan_id, approved)
        finally:
            reset_plan_id(token)

    async def _approve(self, plan_id: uuid.UUID, approved: bool) -> None:
        async with self.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            run = await _latest_run(session, plan.id)
            if approved and plan.status == "scheduled":
                return
            if not approved:
                if plan.status != "awaiting_approval":
                    raise PlanStateError("This plan is not waiting for approval.")
                plan.status = "cancelled"
                plan.approved = False
                if run is not None:
                    _add_event(session, run, "approval_received", "completed", {"approved": False})
                _interact(session, plan, "plan_cancelled", plan.selected_candidate_id)
                await session.commit()
                return

            if plan.status != "awaiting_approval" or not plan.selected_candidate_id:
                raise PlanStateError("Select an option before approving it.")
            rows = await _candidate_rows(session, plan.id)
            match = next(
                (
                    row
                    for row in rows
                    if row.candidate_id == plan.selected_candidate_id and row.shown
                ),
                None,
            )
            if match is None:
                raise InvalidSelection()
            candidate = Candidate.model_validate(match.payload)
            calendar = build_calendar_provider(self.settings, session, plan.user_id)
            if run is not None:
                _add_event(session, run, "approval_received", "completed", {"approved": True})
                _add_event(session, run, "calendar_write_started", "started", {})
            try:
                result = await schedule_approved_plan(
                    calendar,
                    approved=True,
                    plan_id=str(plan.id),
                    candidate=candidate,
                    explanation=match.explanation,
                )
            except ScheduleConflictError:
                plan.error_code = "schedule_conflict"
                plan.error_message = SAFE_MESSAGES["schedule_conflict"]
                if run is not None:
                    _add_event(
                        session,
                        run,
                        "calendar_write_failed",
                        "failed",
                        {"error_code": "schedule_conflict"},
                        error_code="schedule_conflict",
                    )
                await session.commit()
                raise
            except (CalendarNotConnected, CalendarReadFailed, CalendarCreateUnconfirmed) as exc:
                code = {
                    CalendarNotConnected: "calendar_not_connected",
                    CalendarReadFailed: "calendar_read_failed",
                    CalendarCreateUnconfirmed: "calendar_write_unconfirmed",
                }[type(exc)]
                plan.status = "awaiting_approval"
                plan.approved = False
                plan.error_code = code
                plan.error_message = SAFE_MESSAGES[code]
                if run is not None:
                    _add_event(
                        session,
                        run,
                        "calendar_write_failed",
                        "failed",
                        {"error_code": code},
                        error_code=code,
                    )
                await session.commit()
                return
            for row in rows:
                row.approved = row.candidate_id == candidate.id
                row.scheduled = row.candidate_id == candidate.id
            plan.approved = True
            plan.status = "scheduled"
            plan.error_code = None
            plan.error_message = None
            if not result.replayed and run is not None:
                run.status = "completed"
                run.finished_at = datetime.now(UTC)
                _add_event(session, run, "calendar_write_completed", "completed", {})
            if not await _scheduled_interaction_exists(session, plan.id, candidate.id):
                _interact(
                    session,
                    plan,
                    "plan_scheduled",
                    candidate.id,
                    properties=_interaction_properties(match),
                )
            await session.commit()

    async def mark_failed(self, plan_id: uuid.UUID, exc: Exception) -> None:
        code, message = _classify(exc)
        async with self.session_factory() as session:
            plan = await session.get(PlanningSession, plan_id)
            if plan is None:
                return
            plan.status = "failed"
            plan.error_code = code
            plan.error_message = message
            run = await _latest_run(session, plan_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                _add_event(
                    session,
                    run,
                    "planning_failed",
                    "failed",
                    {"error_code": code},
                    error_code=code,
                )
            await session.commit()

    async def revise(self, plan_id: uuid.UUID, message: str) -> None:
        if not await self._plan_is_itinerary(plan_id):
            raise PlanStateError("Tell me which single option to change, or start a new plan.")
        from app.agents.itinerary.runtime import resume_itinerary

        await resume_itinerary(self, plan_id, {"action": "revise", "message": message})

    async def _request_is_itinerary(self, plan_id: uuid.UUID) -> bool:
        async with self.session_factory() as session:
            plan = await session.get(PlanningSession, plan_id)
            if plan is None:
                return False
            return is_itinerary_request(_compose_request(plan))

    async def _plan_is_itinerary(self, plan_id: uuid.UUID) -> bool:
        async with self.session_factory() as session:
            plan = await session.get(PlanningSession, plan_id)
            return plan is not None and plan.plan_type == "itinerary"

    async def _deps(self, session: AsyncSession, run: AgentRun) -> PlanningDeps:
        async def load_preferences():
            return await get_preferences(session, LOCAL_USER_ID)

        deps = PlanningDeps(
            parser=self.parser,
            explainer=self.explainer,
            events=build_event_provider(self.settings),
            restaurants=build_restaurant_provider(self.settings),
            calendar=build_calendar_provider(self.settings, session, LOCAL_USER_ID),
            ranker=HeuristicRanker(self.settings.ranking_weights),
            log=DbEventLog(session, run.id, run.session_id),
            clock=self.clock,
            zone=self.settings.zone(),
            load_preferences=load_preferences,
            schedule=default_schedule_placeholder,
            event_provider_name=self.settings.event_provider,
            place_provider_name=self.settings.place_provider,
        )
        return deps

    async def _persist(
        self,
        session: AsyncSession,
        plan: PlanningSession,
        run: AgentRun,
        final: dict,
    ) -> None:
        status = final.get("status") or "failed"
        ranked_raw = final.get("ranked_candidates") or []
        shown = [item for item in ranked_raw if item.get("shown")]
        if status in {"processing", "scheduling"} and shown:
            status = "awaiting_selection"
        plan.plan_type = final.get("plan_type")
        plan.summary = final.get("summary")
        plan.clarification_question = final.get("clarification_question")
        plan.error_code = final.get("error_code")
        plan.error_message = SAFE_MESSAGES.get(plan.error_code or "", None)
        if final.get("constraints"):
            await session.execute(
                delete(PlanningConstraint).where(PlanningConstraint.session_id == plan.id)
            )
            session.add(
                PlanningConstraint(
                    session_id=plan.id,
                    plan_type=final.get("plan_type"),
                    payload=final["constraints"],
                )
            )
        if ranked_raw:
            recommendation = Recommendation(
                session_id=plan.id,
                user_id=plan.user_id,
                summary=plan.summary,
            )
            session.add(recommendation)
            await session.flush()
            stored: list[tuple[RecommendationCandidate, RankedCandidate]] = []
            for item in ranked_raw:
                ranked = RankedCandidate.model_validate(item)
                row = RecommendationCandidate(
                    recommendation_id=recommendation.id,
                    session_id=plan.id,
                    user_id=plan.user_id,
                    candidate_id=ranked.candidate.id,
                    candidate_type=ranked.candidate.candidate_type,
                    rank_position=ranked.rank_position,
                    final_score=ranked.final_score,
                    preference_score=ranked.components.preference,
                    schedule_score=ranked.components.schedule,
                    distance_score=ranked.components.distance,
                    price_score=ranked.components.price,
                    quality_score=ranked.components.quality,
                    shown=ranked.shown,
                    exclusion_reason=ranked.exclusion_reason,
                    explanation=ranked.explanation,
                    payload=ranked.candidate.model_dump(mode="json"),
                )
                session.add(row)
                stored.append((row, ranked))
            await session.flush()
            for row, ranked in stored:
                if ranked.shown:
                    _interact(
                        session,
                        plan,
                        "recommendation_shown",
                        ranked.candidate.id,
                        properties=_interaction_properties(row),
                    )
        plan.status = status
        if status != "failed":
            run.status = "completed"
            run.finished_at = datetime.now(UTC)


async def default_schedule_placeholder(state: dict):
    del state
    raise ApprovalRequired()


def _default_parser(settings: Settings) -> ConstraintParser:
    if not settings.openai_configured:
        return UnconfiguredParser()
    return OpenAIConstraintParser(OpenAIGateway(settings))


def _default_explainer(settings: Settings) -> Explainer:
    if not settings.openai_configured:
        return TemplateExplainer()
    return OpenAIExplainer(OpenAIGateway(settings))


def _compose_request(plan: PlanningSession) -> str:
    if plan.follow_up:
        return f"{plan.user_request}\n\nAdditional detail: {plan.follow_up}"
    return plan.user_request


def _add_event(
    session: AsyncSession,
    run: AgentRun,
    event_type: str,
    status: str,
    metadata: dict,
    error_code: str | None = None,
) -> None:
    session.add(
        AgentRunEvent(
            agent_run_id=run.id,
            session_id=run.session_id,
            event_type=event_type,
            status=status,
            safe_metadata=metadata,
            error_code=error_code,
        )
    )


def _interaction_properties(row: RecommendationCandidate) -> dict:
    payload = row.payload or {}
    provider = payload.get("provider") or payload.get("source")
    external_id = payload.get("external_id") or row.candidate_id
    return {
        "recommendation_candidate_id": str(row.id),
        "provider": provider,
        "external_id": external_id,
        "candidate_type": row.candidate_type,
    }


async def _scheduled_interaction_exists(
    session: AsyncSession,
    plan_id: uuid.UUID,
    candidate_id: str,
) -> bool:
    found = await session.scalar(
        select(InteractionEvent.id).where(
            InteractionEvent.session_id == plan_id,
            InteractionEvent.candidate_id == candidate_id,
            InteractionEvent.event_name == "plan_scheduled",
        )
    )
    return found is not None


def _interact(
    session: AsyncSession,
    plan: PlanningSession,
    event_name: str,
    candidate_id: str | None,
    properties: dict | None = None,
) -> None:
    session.add(
        InteractionEvent(
            user_id=plan.user_id,
            session_id=plan.id,
            candidate_id=candidate_id,
            event_name=event_name,
            topic=event_name.replace("_", "."),
            properties=properties or {},
        )
    )


async def _owned_plan(session: AsyncSession, plan_id: uuid.UUID) -> PlanningSession:
    plan = await session.get(PlanningSession, plan_id)
    if plan is None or plan.user_id != LOCAL_USER_ID:
        raise PlanNotFound()
    return plan


async def _latest_run(session: AsyncSession, plan_id: uuid.UUID) -> AgentRun | None:
    stmt = (
        select(AgentRun).where(AgentRun.session_id == plan_id).order_by(AgentRun.started_at.desc())
    )
    return await session.scalar(stmt)


async def _candidate_rows(
    session: AsyncSession, plan_id: uuid.UUID
) -> list[RecommendationCandidate]:
    recommendation = await session.scalar(
        select(Recommendation)
        .where(Recommendation.session_id == plan_id)
        .order_by(Recommendation.created_at.desc())
    )
    if recommendation is None:
        return []
    rows = await session.scalars(
        select(RecommendationCandidate)
        .where(RecommendationCandidate.recommendation_id == recommendation.id)
        .order_by(RecommendationCandidate.rank_position)
    )
    return list(rows.all())


async def _invoke(graph, initial: dict, config: RunnableConfig) -> dict:
    try:
        final = await graph.ainvoke(initial, config)
    except GraphInterrupt:
        snapshot = await graph.aget_state(config)
        final = snapshot.values
    if not isinstance(final, dict):
        snapshot = await graph.aget_state(config)
        final = dict(snapshot.values)
    return final


def _classify(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ProviderError):
        return exc.code, exc.message
    if isinstance(exc, AppError):
        return exc.code, SAFE_MESSAGES.get(exc.code, exc.message)
    return "planning_failed", SAFE_MESSAGES["planning_failed"]
