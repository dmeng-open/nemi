from app.integrations.events.mock import _coordinates
from app.integrations.restaurants.catalog import RESTAURANT_TEMPLATES
from app.integrations.restaurants.models import RestaurantCandidate, RestaurantSearchQuery


class MockRestaurantProvider:
    async def search_restaurants(self, query: RestaurantSearchQuery) -> list[RestaurantCandidate]:
        found: list[RestaurantCandidate] = []
        for template in RESTAURANT_TEMPLATES:
            latitude, longitude = _coordinates(template.travel_minutes)
            found.append(
                RestaurantCandidate(
                    id=f"rst_{template.slug}",
                    name=template.name,
                    description=template.description,
                    cuisines=list(template.cuisines),
                    address=template.address,
                    latitude=latitude,
                    longitude=longitude,
                    distance_km=template.distance_km,
                    travel_minutes=template.travel_minutes,
                    price_level=template.price_level,
                    typical_price=template.typical_price,
                    rating=template.rating,
                    url=f"https://example.com/places/{template.slug}",
                    image_url=template.image_url,
                )
            )
        found.sort(key=lambda item: item.id)
        return found[: query.limit]
