import time
from datetime import date, datetime, timedelta
from datetime import time as clock_time
from zoneinfo import ZoneInfo

import pytest
from app.agents.nodes import EventLog
from app.agents.itinerary.artifacts import (
    CalendarAnalysisResult,
    Itinerary,
    ItineraryConstraints,
    ItineraryItem,
    ResearchCandidate,
    RestaurantResearchArtifact,
    TimeWindowPayload,
)
from app.agents.itinerary.engine import critique, validate_itinerary
from app.agents.itinerary.graph import ItineraryDeps, compile_itinerary_graph
from app.agents.itinerary.permissions import authorize, tools_for
from app.agents.itinerary.reducers import merge_tasks
from app.agents.itinerary.routing import decompose_tasks, is_itinerary_request, parse_itinerary_request
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.exceptions import AppError
from app.domain.candidates import Candidate
from app.domain.preferences import UserPreferences
from app.integrations.events.mock import MockEventProvider
from app.integrations.restaurants.mock import MockRestaurantProvider
from app.services.ranking.heuristic import HeuristicRanker
from langgraph.errors import GraphInterrupt
from tests.conftest import CHICAGO, FROZEN_NOW


class _Calendar:
    async def get_events(self, start, end):
        del start, end
        return []


def _deps(settings: Settings, *, delay: float = 0) -> ItineraryDeps:
    async def load():
        return UserPreferences(max_travel_minutes=30)

    return ItineraryDeps(
        events=MockEventProvider(),
        restaurants=MockRestaurantProvider(),
        calendar=_Calendar(),
        ranker=HeuristicRanker(settings.ranking_weights),
        log=EventLog(),
        clock=FrozenClock(FROZEN_NOW),
        zone=CHICAGO,
        load_preferences=load,
        settings=settings,
        branch_delay_seconds=delay,
    )


def test_merge_tasks_updates_by_id() -> None:
    merged = merge_tasks(
        [{"task_id": "calendar", "status": "pending", "retry_count": 0}],
        [{"task_id": "calendar", "status": "completed", "error": None}],
    )
    assert merged[0]["status"] == "completed"
    assert merged[0]["retry_count"] == 0


def test_single_activity_text_is_not_an_itinerary() -> None:
    text = (
        "Find me something interesting to do Saturday afternoon. "
        "I like tech, food and live music."
    )
    assert is_itinerary_request(text) is False
    assert is_itinerary_request("Find me a Japanese restaurant Friday after work.") is False


def test_dinner_only_routing_skips_events() -> None:
    constraints = ItineraryConstraints(
        timezone="America/Chicago",
        wants_restaurant=True,
        wants_event=False,
        date_start=date(2026, 10, 2),
    )
    ids = [task["task_id"] for task in decompose_tasks(constraints)]
    assert "restaurant" in ids
    assert "events" not in ids
    assert "calendar" in ids


def test_date_night_routing_includes_both_research_tasks() -> None:
    parsed = parse_itinerary_request(
        "Plan a date night this Saturday after dinner. Jazz. Budget is $120. Home before 11 PM.",
        today=date(2026, 10, 2),
        timezone="America/Chicago",
    )
    ids = [task["task_id"] for task in decompose_tasks(parsed)]
    assert {"calendar", "restaurant", "events", "itinerary"} <= set(ids)


def test_execution_is_the_only_writer() -> None:
    assert "google_calendar.create_event" not in tools_for("restaurant_research")
    assert "google_calendar.create_event" not in tools_for("event_research")
    assert "google_calendar.create_event" not in tools_for("calendar_analysis")
    assert tools_for("execution") == ["calendar.delete_event", "google_calendar.create_event"]
    with pytest.raises(AppError):
        authorize("restaurant_research", "google_calendar.create_event")
    authorize("execution", "google_calendar.create_event")


def test_end_time_and_budget_are_deterministic() -> None:
    zone = ZoneInfo("America/Chicago")
    start = datetime(2026, 10, 3, 18, 0, tzinfo=zone)
    constraints = ItineraryConstraints(
        timezone="America/Chicago",
        date_start=date(2026, 10, 3),
        time_start=clock_time(17, 0),
        time_end=clock_time(23, 0),
        budget_max=80,
        budget_amount=80,
    )
    late = Itinerary(
        itinerary_id="late",
        start_datetime=start,
        end_datetime=datetime(2026, 10, 3, 23, 25, tzinfo=zone),
        estimated_total_cost=40,
        items=[
            ItineraryItem(
                item_type="restaurant",
                title="Dinner",
                start_datetime=start,
                end_datetime=start + timedelta(hours=1),
                estimated_cost=40,
                source_candidate_id="rst",
            )
        ],
    )
    result = validate_itinerary(late, constraints=constraints, calendar=None)
    assert any(item.type == "END_TIME_EXCEEDED" for item in result.violations)
    pricey = late.model_copy(
        update={
            "end_datetime": datetime(2026, 10, 3, 21, 0, tzinfo=zone),
            "estimated_total_cost": 140,
        }
    )
    budget = validate_itinerary(pricey, constraints=constraints, calendar=None)
    assert any(item.type == "BUDGET" for item in budget.violations)


def test_calendar_overlap_is_a_hard_violation() -> None:
    zone = ZoneInfo("America/Chicago")
    start = datetime(2026, 10, 3, 18, 0, tzinfo=zone)
    end = datetime(2026, 10, 3, 19, 30, tzinfo=zone)
    constraints = ItineraryConstraints(
        timezone="America/Chicago",
        date_start=date(2026, 10, 3),
        time_start=clock_time(17, 0),
        time_end=clock_time(23, 0),
    )
    plan = Itinerary(
        itinerary_id="overlap",
        start_datetime=start,
        end_datetime=end,
        estimated_total_cost=20,
        items=[
            ItineraryItem(
                item_type="restaurant",
                title="Dinner",
                start_datetime=start,
                end_datetime=end,
                source_candidate_id="rst",
            )
        ],
    )
    calendar = CalendarAnalysisResult(
        calendar_read="ok",
        available_windows=[
            TimeWindowPayload(
                start=datetime(2026, 10, 3, 17, 0, tzinfo=zone),
                end=datetime(2026, 10, 3, 18, 0, tzinfo=zone),
            )
        ],
        existing_events=[
            {
                "id": "busy",
                "title": "Busy",
                "start": datetime(2026, 10, 3, 18, 0, tzinfo=zone).isoformat(),
                "end": datetime(2026, 10, 3, 20, 0, tzinfo=zone).isoformat(),
            }
        ],
    )
    result = validate_itinerary(plan, constraints=constraints, calendar=calendar)
    assert result.valid is False
    assert any(item.type == "CALENDAR_OVERLAP" for item in result.violations)


def test_critic_rejects_a_raw_fish_restaurant() -> None:
    zone = ZoneInfo("America/Chicago")
    start = datetime(2026, 10, 3, 18, 0, tzinfo=zone)
    candidate = Candidate(
        id="rst_sora",
        candidate_type="restaurant",
        title="Sora Handroll",
        description="Hand rolls made to order.",
        categories=["japanese"],
        source="mock",
    )
    plan = Itinerary(
        itinerary_id="raw",
        start_datetime=start,
        end_datetime=start + timedelta(hours=2),
        estimated_total_cost=36,
        items=[
            ItineraryItem(
                item_type="restaurant",
                title="Sora Handroll",
                start_datetime=start,
                end_datetime=start + timedelta(hours=1, minutes=30),
                source_candidate_id="rst_sora",
                estimated_cost=36,
            )
        ],
    )
    research = RestaurantResearchArtifact(
        candidate_restaurants=[
            ResearchCandidate(candidate=candidate, dietary="exclude", score=0.2),
            ResearchCandidate(
                candidate=candidate.model_copy(
                    update={"id": "rst_nori", "title": "Nori Ramen House"}
                ),
                dietary="ok",
                score=0.9,
            ),
        ]
    )
    result = critique(
        plan,
        constraints=ItineraryConstraints(
            timezone="America/Chicago",
            dietary_restrictions=["no raw fish"],
            wants_restaurant=True,
        ),
        restaurants=research,
    )
    assert result.status == "REVISE"
    assert result.issues[0].type == "DIETARY_CONSTRAINT"


@pytest.mark.asyncio
async def test_research_branches_run_in_parallel(settings: Settings) -> None:
    deps = _deps(settings, delay=0.2)
    graph = compile_itinerary_graph(deps)
    started = time.perf_counter()
    config = {"configurable": {"thread_id": "parallel"}, "recursion_limit": 40}
    try:
        await graph.ainvoke(
            {
                "session_id": "parallel",
                "user_id": "user",
                "user_request": (
                    "Plan a date night this Saturday. Free after 5 PM. Budget is $120. "
                    "Japanese food, no raw fish. After dinner, jazz. Home before 11 PM."
                ),
                "approved": False,
                "errors": [],
                "trace_events": [],
                "branch_reports": [],
                "tasks": [],
                "status": "processing",
            },
            config,
        )
    except GraphInterrupt:
        pass
    elapsed = time.perf_counter() - started
    assert elapsed < 0.55
    snapshot = await graph.aget_state(config)
    assert snapshot.values["parallel_speedup"] > 1
    assert deps.counters["calendar_analysis"] == 1
    assert deps.counters["restaurant_research"] == 1
    assert deps.counters["event_research"] == 1
