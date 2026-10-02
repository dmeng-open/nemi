from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreatePlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ClarifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class SelectRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=160)


class ApproveRequest(BaseModel):
    approved: bool


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
    timeline: list[TimelineItemResponse]
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
