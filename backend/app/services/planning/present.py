import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, PlanNotFound, PlanStateError
from app.core.messages import SAFE_MESSAGES
from app.integrations.calendar.local import row_to_event
from app.models.agent import AgentRunEvent
from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.models.planning import PlanningSession, Recommendation, RecommendationCandidate
from app.models.user import LOCAL_USER_ID
from app.domain.calendar import CalendarEvent
from app.domain.candidates import Candidate
from app.schemas.plans import (
    CandidateResponse,
    ExecutionResponse,
    PlanCalendarResponse,
    PlanErrorResponse,
    PlanResponse,
    PlanSummaryResponse,
    ScoreComponentsResponse,
    TimelineItemResponse,
    TimelineResponse,
)
from app.services.calendar.idempotency import make_idempotency_key

ICS_FALLBACK_CODES = {"calendar_read_failed", "calendar_write_unconfirmed"}
from app.services.calendar.time import as_utc
from app.services.planning.timeline import timeline_label, visible_timeline


async def get_plan_or_404(session: AsyncSession, plan_id: uuid.UUID) -> PlanningSession:
    plan = await session.get(PlanningSession, plan_id)
    if plan is None or plan.user_id != LOCAL_USER_ID:
        raise PlanNotFound()
    return plan


async def build_plan_response(session: AsyncSession, plan_id: uuid.UUID) -> PlanResponse:
    plan = await get_plan_or_404(session, plan_id)
    timeline = await _timeline(session, plan.id)
    recommendations = await _shown_candidates(session, plan.id)
    action = await _latest_completed_action(session, plan.id)
    execution = await _execution(session, plan, action) if plan.status == "scheduled" else None
    ics_available = _ics_available(plan, action)
    error = None
    if plan.error_code and plan.error_message:
        error = PlanErrorResponse(code=plan.error_code, message=plan.error_message)
    elif plan.status == "no_matches":
        code = plan.error_code or "no_matches"
        error = PlanErrorResponse(
            code=code, message=SAFE_MESSAGES.get(code, SAFE_MESSAGES["no_matches"])
        )
    return PlanResponse(
        plan_id=str(plan.id),
        status=plan.status,
        request=plan.user_request,
        plan_type=plan.plan_type,
        summary=plan.summary,
        clarification_question=plan.clarification_question,
        recommendations=recommendations,
        selected_candidate_id=plan.selected_candidate_id,
        execution=execution,
        error=error,
        calendar=PlanCalendarResponse(ics_available=ics_available),
        timeline=timeline,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


async def build_timeline_response(session: AsyncSession, plan_id: uuid.UUID) -> TimelineResponse:
    plan = await get_plan_or_404(session, plan_id)
    return TimelineResponse(
        plan_id=str(plan.id),
        status=plan.status,
        timeline=await _timeline(session, plan.id),
    )


async def list_plan_summaries(session: AsyncSession, limit: int = 20) -> list[PlanSummaryResponse]:
    stmt = (
        select(PlanningSession)
        .where(PlanningSession.user_id == LOCAL_USER_ID)
        .order_by(PlanningSession.created_at.desc())
        .limit(limit)
    )
    plans = list((await session.scalars(stmt)).all())
    titles: dict[uuid.UUID, str] = {}
    if plans:
        rows = await session.scalars(
            select(RecommendationCandidate).where(
                RecommendationCandidate.session_id.in_([plan.id for plan in plans]),
                RecommendationCandidate.selected.is_(True),
            )
        )
        for row in rows:
            title = row.payload.get("title")
            if isinstance(title, str):
                titles[row.session_id] = title
    return [
        PlanSummaryResponse(
            plan_id=str(plan.id),
            status=plan.status,
            request=plan.user_request,
            plan_type=plan.plan_type,
            summary=plan.summary,
            created_at=plan.created_at,
            selected_title=titles.get(plan.id),
        )
        for plan in plans
    ]


async def ics_event_for_plan(session: AsyncSession, plan_id: uuid.UUID) -> CalendarEvent:
    plan = await get_plan_or_404(session, plan_id)
    action = await _latest_completed_action(session, plan.id)
    if plan.status == "scheduled" and action is not None and action.local_calendar_event_id is not None:
        row = await session.get(LocalCalendarEvent, action.local_calendar_event_id)
        if row is None:
            raise PlanStateError("This plan does not have a calendar event yet.")
        return row_to_event(row)
    if plan.status == "scheduled" and action is not None and action.external_event_id:
        return await _event_from_candidate(session, plan, action.external_event_id)
    if plan.status == "awaiting_approval" and plan.error_code in ICS_FALLBACK_CODES:
        event_id = make_idempotency_key(
            str(plan.id),
            plan.selected_candidate_id or "plan",
            "create_event",
        )
        return await _event_from_candidate(session, plan, event_id)
    raise PlanStateError("Download the calendar file after the plan is scheduled.")


async def _timeline(session: AsyncSession, plan_id: uuid.UUID) -> list[TimelineItemResponse]:
    rows = list(
        (
            await session.scalars(
                select(AgentRunEvent)
                .where(AgentRunEvent.session_id == plan_id)
                .order_by(AgentRunEvent.timestamp, AgentRunEvent.event_type)
            )
        ).all()
    )
    items: list[TimelineItemResponse] = []
    for event, status in visible_timeline(rows):
        if status not in {"started", "completed", "failed"}:
            continue
        items.append(
            TimelineItemResponse(
                id=str(event.id),
                event_type=event.event_type,
                label=timeline_label(event.event_type, event.safe_metadata),
                status=status,
                timestamp=event.timestamp,
            )
        )
    return items


async def _shown_candidates(session: AsyncSession, plan_id: uuid.UUID) -> list[CandidateResponse]:
    recommendation = await session.scalar(
        select(Recommendation)
        .where(Recommendation.session_id == plan_id)
        .order_by(Recommendation.created_at.desc())
    )
    if recommendation is None:
        return []
    rows = list(
        (
            await session.scalars(
                select(RecommendationCandidate)
                .where(
                    RecommendationCandidate.recommendation_id == recommendation.id,
                    RecommendationCandidate.shown.is_(True),
                )
                .order_by(RecommendationCandidate.rank_position)
            )
        ).all()
    )
    return [_candidate_response(row) for row in rows]


def _candidate_response(row: RecommendationCandidate) -> CandidateResponse:
    payload = row.payload or {}
    return CandidateResponse(
        id=row.candidate_id,
        candidate_type=row.candidate_type,  # type: ignore[arg-type]
        title=str(payload.get("title") or "Untitled"),
        description=payload.get("description"),
        categories=list(payload.get("categories") or []),
        start=_parse_dt(payload.get("start_datetime")),
        end=_parse_dt(payload.get("end_datetime")),
        venue=payload.get("venue"),
        address=payload.get("address"),
        distance_km=payload.get("distance_km"),
        travel_minutes=payload.get("estimated_travel_minutes"),
        price_min=payload.get("price_min"),
        price_max=payload.get("price_max"),
        price_level=payload.get("price_level"),
        rating=payload.get("rating"),
        source_url=payload.get("source_url"),
        image_url=payload.get("image_url"),
        score=row.final_score,
        components=ScoreComponentsResponse(
            preference=row.preference_score,
            schedule=row.schedule_score,
            distance=row.distance_score,
            price=row.price_score,
            quality=row.quality_score,
        ),
        schedule_compatible=row.exclusion_reason is None,
        explanation=row.explanation or "",
        calendar_checked=bool(payload.get("calendar_checked", True)),
        travel_time_is_estimate=bool(payload.get("travel_time_is_estimate", False)),
    )


def _parse_dt(value):
    if not value:
        return None
    from datetime import datetime

    parsed = datetime.fromisoformat(value)
    return as_utc(parsed)


async def _latest_completed_action(
    session: AsyncSession, plan_id: uuid.UUID
) -> CalendarAction | None:
    return await session.scalar(
        select(CalendarAction)
        .where(CalendarAction.session_id == plan_id, CalendarAction.status == "completed")
        .order_by(CalendarAction.created_at.desc())
    )


def _ics_available(plan: PlanningSession, action: CalendarAction | None) -> bool:
    if plan.status == "scheduled" and action is not None:
        return bool(action.local_calendar_event_id or action.external_event_id)
    return plan.status == "awaiting_approval" and plan.error_code in ICS_FALLBACK_CODES


async def _execution(
    session: AsyncSession,
    plan: PlanningSession,
    action: CalendarAction | None,
) -> ExecutionResponse | None:
    if action is None:
        return None
    if action.local_calendar_event_id is not None:
        row = await session.get(LocalCalendarEvent, action.local_calendar_event_id)
        if row is None:
            return None
        event = row_to_event(row)
        return ExecutionResponse(
            calendar_event_id=event.id,
            title=event.title,
            start=event.start,
            end=event.end,
            location=event.location,
        )
    if action.external_event_id:
        event = await _event_from_candidate(session, plan, action.external_event_id)
        return ExecutionResponse(
            calendar_event_id=event.id,
            title=event.title,
            start=event.start,
            end=event.end,
            location=event.location,
        )
    return None


async def _event_from_candidate(
    session: AsyncSession,
    plan: PlanningSession,
    event_id: str,
) -> CalendarEvent:
    row = await session.scalar(
        select(RecommendationCandidate)
        .where(
            RecommendationCandidate.session_id == plan.id,
            RecommendationCandidate.candidate_id == plan.selected_candidate_id,
            RecommendationCandidate.shown.is_(True),
        )
        .order_by(RecommendationCandidate.created_at.desc())
    )
    if row is None:
        raise PlanStateError("This plan does not have a calendar event yet.")
    candidate = Candidate.model_validate(row.payload)
    if candidate.start_datetime is None or candidate.end_datetime is None:
        raise PlanStateError("This plan does not have a calendar event yet.")
    if candidate.start_datetime.tzinfo is None or candidate.end_datetime.tzinfo is None:
        raise AppError(
            "Include a timezone on the start and end times.",
            code="validation_error",
            status_code=422,
        )
    location_parts = [part for part in (candidate.venue, candidate.address) if part]
    lines = ["Planned with Nemi."]
    if row.explanation:
        lines.append(row.explanation)
    if candidate.source_url:
        lines.append(candidate.source_url)
    return CalendarEvent(
        id=event_id,
        title=candidate.title,
        start=candidate.start_datetime,
        end=candidate.end_datetime,
        location=", ".join(location_parts) or None,
        description="\n\n".join(lines),
        source_url=candidate.source_url,
    )
