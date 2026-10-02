import logging

import httpx

from app.core.clock import Clock, SystemClock
from app.core.exceptions import ProviderError
from app.core.messages import PLACES_FAILED, PLACES_NOT_CONFIGURED
from app.integrations.restaurants.models import RestaurantCandidate, RestaurantSearchQuery
from app.providers.cache import (
    DiscoveryCache,
    NullDiscoveryCache,
    discovery_cache_key,
    round_coord,
)
from app.providers.health import InMemoryProviderHealth
from app.providers.http import (
    TIMEOUT,
    error_from_status,
    error_from_transport,
    failed,
    log_provider_call,
    not_configured,
)
from app.services.planning.geo import estimate_travel_minutes, haversine_km
from app.services.planning.taxonomy import humanize, normalize_token, slugify

logger = logging.getLogger(__name__)

PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.rating,places.userRatingCount,places.priceLevel,places.googleMapsUri,"
    "places.businessStatus,places.primaryType,places.types"
)
CLOSED = {"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}
SKIP_TYPES = {"restaurant", "food", "point_of_interest", "establishment"}
PRICE_BANDS: dict[str, tuple[int, float]] = {
    "PRICE_LEVEL_FREE": (0, 0),
    "PRICE_LEVEL_INEXPENSIVE": (1, 15),
    "PRICE_LEVEL_MODERATE": (2, 35),
    "PRICE_LEVEL_EXPENSIVE": (3, 70),
    "PRICE_LEVEL_VERY_EXPENSIVE": (4, 120),
}
MAX_CANDIDATE_ID = 160
MAX_PAGE_SIZE = 20


class GooglePlacesProvider:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        cache: DiscoveryCache | None = None,
        health: InMemoryProviderHealth | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.api_key = api_key
        self._client = client
        self.cache = cache or NullDiscoveryCache()
        self.health = health
        self.clock = clock or SystemClock()

    async def search_restaurants(self, query: RestaurantSearchQuery) -> list[RestaurantCandidate]:
        if query.latitude is None or query.longitude is None:
            raise ProviderError(
                "Google Places needs a latitude and longitude.",
                retryable=False,
                code="provider_failed",
                status_code=502,
            )
        if not self.api_key.strip():
            raise not_configured(PLACES_NOT_CONFIGURED)
        key = discovery_cache_key(_cache_payload(query))
        cached = self.cache.get(key)
        if isinstance(cached, list):
            log_provider_call(
                provider="google_places",
                operation="search",
                status_code=None,
                cache="hit",
                count=len(cached),
            )
            return [RestaurantCandidate.model_validate(item) for item in cached]
        log_provider_call(
            provider="google_places",
            operation="search",
            status_code=None,
            cache="miss",
        )
        payload = await self._fetch(query)
        places, skipped = _normalize_places(payload, query, retrieved_at=self.clock.now())
        if skipped:
            log_provider_call(
                provider="google_places",
                operation="search",
                status_code=200,
                skipped=skipped,
                count=len(places),
            )
        self.cache.set(key, [item.model_dump(mode="json") for item in places])
        if self.health is not None:
            self.health.record("google_places", ok=True, at=self.clock.now())
        return places

    async def _fetch(self, query: RestaurantSearchQuery) -> dict:
        assert query.latitude is not None and query.longitude is not None
        radius_km = query.radius_km or 10
        body = {
            "textQuery": _text_query(query.cuisines),
            "pageSize": max(1, min(query.limit, MAX_PAGE_SIZE)),
            "includedType": "restaurant",
            "strictTypeFiltering": True,
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": query.latitude,
                        "longitude": query.longitude,
                    },
                    "radius": radius_km * 1000,
                }
            },
        }
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
            "Content-Type": "application/json",
        }
        client, owned = self._open_client()
        try:
            try:
                response = await client.post(PLACES_URL, json=body, headers=headers, timeout=TIMEOUT)
            except httpx.TimeoutException:
                self._record(ok=False)
                raise error_from_transport(
                    provider="google_places",
                    operation="search",
                    failed_message=PLACES_FAILED,
                ) from None
            except httpx.HTTPError:
                self._record(ok=False)
                raise error_from_transport(
                    provider="google_places",
                    operation="search",
                    failed_message=PLACES_FAILED,
                ) from None
        finally:
            if owned:
                await client.aclose()
        if response.status_code != 200:
            self._record(ok=False)
            raise error_from_status(
                response.status_code,
                provider="google_places",
                operation="search",
                not_configured_message=PLACES_NOT_CONFIGURED,
                failed_message=PLACES_FAILED,
                quota=_is_quota(response),
            )
        try:
            payload = response.json()
        except ValueError:
            self._record(ok=False)
            raise _bad_body() from None
        if not isinstance(payload, dict):
            self._record(ok=False)
            raise _bad_body()
        log_provider_call(
            provider="google_places",
            operation="search",
            status_code=response.status_code,
        )
        return payload

    def _open_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=TIMEOUT), True

    def _record(self, *, ok: bool) -> None:
        if self.health is not None:
            self.health.record("google_places", ok=ok, at=self.clock.now())


def _bad_body() -> ProviderError:
    log_provider_call(
        provider="google_places",
        operation="search",
        status_code=200,
        error_code="provider_failed",
    )
    return failed(PLACES_FAILED)


def _is_quota(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("status") == "RESOURCE_EXHAUSTED"


def _cache_payload(query: RestaurantSearchQuery) -> dict:
    return {
        "provider": "google_places",
        "operation": "search",
        "city": None,
        "latitude": round_coord(query.latitude),
        "longitude": round_coord(query.longitude),
        "radius": query.radius_km,
        "date_start": query.date_start.isoformat() if query.date_start else None,
        "date_end": query.date_end.isoformat() if query.date_end else None,
        "categories": sorted(query.cuisines),
        "timezone": query.timezone,
    }


def _text_query(cuisines: list[str]) -> str:
    label = humanize(cuisines)
    return label or "restaurant"


def _normalize_places(
    payload: dict,
    query: RestaurantSearchQuery,
    *,
    retrieved_at,
) -> tuple[list[RestaurantCandidate], int]:
    raw_places = payload.get("places")
    if not isinstance(raw_places, list):
        return [], 0
    found: list[RestaurantCandidate] = []
    skipped = 0
    for raw in raw_places:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        if raw.get("businessStatus") in CLOSED:
            continue
        place_id = raw.get("id")
        if not isinstance(place_id, str) or not place_id or len(place_id) > MAX_CANDIDATE_ID:
            skipped += 1
            continue
        latitude, longitude = _location(raw.get("location"))
        distance_km = None
        travel_minutes = None
        estimate = False
        if (
            query.latitude is not None
            and query.longitude is not None
            and latitude is not None
            and longitude is not None
        ):
            distance_km = round(haversine_km(query.latitude, query.longitude, latitude, longitude), 3)
            travel_minutes = estimate_travel_minutes(distance_km)
            estimate = True
        price_level, typical_price = _price_band(raw.get("priceLevel"))
        rating = raw.get("rating") if isinstance(raw.get("rating"), int | float) else None
        review_count = raw.get("userRatingCount")
        reviews = int(review_count) if isinstance(review_count, int | float) else None
        display = raw.get("displayName")
        title = "Restaurant"
        if isinstance(display, dict) and isinstance(display.get("text"), str) and display["text"].strip():
            title = display["text"].strip()
        address = raw.get("formattedAddress")
        url = raw.get("googleMapsUri") if isinstance(raw.get("googleMapsUri"), str) else None
        found.append(
            RestaurantCandidate(
                id=place_id,
                name=title,
                description="",
                cuisines=_cuisines(raw),
                address=address.strip() if isinstance(address, str) else "",
                latitude=latitude,
                longitude=longitude,
                distance_km=distance_km,
                travel_minutes=travel_minutes,
                price_level=price_level,
                typical_price=typical_price,
                rating=float(rating) if rating is not None else None,
                url=url,
                image_url=None,
                source="google_places",
                provider="google_places",
                external_id=place_id,
                retrieved_at=retrieved_at,
                review_count=reviews,
                travel_time_is_estimate=estimate,
            )
        )
    return found, skipped


def _location(value: object) -> tuple[float | None, float | None]:
    if not isinstance(value, dict):
        return None, None
    latitude = value.get("latitude")
    longitude = value.get("longitude")
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return None, None
    return float(latitude), float(longitude)


def _price_band(value: object) -> tuple[int | None, float | None]:
    if not isinstance(value, str):
        return None, None
    band = PRICE_BANDS.get(value)
    if band is None:
        return None, None
    return band


def _cuisines(raw: dict) -> list[str]:
    tokens: list[str] = []
    primary = raw.get("primaryType")
    values: list[object] = [primary] if isinstance(primary, str) else []
    types = raw.get("types")
    if isinstance(types, list):
        values.extend(types)
    for value in values:
        if not isinstance(value, str):
            continue
        token = _place_category(value)
        if token and token not in SKIP_TYPES and token not in tokens:
            tokens.append(token)
    return tokens


def _place_category(value: str) -> str:
    slug = slugify(value)
    for suffix in ("_restaurant", "_food"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return normalize_token(slug, cuisine=True)
