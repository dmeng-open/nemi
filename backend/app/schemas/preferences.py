from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.planning.taxonomy import normalize_list

DayName = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class TimeRangePayload(BaseModel):
    start: time
    end: time
    label: str | None = None

    @model_validator(mode="after")
    def end_after_start(self) -> "TimeRangePayload":
        if self.end <= self.start:
            raise ValueError("time range end must be after the start")
        return self


class PreferencesPayload(BaseModel):
    preferred_event_categories: list[str] = Field(default_factory=list, max_length=20)
    preferred_cuisines: list[str] = Field(default_factory=list, max_length=20)
    disliked_categories: list[str] = Field(default_factory=list, max_length=20)
    default_budget: float | None = Field(default=None, ge=0, le=10000)
    max_travel_minutes: int | None = Field(default=None, ge=0, le=180)
    preferred_days: list[DayName] = Field(default_factory=list, max_length=7)
    preferred_time_ranges: list[TimeRangePayload] = Field(default_factory=list, max_length=4)

    @field_validator("preferred_event_categories", "disliked_categories")
    @classmethod
    def clean_categories(cls, value: list[str]) -> list[str]:
        return normalize_list(value)

    @field_validator("preferred_cuisines")
    @classmethod
    def clean_cuisines(cls, value: list[str]) -> list[str]:
        return normalize_list(value, cuisine=True)
