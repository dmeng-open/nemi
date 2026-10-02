from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ProviderNotConfigured
from app.integrations.calendar.google import GoogleCalendarProvider
from app.integrations.calendar.local import LocalCalendarProvider
from app.integrations.events.mock import MockEventProvider
from app.integrations.events.ticketmaster import TicketmasterEventProvider
from app.integrations.restaurants.google_places import GooglePlacesProvider
from app.integrations.restaurants.mock import MockRestaurantProvider
from app.models.user import LOCAL_USER_ID
from app.repositories.calendar import CalendarRepository


def build_event_provider(settings: Settings):
    if settings.event_provider == "mock":
        return MockEventProvider()
    if settings.event_provider == "ticketmaster":
        return TicketmasterEventProvider(settings.ticketmaster_api_key.get_secret_value())
    raise ProviderNotConfigured("Unknown event provider.")


def build_restaurant_provider(settings: Settings):
    if settings.place_provider == "mock":
        return MockRestaurantProvider()
    if settings.place_provider == "google":
        return GooglePlacesProvider(settings.google_places_api_key.get_secret_value())
    raise ProviderNotConfigured("Unknown place provider.")


def build_calendar_provider(settings: Settings, session: AsyncSession, user_id=LOCAL_USER_ID):
    if settings.calendar_provider == "local":
        return LocalCalendarProvider(CalendarRepository(session), user_id)
    if settings.calendar_provider == "google":
        return GoogleCalendarProvider(
            settings.google_client_id.get_secret_value(),
            settings.google_client_secret.get_secret_value(),
        )
    raise ProviderNotConfigured("Unknown calendar provider.")
