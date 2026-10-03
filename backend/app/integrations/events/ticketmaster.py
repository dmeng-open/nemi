import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.clock import Clock, SystemClock
from app.core.exceptions import ProviderError
from app.core.messages import TICKETMASTER_FAILED, TICKETMASTER_NOT_CONFIGURED
from app.integrations.events.models import EventCandidate, EventSearchQuery
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
    log_provider_call,
    not_configured,
)
from app.services.planning.geo import estimate_travel_minutes, haversine_km
from app.services.planning.taxonomy import normalize_token

logger = logging.getLogger(__name__)

TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
CLASSIFICATION = {
    "live_music": "Music",
    "arts": "Arts",
    "comedy": "Comedy",
    "film": "Film",
}
# Ticketmaster often omits an end. Two hours keeps the event schedulable.
DEFAULT_EVENT_DURATION = timedelta(hours=2)
MAX_CANDIDATE_ID = 160


class TicketmasterEventProvider:
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

    async def search_events(self, query: EventSearchQuery) -> list[EventCandidate]:
        if not self.api_key.strip():
            raise not_configured(TICKETMASTER_NOT_CONFIGURED)
        key = discovery_cache_key(_cache_payload(query))
        cached = self.cache.get(key)
        if isinstance(cached, list):
            log_provider_call(
                provider="ticketmaster",
                operation="search",
                status_code=None,
                cache="hit",
                count=len(cached),
            )
            return [EventCandidate.model_validate(item) for item in cached]
        log_provider_call(
            provider="ticketmaster",
            operation="search",
            status_code=None,
            cache="miss",
        )
        payload = await self._fetch(query)
        events, skipped = _normalize_events(payload, query, retrieved_at=self.clock.now())
        if skipped:
            log_provider_call(
                provider="ticketmaster",
                operation="search",
                status_code=200,
                skipped=skipped,
                count=len(events),
            )
        self.cache.set(key, [item.model_dump(mode="json") for item in events])
        if self.health is not None:
            self.health.record("ticketmaster", ok=True, at=self.clock.now())
        return events

    async def _fetch(self, query: EventSearchQuery) -> dict:
        client, owned = self._open_client()
        try:
            try:
                response = await client.get(
                    TICKETMASTER_URL,
                    params=_params(query, self.api_key),
                    timeout=TIMEOUT,
                )
            except httpx.TimeoutException:
                self._record(ok=False)
                raise error_from_transport(
                    provider="ticketmaster",
                    operation="search",
                    failed_message=TICKETMASTER_FAILED,
                ) from None
            except httpx.HTTPError:
                self._record(ok=False)
                raise error_from_transport(
                    provider="ticketmaster",
                    operation="search",
                    failed_message=TICKETMASTER_FAILED,
                ) from None
        finally:
            if owned:
                await client.aclose()
        if response.status_code != 200:
            self._record(ok=False)
            raise error_from_status(
                response.status_code,
                provider="ticketmaster",
                operation="search",
                not_configured_message=TICKETMASTER_NOT_CONFIGURED,
                failed_message=TICKETMASTER_FAILED,
            )
        try:
            payload = response.json()
        except ValueError:
            self._record(ok=False)
            raise failed_body() from None
        if not isinstance(payload, dict):
            self._record(ok=False)
            raise failed_body()
        log_provider_call(
            provider="ticketmaster",
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
            self.health.record("ticketmaster", ok=ok, at=self.clock.now())


def failed_body() -> ProviderError:
    from app.providers.http import failed

    log_provider_call(
        provider="ticketmaster",
        operation="search",
        status_code=200,
        error_code="provider_failed",
    )
    return failed(TICKETMASTER_FAILED)


def _cache_payload(query: EventSearchQuery) -> dict:
    return {
        "provider": "ticketmaster",
        "operation": "search",
        "city": (query.city or "").strip() or None,
        "latitude": round_coord(query.latitude),
        "longitude": round_coord(query.longitude),
        "radius": query.radius_km,
        "date_start": query.date_start.isoformat(),
        "date_end": query.date_end.isoformat(),
        "categories": sorted(query.categories),
        "timezone": query.timezone,
    }


def _params(query: EventSearchQuery, api_key: str) -> dict[str, str | int]:
    zone = _zone(query.timezone)
    start = datetime.combine(query.date_start, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(query.date_end, time.max, tzinfo=zone).astimezone(UTC)
    params: dict[str, str | int] = {
        "apikey": api_key,
        "startDateTime": _utc_z(start),
        "endDateTime": _utc_z(end),
        "size": query.limit,
    }
    classification = _classification(query.categories)
    if classification is not None:
        params["classificationName"] = classification
    if query.latitude is not None and query.longitude is not None:
        params["latlong"] = f"{query.latitude},{query.longitude}"
        params["radius"] = int(query.radius_km or 10)
        params["unit"] = "km"
    elif query.city and query.city.strip():
        params["city"] = query.city.strip()
    return params


def _classification(categories: list[str]) -> str | None:
    if not categories:
        return None
    token = normalize_token(categories[0])
    return CLASSIFICATION.get(token)


def _utc_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _normalize_events(
    payload: dict,
    query: EventSearchQuery,
    *,
    retrieved_at: datetime,
) -> tuple[list[EventCandidate], int]:
    embedded = payload.get("_embedded")
    raw_events = embedded.get("events") if isinstance(embedded, dict) else None
    if not isinstance(raw_events, list):
        return [], 0
    zone = _zone(query.timezone)
    found: list[EventCandidate] = []
    skipped = 0
    for raw in raw_events:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        event_id = raw.get("id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > MAX_CANDIDATE_ID:
            skipped += 1
            continue
        start, end, listed_time_missing = _event_times(raw, zone)
        if start is None or end is None:
            skipped += 1
            continue
        venue_name, address, latitude, longitude = _venue(raw)
        distance_km = None
        travel_minutes = None
        estimate = False
        if (
            query.latitude is not None
            and query.longitude is not None
            and latitude is not None
            and longitude is not None
        ):
            distance_km = round(
                haversine_km(query.latitude, query.longitude, latitude, longitude),
                3,
            )
            travel_minutes = estimate_travel_minutes(distance_km)
            estimate = True
        name = raw.get("name")
        title = name.strip() if isinstance(name, str) and name.strip() else "Untitled event"
        url = raw.get("url") if isinstance(raw.get("url"), str) else None
        found.append(
            EventCandidate(
                id=event_id,
                title=title,
                description=_description(raw),
                categories=_categories(raw),
                start=start,
                end=end,
                venue=venue_name,
                address=address,
                latitude=latitude,
                longitude=longitude,
                distance_km=distance_km,
                travel_minutes=travel_minutes,
                price=_price(raw),
                rating=None,
                url=url or "",
                image_url=_widest_image(raw),
                source="ticketmaster",
                provider="ticketmaster",
                external_id=event_id,
                retrieved_at=retrieved_at,
                travel_time_is_estimate=estimate,
                listed_time_missing=listed_time_missing,
            )
        )
    return found, skipped


def _event_times(raw: dict, fallback: ZoneInfo) -> tuple[datetime | None, datetime | None, bool]:
    dates = raw.get("dates")
    if not isinstance(dates, dict):
        return None, None, False
    zone = _event_zone(dates.get("timezone"), fallback)
    start_point = dates.get("start")
    start = _point_time(start_point, zone)
    if start is None:
        start = _date_only_start(start_point, zone)
        if start is None:
            return None, None, False
        return start, start + DEFAULT_EVENT_DURATION, True
    end = _point_time(dates.get("end"), zone)
    if end is None or end <= start:
        end = start + DEFAULT_EVENT_DURATION
    return start, end, False


def _date_only_start(point: object, zone: ZoneInfo) -> datetime | None:
    """Keep a dated listing that has no clock time. Noon is a placeholder, not midnight."""
    if not isinstance(point, dict):
        return None
    local_date = point.get("localDate")
    if not isinstance(local_date, str) or not local_date.strip():
        return None
    if isinstance(point.get("localTime"), str) and point.get("localTime").strip():
        return None
    if isinstance(point.get("dateTime"), str) and point.get("dateTime").strip():
        return None
    try:
        return datetime.combine(date.fromisoformat(local_date), time(12, 0), tzinfo=zone)
    except ValueError:
        return None


def _event_zone(name: object, fallback: ZoneInfo) -> ZoneInfo:
    if not isinstance(name, str) or not name:
        return fallback
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return fallback


def _point_time(point: object, zone: ZoneInfo) -> datetime | None:
    if not isinstance(point, dict):
        return None
    date_time = point.get("dateTime")
    if isinstance(date_time, str) and date_time.strip():
        return _parse_aware(date_time, zone)
    local_date = point.get("localDate")
    local_time = point.get("localTime")
    if not isinstance(local_date, str) or not isinstance(local_time, str) or not local_time.strip():
        return None
    try:
        return datetime.combine(date.fromisoformat(local_date), time.fromisoformat(local_time), tzinfo=zone)
    except ValueError:
        return None


def _parse_aware(value: str, zone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed


def _venue(raw: dict) -> tuple[str, str, float | None, float | None]:
    embedded = raw.get("_embedded")
    venues = embedded.get("venues") if isinstance(embedded, dict) else None
    venue = venues[0] if isinstance(venues, list) and venues and isinstance(venues[0], dict) else {}
    name = venue.get("name") if isinstance(venue, dict) else None
    venue_name = name.strip() if isinstance(name, str) and name.strip() else "Venue to be announced"
    address = _address(venue if isinstance(venue, dict) else {})
    latitude, longitude = _coordinates(venue if isinstance(venue, dict) else {})
    return venue_name, address, latitude, longitude


def _address(venue: dict) -> str:
    parts: list[str] = []
    address = venue.get("address")
    if isinstance(address, dict):
        line = address.get("line1")
        if isinstance(line, str) and line.strip():
            parts.append(line.strip())
    city = venue.get("city")
    if isinstance(city, dict):
        city_name = city.get("name")
        if isinstance(city_name, str) and city_name.strip():
            parts.append(city_name.strip())
    state = venue.get("state")
    if isinstance(state, dict):
        code = state.get("stateCode") or state.get("name")
        if isinstance(code, str) and code.strip():
            parts.append(code.strip())
    return ", ".join(parts)


def _coordinates(venue: dict) -> tuple[float | None, float | None]:
    location = venue.get("location")
    if not isinstance(location, dict):
        return None, None
    latitude = _float_or_none(location.get("latitude"))
    longitude = _float_or_none(location.get("longitude"))
    if latitude is None or longitude is None:
        return None, None
    return latitude, longitude


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _price(raw: dict) -> float | None:
    ranges = raw.get("priceRanges")
    if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], dict):
        return None
    return _float_or_none(ranges[0].get("min"))


def _widest_image(raw: dict) -> str | None:
    images = raw.get("images")
    if not isinstance(images, list):
        return None
    best_url: str | None = None
    best_width = -1
    for image in images:
        if not isinstance(image, dict):
            continue
        url = image.get("url")
        if not isinstance(url, str) or not url:
            continue
        width = image.get("width")
        width_value = int(width) if isinstance(width, int | float) else 0
        if width_value >= best_width:
            best_url = url
            best_width = width_value
    return best_url


def _categories(raw: dict) -> list[str]:
    tokens: list[str] = []
    classifications = raw.get("classifications")
    if not isinstance(classifications, list):
        return tokens
    for item in classifications:
        if not isinstance(item, dict):
            continue
        for key in ("segment", "genre", "subGenre"):
            node = item.get(key)
            if not isinstance(node, dict):
                continue
            name = node.get("name")
            if not isinstance(name, str) or not name.strip() or name.strip().lower() == "undefined":
                continue
            token = normalize_token(name)
            if token and token not in tokens:
                tokens.append(token)
    return tokens


def _description(raw: dict) -> str:
    for key in ("info", "pleaseNote"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
