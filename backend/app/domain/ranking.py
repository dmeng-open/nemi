from datetime import time
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from app.domain.calendar import CalendarEvent, TimeWindow
from app.domain.candidates import Candidate


class RankingWeights(BaseModel):
    preference: float = 0.35
    schedule: float = 0.25
    distance: float = 0.15
    price: float = 0.10
    quality: float = 0.15

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "RankingWeights":
        total = self.preference + self.schedule + self.distance + self.price + self.quality
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Ranking weights must sum to 1.")
        return self


class ScoreComponents(BaseModel):
    preference: float
    schedule: float
    distance: float
    price: float
    quality: float


class RankingContext(BaseModel):
    requested_categories: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    disliked_categories: list[str] = Field(default_factory=list)
    budget_max: float | None = None
    max_travel_minutes: int | None = None
    free_windows: list[TimeWindow] = Field(default_factory=list)
    busy_events: list[CalendarEvent] = Field(default_factory=list)
    preferred_time_start: time | None = None
    preferred_time_end: time | None = None
    timezone: str = "America/Chicago"
    calendar_read: Literal["ok", "unavailable"] = "ok"


class RankedCandidate(BaseModel):
    candidate: Candidate
    final_score: float
    components: ScoreComponents
    schedule_compatible: bool
    exclusion_reason: str | None = None
    explanation: str | None = None
    shown: bool = False
    rank_position: int = 0


class CandidateRanker(Protocol):
    async def rank(
        self,
        candidates: list[Candidate],
        context: RankingContext,
    ) -> list[RankedCandidate]: ...
