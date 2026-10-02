import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

LOCAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
LOCAL_USER_EMAIL = "local@nemi.app"


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    preferences: Mapped["UserPreference | None"] = relationship(back_populates="user")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), unique=True)
    preferred_event_categories: Mapped[list] = mapped_column(JSON, default=list)
    preferred_cuisines: Mapped[list] = mapped_column(JSON, default=list)
    disliked_categories: Mapped[list] = mapped_column(JSON, default=list)
    default_budget: Mapped[float | None] = mapped_column(Float, default=None)
    max_travel_minutes: Mapped[int | None] = mapped_column(default=None)
    preferred_days: Mapped[list] = mapped_column(JSON, default=list)
    preferred_time_ranges: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="preferences")
