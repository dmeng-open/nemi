from app.core.exceptions import ProviderNotConfigured
from app.integrations.events.models import EventCandidate, EventSearchQuery


class TicketmasterEventProvider:
    """Registered for a later Ticketmaster implementation. V0 does not call the API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search_events(self, query: EventSearchQuery) -> list[EventCandidate]:
        del query
        raise ProviderNotConfigured("Ticketmaster is not enabled in V0. Set EVENT_PROVIDER=mock.")
