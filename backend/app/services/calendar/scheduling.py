from app.core.exceptions import ApprovalRequired, InvalidSelection
from app.domain.calendar import CalendarExecutionResult, NewCalendarEvent
from app.domain.candidates import Candidate
from app.integrations.calendar.local import LocalCalendarProvider
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
    return "\n\n".join(lines)


async def schedule_approved_plan(
    calendar: LocalCalendarProvider,
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
    draft = NewCalendarEvent(
        title=candidate.title,
        start=candidate.start_datetime,
        end=candidate.end_datetime,
        location=_location(candidate),
        description=_description(candidate, explanation),
        source_url=candidate.source_url,
        planning_session_id=plan_id,
    )
    return await calendar.create_event(
        draft,
        idempotency_key=make_idempotency_key(plan_id, candidate.id, "create_event"),
        candidate_id=candidate.id,
    )
