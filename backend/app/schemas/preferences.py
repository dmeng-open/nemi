from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    home_city: str | None = Field(default=None, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    default_radius_km: float | None = Field(default=None, ge=1, le=50)
    timezone: str | None = None

    @field_validator("home_city")
    @classmethod
    def blank_city_is_null(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        try:
            ZoneInfo(text)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA name") from exc
        return text

    @model_validator(mode="after")
    def coordinates_are_a_pair(self) -> "PreferencesPayload":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be set or both be omitted")
        return self

    @field_validator("preferred_event_categories", "disliked_categories")
    @classmethod
    def clean_categories(cls, value: list[str]) -> list[str]:
        return normalize_list(value)

    @field_validator("preferred_cuisines")
    @classmethod
    def clean_cuisines(cls, value: list[str]) -> list[str]:
        return normalize_list(value, cuisine=True)
