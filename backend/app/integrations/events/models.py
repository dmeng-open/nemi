from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.candidates import Candidate


class EventSearchQuery(BaseModel):
    date_start: date
    date_end: date
    timezone: str
    categories: list[str] = Field(default_factory=list)
    budget_max: float | None = None
    max_travel_minutes: int | None = None
    limit: int = 40
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None


class EventCandidate(BaseModel):
    id: str
    title: str
    description: str
    categories: list[str]
    start: datetime
    end: datetime
    venue: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    travel_minutes: int | None = None
    price: float | None = None
    rating: float | None = None
    url: str | None = None
    image_url: str | None = None
    source: str = "mock_events"
    provider: str = "mock"
    external_id: str | None = None
    retrieved_at: datetime | None = None
    travel_time_is_estimate: bool = False
    listed_time_missing: bool = False

    def to_candidate(self) -> Candidate:
        return Candidate(
            id=self.id,
            candidate_type="event",
            title=self.title,
            description=self.description,
            categories=list(self.categories),
            start_datetime=self.start,
            end_datetime=self.end,
            venue=self.venue,
            address=self.address,
            latitude=self.latitude,
            longitude=self.longitude,
            distance_km=self.distance_km,
            estimated_travel_minutes=self.travel_minutes,
            price_min=self.price,
            price_max=self.price,
            rating=self.rating,
            source=self.source,
            source_url=self.url,
            image_url=self.image_url,
            provider=self.provider,
            external_id=self.external_id or self.id,
            retrieved_at=self.retrieved_at,
            travel_time_is_estimate=self.travel_time_is_estimate,
            calendar_checked=not self.listed_time_missing,
            listed_time_missing=self.listed_time_missing,
        )
