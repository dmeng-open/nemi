import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.domain.candidates import Candidate
from app.domain.ranking import RankedCandidate, RankingContext, ScoreComponents
from app.integrations.events.models import EventCandidate
from app.main import create_app
from app.models.agent import AgentRun, AgentRunEvent, InteractionEvent
from app.models.calendar import LocalCalendarEvent
from app.models.planning import PlanningSession, Recommendation, RecommendationCandidate
from app.models.user import LOCAL_USER_ID
from app.providers.factory import (
    build_calendar_provider,
    build_event_provider,
    build_restaurant_provider,
)
from app.providers.health import InMemoryProviderHealth
from app.repositories.users import get_preference_row
from app.services.integrations_status import build_integrations_response
from app.services.planning.orchestrator import PlanningOrchestrator
from app.services.recommendations.explanations import merge_explanations, template_explanation
from sqlalchemy import func, select
from tests.conftest import FROZEN_NOW
from tests.test_workflow import FixedParser, friday_dinner, saturday_event


def _ranked(text_candidate: Candidate) -> RankedCandidate:
    return RankedCandidate(
        candidate=text_candidate,
        final_score=0.8,
        components=ScoreComponents(
            preference=0.8, schedule=0.5, distance=0.8, price=0.8, quality=0.8
        ),
        schedule_compatible=True,
        shown=True,
        rank_position=1,
    )


@pytest.mark.asyncio
async def test_real_candidate_ranks_selects_and_approves_on_the_local_calendar(
    session_factory, settings, clock
) -> None:
    class OneEvent:
        async def search_events(self, query):
            zone = ZoneInfo(query.timezone)
            start = datetime(2026, 10, 3, 14, 0, tzinfo=zone)
            return [
                EventCandidate(
                    id="tm_real",
                    title="Real Workshop",
                    description="A real listing.",
                    categories=["technology"],
                    start=start,
                    end=start.replace(hour=16),
                    venue="Hall",
                    address="1 Main St",
                    latitude=41.9,
                    longitude=-87.65,
                    distance_km=2.0,
                    travel_minutes=8,
                    price=None,
                    rating=None,
                    url="https://example.com/real",
                    source="ticketmaster",
                    provider="ticketmaster",
                    external_id="tm_real",
                    travel_time_is_estimate=True,
                )
            ]

    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    original = orchestrator._deps

    async def deps(session, run):
        built = await original(session, run)
        built.events = OneEvent()
        return built

    orchestrator._deps = deps
    plan_id = await orchestrator.create_plan("Saturday workshop")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_selection"
    assert plan.recommendations[0].title == "Real Workshop"
    await orchestrator.select(plan_id, "tm_real")
    await orchestrator.approve(plan_id, True)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(LocalCalendarEvent)
            .where(LocalCalendarEvent.planning_session_id == plan_id)
        )
        again = await build_plan_response(session, plan_id)
    assert count == 1
    assert again.status == "scheduled"


@pytest.mark.asyncio
async def test_interaction_rows_are_stable_across_discovery(session_factory, settings, clock) -> None:
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Saturday afternoon")
    await orchestrator.run_discovery(plan_id)
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        generations = await session.scalar(
            select(func.count()).select_from(Recommendation).where(Recommendation.session_id == plan_id)
        )
        plan = await build_plan_response(session, plan_id)
    assert generations == 2
    assert len(plan.recommendations) == 3
    chosen = plan.recommendations[0]
    other = plan.recommendations[1]
    await orchestrator.reject(plan_id, other.id)
    await orchestrator.reject(plan_id, other.id)
    await orchestrator.select(plan_id, chosen.id)
    await orchestrator.approve(plan_id, True)

    async with session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(InteractionEvent).where(InteractionEvent.session_id == plan_id)
                )
            ).all()
        )
        rejected = await session.scalar(
            select(RecommendationCandidate).where(
                RecommendationCandidate.session_id == plan_id,
                RecommendationCandidate.candidate_id == other.id,
                RecommendationCandidate.rejected.is_(True),
            )
        )
        other_rejected = await session.scalar(
            select(func.count())
            .select_from(RecommendationCandidate)
            .where(
                RecommendationCandidate.session_id == plan_id,
                RecommendationCandidate.candidate_id != other.id,
                RecommendationCandidate.rejected.is_(True),
            )
        )
    topics = [event.topic for event in events]
    assert topics.count("recommendation.shown") == 6
    assert topics.count("recommendation.selected") == 1
    assert topics.count("recommendation.rejected") == 1
    assert topics.count("plan.scheduled") == 1
    assert "plan.approved" not in topics
    assert rejected is not None
    assert other_rejected == 0
    for event in events:
        if event.topic == "recommendation.shown":
            assert "recommendation_candidate_id" in event.properties
            assert "score" not in event.properties
            assert "final_score" not in event.properties
            assert "components" not in event.properties


@pytest.mark.asyncio
async def test_preference_timezone_overrides_the_app_timezone(session_factory, settings, clock) -> None:
    async with session_factory() as session:
        row = await get_preference_row(session, LOCAL_USER_ID)
        row.timezone = "America/New_York"
        await session.commit()
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Saturday afternoon")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    workshop = next(item for item in plan.recommendations if item.title == "AI Builders Workshop")
    assert workshop.start is not None
    assert workshop.start.astimezone(UTC).hour == 18


def test_naive_calendar_input_is_rejected(settings) -> None:
    from fastapi.testclient import TestClient

    app = create_app(settings)
    with TestClient(app) as client:
        created = client.post(
            "/api/calendar/events",
            json={
                "title": "Gym",
                "start": "2026-10-03T10:00:00",
                "end": "2026-10-03T11:00:00",
            },
        )
        window = client.get(
            "/api/calendar/window",
            params={"start": "2026-10-03T10:00:00", "end": "2026-10-03T11:00:00"},
        )
    assert created.status_code == 422
    assert window.status_code == 422


@pytest.mark.asyncio
async def test_ticketmaster_without_a_city_pauses_and_continue_reuses_the_plan(
    session_factory, clock, tmp_path
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'gate.db'}",
        openai_api_key="",
        auto_create_schema=True,
        event_provider="ticketmaster",
        ticketmaster_api_key="present",
        place_provider="mock",
        calendar_provider="local",
    )
    from app.db.base import Base
    from app.db.session import create_engine, create_session_factory
    from app.repositories.users import ensure_local_user

    engine = create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session:
        await ensure_local_user(session)
        await session.commit()

    calls = {"n": 0}

    class Counting:
        async def search_events(self, query):
            del query
            calls["n"] += 1
            return []

    orchestrator = PlanningOrchestrator(
        factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    original = orchestrator._deps

    async def deps(session, run):
        built = await original(session, run)
        built.events = Counting()
        built.event_provider_name = "ticketmaster"
        return built

    orchestrator._deps = deps
    plan_id = await orchestrator.create_plan("Saturday")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with factory() as session:
        paused = await build_plan_response(session, plan_id)
    assert paused.status == "awaiting_location"
    assert paused.error is not None
    assert paused.error.code == "city_required"
    assert calls["n"] == 0

    async with factory() as session:
        row = await get_preference_row(session, LOCAL_USER_ID)
        row.home_city = "Chicago"
        await session.commit()
    await orchestrator.continue_plan(plan_id)
    await orchestrator.run_discovery(plan_id)
    async with factory() as session:
        resumed = await build_plan_response(session, plan_id)
    assert resumed.plan_id == str(plan_id)
    assert resumed.status != "awaiting_location"
    assert calls["n"] == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_places_without_coordinates_pauses_and_mock_does_not(session_factory, settings, clock) -> None:
    class CountingPlaces:
        async def search_restaurants(self, query):
            del query
            raise AssertionError("places was called")

    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(friday_dinner()),
        clock=clock,
    )
    original = orchestrator._deps

    async def deps(session, run):
        built = await original(session, run)
        built.restaurants = CountingPlaces()
        built.place_provider_name = "google"
        return built

    orchestrator._deps = deps
    plan_id = await orchestrator.create_plan("Friday dinner")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_location"
    assert plan.error is not None
    assert plan.error.code == "location_required"

    mock = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    mock_id = await mock.create_plan("Saturday")
    await mock.run_discovery(mock_id)
    async with session_factory() as session:
        ready = await build_plan_response(session, mock_id)
    assert ready.status == "awaiting_selection"


@pytest.mark.asyncio
async def test_calendar_read_failure_keeps_candidates_and_does_not_claim_a_free_slot(
    session_factory, settings, clock
) -> None:
    class DownCalendar:
        async def get_events(self, start, end):
            del start, end
            raise ProviderError("calendar down", retryable=False, code="provider_unavailable")

        async def create_event(self, draft, *, idempotency_key, candidate_id):
            del draft, idempotency_key, candidate_id
            raise AssertionError("create should not run")

    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    original = orchestrator._deps

    async def deps(session, run):
        built = await original(session, run)
        built.calendar = DownCalendar()
        return built

    orchestrator._deps = deps
    plan_id = await orchestrator.create_plan("Saturday")
    await orchestrator.run_discovery(plan_id)
    async with session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(RecommendationCandidate).where(
                        RecommendationCandidate.session_id == plan_id,
                        RecommendationCandidate.shown.is_(True),
                    )
                )
            ).all()
        )
    assert rows
    assert all(row.exclusion_reason != "outside_window" for row in rows)
    assert all(row.schedule_score == pytest.approx(0.5) for row in rows)
    assert all(row.explanation and "open time" not in row.explanation.lower() for row in rows)
    assert all("free slot" not in (row.explanation or "").lower() for row in rows)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        shown = await build_plan_response(session, plan_id)
    labels = [item.label for item in shown.timeline]
    assert "Calendar could not be checked" in labels
    assert "Checked for schedule conflicts" not in labels
    assert "Schedule conflicts were not checked" in labels


def test_explanation_replaces_ungrounded_price_and_venue() -> None:
    candidate = Candidate(
        id="kept",
        candidate_type="event",
        title="Kept",
        venue="Catalyst Hall",
        address="1840 N Halsted St",
        categories=["technology"],
        estimated_travel_minutes=12,
        rating=4.8,
        price_min=40,
        source="ticketmaster",
        calendar_checked=True,
    )
    item = _ranked(candidate)
    fallback = {"kept": "Fallback reason."}
    priced = merge_explanations([item], {"kept": "This costs $40."}, fallback)
    invented = merge_explanations([item], {"kept": "Meet at The Hidden Room tonight."}, fallback)
    assert priced["kept"] == "Fallback reason."
    assert invented["kept"] == "Fallback reason."
    context = RankingContext(calendar_read="unavailable")
    text = template_explanation(item.model_copy(update={"schedule_compatible": True}), context)
    assert "open time" not in text
    assert "free" not in text.lower()


def test_integrations_with_a_key_and_no_call_is_configured() -> None:
    settings = Settings(
        _env_file=None,
        event_provider="ticketmaster",
        ticketmaster_api_key="present-key",
        place_provider="mock",
        calendar_provider="local",
        app_timezone="America/Chicago",
    )
    payload = build_integrations_response(settings, InMemoryProviderHealth(), None)
    assert payload.event_provider.connection == "configured"
    assert payload.event_provider.status == "ready"
    assert payload.demo_mode is False


@pytest.mark.asyncio
async def test_integrations_route_does_not_call_upstream(settings, monkeypatch) -> None:
    created: list[int] = []

    class Guard:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            created.append(1)
            raise AssertionError("httpx client constructed")

    monkeypatch.setattr("app.api.routes.integrations.httpx.AsyncClient", Guard)
    app = create_app(
        Settings(
            _env_file=None,
            database_url=settings.database_url,
            openai_api_key="",
            auto_create_schema=True,
            event_provider="ticketmaster",
            ticketmaster_api_key="present-key",
            place_provider="mock",
            calendar_provider="local",
            app_timezone="America/Chicago",
        )
    )
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/api/integrations")
    assert response.status_code == 200
    body = response.json()
    assert body["event_provider"]["connection"] == "configured"
    assert created == []


def test_mock_providers_do_not_construct_httpx(monkeypatch, settings) -> None:
    created: list[int] = []

    class Guard:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            created.append(1)

    monkeypatch.setattr(httpx, "AsyncClient", Guard)
    assert settings.event_provider == "mock"
    build_event_provider(settings)
    build_restaurant_provider(settings)
    assert created == []


@pytest.mark.asyncio
async def test_mock_discovery_does_not_construct_httpx(session_factory, settings, clock, monkeypatch) -> None:
    created: list[int] = []

    class Guard:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            created.append(1)

    monkeypatch.setattr(httpx, "AsyncClient", Guard)
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Saturday")
    await orchestrator.run_discovery(plan_id)
    async with session_factory() as session:
        build_event_provider(settings)
        build_restaurant_provider(settings)
        build_calendar_provider(settings, session)
    assert created == []


@pytest.mark.asyncio
async def test_interactions_list_excludes_agent_events(session_factory, settings) -> None:
    async with session_factory() as session:
        plan = PlanningSession(user_id=LOCAL_USER_ID, user_request="Saturday", status="awaiting_selection")
        session.add(plan)
        await session.flush()
        run = AgentRun(session_id=plan.id, user_id=LOCAL_USER_ID, status="completed")
        session.add(run)
        await session.flush()
        session.add(
            AgentRunEvent(
                agent_run_id=run.id,
                session_id=plan.id,
                event_type="search_completed",
                status="completed",
                safe_metadata={},
            )
        )
        session.add(
            InteractionEvent(
                user_id=LOCAL_USER_ID,
                session_id=plan.id,
                candidate_id="evt_1",
                event_name="recommendation_shown",
                topic="recommendation.shown",
                properties={"recommendation_candidate_id": str(uuid.uuid4()), "provider": "mock"},
            )
        )
        await session.commit()
    app = create_app(settings)
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/api/interactions")
    assert response.status_code == 200
    topics = [item["topic"] for item in response.json()["items"]]
    assert "recommendation.shown" in topics
    assert "search_completed" not in topics


@pytest.mark.asyncio
async def test_replayed_confirmation_writes_plan_scheduled_once(
    session_factory, settings, clock, monkeypatch
) -> None:
    from app.domain.calendar import CalendarExecutionResult
    from app.services.planning import orchestrator as orchestrator_module

    async def replayed(*args, **kwargs):
        del args, kwargs
        return CalendarExecutionResult(
            calendar_event_id="evt-replayed",
            title="AI Builders Workshop",
            start=FROZEN_NOW,
            end=FROZEN_NOW,
            replayed=True,
        )

    monkeypatch.setattr(orchestrator_module, "schedule_approved_plan", replayed)
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Saturday afternoon")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    chosen = plan.recommendations[0]
    await orchestrator.select(plan_id, chosen.id)
    await orchestrator.approve(plan_id, True)

    async with session_factory() as session:
        stored = await session.get(PlanningSession, plan_id)
        assert stored is not None
        stored.status = "awaiting_approval"
        count = await session.scalar(
            select(func.count())
            .select_from(InteractionEvent)
            .where(
                InteractionEvent.session_id == plan_id,
                InteractionEvent.candidate_id == chosen.id,
                InteractionEvent.event_name == "plan_scheduled",
            )
        )
        await session.commit()
    assert count == 1

    await orchestrator.approve(plan_id, True)
    async with session_factory() as session:
        again = await session.scalar(
            select(func.count())
            .select_from(InteractionEvent)
            .where(
                InteractionEvent.session_id == plan_id,
                InteractionEvent.candidate_id == chosen.id,
                InteractionEvent.event_name == "plan_scheduled",
            )
        )
    assert again == 1
