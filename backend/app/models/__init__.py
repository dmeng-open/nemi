"""ORM models. Importing this package registers every table."""

from app.models.agent import AgentRun, AgentRunEvent, InteractionEvent
from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.models.planning import (
    PlanningConstraint,
    PlanningSession,
    Recommendation,
    RecommendationCandidate,
)
from app.models.user import LOCAL_USER_EMAIL, LOCAL_USER_ID, User, UserPreference

__all__ = [
    "LOCAL_USER_EMAIL",
    "LOCAL_USER_ID",
    "AgentRun",
    "AgentRunEvent",
    "CalendarAction",
    "InteractionEvent",
    "LocalCalendarEvent",
    "PlanningConstraint",
    "PlanningSession",
    "Recommendation",
    "RecommendationCandidate",
    "User",
    "UserPreference",
]
