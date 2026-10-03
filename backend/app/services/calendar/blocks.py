from datetime import datetime, timedelta

from app.core.exceptions import ApprovalRequired, ProviderError, ScheduleConflictError
from app.domain.calendar import CalendarExecutionResult, NewCalendarEvent
from app.services.calendar.conflicts import overlaps
from app.services.calendar.idempotency import make_idempotency_key
from app.services.calendar.time import as_utc


def _repository(calendar: object):
    for name in ("repository", "calendar"):
        repo = getattr(calendar, name, None)
        if repo is not None and hasattr(repo, "get_action"):
            return repo
    return None


async def schedule_block(
    calendar: object,
    *,
    approved: bool,
    plan_id: str,
    item_id: str,
    title: str,
    start: datetime,
    end: datetime,
    location: str | None,
    description: str | None,
) -> CalendarExecutionResult:
    if not approved:
        raise ApprovalRequired()
    if start.tzinfo is None or end.tzinfo is None:
        raise ProviderError(
            "Calendar times need a timezone.",
            retryable=False,
            code="validation_error",
        )
    key = make_idempotency_key(plan_id, item_id, "create_event")
    repo = _repository(calendar)
    if repo is not None:
        existing = await repo.get_action(key)
        if existing is not None and existing.status == "completed":
            return await calendar.create_event(  # type: ignore[attr-defined]
                NewCalendarEvent(
                    title=title,
                    start=start,
                    end=end,
                    location=location,
                    description=description,
                    planning_session_id=plan_id,
                ),
                idempotency_key=key,
                candidate_id=item_id,
            )
    busy = await calendar.get_events(  # type: ignore[attr-defined]
        as_utc(start) - timedelta(days=1),
        as_utc(end) + timedelta(days=1),
    )
    if overlaps(start, end, busy):
        raise ScheduleConflictError()
    return await calendar.create_event(  # type: ignore[attr-defined]
        NewCalendarEvent(
            title=title,
            start=start,
            end=end,
            location=location,
            description=description,
            planning_session_id=plan_id,
        ),
        idempotency_key=key,
        candidate_id=item_id,
    )
