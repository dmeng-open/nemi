from datetime import datetime

from app.core.exceptions import ProviderNotConfigured
from app.domain.calendar import CalendarEvent, CalendarExecutionResult, NewCalendarEvent


class GoogleCalendarProvider:
    """Registered for a later Google Calendar implementation. V0 does not call the API."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        del start, end
        raise ProviderNotConfigured(
            "Google Calendar is not enabled in V0. Set CALENDAR_PROVIDER=local."
        )

    async def create_event(
        self,
        draft: NewCalendarEvent,
        *,
        idempotency_key: str,
        candidate_id: str,
    ) -> CalendarExecutionResult:
        del draft, idempotency_key, candidate_id
        raise ProviderNotConfigured(
            "Google Calendar is not enabled in V0. Set CALENDAR_PROVIDER=local."
        )
