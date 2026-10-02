from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import AgentRun


def utcnow() -> datetime:
    return datetime.now(UTC)


class PlanningSession(Base):
    __tablename__ = "planning_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    user_request: Mapped[str] = mapped_column(Text)
    follow_up: Mapped[str | None] = mapped_column(Text, default=None)
    plan_type: Mapped[str | None] = mapped_column(String(32), default=None)
    status: Mapped[str] = mapped_column(String(40), default="processing", index=True)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    clarification_question: Mapped[str | None] = mapped_column(Text, default=None)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(160), default=None)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    constraints: Mapped[PlanningConstraint | None] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[AgentRun]] = relationship(back_populates="session")


class PlanningConstraint(Base):
    __tablename__ = "planning_constraints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("planning_sessions.id"), unique=True
    )
    plan_type: Mapped[str | None] = mapped_column(String(32), default=None)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[PlanningSession] = relationship(back_populates="constraints")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("planning_sessions.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[PlanningSession] = relationship(back_populates="recommendations")
    candidates: Mapped[list[RecommendationCandidate]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
    )


class RecommendationCandidate(Base):
    __tablename__ = "recommendation_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recommendations.id"), index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    candidate_id: Mapped[str] = mapped_column(String(160))
    candidate_type: Mapped[str] = mapped_column(String(32))
    rank_position: Mapped[int] = mapped_column(Integer)
    final_score: Mapped[float] = mapped_column(Float)
    preference_score: Mapped[float] = mapped_column(Float)
    schedule_score: Mapped[float] = mapped_column(Float)
    distance_score: Mapped[float] = mapped_column(Float)
    price_score: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    shown: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(40), default=None)
    explanation: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recommendation: Mapped[Recommendation] = relationship(back_populates="candidates")
