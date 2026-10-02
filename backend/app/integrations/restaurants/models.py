from datetime import date, datetime

from pydantic import BaseModel, Field

from app.domain.candidates import Candidate


class RestaurantSearchQuery(BaseModel):
    timezone: str
    cuisines: list[str] = Field(default_factory=list)
    budget_max: float | None = None
    max_travel_minutes: int | None = None
    limit: int = 40
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    date_start: date | None = None
    date_end: date | None = None


class RestaurantCandidate(BaseModel):
    id: str
    name: str
    description: str
    cuisines: list[str]
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    travel_minutes: int | None = None
    price_level: int | None = None
    typical_price: float | None = None
    rating: float | None = None
    url: str | None = None
    image_url: str | None = None
    source: str = "mock_restaurants"
    provider: str = "mock"
    external_id: str | None = None
    retrieved_at: datetime | None = None
    review_count: int | None = None
    travel_time_is_estimate: bool = False

    def to_candidate(self) -> Candidate:
        return Candidate(
            id=self.id,
            candidate_type="restaurant",
            title=self.name,
            description=self.description,
            categories=list(self.cuisines),
            address=self.address,
            latitude=self.latitude,
            longitude=self.longitude,
            distance_km=self.distance_km,
            estimated_travel_minutes=self.travel_minutes,
            price_min=self.typical_price,
            price_max=self.typical_price,
            price_level=self.price_level,
            rating=self.rating,
            source=self.source,
            source_url=self.url,
            image_url=self.image_url,
            provider=self.provider,
            external_id=self.external_id or self.id,
            retrieved_at=self.retrieved_at,
            review_count=self.review_count,
            travel_time_is_estimate=self.travel_time_is_estimate,
        )
