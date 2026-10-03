import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class LocalCalendarEvent(Base):
    __tablename__ = "local_calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    location: Mapped[str | None] = mapped_column(String(300), default=None)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(500), default=None)
    planning_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("planning_sessions.id"), default=None
    )
    seed_key: Mapped[str | None] = mapped_column(String(160), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CalendarAction(Base):
    __tablename__ = "calendar_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("planning_sessions.id"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(String(160))
    action_type: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    local_calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("local_calendar_events.id", ondelete="SET NULL"),
        default=None,
    )
    external_event_id: Mapped[str | None] = mapped_column(String(128), default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
