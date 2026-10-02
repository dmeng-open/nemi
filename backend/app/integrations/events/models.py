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


class EventCandidate(BaseModel):
    id: str
    title: str
    description: str
    categories: list[str]
    start: datetime
    end: datetime
    venue: str
    address: str
    latitude: float
    longitude: float
    distance_km: float
    travel_minutes: int
    price: float
    rating: float
    url: str
    image_url: str

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
            source="mock_events",
            source_url=self.url,
            image_url=self.image_url,
        )
