"""ORM models. Importing this package registers every table."""

from app.models.agent import AgentRun, AgentRunEvent, InteractionEvent
from app.models.calendar import CalendarAction, LocalCalendarEvent
from app.models.multi_agent import (
    AgentArtifact,
    AgentSpan,
    AgentTaskRow,
    AgentThread,
    ExecutionAction,
    ItineraryItemRecord,
    ItineraryRecord,
)
from app.models.oauth import OAuthConnection, OAuthState
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
    "AgentArtifact",
    "AgentRun",
    "AgentRunEvent",
    "AgentSpan",
    "AgentTaskRow",
    "AgentThread",
    "CalendarAction",
    "ExecutionAction",
    "InteractionEvent",
    "ItineraryItemRecord",
    "ItineraryRecord",
    "LocalCalendarEvent",
    "OAuthConnection",
    "OAuthState",
    "PlanningConstraint",
    "PlanningSession",
    "Recommendation",
    "RecommendationCandidate",
    "User",
    "UserPreference",
]
