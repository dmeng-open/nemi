from app.core.exceptions import ProviderNotConfigured
from app.integrations.restaurants.models import RestaurantCandidate, RestaurantSearchQuery


class GooglePlacesProvider:
    """Registered for a later Google Places implementation. V0 does not call the API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search_restaurants(self, query: RestaurantSearchQuery) -> list[RestaurantCandidate]:
        del query
        raise ProviderNotConfigured("Google Places is not enabled in V0. Set PLACE_PROVIDER=mock.")
