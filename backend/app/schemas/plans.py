from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreatePlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ClarifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class SelectRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=160)


class RejectRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=160)


class ApproveRequest(BaseModel):
    approved: bool
    itinerary_id: str | None = None


class ReviseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ExecutionCommandRequest(BaseModel):
    action: Literal["retry", "keep", "cancel_created"]
    confirm: bool = False


class PlanCreatedResponse(BaseModel):
    plan_id: str
    status: str


class ScoreComponentsResponse(BaseModel):
    preference: float
    schedule: float
    distance: float
    price: float
    quality: float


class CandidateResponse(BaseModel):
    id: str
    candidate_type: Literal["event", "restaurant"]
    title: str
    description: str | None = None
    categories: list[str]
    start: datetime | None = None
    end: datetime | None = None
    venue: str | None = None
    address: str | None = None
    distance_km: float | None = None
    travel_minutes: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    price_level: int | None = None
    rating: float | None = None
    source_url: str | None = None
    image_url: str | None = None
    score: float
    components: ScoreComponentsResponse
    schedule_compatible: bool
    explanation: str
    calendar_checked: bool = True
    travel_time_is_estimate: bool = False
    listed_time_missing: bool = False


class TimelineItemResponse(BaseModel):
    id: str
    event_type: str
    label: str
    status: Literal["started", "completed", "failed"]
    timestamp: datetime


class ExecutionResponse(BaseModel):
    calendar_event_id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None


class PlanErrorResponse(BaseModel):
    code: str
    message: str


class PlanCalendarResponse(BaseModel):
    ics_available: bool


class PlanResponse(BaseModel):
    plan_id: str
    status: str
    request: str
    plan_type: str | None
    summary: str | None
    clarification_question: str | None
    recommendations: list[CandidateResponse]
    selected_candidate_id: str | None
    execution: ExecutionResponse | None
    error: PlanErrorResponse | None
    calendar: PlanCalendarResponse
    timeline: list[TimelineItemResponse]
    itineraries: list[ItineraryResponse] = Field(default_factory=list)
    agents: list[AgentProgressResponse] = Field(default_factory=list)
    execution_status: str | None = None
    execution_actions: list[ExecutionActionResponse] = Field(default_factory=list)
    limiting_constraint: str | None = None
    parallel_speedup: float | None = None
    execution_resolution: str | None = None
    created_at: datetime
    updated_at: datetime


class PlanSummaryResponse(BaseModel):
    plan_id: str
    status: str
    request: str
    plan_type: str | None
    summary: str | None
    created_at: datetime
    selected_title: str | None = None


class TimelineResponse(BaseModel):
    plan_id: str
    status: str
    timeline: list[TimelineItemResponse]


class ItineraryItemResponse(BaseModel):
    item_type: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    estimated_cost: float | None = None
    travel_time_is_estimate: bool = False


class ConstraintCheckResponse(BaseModel):
    code: str
    label: str
    status: str
    message: str


class ItineraryResponse(BaseModel):
    id: str
    items: list[ItineraryItemResponse]
    estimated_total_cost: float
    start: datetime
    end: datetime
    explanation: str | None = None
    checks: list[ConstraintCheckResponse] = Field(default_factory=list)
    valid: bool = True


class AgentProgressResponse(BaseModel):
    agent: str
    label: str
    status: str
    detail: str | None = None
    duration_ms: int | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0
    tool_calls: list[str] = Field(default_factory=list)
    retry_count: int = 0
    error_code: str | None = None


class ExecutionActionResponse(BaseModel):
    item_id: str
    title: str
    status: str
    calendar_event_id: str | None = None
    error_code: str | None = None
