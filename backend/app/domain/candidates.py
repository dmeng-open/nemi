from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    id: str
    candidate_type: Literal["event", "restaurant"]
    title: str
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    venue: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    estimated_travel_minutes: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    price_level: int | None = None
    rating: float | None = None
    review_count: int | None = None
    source: str
    source_url: str | None = None
    image_url: str | None = None
    provider: str | None = None
    external_id: str | None = None
    retrieved_at: datetime | None = None
    travel_time_is_estimate: bool = False
    calendar_checked: bool = True
