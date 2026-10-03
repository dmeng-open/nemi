from datetime import timedelta

from app.core.exceptions import (
    AppError,
    ApprovalRequired,
    CalendarCreateUnconfirmed,
    CalendarNotConnected,
    CalendarReadFailed,
    InvalidSelection,
    ProviderError,
    ProviderNotConfigured,
    ScheduleConflictError,
)
from app.domain.calendar import CalendarExecutionResult, CalendarGateway, NewCalendarEvent
from app.domain.candidates import Candidate
from app.providers.retry import call_with_retries
from app.services.calendar.conflicts import overlaps
from app.services.calendar.idempotency import make_idempotency_key


def _location(candidate: Candidate) -> str | None:
    parts = [part for part in (candidate.venue, candidate.address) if part]
    return ", ".join(parts) or None


def _description(candidate: Candidate, explanation: str | None) -> str:
    lines = ["Planned with Nemi."]
    if explanation:
        lines.append(explanation)
    if candidate.source_url:
        lines.append(candidate.source_url)
    if candidate.listed_time_missing:
        lines.append(
            "Ticketmaster listed this date without a start time. "
            "The calendar block is a noon placeholder, not a published show time."
        )
    return "\n\n".join(lines)


async def schedule_approved_plan(
    calendar: CalendarGateway,
    *,
    approved: bool,
    plan_id: str,
    candidate: Candidate,
    explanation: str | None,
) -> CalendarExecutionResult:
    if not approved:
        raise ApprovalRequired()
    if candidate.start_datetime is None or candidate.end_datetime is None:
        raise InvalidSelection("This option does not have a time to schedule.")
    start = candidate.start_datetime
    end = candidate.end_datetime
    if start.tzinfo is None or end.tzinfo is None:
        raise AppError(
            "Include a timezone on the start and end times.",
            code="validation_error",
            status_code=422,
        )
    try:
        busy = await call_with_retries(
            lambda: calendar.get_events(start - timedelta(days=1), end + timedelta(days=1)),
            base_delay=0.25,
        )
    except ProviderNotConfigured:
        raise CalendarNotConnected() from None
    except ProviderError:
        raise CalendarReadFailed() from None
    if overlaps(start, end, busy):
        raise ScheduleConflictError()
    draft = NewCalendarEvent(
        title=candidate.title,
        start=start,
        end=end,
        location=_location(candidate),
        description=_description(candidate, explanation),
        source_url=candidate.source_url,
        planning_session_id=plan_id,
    )
    try:
        return await calendar.create_event(
            draft,
            idempotency_key=make_idempotency_key(plan_id, candidate.id, "create_event"),
            candidate_id=candidate.id,
        )
    except CalendarCreateUnconfirmed:
        raise
    except ProviderNotConfigured:
        raise CalendarNotConnected() from None
    except ProviderError:
        raise CalendarCreateUnconfirmed() from None
