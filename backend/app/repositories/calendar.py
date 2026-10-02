import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.services.calendar.time import as_utc


class CalendarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_between(
        self,
        user_id: uuid.UUID,
        start: datetime,
        end: datetime,
    ) -> list[LocalCalendarEvent]:
        start = as_utc(start)
        end = as_utc(end)
        stmt = (
            select(LocalCalendarEvent)
            .where(
                LocalCalendarEvent.user_id == user_id,
                LocalCalendarEvent.start_at < end,
                LocalCalendarEvent.end_at > start,
            )
            .order_by(LocalCalendarEvent.start_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_for_user(self, user_id: uuid.UUID) -> list[LocalCalendarEvent]:
        stmt = (
            select(LocalCalendarEvent)
            .where(LocalCalendarEvent.user_id == user_id)
            .order_by(LocalCalendarEvent.start_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_event(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> LocalCalendarEvent | None:
        stmt = select(LocalCalendarEvent).where(
            LocalCalendarEvent.id == event_id,
            LocalCalendarEvent.user_id == user_id,
        )
        return await self.session.scalar(stmt)

    async def get_by_seed(self, seed_key: str) -> LocalCalendarEvent | None:
        stmt = select(LocalCalendarEvent).where(LocalCalendarEvent.seed_key == seed_key)
        return await self.session.scalar(stmt)

    async def get_action(self, idempotency_key: str) -> CalendarAction | None:
        stmt = select(CalendarAction).where(CalendarAction.idempotency_key == idempotency_key)
        return await self.session.scalar(stmt)

    async def create_user_event(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        start: datetime,
        end: datetime,
        location: str | None = None,
        description: str | None = None,
        source_url: str | None = None,
        seed_key: str | None = None,
        planning_session_id: uuid.UUID | None = None,
    ) -> LocalCalendarEvent:
        if seed_key:
            existing = await self.get_by_seed(seed_key)
            if existing is not None:
                return existing
        row = LocalCalendarEvent(
            user_id=user_id,
            title=title,
            description=description,
            location=location,
            start_at=as_utc(start),
            end_at=as_utc(end),
            source_url=source_url,
            seed_key=seed_key,
            planning_session_id=planning_session_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete_event(self, event_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        row = await self.get_event(event_id, user_id)
        if row is None:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True
