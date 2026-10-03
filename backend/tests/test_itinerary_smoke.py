import pytest
from app.core.clock import FrozenClock
from app.services.planning.orchestrator import PlanningOrchestrator
from tests.conftest import FROZEN_NOW

DATE_NIGHT = """Plan a date night this Saturday.

We're free after 5 PM.

Budget is $120 total.

We want Japanese food, but one person doesn't eat raw fish.

After dinner we'd like something relaxed: jazz, comedy, art, or something interesting.

Keep travel reasonable.

We need to be home before 11 PM.
"""


@pytest.mark.asyncio
async def test_date_night_builds_itineraries(
    session_factory, settings, clock
) -> None:
    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(DATE_NIGHT)
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval", plan.error
    assert plan.plan_type == "itinerary"
    assert plan.itineraries
    top = plan.itineraries[0]
    kinds = {item.item_type for item in top.items}
    assert "restaurant" in kinds
    assert "event" in kinds
    assert top.estimated_total_cost <= 120
    assert all(check.status != "fail" for check in top.checks)
    from app.models.calendar import LocalCalendarEvent
    from sqlalchemy import func, select

    await orchestrator.approve(plan_id, True, top.id)
    await orchestrator.approve(plan_id, True, top.id)
    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
        event_count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert plan.status == "scheduled", plan.error
    assert event_count == 2


@pytest.mark.asyncio
async def test_saturday_event_stays_on_the_single_activity_path(session_factory, settings) -> None:
    clock = FrozenClock(FROZEN_NOW)
    from datetime import date

    from app.domain.constraints import ConstraintDraft
    from app.services.planning.dates import finalize_constraints
    from app.services.recommendations.explanations import TemplateExplainer
    from tests.test_workflow import FixedParser

    constraints = finalize_constraints(
        ConstraintDraft(
            plan_type="event",
            day_hint="saturday",
            time_of_day="afternoon",
            categories=["tech"],
            budget_amount=50,
            budget_kind="maximum",
            max_travel_minutes=20,
        ),
        date(2026, 10, 3),
    )
    orchestrator = PlanningOrchestrator(
        session_factory,
        settings,
        parser=FixedParser(constraints),
        explainer=TemplateExplainer(),
        clock=clock,
    )
    plan_id = await orchestrator.create_plan(
        "Find me something interesting to do Saturday afternoon. I like tech, food and live music."
    )
    await orchestrator.run_discovery(plan_id)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.plan_type == "event"
    assert plan.status == "awaiting_selection"


@pytest.mark.asyncio
async def test_revision_limit_stays_approvable(session_factory, settings, clock) -> None:
    settings.max_replan_attempts = 1
    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(DATE_NIGHT)
    await orchestrator.run_discovery(plan_id)
    await orchestrator.revise(plan_id, "Make this cheaper")
    await orchestrator.revise(plan_id, "Make this cheaper")
    from app.models.calendar import LocalCalendarEvent
    from app.services.planning.present import build_plan_response
    from sqlalchemy import func, select

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval", plan.error
    assert plan.itineraries
    await orchestrator.approve(plan_id, True, "not-a-real-itinerary")
    async with session_factory() as session:
        stalled = await build_plan_response(session, plan_id)
        written = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert stalled.status == "awaiting_approval"
    assert written == 0
    await orchestrator.approve(plan_id, True, plan.itineraries[0].id)
    async with session_factory() as session:
        finished = await build_plan_response(session, plan_id)
    assert finished.status == "scheduled", finished.error


@pytest.mark.asyncio
async def test_finish_earlier_does_not_rerun_both_branches(
    session_factory, settings, clock
) -> None:
    from app.models.multi_agent import AgentSpan, AgentTaskRow
    from app.services.planning.present import build_plan_response
    from sqlalchemy import func, select

    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(DATE_NIGHT)
    await orchestrator.run_discovery(plan_id)

    async def _count(agent: str) -> int:
        async with session_factory() as session:
            return await session.scalar(
                select(func.count())
                .select_from(AgentSpan)
                .where(AgentSpan.session_id == plan_id, AgentSpan.agent_name == agent)
            )

    restaurants = await _count("restaurant_research")
    events = await _count("event_research")
    await orchestrator.revise(plan_id, "Finish earlier")
    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
        tasks = list(
            await session.scalars(select(AgentTaskRow).where(AgentTaskRow.session_id == plan_id))
        )
    assert plan.status == "awaiting_approval", plan.error
    assert plan.itineraries
    status = {row.task_key: row.status for row in tasks}
    assert status.get("calendar") == "completed"
    both_pending = status.get("restaurant") == "pending" and status.get("events") == "pending"
    assert not both_pending
    reran_restaurants = await _count("restaurant_research") > restaurants
    reran_events = await _count("event_research") > events
    assert not (reran_restaurants and reran_events)


@pytest.mark.asyncio
async def test_no_key_spans_stay_deterministic(session_factory, settings, clock) -> None:
    from app.models.multi_agent import AgentSpan
    from sqlalchemy import select

    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(DATE_NIGHT)
    await orchestrator.run_discovery(plan_id)
    async with session_factory() as session:
        spans = list(
            await session.scalars(select(AgentSpan).where(AgentSpan.session_id == plan_id))
        )
    assert spans
    supervisor = next(span for span in spans if span.agent_name == "supervisor")
    assert supervisor.model == "deterministic"
    assert supervisor.prompt_version == "supervisor_policy_v1"
    assert supervisor.input_tokens == 0
    assert supervisor.output_tokens == 0
    for span in spans:
        assert span.model == "deterministic"
        assert span.input_tokens == 0
        assert span.output_tokens == 0
        assert span.prompt_version != "supervisor_v1"
        flags = span.safe_metadata or {}
        assert "tokens_unreported" not in flags
        assert "cost_unpriced" not in flags


@pytest.mark.asyncio
async def test_empty_replan_keeps_previous_itinerary_rows(session_factory, settings, clock) -> None:
    from app.agents.itinerary.persist import _replace_itineraries
    from app.models.multi_agent import ItineraryRecord
    from sqlalchemy import select

    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(DATE_NIGHT)
    await orchestrator.run_discovery(plan_id)
    async with session_factory() as session:
        before = list(
            await session.scalars(
                select(ItineraryRecord).where(ItineraryRecord.session_id == plan_id)
            )
        )
        keys = [row.itinerary_key for row in before]
        assert keys
        await _replace_itineraries(session, plan_id, [], None)
        await session.commit()
        after = list(
            await session.scalars(
                select(ItineraryRecord).where(ItineraryRecord.session_id == plan_id)
            )
        )
    assert [row.itinerary_key for row in after] == keys
