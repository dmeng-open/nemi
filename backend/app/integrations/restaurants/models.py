from pydantic import BaseModel, Field

from app.domain.candidates import Candidate


class RestaurantSearchQuery(BaseModel):
    timezone: str
    cuisines: list[str] = Field(default_factory=list)
    budget_max: float | None = None
    max_travel_minutes: int | None = None
    limit: int = 40


class RestaurantCandidate(BaseModel):
    id: str
    name: str
    description: str
    cuisines: list[str]
    address: str
    latitude: float
    longitude: float
    distance_km: float
    travel_minutes: int
    price_level: int
    typical_price: float
    rating: float
    url: str
    image_url: str

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
            source="mock_restaurants",
            source_url=self.url,
            image_url=self.image_url,
        )
