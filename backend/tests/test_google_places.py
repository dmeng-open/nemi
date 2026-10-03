import httpx
import pytest
from app.core.clock import FrozenClock
from app.core.exceptions import ProviderError
from app.integrations.restaurants.google_places import PLACES_FIELD_MASK, GooglePlacesProvider
from app.integrations.restaurants.models import RestaurantSearchQuery
from app.providers.retry import call_with_retries
from tests.conftest import FROZEN_NOW


def _query() -> RestaurantSearchQuery:
    return RestaurantSearchQuery(
        timezone="America/Chicago",
        cuisines=["japanese"],
        latitude=41.9,
        longitude=-87.65,
        radius_km=10,
        limit=40,
    )


def _place(**overrides) -> dict:
    payload = {
        "id": "place-1",
        "displayName": {"text": "Kura"},
        "formattedAddress": "1954 N Halsted St",
        "location": {"latitude": 41.92, "longitude": -87.65},
        "rating": 4.6,
        "userRatingCount": 80,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "googleMapsUri": "https://maps.example/kura",
        "businessStatus": "OPERATIONAL",
        "primaryType": "japanese_restaurant",
        "types": ["japanese_restaurant", "restaurant"],
    }
    payload.update(overrides)
    return payload


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_places_normalizes_category_price_band_and_field_mask() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["mask"] = request.headers["X-Goog-FieldMask"]
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"places": [_place()]})

    provider = GooglePlacesProvider("places-key", client=_client(handler), clock=FrozenClock(FROZEN_NOW))
    found = await provider.search_restaurants(_query())
    assert seen["mask"] == PLACES_FIELD_MASK
    assert "*" not in seen["mask"].split(",")
    assert '"includedType":"restaurant"' in seen["body"].replace(" ", "")
    assert len(found) == 1
    place = found[0]
    assert place.source == "google_places"
    assert "japanese" in place.cuisines
    assert place.price_level == 2
    assert place.typical_price == 35
    assert place.rating == pytest.approx(4.6)
    assert place.review_count == 80
    assert place.travel_time_is_estimate is True
    assert place.to_candidate().source == "google_places"


@pytest.mark.asyncio
async def test_places_missing_rating_stays_null_and_closed_places_drop() -> None:
    open_place = _place(id="open", rating=None, userRatingCount=None, priceLevel=None)
    open_place.pop("rating")
    closed = _place(id="closed", businessStatus="CLOSED_TEMPORARILY")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"places": [closed, open_place, _place(id="shut", businessStatus="CLOSED_PERMANENTLY")]})

    provider = GooglePlacesProvider("places-key", client=_client(handler))
    found = await provider.search_restaurants(_query())
    assert [item.id for item in found] == ["open"]
    assert found[0].rating is None
    assert found[0].price_level is None
    assert found[0].typical_price is None


@pytest.mark.asyncio
async def test_places_empty_list_is_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"places": []})

    provider = GooglePlacesProvider("places-key", client=_client(handler))
    assert await provider.search_restaurants(_query()) == []


@pytest.mark.asyncio
async def test_places_does_not_call_without_coordinates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise AssertionError("http was called")

    provider = GooglePlacesProvider("places-key", client=_client(handler))
    query = _query().model_copy(update={"latitude": None, "longitude": None})
    with pytest.raises(ProviderError):
        await provider.search_restaurants(query)


@pytest.mark.asyncio
async def test_places_quota_and_timeout_are_retryable() -> None:
    statuses = iter([429, 429, 429])

    def quota(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            next(statuses),
            json={"error": {"status": "RESOURCE_EXHAUSTED"}},
        )

    provider = GooglePlacesProvider("places-key", client=_client(quota))
    with pytest.raises(ProviderError) as caught:
        await call_with_retries(lambda: provider.search_restaurants(_query()))
    assert caught.value.code == "provider_unavailable"
    assert caught.value.retryable is True

    def timeout(request: httpx.Request) -> httpx.Response:
        del request
        raise httpx.TimeoutException("timed out")

    provider = GooglePlacesProvider("places-key", client=_client(timeout))
    with pytest.raises(ProviderError) as caught:
        await call_with_retries(lambda: provider.search_restaurants(_query()))
    assert caught.value.code == "provider_unavailable"
    assert caught.value.retryable is True
