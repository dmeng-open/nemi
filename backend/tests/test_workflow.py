from datetime import date

import pytest
from app.agents.graph import compile_planning_graph
from app.agents.nodes import PlanningDeps, make_nodes
from app.core.exceptions import ApprovalRequired
from app.domain.calendar import CalendarExecutionResult
from app.domain.constraints import ConstraintDraft, PlanningConstraints
from app.integrations.events.mock import MockEventProvider
from app.integrations.restaurants.mock import MockRestaurantProvider
from app.models.calendar import LocalCalendarEvent
from app.repositories.calendar import CalendarRepository
from app.services.calendar.scheduling import schedule_approved_plan
from app.services.planning.dates import finalize_constraints
from app.services.planning.orchestrator import PlanningOrchestrator
from app.services.ranking.heuristic import HeuristicRanker
from app.services.recommendations.explanations import TemplateExplainer
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import func, select
from tests.conftest import CHICAGO, FROZEN_NOW


class _EmptyCalendar:
    async def get_events(self, start, end):
        del start, end
        return []


class FixedParser:
    def __init__(self, constraints: PlanningConstraints) -> None:
        self.constraints = constraints

    async def parse(self, text: str, *, now, zone) -> PlanningConstraints:
        del text, now, zone
        return self.constraints


def saturday_event() -> PlanningConstraints:
    return finalize_constraints(
        ConstraintDraft(
            plan_type="event",
            day_hint="saturday",
            time_of_day="afternoon",
            categories=["tech", "food", "live music"],
            budget_amount=50,
            budget_kind="maximum",
            max_travel_minutes=20,
        ),
        date(2026, 10, 3),
    )


def friday_dinner() -> PlanningConstraints:
    return finalize_constraints(
        ConstraintDraft(
            plan_type="restaurant",
            day_hint="friday",
            time_of_day="after_work",
            cuisines=["japanese"],
            budget_amount=50,
            budget_kind="around",
            max_travel_minutes=30,
        ),
        date(2026, 10, 2),
    )


@pytest.mark.asyncio
async def test_event_discovery_ranks_filters_and_does_not_write(
    session_factory, settings, clock
) -> None:
    async with session_factory() as session:
        repo = CalendarRepository(session)
        await repo.create_user_event(
            user_id=__import__("app.models.user", fromlist=["LOCAL_USER_ID"]).LOCAL_USER_ID,
            title="Gym",
            start=FROZEN_NOW.replace(day=3, hour=10, minute=0),
            end=FROZEN_NOW.replace(day=3, hour=11, minute=0),
        )
        await repo.create_user_event(
            user_id=__import__("app.models.user", fromlist=["LOCAL_USER_ID"]).LOCAL_USER_ID,
            title="Dinner with friends",
            start=FROZEN_NOW.replace(day=3, hour=18, minute=0),
            end=FROZEN_NOW.replace(day=3, hour=20, minute=0),
        )
        await session.commit()

    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan(
        "Find me something interesting to do Saturday afternoon under $50 within 20 minutes."
    )
    await orchestrator.run_discovery(plan_id)

    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
        event_count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert plan.status == "awaiting_selection"
    assert len(plan.recommendations) == 3
    titles = {item.title for item in plan.recommendations}
    assert "AI Builders Workshop" in titles
    assert "Startup Founder Meetup" not in titles
    assert "Live Comedy Show" not in titles
    assert all(
        item.travel_minutes is not None and item.travel_minutes <= 20
        for item in plan.recommendations
    )
    assert all(item.price_min is not None and item.price_min <= 50 for item in plan.recommendations)
    assert all(item.explanation for item in plan.recommendations)
    assert any(item.label.startswith("Found") for item in plan.timeline)
    assert event_count == 2


@pytest.mark.asyncio
async def test_restaurant_discovery_prefers_nearby_japanese(
    session_factory, settings, clock
) -> None:
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(friday_dinner()),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Find me a Japanese restaurant Friday after work.")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_selection"
    assert plan.plan_type == "restaurant"
    assert len(plan.recommendations) == 3
    assert all("japanese" in item.categories for item in plan.recommendations)
    assert all(
        item.travel_minutes is not None and item.travel_minutes <= 30
        for item in plan.recommendations
    )
    assert all(item.start is not None and item.end is not None for item in plan.recommendations)


@pytest.mark.asyncio
async def test_double_approval_creates_one_event(session_factory, settings, clock) -> None:
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Saturday afternoon workshop")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    chosen = next(item for item in plan.recommendations if item.title == "AI Builders Workshop")
    await orchestrator.select(plan_id, chosen.id)
    await orchestrator.approve(plan_id, True)
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
    assert again.execution is not None
    assert again.execution.title == "AI Builders Workshop"


@pytest.mark.asyncio
async def test_calendar_write_requires_approval(session_factory) -> None:
    from app.domain.candidates import Candidate
    from app.integrations.calendar.local import LocalCalendarProvider
    from app.models.user import LOCAL_USER_ID

    candidate = Candidate(
        id="evt_test",
        candidate_type="event",
        title="Test",
        start_datetime=FROZEN_NOW,
        end_datetime=FROZEN_NOW.replace(hour=16),
        source="test",
    )
    async with session_factory() as session:
        provider = LocalCalendarProvider(CalendarRepository(session), LOCAL_USER_ID)
        with pytest.raises(ApprovalRequired):
            await schedule_approved_plan(
                provider,
                approved=False,
                plan_id=str(__import__("uuid").uuid4()),
                candidate=candidate,
                explanation=None,
            )


@pytest.mark.asyncio
async def test_no_candidates_sets_a_clear_status(session_factory, settings, clock) -> None:
    impossible = finalize_constraints(
        ConstraintDraft(
            plan_type="event",
            day_hint="saturday",
            time_of_day="afternoon",
            budget_amount=1,
            budget_kind="maximum",
            max_travel_minutes=1,
        ),
        date(2026, 10, 3),
    )
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(impossible),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan("Something impossible")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "no_matches"
    assert plan.error is not None
    assert plan.error.code == "no_events"
    assert plan.recommendations == []


@pytest.mark.asyncio
async def test_provider_failure_is_stored(session_factory, settings, clock) -> None:
    from app.core.exceptions import ProviderError

    class Down:
        async def search_events(self, query):
            del query
            raise ProviderError("search down", retryable=False)

        async def search_restaurants(self, query):
            del query
            raise ProviderError("search down", retryable=False)

    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(saturday_event()),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    original = orchestrator._deps

    async def broken_deps(session, run):
        deps = await original(session, run)
        deps.events = Down()
        return deps

    orchestrator._deps = broken_deps
    plan_id = await orchestrator.create_plan("Saturday")
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "failed"
    assert plan.error is not None
    assert plan.error.code == "provider_failed"


@pytest.mark.asyncio
async def test_full_graph_waits_for_selection_and_approval() -> None:
    created: list[bool] = []

    async def schedule(state: dict):
        if not state.get("approved"):
            raise ApprovalRequired()
        created.append(True)
        return CalendarExecutionResult(
            calendar_event_id="evt",
            title="AI Builders Workshop",
            start=FROZEN_NOW,
            end=FROZEN_NOW.replace(hour=16),
            replayed=False,
        )

    class Log:
        async def emit(self, *args, **kwargs):
            del args, kwargs

    async def load_preferences():
        from app.domain.preferences import UserPreferences

        return UserPreferences(
            preferred_event_categories=["technology"],
            default_budget=50,
            max_travel_minutes=30,
            preferred_time_ranges=[],
        )

    deps = PlanningDeps(
        parser=FixedParser(saturday_event()),
        explainer=TemplateExplainer(),
        events=MockEventProvider(),
        restaurants=MockRestaurantProvider(),
        calendar=_EmptyCalendar(),
        ranker=HeuristicRanker(
            __import__("app.domain.ranking", fromlist=["RankingWeights"]).RankingWeights()
        ),
        log=Log(),
        clock=__import__("app.core.clock", fromlist=["FrozenClock"]).FrozenClock(FROZEN_NOW),
        zone=CHICAGO,
        load_preferences=load_preferences,
        schedule=schedule,
    )
    graph = compile_planning_graph(make_nodes(deps), MemorySaver())
    config = {"configurable": {"thread_id": "graph-test"}}
    state = await graph.ainvoke(
        {
            "session_id": "graph-test",
            "user_id": "user",
            "user_request": "Saturday afternoon",
            "approved": False,
            "errors": [],
            "status": "processing",
        },
        config,
    )
    assert created == []
    assert state["status"] == "awaiting_selection"
    shown = [item for item in state["ranked_candidates"] if item["shown"]]
    chosen = shown[0]["candidate"]["id"]
    state = await graph.ainvoke(Command(resume=chosen), config)
    assert created == []
    state = await graph.ainvoke(Command(resume=True), config)
    assert created == [True]
    assert state["status"] == "scheduled"


@pytest.mark.asyncio
async def test_parser_retries_invalid_output(monkeypatch) -> None:
    from app.agents.llm import OpenAIConstraintParser
    from app.core.exceptions import LLMValidationError

    class Gateway:
        def __init__(self) -> None:
            self.calls = 0

        async def parse(self, *, system, user, schema):
            del system, user
            self.calls += 1
            if self.calls < 3:
                raise LLMValidationError("bad")
            return schema(
                plan_type="event",
                day_hint="saturday",
                time_of_day="afternoon",
                categories=["tech"],
                budget_amount=20,
                budget_kind="maximum",
            )

    gateway = Gateway()
    parser = OpenAIConstraintParser(gateway)  # type: ignore[arg-type]
    result = await parser.parse("Saturday", now=FROZEN_NOW, zone=CHICAGO)
    assert gateway.calls == 3
    assert result.date_start == date(2026, 10, 3)
    assert result.categories == ["technology"]


@pytest.mark.asyncio
async def test_retry_stops_for_a_non_retryable_provider() -> None:
    from app.core.exceptions import ProviderError
    from app.providers.retry import call_with_retries

    async def boom():
        raise ProviderError("nope", retryable=False)

    with pytest.raises(ProviderError):
        await call_with_retries(boom)
