import uuid
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import PlanStateError, ScheduleConflictError
from app.domain.calendar import CalendarEvent, CalendarExecutionResult, NewCalendarEvent
from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.repositories.calendar import CalendarRepository
from app.services.calendar.conflicts import overlaps
from app.services.calendar.time import as_utc


def row_to_event(row: LocalCalendarEvent) -> CalendarEvent:
    return CalendarEvent(
        id=str(row.id),
        title=row.title,
        start=as_utc(row.start_at),
        end=as_utc(row.end_at),
        location=row.location,
        description=row.description,
        source_url=row.source_url,
    )


class LocalCalendarProvider:
    def __init__(self, repository: CalendarRepository, user_id: uuid.UUID) -> None:
        self.repository = repository
        self.user_id = user_id

    async def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        rows = await self.repository.list_between(self.user_id, as_utc(start), as_utc(end))
        return [row_to_event(row) for row in rows]

    async def create_event(
        self,
        draft: NewCalendarEvent,
        *,
        idempotency_key: str,
        candidate_id: str,
    ) -> CalendarExecutionResult:
        existing = await self.repository.get_action(idempotency_key)
        if existing and existing.status == "completed" and existing.local_calendar_event_id:
            row = await self.repository.get_event(existing.local_calendar_event_id, self.user_id)
            if row is not None:
                return _result(row, replayed=True)

        start = as_utc(draft.start)
        end = as_utc(draft.end)
        busy = await self.get_events(start - timedelta(days=1), end + timedelta(days=1))
        if overlaps(start, end, busy):
            raise ScheduleConflictError()

        if draft.planning_session_id is None:
            raise PlanStateError("A planned event needs a plan id.")

        event_row = LocalCalendarEvent(
            id=uuid.uuid4(),
            user_id=self.user_id,
            title=draft.title,
            description=draft.description,
            location=draft.location,
            start_at=start,
            end_at=end,
            source_url=draft.source_url,
            planning_session_id=uuid.UUID(draft.planning_session_id),
        )
        action = CalendarAction(
            user_id=self.user_id,
            session_id=uuid.UUID(draft.planning_session_id),
            candidate_id=candidate_id,
            action_type="create_event",
            idempotency_key=idempotency_key,
            status="completed",
            local_calendar_event_id=event_row.id,
        )
        session = self.repository.session
        try:
            async with session.begin_nested():
                session.add(event_row)
                session.add(action)
                await session.flush()
        except IntegrityError:
            raced = await self.repository.get_action(idempotency_key)
            if raced and raced.local_calendar_event_id:
                row = await self.repository.get_event(raced.local_calendar_event_id, self.user_id)
                if row is not None:
                    return _result(row, replayed=True)
            raise
        return _result(event_row, replayed=False)


def _result(row: LocalCalendarEvent, *, replayed: bool) -> CalendarExecutionResult:
    event = row_to_event(row)
    return CalendarExecutionResult(
        calendar_event_id=event.id,
        title=event.title,
        start=event.start,
        end=event.end,
        location=event.location,
        replayed=replayed,
    )
