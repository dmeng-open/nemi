import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.itinerary.artifacts import Itinerary
from app.agents.itinerary.permissions import authorize
from app.core.exceptions import PlanStateError, ScheduleConflictError
from app.core.messages import SAFE_MESSAGES
from app.models.multi_agent import AgentArtifact, ExecutionAction, ItineraryRecord
from app.models.planning import PlanningSession
from app.models.user import LOCAL_USER_ID
from app.providers.factory import build_calendar_provider
from app.services.calendar.blocks import schedule_block
from app.services.calendar.idempotency import make_idempotency_key


async def apply_execution_command(
    session: AsyncSession,
    settings,
    plan: PlanningSession,
    *,
    action: str,
    confirm: bool,
) -> None:
    if plan.plan_type != "itinerary":
        raise PlanStateError("This plan does not have an itinerary execution.")
    if action == "keep":
        if plan.status != "partial_success":
            raise PlanStateError("There is no partial schedule to keep.")
        await _set_resolution(session, plan.id, "kept")
        plan.summary = "The partial schedule stays on the calendar."
        return
    if action == "cancel_created":
        if not confirm:
            raise PlanStateError("Confirm before removing calendar events.")
        authorize("execution", "calendar.delete_event")
        calendar = build_calendar_provider(settings, session, LOCAL_USER_ID)
        rows = await _actions(session, plan.id)
        for row in rows:
            if row.status != "completed" or not row.calendar_event_id:
                continue
            delete = getattr(calendar, "delete_event", None)
            if delete is not None:
                await delete(row.calendar_event_id)
            row.status = "cancelled"
        plan.status = "cancelled"
        plan.approved = False
        plan.error_code = None
        plan.error_message = None
        plan.summary = "Removed the calendar events from this plan."
        await _set_resolution(session, plan.id, "cancelled")
        return
    if action != "retry":
        raise PlanStateError("That execution action is not available.")
    if plan.status not in {"partial_success", "failed"}:
        raise PlanStateError("Nothing left to retry.")
    rows = await _actions(session, plan.id)
    if not rows:
        raise PlanStateError("This plan has no calendar write to retry.")
    record = await _selected_itinerary(session, plan.id)
    if record is None:
        raise PlanStateError("This plan has no itinerary to schedule.")
    authorize("execution", "google_calendar.create_event")
    itinerary = Itinerary.model_validate(record.payload)
    calendar = build_calendar_provider(settings, session, LOCAL_USER_ID)
    any_failed = False
    any_ok = False
    considered = False
    for item in itinerary.items:
        if item.item_type not in {"restaurant", "event"}:
            continue
        item_id = f"{itinerary.itinerary_id}:{item.item_type}:{item.source_candidate_id}"
        idempotency_key = make_idempotency_key(str(plan.id), item_id, "create_event")
        existing = _action_for_item(rows, item_id, idempotency_key)
        if existing is None:
            continue
        considered = True
        if existing.status == "completed":
            any_ok = True
            continue
        try:
            result = await schedule_block(
                calendar,
                approved=True,
                plan_id=str(plan.id),
                item_id=item_id,
                title=item.title,
                start=item.start_datetime,
                end=item.end_datetime,
                location=item.location,
                description="Planned with Nemi.\n\nTravel times on this itinerary are estimates.",
            )
        except ScheduleConflictError:
            await _upsert_action(
                session,
                plan.id,
                itinerary.itinerary_id,
                item_id,
                item.title,
                "failed",
                None,
                "schedule_conflict",
            )
            any_failed = True
            continue
        await _upsert_action(
            session,
            plan.id,
            itinerary.itinerary_id,
            item_id,
            item.title,
            "completed",
            result.calendar_event_id,
            None,
        )
        any_ok = True
    if not considered:
        return
    if any_ok and not any_failed:
        plan.status = "scheduled"
        plan.approved = True
        plan.error_code = None
        plan.error_message = None
        plan.summary = "Scheduled successfully"
    elif any_ok:
        plan.status = "partial_success"
        plan.error_code = "partial_success"
        plan.error_message = SAFE_MESSAGES["partial_success"]
    else:
        plan.status = "failed"
        plan.error_code = "calendar_write_failed"
        plan.error_message = SAFE_MESSAGES["planning_failed"]


async def _selected_itinerary(session: AsyncSession, plan_id: uuid.UUID) -> ItineraryRecord | None:
    return await session.scalar(
        select(ItineraryRecord).where(
            ItineraryRecord.session_id == plan_id,
            ItineraryRecord.selected.is_(True),
        )
    )


def _action_for_item(
    rows: list[ExecutionAction],
    item_id: str,
    idempotency_key: str,
) -> ExecutionAction | None:
    matched = next((row for row in rows if row.idempotency_key == idempotency_key), None)
    if matched is not None:
        return matched
    return next((row for row in rows if row.item_key == item_id), None)


async def _actions(session: AsyncSession, plan_id: uuid.UUID) -> list[ExecutionAction]:
    return list(
        (
            await session.scalars(
                select(ExecutionAction).where(ExecutionAction.session_id == plan_id)
            )
        ).all()
    )


async def _upsert_action(
    session: AsyncSession,
    plan_id: uuid.UUID,
    itinerary_key: str,
    item_id: str,
    title: str,
    status: str,
    calendar_event_id: str | None,
    error_code: str | None,
) -> None:
    existing = await session.scalar(
        select(ExecutionAction).where(
            ExecutionAction.session_id == plan_id,
            ExecutionAction.item_key == item_id,
        )
    )
    if existing is None:
        session.add(
            ExecutionAction(
                session_id=plan_id,
                itinerary_key=itinerary_key,
                item_key=item_id,
                idempotency_key=make_idempotency_key(str(plan_id), item_id, "create_event"),
                title=title,
                status=status,
                calendar_event_id=calendar_event_id,
                error_code=error_code,
            )
        )
        return
    existing.status = status
    existing.calendar_event_id = calendar_event_id or existing.calendar_event_id
    existing.error_code = error_code


async def _set_resolution(session: AsyncSession, plan_id: uuid.UUID, resolution: str) -> None:
    row = await session.scalar(
        select(AgentArtifact).where(
            AgentArtifact.session_id == plan_id,
            AgentArtifact.artifact_type == "planning_metrics",
        )
    )
    if row is None:
        session.add(
            AgentArtifact(
                session_id=plan_id,
                artifact_type="planning_metrics",
                payload={"resolution": resolution},
            )
        )
        return
    payload = dict(row.payload or {})
    payload["resolution"] = resolution
    row.payload = payload
