from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.candidates import Candidate


class TaskType(StrEnum):
    CALENDAR_ANALYSIS = "calendar_analysis"
    RESTAURANT_RESEARCH = "restaurant_research"
    EVENT_RESEARCH = "event_research"
    ITINERARY_GENERATION = "itinerary_generation"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SupervisorDecision(StrEnum):
    CONTINUE = "CONTINUE"
    RETRY_BRANCH = "RETRY_BRANCH"
    REPLAN = "REPLAN"
    ASK_USER = "ASK_USER"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    FAIL = "FAIL"


class AgentTask(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = Field(default_factory=list)
    assigned_agent: str
    input: dict = Field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    retryable: bool = False
    retry_count: int = 0


class ItineraryConstraints(BaseModel):
    date_start: date | None = None
    date_end: date | None = None
    time_start: time = time(17, 0)
    time_end: time = time(23, 0)
    cuisines: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    category_match_required: bool = False
    dietary_restrictions: list[str] = Field(default_factory=list)
    budget_amount: float | None = None
    budget_max: float | None = None
    budget_kind: Literal["maximum", "around", "unspecified"] = "unspecified"
    max_travel_minutes: int | None = 30
    hard_travel_minutes: int | None = 45
    wants_restaurant: bool = False
    wants_event: bool = False
    timezone: str
    summary: str = ""
    shift_minutes: int = 0
    needs_clarification: bool = False
    clarification_question: str | None = None


class TimeWindowPayload(BaseModel):
    start: datetime
    end: datetime


class CalendarAnalysisResult(BaseModel):
    available_windows: list[TimeWindowPayload] = Field(default_factory=list)
    existing_events: list[dict] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    calendar_read: Literal["ok", "unavailable"] = "ok"
    uncertainties: list[str] = Field(default_factory=list)


class ResearchCandidate(BaseModel):
    candidate: Candidate
    dietary: Literal["ok", "exclude", "uncertain"] = "ok"
    score: float = 0
    exclusion_reason: str | None = None


class RestaurantResearchArtifact(BaseModel):
    candidate_restaurants: list[ResearchCandidate] = Field(default_factory=list)
    excluded_candidates: list[dict] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    provider_failures: list[str] = Field(default_factory=list)


class EventResearchArtifact(BaseModel):
    candidate_events: list[ResearchCandidate] = Field(default_factory=list)
    excluded_candidates: list[dict] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    provider_failures: list[str] = Field(default_factory=list)


class ItineraryItem(BaseModel):
    item_type: Literal["restaurant", "event", "travel", "buffer"]
    title: str
    start_datetime: datetime
    end_datetime: datetime
    location: str | None = None
    estimated_cost: float | None = None
    source_candidate_id: str | None = None
    travel_time_is_estimate: bool = False


class ConstraintCheck(BaseModel):
    code: str
    label: str
    status: Literal["pass", "fail", "soft"]
    message: str


class Itinerary(BaseModel):
    itinerary_id: str
    items: list[ItineraryItem]
    estimated_total_cost: float
    start_datetime: datetime
    end_datetime: datetime
    explanation: str | None = None
    checks: list[ConstraintCheck] = Field(default_factory=list)
    valid: bool = True
    restaurant_id: str | None = None
    event_id: str | None = None


class Violation(BaseModel):
    type: str
    message: str


class VerificationResult(BaseModel):
    valid: bool
    violations: list[Violation] = Field(default_factory=list)
    limiting_constraint: str | None = None


class SemanticReview(BaseModel):
    complete: bool
    partial: bool = False
    issues: list[str] = Field(default_factory=list)


class CriticIssue(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    message: str
    target_task: str | None = None


class CriticResult(BaseModel):
    status: Literal["PASS", "REVISE"]
    issues: list[CriticIssue] = Field(default_factory=list)


class ExecutionActionResult(BaseModel):
    item_id: str
    title: str
    status: Literal["completed", "failed", "pending"]
    calendar_event_id: str | None = None
    error_code: str | None = None
    replayed: bool = False


class ExecutionReport(BaseModel):
    status: Literal["success", "partial_success", "failed"]
    actions: list[ExecutionActionResult] = Field(default_factory=list)


def dump(model: BaseModel) -> dict:
    return model.model_dump(mode="json")
