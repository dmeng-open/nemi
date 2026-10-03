from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.messages import (
    CALENDAR_NOT_CONFIGURED,
    PLACES_FAILED,
    PLACES_NOT_CONFIGURED,
    TICKETMASTER_FAILED,
    TICKETMASTER_NOT_CONFIGURED,
)
from app.providers.health import InMemoryProviderHealth
from app.schemas.integrations import IntegrationsResponse, ProviderStatus


@dataclass(frozen=True)
class CalendarConnection:
    status: str
    has_refresh_token: bool
    account_email: str | None = None


def _secret(value: str) -> bool:
    return bool(value.strip())


def build_integrations_response(
    settings: Settings,
    health: InMemoryProviderHealth,
    calendar: CalendarConnection | None,
    *,
    now: datetime | None = None,
) -> IntegrationsResponse:
    moment = now or datetime.now(UTC)
    window = float(settings.integrations_health_ttl_seconds)
    events = _events(settings, health, moment, window)
    places = _places(settings, health, moment, window)
    calendar_status = _calendar(settings, health, calendar, moment, window)
    demo = (
        settings.event_provider == "mock"
        and settings.place_provider == "mock"
        and settings.calendar_provider == "local"
    )
    return IntegrationsResponse(
        event_provider=events,
        place_provider=places,
        calendar_provider=calendar_status,
        openai_configured=settings.openai_configured,
        timezone=settings.app_timezone,
        demo_mode=demo,
    )


def _events(
    settings: Settings,
    health: InMemoryProviderHealth,
    now: datetime,
    window: float,
) -> ProviderStatus:
    if settings.event_provider == "mock":
        return ProviderStatus(
            key="mock",
            label="Mock events",
            mode="mock",
            status="ready",
            connection="mock",
            detail="Demo events around a Chicago neighborhood. No external account.",
        )
    if health.unhealthy("ticketmaster", now=now, window_seconds=window):
        return ProviderStatus(
            key="ticketmaster",
            label="Ticketmaster",
            mode="ticketmaster",
            status="unavailable",
            connection="unhealthy",
            detail=TICKETMASTER_FAILED,
        )
    if not _secret(settings.ticketmaster_api_key.get_secret_value()):
        return ProviderStatus(
            key="ticketmaster",
            label="Ticketmaster",
            mode="ticketmaster",
            status="unavailable",
            connection="not_configured",
            detail=TICKETMASTER_NOT_CONFIGURED,
        )
    return ProviderStatus(
        key="ticketmaster",
        label="Ticketmaster",
        mode="ticketmaster",
        status="ready",
        connection="configured",
        detail="Ticketmaster is configured.",
    )


def _places(
    settings: Settings,
    health: InMemoryProviderHealth,
    now: datetime,
    window: float,
) -> ProviderStatus:
    if settings.place_provider == "mock":
        return ProviderStatus(
            key="mock",
            label="Mock restaurants",
            mode="mock",
            status="ready",
            connection="mock",
            detail="Demo restaurants around a Chicago neighborhood. No external account.",
        )
    if health.unhealthy("google_places", now=now, window_seconds=window):
        return ProviderStatus(
            key="google",
            label="Google Places",
            mode="google",
            status="unavailable",
            connection="unhealthy",
            detail=PLACES_FAILED,
        )
    if not _secret(settings.google_places_api_key.get_secret_value()):
        return ProviderStatus(
            key="google",
            label="Google Places",
            mode="google",
            status="unavailable",
            connection="not_configured",
            detail=PLACES_NOT_CONFIGURED,
        )
    return ProviderStatus(
        key="google",
        label="Google Places",
        mode="google",
        status="ready",
        connection="configured",
        detail="Google Places is configured.",
    )


def _calendar(
    settings: Settings,
    health: InMemoryProviderHealth,
    calendar: CalendarConnection | None,
    now: datetime,
    window: float,
) -> ProviderStatus:
    if settings.calendar_provider == "local":
        return ProviderStatus(
            key="local",
            label="Local calendar",
            mode="local",
            status="ready",
            connection="local",
            detail="Events stay in Nemi's database and can be exported as .ics.",
        )
    if health.unhealthy("google_calendar", now=now, window_seconds=window):
        return ProviderStatus(
            key="google",
            label="Google Calendar",
            mode="google",
            status="unavailable",
            connection="unhealthy",
            detail="Google Calendar could not be reached.",
            account_email=None,
        )
    client_ready = _secret(settings.google_client_id.get_secret_value()) and _secret(
        settings.google_client_secret.get_secret_value()
    )
    if not client_ready:
        return ProviderStatus(
            key="google",
            label="Google Calendar",
            mode="google",
            status="unavailable",
            connection="not_configured",
            detail=CALENDAR_NOT_CONFIGURED,
        )
    if (
        calendar is None
        or calendar.status != "connected"
        or not calendar.has_refresh_token
    ):
        return ProviderStatus(
            key="google",
            label="Google Calendar",
            mode="google",
            status="unavailable",
            connection="oauth_required",
            detail="Connect Google Calendar to read busy time and add plans.",
        )
    return ProviderStatus(
        key="google",
        label="Google Calendar",
        mode="google",
        status="ready",
        connection="connected",
        detail="Connected.",
        account_email=calendar.account_email,
    )
