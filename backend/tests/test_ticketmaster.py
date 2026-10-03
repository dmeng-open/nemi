import logging
from datetime import date, timedelta

import httpx
import pytest
from app.core.clock import FrozenClock
from app.core.exceptions import ProviderError, ProviderNotConfigured
from app.integrations.events.models import EventSearchQuery
from app.integrations.events.ticketmaster import TicketmasterEventProvider
from app.providers.cache import InMemoryDiscoveryCache
from app.providers.retry import call_with_retries
from tests.conftest import FROZEN_NOW

API_KEY = "tm-test-key-should-not-be-logged"


def _query() -> EventSearchQuery:
    return EventSearchQuery(
        date_start=date(2026, 10, 3),
        date_end=date(2026, 10, 3),
        timezone="America/Chicago",
        categories=["live_music"],
        city="Chicago",
        limit=40,
    )


def _event(**overrides) -> dict:
    payload = {
        "id": "tm-1",
        "name": "Night Shift",
        "url": "https://example.com/events/night",
        "info": "A late set.",
        "dates": {
            "start": {"dateTime": "2026-10-03T23:00:00Z"},
            "timezone": "America/Chicago",
        },
        "classifications": [{"genre": {"name": "Jazz"}}],
        "images": [
            {"url": "https://example.com/small.jpg", "width": 100},
            {"url": "https://example.com/wide.jpg", "width": 800},
        ],
        "priceRanges": [{"min": 42}],
        "_embedded": {
            "venues": [
                {
                    "name": "The Hall",
                    "address": {"line1": "1 Main St"},
                    "city": {"name": "Chicago"},
                    "location": {"latitude": "41.880", "longitude": "-87.630"},
                }
            ]
        },
    }
    payload.update(overrides)
    return payload


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_ticketmaster_normalizes_price_coordinates_and_aware_times() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["classification"] = request.url.params.get("classificationName", "")
        seen["city"] = request.url.params.get("city", "")
        return httpx.Response(200, json={"_embedded": {"events": [_event()]}})

    provider = TicketmasterEventProvider(
        API_KEY,
        client=_client(handler),
        clock=FrozenClock(FROZEN_NOW),
    )
    found = await provider.search_events(_query())
    assert len(found) == 1
    event = found[0]
    assert event.source == "ticketmaster"
    assert event.provider == "ticketmaster"
    assert event.external_id == "tm-1"
    assert event.price == 42
    assert event.latitude == pytest.approx(41.88)
    assert event.start.tzinfo is not None
    assert event.end > event.start
    assert event.image_url == "https://example.com/wide.jpg"
    assert seen["classification"] == "Music"
    assert seen["city"] == "Chicago"
    candidate = event.to_candidate()
    assert candidate.source == "ticketmaster"
    assert event.end - event.start == timedelta(hours=2)


@pytest.mark.asyncio
async def test_ticketmaster_date_only_is_not_a_midnight_block() -> None:
    date_only = _event(id="date-only")
    date_only["dates"] = {"start": {"localDate": "2026-10-03"}, "timezone": "America/Chicago"}
    timed = _event(id="timed")
    timed["dates"] = {
        "start": {"localDate": "2026-10-03", "localTime": "19:30:00"},
        "timezone": "America/Chicago",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"_embedded": {"events": [date_only, timed]}})

    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    found = await provider.search_events(_query())
    assert [event.external_id for event in found] == ["date-only", "timed"]
    undated = found[0]
    assert undated.listed_time_missing is True
    assert undated.start.hour == 12
    assert undated.start.minute == 0
    assert undated.end - undated.start == timedelta(hours=2)
    event = found[1]
    assert event.listed_time_missing is False
    assert event.start.hour == 19
    assert event.start.minute == 30
    assert event.end - event.start == timedelta(hours=2)


@pytest.mark.asyncio
async def test_ticketmaster_keeps_events_with_missing_price_and_coordinates() -> None:
    raw = _event()
    raw.pop("priceRanges")
    raw["_embedded"]["venues"][0].pop("location")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json={"_embedded": {"events": [raw]}})

    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    found = await provider.search_events(_query())
    assert len(found) == 1
    assert found[0].price is None
    assert found[0].latitude is None
    assert found[0].longitude is None
    assert found[0].distance_km is None
    assert found[0].travel_minutes is None


@pytest.mark.asyncio
async def test_ticketmaster_empty_list_is_success_and_cached() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        calls["n"] += 1
        return httpx.Response(200, json={})

    provider = TicketmasterEventProvider(
        API_KEY,
        client=_client(handler),
        cache=InMemoryDiscoveryCache(600),
    )
    assert await provider.search_events(_query()) == []
    assert await provider.search_events(_query()) == []
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_ticketmaster_coordinate_search_omits_city_and_estimates_travel() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["city"] = request.url.params.get("city", "")
        seen["latlong"] = request.url.params.get("latlong", "")
        seen["unit"] = request.url.params.get("unit", "")
        return httpx.Response(200, json={"_embedded": {"events": [_event()]}})

    query = _query().model_copy(update={"latitude": 41.878, "longitude": -87.63, "radius_km": 10})
    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    found = await provider.search_events(query)
    assert seen["city"] == ""
    assert seen["latlong"] == "41.878,-87.63"
    assert seen["unit"] == "km"
    assert found[0].travel_time_is_estimate is True
    assert found[0].distance_km is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "retryable", "calls"),
    [
        (401, "provider_not_configured", False, 1),
        (429, "provider_unavailable", True, 3),
        (500, "provider_unavailable", True, 3),
    ],
)
async def test_ticketmaster_maps_status_and_retries(
    status: int, code: str, retryable: bool, calls: int
) -> None:
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        seen["n"] += 1
        return httpx.Response(status, json={"error": "upstream"})

    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    with pytest.raises(ProviderError) as caught:
        await call_with_retries(lambda: provider.search_events(_query()))
    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert seen["n"] == calls


@pytest.mark.asyncio
async def test_ticketmaster_timeout_is_retryable() -> None:
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        seen["n"] += 1
        raise httpx.TimeoutException("timed out")

    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    with pytest.raises(ProviderError) as caught:
        await call_with_retries(lambda: provider.search_events(_query()))
    assert caught.value.code == "provider_unavailable"
    assert caught.value.retryable is True
    assert seen["n"] == 3


@pytest.mark.asyncio
async def test_ticketmaster_does_not_log_the_api_key(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(500, json={})

    provider = TicketmasterEventProvider(API_KEY, client=_client(handler))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ProviderError):
        await provider.search_events(_query())
    assert API_KEY not in caplog.text
    assert all(API_KEY not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_missing_ticketmaster_key_does_not_call_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise AssertionError("http was called")

    provider = TicketmasterEventProvider("", client=_client(handler))
    with pytest.raises(ProviderNotConfigured) as caught:
        await provider.search_events(_query())
    assert caught.value.code == "provider_not_configured"
    assert "Demo results were not substituted" in caught.value.message
