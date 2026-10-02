import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.core.clock import FrozenClock
from app.core.exceptions import AppError, ProviderNotConfigured, ScheduleConflictError
from app.domain.calendar import NewCalendarEvent
from app.domain.candidates import Candidate
from app.integrations.calendar.google import GoogleCalendarProvider
from app.models.calendar import CalendarAction
from app.models.planning import PlanningSession
from app.models.user import LOCAL_USER_ID
from app.repositories.calendar import CalendarRepository
from app.repositories.oauth import OAuthConnectionRepository
from app.services.calendar.idempotency import make_idempotency_key
from app.services.calendar.scheduling import schedule_approved_plan
from app.services.oauth import (
    finish_callback,
    hash_state,
    normalize_return_path,
    resolve_return_path,
    start_connect,
)
from sqlalchemy import func, select

NOW = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
START = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)
END = datetime(2026, 10, 3, 21, 0, tzinfo=UTC)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _connected(session, *, expires_at: datetime | None = None, access_token: str = "access-token"):
    await OAuthConnectionRepository(session).save_connection(
        user_id=LOCAL_USER_ID,
        refresh_token="refresh-token",
        access_token=access_token,
        access_token_expires_at=expires_at or (NOW + timedelta(hours=1)),
        scopes=["https://www.googleapis.com/auth/calendar.events"],
        now=NOW,
    )


def _provider(session, client: httpx.AsyncClient) -> GoogleCalendarProvider:
    return GoogleCalendarProvider(
        "client-id",
        "client-secret",
        user_id=LOCAL_USER_ID,
        oauth=OAuthConnectionRepository(session),
        calendar=CalendarRepository(session),
        client=client,
        clock=FrozenClock(NOW),
        retry_base_delay=0,
    )


def _draft(plan_id: uuid.UUID) -> NewCalendarEvent:
    return NewCalendarEvent(
        title="Real Workshop",
        start=START,
        end=END,
        location="Hall",
        description="Planned with Nemi.",
        planning_session_id=str(plan_id),
    )


async def _plan(session) -> PlanningSession:
    plan = PlanningSession(user_id=LOCAL_USER_ID, user_request="Saturday", status="awaiting_approval")
    session.add(plan)
    await session.flush()
    return plan


@pytest.mark.asyncio
async def test_oauth_state_is_single_use_and_expiry_is_rejected(session_factory) -> None:
    nonce = "nonce-1"
    async with session_factory() as session:
        await OAuthConnectionRepository(session).create_state(
            user_id=LOCAL_USER_ID,
            state_hash=hash_state(nonce),
            return_path="/integrations",
            expires_at=NOW + timedelta(minutes=10),
        )
        await session.commit()
    async with session_factory() as session:
        repo = OAuthConnectionRepository(session)
        first = await repo.consume_state(hash_state(nonce), now=NOW)
        second = await repo.consume_state(hash_state(nonce), now=NOW)
        await session.commit()
    assert first is not None
    assert second is None

    async with session_factory() as session:
        await OAuthConnectionRepository(session).create_state(
            user_id=LOCAL_USER_ID,
            state_hash=hash_state("expired"),
            return_path="/integrations",
            expires_at=NOW - timedelta(seconds=1),
        )
        await session.commit()
    async with session_factory() as session:
        missed = await OAuthConnectionRepository(session).consume_state(hash_state("expired"), now=NOW)
    assert missed is None


def test_absolute_return_path_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        normalize_return_path("https://evil.example/integrations")
    assert caught.value.status_code == 422
    with pytest.raises(AppError):
        normalize_return_path("//evil.example")
    with pytest.raises(AppError):
        normalize_return_path("/integrations?next=https://evil.example")
    with pytest.raises(AppError):
        normalize_return_path("/plans/not-a-uuid")
    assert normalize_return_path(None) == "/integrations"
    assert normalize_return_path("/integrations") == "/integrations"


@pytest.mark.asyncio
async def test_existing_plan_path_is_allowed(session_factory) -> None:
    async with session_factory() as session:
        plan = await _plan(session)
        await session.commit()
        allowed = await resolve_return_path(session, f"/plans/{plan.id}")
        assert allowed == f"/plans/{plan.id}"
        with pytest.raises(AppError):
            await resolve_return_path(session, f"/plans/{uuid.uuid4()}")


@pytest.mark.asyncio
async def test_connect_url_uses_calendar_events_scope_only(session_factory) -> None:
    async with session_factory() as session:
        url = await start_connect(
            OAuthConnectionRepository(session),
            user_id=LOCAL_USER_ID,
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost:8000/api/integrations/google/calendar/callback",
            return_path="/integrations",
            now=NOW,
        )
    assert "calendar.events" in url
    assert "include_granted_scopes=false" in url
    assert "openid" not in url
    assert "prompt=consent" in url
    assert "access_type=offline" in url


@pytest.mark.asyncio
async def test_callback_redirect_does_not_carry_the_code(session_factory) -> None:
    nonce = "callback-nonce"

    def handler(request: httpx.Request) -> httpx.Response:
        assert "code" in request.read().decode()
        return httpx.Response(
            200,
            json={"access_token": "ya29.secret", "refresh_token": "refresh-secret", "expires_in": 3600},
        )

    async with session_factory() as session:
        await OAuthConnectionRepository(session).create_state(
            user_id=LOCAL_USER_ID,
            state_hash=hash_state(nonce),
            return_path="/integrations",
            expires_at=NOW + timedelta(minutes=10),
        )
        target = await finish_callback(
            OAuthConnectionRepository(session),
            _client(handler),
            code="auth-code-secret",
            state=nonce,
            error=None,
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost:8000/api/integrations/google/calendar/callback",
            base_url="http://localhost:5173",
            now=NOW,
        )
        row = await OAuthConnectionRepository(session).get(LOCAL_USER_ID)
        await session.commit()
    assert target == "http://localhost:5173/integrations"
    assert "auth-code-secret" not in target
    assert "ya29" not in target
    assert "refresh-secret" not in target
    assert row is not None
    assert row.account_email is None
    assert row.status == "connected"


@pytest.mark.asyncio
async def test_google_read_maps_aware_events(session_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer access-token"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "g1",
                        "summary": "Busy",
                        "start": {"dateTime": "2026-10-03T19:00:00Z"},
                        "end": {"dateTime": "2026-10-03T20:00:00Z"},
                        "location": "Desk",
                    }
                ]
            },
        )

    async with session_factory() as session:
        await _connected(session)
        events = await _provider(session, _client(handler)).get_events(START, END)
    assert len(events) == 1
    assert events[0].title == "Busy"
    assert events[0].start.tzinfo is not None


@pytest.mark.asyncio
async def test_google_create_uses_hex_key_and_duplicate_is_replayed(session_factory) -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            import json

            body = json.loads(request.content)
            posts.append(body["id"])
            return httpx.Response(200, json={"id": body["id"]})
        return httpx.Response(200, json={"items": []})

    async with session_factory() as session:
        plan = await _plan(session)
        key = make_idempotency_key(str(plan.id), "cand-1", "create_event")
        provider = _provider(session, _client(handler))
        await _connected(session)
        first = await provider.create_event(_draft(plan.id), idempotency_key=key, candidate_id="cand-1")
        second = await provider.create_event(_draft(plan.id), idempotency_key=key, candidate_id="cand-1")
        count = await session.scalar(select(func.count()).select_from(CalendarAction))
        await session.commit()
    assert len(key) == 64
    assert posts == [key]
    assert first.replayed is False
    assert second.replayed is True
    assert count == 1


@pytest.mark.asyncio
async def test_google_create_conflict_is_replayed_without_a_second_event(session_factory) -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posts.append(request.url.path)
            return httpx.Response(409, json={"error": {"code": 409}})
        return httpx.Response(200, json={"items": []})

    async with session_factory() as session:
        plan = await _plan(session)
        key = make_idempotency_key(str(plan.id), "cand-1", "create_event")
        provider = _provider(session, _client(handler))
        await _connected(session)
        first = await provider.create_event(_draft(plan.id), idempotency_key=key, candidate_id="cand-1")
        second = await provider.create_event(_draft(plan.id), idempotency_key=key, candidate_id="cand-1")
        await session.commit()
    assert posts == ["/calendar/v3/calendars/primary/events"]
    assert first.replayed is True
    assert first.calendar_event_id == key
    assert second.replayed is True
    assert second.calendar_event_id == key


@pytest.mark.asyncio
async def test_google_timeout_gets_before_another_insert(session_factory) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls.append("post")
            raise httpx.TimeoutException("timed out")
        if request.method == "GET" and "/events/" in request.url.path:
            calls.append("get")
            event_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "id": event_id,
                    "summary": "Real Workshop",
                    "start": {"dateTime": START.isoformat()},
                    "end": {"dateTime": END.isoformat()},
                },
            )
        return httpx.Response(200, json={"items": []})

    async with session_factory() as session:
        plan = await _plan(session)
        await _connected(session)
        key = make_idempotency_key(str(plan.id), "cand-1", "create_event")
        result = await _provider(session, _client(handler)).create_event(
            _draft(plan.id),
            idempotency_key=key,
            candidate_id="cand-1",
        )
        await session.commit()
    assert calls == ["post", "get"]
    assert result.calendar_event_id == key
    assert result.replayed is False


@pytest.mark.asyncio
async def test_expired_token_is_refreshed(session_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer new-access"
        return httpx.Response(200, json={"items": []})

    async with session_factory() as session:
        await _connected(session, expires_at=NOW - timedelta(minutes=5), access_token="old-access")
        events = await _provider(session, _client(handler)).get_events(START, END)
        await session.commit()
    assert events == []


@pytest.mark.asyncio
async def test_invalid_grant_creates_nothing(session_factory) -> None:
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(400, json={"error": "invalid_grant"})
        posts.append(request.method)
        return httpx.Response(500, json={})

    candidate = Candidate(
        id="cand-1",
        candidate_type="event",
        title="Real Workshop",
        start_datetime=START,
        end_datetime=END,
        source="ticketmaster",
    )
    async with session_factory() as session:
        plan = await _plan(session)
        await _connected(session, expires_at=NOW - timedelta(minutes=5))
        provider = _provider(session, _client(handler))
        with pytest.raises(Exception) as caught:
            await schedule_approved_plan(
                provider,
                approved=True,
                plan_id=str(plan.id),
                candidate=candidate,
                explanation=None,
            )
        count = await session.scalar(select(func.count()).select_from(CalendarAction))
        await session.commit()
    from app.core.exceptions import CalendarNotConnected

    assert isinstance(caught.value, CalendarNotConnected)
    assert posts == []
    assert count == 0


@pytest.mark.asyncio
async def test_overlap_does_not_write_a_calendar_action(session_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise AssertionError("create was called")
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "busy",
                        "summary": "Busy",
                        "start": {"dateTime": START.isoformat()},
                        "end": {"dateTime": END.isoformat()},
                    }
                ]
            },
        )

    candidate = Candidate(
        id="cand-1",
        candidate_type="event",
        title="Real Workshop",
        start_datetime=START,
        end_datetime=END,
        source="ticketmaster",
    )
    async with session_factory() as session:
        plan = await _plan(session)
        await _connected(session)
        with pytest.raises(ScheduleConflictError):
            await schedule_approved_plan(
                _provider(session, _client(handler)),
                approved=True,
                plan_id=str(plan.id),
                candidate=candidate,
                explanation=None,
            )
        count = await session.scalar(select(func.count()).select_from(CalendarAction))
    assert count == 0


def test_missing_client_is_not_configured() -> None:
    with pytest.raises(ProviderNotConfigured):
        from app.services.oauth import require_oauth_client

        require_oauth_client("", "secret", "http://localhost/callback")
