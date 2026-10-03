import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.itinerary.engine import estimate_cost_usd
from app.agents.nodes import EventLog
from app.core.messages import SAFE_MESSAGES
from app.models.agent import AgentRun, AgentRunEvent
from app.models.multi_agent import (
    AgentArtifact,
    AgentSpan,
    AgentTaskRow,
    AgentThread,
    ExecutionAction,
    ItineraryItemRecord,
    ItineraryRecord,
)
from app.models.planning import PlanningConstraint, PlanningSession
from app.services.calendar.idempotency import make_idempotency_key

PARENTS = {
    "calendar_analysis": "supervisor",
    "restaurant_research": "supervisor",
    "event_research": "supervisor",
    "itinerary_planner": "supervisor",
    "verifier": "supervisor",
    "critic": "supervisor",
    "execution": "supervisor",
}


class DbSpanLog(EventLog):
    def __init__(self, session: AsyncSession, run_id, session_id, lock: asyncio.Lock | None = None) -> None:
        self.session = session
        self.run_id = run_id
        self.session_id = session_id
        self._lock = lock or asyncio.Lock()

    async def emit(
        self,
        event_type: str,
        status: str,
        metadata: dict | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self._lock:
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

    async def span(
        self,
        *,
        agent: str,
        status: str,
        duration_ms: int,
        detail: str,
        tools: list[str],
        error_code: str | None,
        retry_count: int,
        policy_version: str | None,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float | None = None,
        metadata: dict | None = None,
    ) -> None:
        safe = {"detail": detail}
        if metadata:
            for key, value in metadata.items():
                if key != "detail":
                    safe[key] = value
        cost = estimate_cost_usd(0, 0) if estimated_cost_usd is None else estimated_cost_usd
        async with self._lock:
            self.session.add(
                AgentSpan(
                    session_id=self.session_id,
                    agent_run_id=self.run_id,
                    agent_name=agent,
                    parent_agent=PARENTS.get(agent),
                    status=status,
                    duration_ms=duration_ms,
                    model=model,
                    prompt_version=policy_version,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost_usd=cost,
                    tool_calls=tools,
                    retry_count=retry_count,
                    error_code=error_code,
                    safe_metadata=safe,
                )
            )
            await self.session.commit()


async def persist_itinerary_state(
    session: AsyncSession,
    plan: PlanningSession,
    run: AgentRun,
    final: dict,
) -> None:
    status = final.get("status") or "failed"
    plan.plan_type = "itinerary"
    plan.status = status
    plan.summary = final.get("summary")
    plan.clarification_question = final.get("clarification_question")
    plan.error_code = final.get("error_code")
    if plan.error_code and plan.error_code in SAFE_MESSAGES:
        plan.error_message = SAFE_MESSAGES[plan.error_code]
    elif status == "no_matches":
        plan.error_code = plan.error_code or "no_matches"
        plan.error_message = final.get("summary") or final.get("limiting_constraint")
    elif status == "partial_success":
        plan.error_message = SAFE_MESSAGES["partial_success"]
    else:
        plan.error_message = None
    plan.approved = status == "scheduled"
    if final.get("constraints"):
        await session.execute(delete(PlanningConstraint).where(PlanningConstraint.session_id == plan.id))
        session.add(
            PlanningConstraint(
                session_id=plan.id,
                plan_type="itinerary",
                payload=final["constraints"],
            )
        )
    await _replace_tasks(session, plan.id, final.get("tasks") or [])
    await _replace_artifacts(session, plan.id, final)
    chosen = final.get("approved_itinerary_id")
    await _replace_itineraries(session, plan.id, final.get("itineraries") or [], chosen)
    await _replace_execution(session, plan.id, final.get("execution_result"), chosen)
    thread = await session.scalar(select(AgentThread).where(AgentThread.session_id == plan.id))
    thread_status = "interrupted" if status == "awaiting_approval" else status
    if thread is None:
        session.add(
            AgentThread(
                session_id=plan.id,
                thread_id=str(plan.id),
                status=thread_status,
            )
        )
    else:
        thread.status = thread_status
    if status not in {"processing", "scheduling"}:
        run.status = "completed" if status != "failed" else "failed"
        run.finished_at = datetime.now(UTC)


async def _replace_tasks(session: AsyncSession, session_id, tasks: list[dict]) -> None:
    await session.execute(delete(AgentTaskRow).where(AgentTaskRow.session_id == session_id))
    for task in tasks:
        session.add(
            AgentTaskRow(
                session_id=session_id,
                task_key=task.get("task_id") or task.get("task_type"),
                task_type=task.get("task_type") or "task",
                status=task.get("status") or "pending",
                assigned_agent=task.get("assigned_agent") or task.get("task_type") or "supervisor",
                dependencies=task.get("dependencies") or [],
                payload=task,
                error=task.get("error"),
            )
        )


async def _replace_artifacts(session: AsyncSession, session_id, final: dict) -> None:
    await session.execute(delete(AgentArtifact).where(AgentArtifact.session_id == session_id))
    for key in (
        "calendar_result",
        "restaurant_research",
        "event_research",
        "verification",
        "semantic_review",
        "critic_result",
    ):
        payload = final.get(key)
        if payload:
            session.add(AgentArtifact(session_id=session_id, artifact_type=key, payload=payload))
    session.add(
        AgentArtifact(
            session_id=session_id,
            artifact_type="planning_metrics",
            payload={
                "parallel_speedup": final.get("parallel_speedup"),
                "replan_count": final.get("replan_count") or 0,
                "limiting_constraint": final.get("limiting_constraint"),
            },
        )
    )


async def _replace_itineraries(
    session: AsyncSession,
    session_id,
    itineraries: list[dict],
    chosen: str | None,
) -> None:
    existing = list(
        (
            await session.scalars(select(ItineraryRecord).where(ItineraryRecord.session_id == session_id))
        ).all()
    )
    if existing and not itineraries:
        return
    if existing:
        ids = [row.id for row in existing]
        await session.execute(delete(ItineraryItemRecord).where(ItineraryItemRecord.itinerary_id.in_(ids)))
        await session.execute(delete(ItineraryRecord).where(ItineraryRecord.session_id == session_id))
    for index, raw in enumerate(itineraries):
        record = ItineraryRecord(
            session_id=session_id,
            itinerary_key=raw["itinerary_id"],
            rank_position=index,
            estimated_total_cost=raw.get("estimated_total_cost") or 0,
            start_at=datetime.fromisoformat(raw["start_datetime"]),
            end_at=datetime.fromisoformat(raw["end_datetime"]),
            explanation=raw.get("explanation"),
            valid=bool(raw.get("valid", True)),
            selected=raw["itinerary_id"] == chosen,
            payload=raw,
        )
        session.add(record)
        await session.flush()
        for position, item in enumerate(raw.get("items") or []):
            session.add(
                ItineraryItemRecord(
                    itinerary_id=record.id,
                    position=position,
                    item_type=item["item_type"],
                    title=item["title"],
                    start_at=datetime.fromisoformat(item["start_datetime"]),
                    end_at=datetime.fromisoformat(item["end_datetime"]),
                    location=item.get("location"),
                    estimated_cost=item.get("estimated_cost"),
                    source_candidate_id=item.get("source_candidate_id"),
                )
            )


async def _replace_execution(session, session_id, report: dict | None, chosen: str | None) -> None:
    if not report:
        return
    for action in report.get("actions") or []:
        item_key = action["item_id"]
        existing = await session.scalar(
            select(ExecutionAction).where(
                ExecutionAction.session_id == session_id,
                ExecutionAction.item_key == item_key,
            )
        )
        if existing is None:
            session.add(
                ExecutionAction(
                    session_id=session_id,
                    itinerary_key=chosen or "",
                    item_key=item_key,
                    idempotency_key=make_idempotency_key(str(session_id), item_key, "create_event"),
                    title=action.get("title") or "Plan",
                    status=action.get("status") or "failed",
                    calendar_event_id=action.get("calendar_event_id"),
                    error_code=action.get("error_code"),
                )
            )
        else:
            existing.status = action.get("status") or existing.status
            existing.calendar_event_id = action.get("calendar_event_id") or existing.calendar_event_id
            existing.error_code = action.get("error_code")
