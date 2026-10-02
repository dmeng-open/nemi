from datetime import time

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: time
    end: time
    label: str | None = None


class UserPreferences(BaseModel):
    preferred_event_categories: list[str] = Field(default_factory=list)
    preferred_cuisines: list[str] = Field(default_factory=list)
    disliked_categories: list[str] = Field(default_factory=list)
    default_budget: float | None = None
    max_travel_minutes: int | None = None
    preferred_days: list[str] = Field(default_factory=list)
    preferred_time_ranges: list[TimeRange] = Field(default_factory=list)
