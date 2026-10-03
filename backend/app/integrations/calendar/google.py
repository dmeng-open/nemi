import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.exc import IntegrityError

from app.core.clock import Clock, SystemClock
from app.core.exceptions import (
    AppError,
    CalendarCreateUnconfirmed,
    ProviderError,
    ProviderNotConfigured,
)
from app.domain.calendar import CalendarEvent, CalendarExecutionResult, NewCalendarEvent
from app.models.calendar import CalendarAction
from app.providers.health import InMemoryProviderHealth
from app.providers.http import TIMEOUT, error_from_status, error_from_transport, log_provider_call
from app.repositories.calendar import CalendarRepository
from app.repositories.oauth import OAuthConnectionRepository
from app.services.calendar.time import as_utc
from app.services.oauth import InvalidGrant, TokenExchangeFailed, refresh_access_token

CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MAX_PAGES = 5


class GoogleCalendarProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        user_id: uuid.UUID,
        oauth: OAuthConnectionRepository,
        calendar: CalendarRepository,
        client: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        health: InMemoryProviderHealth | None = None,
        retry_base_delay: float = 0.25,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_id = user_id
        self.oauth = oauth
        self.calendar = calendar
        self._client = client
        self.clock = clock or SystemClock()
        self.health = health
        self.retry_base_delay = retry_base_delay

    async def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        _reject_naive(start, end)
        events: list[CalendarEvent] = []
        page_token: str | None = None
        zone = start.tzinfo if isinstance(start.tzinfo, ZoneInfo) else ZoneInfo("UTC")
        for _ in range(MAX_PAGES):
            params: dict[str, str] = {
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": "250",
            }
            if page_token:
                params["pageToken"] = page_token
            payload = await self._request("GET", CALENDAR_API, params=params)
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        mapped = _map_event(item, zone)
                        if mapped is not None:
                            events.append(mapped)
            token = payload.get("nextPageToken") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                break
            page_token = token
        if self.health is not None:
            self.health.record("google_calendar", ok=True, at=self.clock.now())
        return events

    async def create_event(
        self,
        draft: NewCalendarEvent,
        *,
        idempotency_key: str,
        candidate_id: str,
    ) -> CalendarExecutionResult:
        _reject_naive(draft.start, draft.end)
        existing = await self.calendar.get_action(idempotency_key)
        if existing is not None and existing.status == "completed":
            return _draft_result(draft, idempotency_key, replayed=True)

        last_unconfirmed = True
        for attempt in range(3):
            try:
                await self._insert(draft, idempotency_key)
                await self._store_action(draft, idempotency_key, candidate_id)
                if self.health is not None:
                    self.health.record("google_calendar", ok=True, at=self.clock.now())
                return _draft_result(draft, idempotency_key, replayed=False)
            except _AlreadyExists:
                await self._store_action(draft, idempotency_key, candidate_id)
                return _draft_result(draft, idempotency_key, replayed=True)
            except _RetryableCreate:
                found = await self._lookup(idempotency_key)
                if found:
                    await self._store_action(draft, idempotency_key, candidate_id)
                    if self.health is not None:
                        self.health.record("google_calendar", ok=True, at=self.clock.now())
                    return _draft_result(draft, idempotency_key, replayed=False)
                last_unconfirmed = True
                if attempt == 2:
                    break
                await self._pause(attempt)
            except ProviderNotConfigured:
                raise
            except ProviderError as exc:
                if not exc.retryable:
                    found = await self._lookup(idempotency_key)
                    if found:
                        await self._store_action(draft, idempotency_key, candidate_id)
                        return _draft_result(draft, idempotency_key, replayed=False)
                    raise CalendarCreateUnconfirmed() from None
                found = await self._lookup(idempotency_key)
                if found:
                    await self._store_action(draft, idempotency_key, candidate_id)
                    return _draft_result(draft, idempotency_key, replayed=False)
                if attempt == 2:
                    break
                await self._pause(attempt)
        if last_unconfirmed:
            if self.health is not None:
                self.health.record("google_calendar", ok=False, at=self.clock.now())
            raise CalendarCreateUnconfirmed()
        raise CalendarCreateUnconfirmed()

    async def delete_event(self, event_id: str) -> None:
        token = await self._access_token(force=False)
        response = await self._send(
            "DELETE",
            f"{CALENDAR_API}/{event_id}",
            token,
            params=None,
            json_body=None,
        )
        if response.status_code == 401:
            token = await self._access_token(force=True)
            response = await self._send(
                "DELETE",
                f"{CALENDAR_API}/{event_id}",
                token,
                params=None,
                json_body=None,
            )
        if response.status_code in {200, 204, 404}:
            return
        raise error_from_status(
            response.status_code,
            provider="google_calendar",
            operation="delete",
            not_configured_message="Connect Google Calendar to change this plan.",
            failed_message="Google Calendar could not remove the event.",
        )

    async def _insert(self, draft: NewCalendarEvent, event_id: str) -> None:
        body = {
            "id": event_id,
            "summary": draft.title,
            "description": draft.description,
            "location": draft.location,
            "start": {"dateTime": draft.start.isoformat()},
            "end": {"dateTime": draft.end.isoformat()},
        }
        try:
            payload = await self._request("POST", CALENDAR_API, json_body=body)
        except ProviderError as exc:
            if exc.status_code == 409:
                raise _AlreadyExists() from None
            raise
        if not isinstance(payload, dict):
            raise _RetryableCreate()

    async def _lookup(self, event_id: str) -> bool:
        try:
            payload = await self._request("GET", f"{CALENDAR_API}/{event_id}")
        except ProviderError as exc:
            if exc.status_code == 404:
                return False
            return False
        return isinstance(payload, dict) and bool(payload.get("id"))

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
    ) -> dict:
        token = await self._access_token(force=False)
        response = await self._send(method, url, token, params=params, json_body=json_body)
        if response.status_code == 401:
            token = await self._access_token(force=True)
            response = await self._send(method, url, token, params=params, json_body=json_body)
        if response.status_code == 404:
            raise ProviderError(
                "Google Calendar could not find that event.",
                retryable=False,
                code="provider_failed",
                status_code=404,
            )
        if response.status_code == 409:
            raise ProviderError(
                "Google Calendar already has this event.",
                retryable=False,
                code="provider_failed",
                status_code=409,
            )
        if response.status_code != 200 and not (method == "POST" and response.status_code == 201):
            if self.health is not None and response.status_code >= 400:
                self.health.record("google_calendar", ok=False, at=self.clock.now())
            raise error_from_status(
                response.status_code,
                provider="google_calendar",
                operation=method.lower(),
                not_configured_message="Connect Google Calendar to add this plan.",
                failed_message="Google Calendar could not be reached.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "Google Calendar could not be reached.",
                retryable=True,
                code="provider_unavailable",
                status_code=503,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError(
                "Google Calendar could not be reached.",
                retryable=True,
                code="provider_unavailable",
                status_code=503,
            )
        log_provider_call(
            provider="google_calendar",
            operation=method.lower(),
            status_code=response.status_code,
        )
        return payload

    async def _send(
        self,
        method: str,
        url: str,
        token: str,
        *,
        params: dict[str, str] | None,
        json_body: dict | None,
    ) -> httpx.Response:
        client, owned = self._open_client()
        try:
            try:
                return await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=TIMEOUT,
                )
            except httpx.TimeoutException:
                self._fail_health()
                if method == "POST":
                    raise _RetryableCreate() from None
                raise error_from_transport(
                    provider="google_calendar",
                    operation=method.lower(),
                    failed_message="Google Calendar could not be reached.",
                ) from None
            except httpx.HTTPError:
                self._fail_health()
                if method == "POST":
                    raise _RetryableCreate() from None
                raise error_from_transport(
                    provider="google_calendar",
                    operation=method.lower(),
                    failed_message="Google Calendar could not be reached.",
                ) from None
        finally:
            if owned:
                await client.aclose()

    async def _access_token(self, *, force: bool) -> str:
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ProviderNotConfigured(
                "Google Calendar is selected but no OAuth client is configured."
            )
        row = await self.oauth.get(self.user_id)
        if row is None or row.status != "connected" or not row.refresh_token:
            raise ProviderNotConfigured("Connect Google Calendar to add this plan.")
        now = self.clock.now()
        expires = row.access_token_expires_at
        if (
            not force
            and row.access_token
            and expires is not None
            and as_utc(expires) > as_utc(now) + timedelta(seconds=60)
        ):
            return row.access_token
        client, owned = self._open_client()
        try:
            try:
                bundle = await refresh_access_token(
                    client,
                    refresh_token=row.refresh_token,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                )
            except InvalidGrant:
                await self.oauth.mark_revoked(self.user_id, now=now)
                raise ProviderNotConfigured("Connect Google Calendar to add this plan.") from None
            except TokenExchangeFailed:
                raise ProviderError(
                    "Google Calendar could not be reached.",
                    retryable=True,
                    code="provider_unavailable",
                    status_code=503,
                ) from None
        finally:
            if owned:
                await client.aclose()
        await self.oauth.update_access_token(
            row,
            refresh_token=bundle.refresh_token,
            access_token=bundle.access_token,
            access_token_expires_at=now + timedelta(seconds=max(bundle.expires_in - 60, 0)),
            now=now,
        )
        return bundle.access_token

    async def _store_action(
        self,
        draft: NewCalendarEvent,
        idempotency_key: str,
        candidate_id: str,
    ) -> None:
        existing = await self.calendar.get_action(idempotency_key)
        if existing is not None and existing.status == "completed":
            return
        if draft.planning_session_id is None:
            raise AppError("A planned event needs a plan id.", code="plan_not_ready", status_code=409)
        action = CalendarAction(
            user_id=self.user_id,
            session_id=uuid.UUID(draft.planning_session_id),
            candidate_id=candidate_id,
            action_type="create_event",
            idempotency_key=idempotency_key,
            status="completed",
            local_calendar_event_id=None,
            external_event_id=idempotency_key,
        )
        session = self.calendar.session
        try:
            async with session.begin_nested():
                session.add(action)
                await session.flush()
        except IntegrityError:
            raced = await self.calendar.get_action(idempotency_key)
            if raced is not None and raced.status == "completed":
                return
            raise

    async def _pause(self, attempt: int) -> None:
        if self.retry_base_delay <= 0:
            return
        import asyncio

        delay = min(self.retry_base_delay * (2**attempt), 2.0)
        await asyncio.sleep(delay)

    def _fail_health(self) -> None:
        if self.health is not None:
            self.health.record("google_calendar", ok=False, at=self.clock.now())

    def _open_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=TIMEOUT), True


class _AlreadyExists(Exception):
    pass


class _RetryableCreate(Exception):
    pass


def _reject_naive(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise AppError(
            "Include a timezone on the start and end times.",
            code="validation_error",
            status_code=422,
        )


def _draft_result(
    draft: NewCalendarEvent,
    event_id: str,
    *,
    replayed: bool,
) -> CalendarExecutionResult:
    return CalendarExecutionResult(
        calendar_event_id=event_id,
        title=draft.title,
        start=draft.start,
        end=draft.end,
        location=draft.location,
        replayed=replayed,
    )


def _map_event(item: dict, zone: ZoneInfo) -> CalendarEvent | None:
    if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
        return None
    start = _google_time(item.get("start"), zone)
    end = _google_time(item.get("end"), zone)
    if start is None or end is None or end <= start:
        return None
    event_id = item.get("id")
    title = item.get("summary")
    location = item.get("location")
    description = item.get("description")
    link = item.get("htmlLink")
    return CalendarEvent(
        id=event_id if isinstance(event_id, str) and event_id else "google-event",
        title=title.strip() if isinstance(title, str) and title.strip() else "Busy",
        start=start,
        end=end,
        location=location if isinstance(location, str) else None,
        description=description if isinstance(description, str) else None,
        source_url=link if isinstance(link, str) else None,
    )


def _google_time(node: object, zone: ZoneInfo) -> datetime | None:
    if not isinstance(node, dict):
        return None
    date_time = node.get("dateTime")
    if isinstance(date_time, str) and date_time.strip():
        parsed = _parse_aware(date_time, zone)
        return parsed
    day = node.get("date")
    if isinstance(day, str):
        try:
            return datetime.combine(date.fromisoformat(day), time.min, tzinfo=zone)
        except ValueError:
            return None
    return None


def _parse_aware(value: str, zone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed
