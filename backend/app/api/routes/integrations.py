from fastapi import APIRouter, Depends

from app.api.deps import get_settings
from app.core.config import Settings
from app.schemas.integrations import IntegrationsResponse, ProviderStatus

router = APIRouter(prefix="/integrations", tags=["integrations"])

PROVIDER_COPY = {
    ("events", "mock"): (
        "Mock events",
        "Demo events around a Chicago neighborhood. No external account.",
    ),
    ("events", "ticketmaster"): (
        "Ticketmaster",
        "Not available in V0. Switch EVENT_PROVIDER back to mock.",
    ),
    ("places", "mock"): (
        "Mock restaurants",
        "Demo restaurants around a Chicago neighborhood. No external account.",
    ),
    ("places", "google"): (
        "Google Places",
        "Not available in V0. Switch PLACE_PROVIDER back to mock.",
    ),
    ("calendar", "local"): (
        "Local calendar",
        "Events stay in Nemi's database and can be exported as .ics.",
    ),
    ("calendar", "google"): (
        "Google Calendar",
        "Not available in V0. Switch CALENDAR_PROVIDER back to local.",
    ),
}


def _status(kind: str, mode: str, *, ready: bool) -> ProviderStatus:
    label, detail = PROVIDER_COPY.get(
        (kind, mode),
        (mode, "This provider is not available in V0."),
    )
    return ProviderStatus(
        key=mode,
        label=label,
        mode=mode,
        status="ready" if ready else "unavailable",
        detail=detail,
    )


@router.get("", response_model=IntegrationsResponse)
async def read_integrations(settings: Settings = Depends(get_settings)) -> IntegrationsResponse:
    event_ready = settings.event_provider == "mock"
    place_ready = settings.place_provider == "mock"
    calendar_ready = settings.calendar_provider == "local"
    return IntegrationsResponse(
        event_provider=_status("events", settings.event_provider, ready=event_ready),
        place_provider=_status("places", settings.place_provider, ready=place_ready),
        calendar_provider=_status("calendar", settings.calendar_provider, ready=calendar_ready),
        openai_configured=settings.openai_configured,
        timezone=settings.app_timezone,
        demo_mode=event_ready and place_ready and calendar_ready,
    )
