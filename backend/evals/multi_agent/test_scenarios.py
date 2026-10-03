"""Multi-agent scenarios. They use the mock catalogs and a fixed clock."""

from datetime import date

import pytest
from app.agents.v3.artifacts import (
    EventResearchArtifact,
    ItineraryConstraints,
    RestaurantResearchArtifact,
)
from app.agents.v3.engine import build_itineraries
from app.models.calendar import LocalCalendarEvent
from app.models.multi_agent import AgentSpan
from app.services.planning.orchestrator import PlanningOrchestrator
from sqlalchemy import func, select
from tests.test_v3_smoke import DATE_NIGHT


async def _run(session_factory, settings, clock, text: str, injection: str = ""):
    settings.failure_injection = injection
    orchestrator = PlanningOrchestrator(session_factory, settings, clock=clock)
    plan_id = await orchestrator.create_plan(text)
    await orchestrator.run_discovery(plan_id)
    return orchestrator, plan_id


async def _spans(session_factory, plan_id, agent: str) -> int:
    async with session_factory() as session:
        return await session.scalar(
            select(func.count())
            .select_from(AgentSpan)
            .where(AgentSpan.session_id == plan_id, AgentSpan.agent_name == agent)
        )


async def test_valid_dinner_and_event(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval"
    assert plan.itineraries
    assert {item.item_type for item in plan.itineraries[0].items} >= {"restaurant", "event"}


async def test_event_provider_timeout_keeps_dinner(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "EVENT_PROVIDER_TIMEOUT")
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval"
    kinds = {item.item_type for item in plan.itineraries[0].items}
    assert "restaurant" in kinds
    assert "event" not in kinds
    assert await _spans(session_factory, plan_id, "calendar_analysis") == 1


async def test_restaurant_provider_failure_does_not_abort_the_run(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "RESTAURANT_PROVIDER_FAILURE")
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status in {"awaiting_approval", "no_matches"}
    assert await _spans(session_factory, plan_id, "event_research") == 1


async def test_calendar_read_failure_is_explicit(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "CALENDAR_READ_FAILURE")
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval"
    calendar = next(agent for agent in plan.agents if agent.agent == "calendar_analysis")
    assert "could not" in (calendar.detail or "").lower()


async def test_critic_reject_reruns_restaurants_only(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "CRITIC_REJECT")
    assert await _spans(session_factory, plan_id, "calendar_analysis") == 1
    assert await _spans(session_factory, plan_id, "restaurant_research") >= 2


async def test_revision_replaces_the_restaurant_only(session_factory, settings, clock) -> None:
    orchestrator, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    before = await _spans(session_factory, plan_id, "restaurant_research")
    await orchestrator.revise(plan_id, "I don't like the restaurant.")
    assert await _spans(session_factory, plan_id, "calendar_analysis") == 1
    assert await _spans(session_factory, plan_id, "restaurant_research") > before


async def test_revision_can_target_only_the_event(session_factory, settings, clock) -> None:
    orchestrator, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    restaurants = await _spans(session_factory, plan_id, "restaurant_research")
    await orchestrator.revise(plan_id, "Replace the activity with something quieter.")
    assert await _spans(session_factory, plan_id, "restaurant_research") == restaurants
    assert await _spans(session_factory, plan_id, "event_research") >= 2
    assert await _spans(session_factory, plan_id, "calendar_analysis") == 1


async def test_double_approval_writes_two_events_once(session_factory, settings, clock) -> None:
    orchestrator, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    await orchestrator.approve(plan_id, True, plan.itineraries[0].id)
    await orchestrator.approve(plan_id, True, plan.itineraries[0].id)
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert count == 2


async def test_partial_calendar_write_can_retry(session_factory, settings, clock) -> None:
    orchestrator, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    from app.services.planning.present import build_plan_response

    settings.failure_injection = "CALENDAR_WRITE_FAILURE"
    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    await orchestrator.approve(plan_id, True, plan.itineraries[0].id)
    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
        count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert plan.status == "partial_success"
    assert count == 1
    settings.failure_injection = ""
    from app.agents.v3.compensation import apply_execution_command
    from app.services.planning.present import get_plan_or_404

    async with session_factory() as session:
        stored = await get_plan_or_404(session, plan_id)
        await apply_execution_command(session, settings, stored, action="retry", confirm=False)
        await session.commit()
        count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
        refreshed = await build_plan_response(session, plan_id)
    assert count == 2
    assert refreshed.status == "scheduled"


async def test_cancel_created_events_requires_confirmation(session_factory, settings, clock) -> None:
    orchestrator, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT)
    from app.agents.v3.compensation import apply_execution_command
    from app.core.exceptions import PlanStateError
    from app.services.planning.present import build_plan_response, get_plan_or_404

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    await orchestrator.approve(plan_id, True, plan.itineraries[0].id)
    async with session_factory() as session:
        stored = await get_plan_or_404(session, plan_id)
        with pytest.raises(PlanStateError):
            await apply_execution_command(
                session, settings, stored, action="cancel_created", confirm=False
            )
        await session.rollback()
        stored = await get_plan_or_404(session, plan_id)
        await apply_execution_command(
            session, settings, stored, action="cancel_created", confirm=True
        )
        await session.commit()
        count = await session.scalar(select(func.count()).select_from(LocalCalendarEvent))
    assert count == 0


def test_empty_restaurant_research_can_still_plan_an_event() -> None:
    constraints = ItineraryConstraints(
        timezone="America/Chicago",
        date_start=date(2026, 10, 3),
        wants_restaurant=False,
        wants_event=True,
        budget_max=50,
    )
    plans = build_itineraries(
        constraints=constraints,
        calendar=None,
        restaurants=RestaurantResearchArtifact(),
        events=EventResearchArtifact(),
        rejected_ids=set(),
    )
    assert plans == []


async def test_supervisor_retry_recovers_the_event_branch(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "SUPERVISOR_RETRY")
    from app.services.planning.present import build_plan_response

    async with session_factory() as session:
        plan = await build_plan_response(session, plan_id)
    assert plan.status == "awaiting_approval"
    assert any(item.item_type == "event" for item in plan.itineraries[0].items)
    assert await _spans(session_factory, plan_id, "event_research") >= 2


async def test_planner_invalid_output_retries(session_factory, settings, clock) -> None:
    _, plan_id = await _run(session_factory, settings, clock, DATE_NIGHT, "PLANNER_INVALID_OUTPUT")
    async with session_factory() as session:
        span = await session.scalar(
            select(AgentSpan).where(
                AgentSpan.session_id == plan_id,
                AgentSpan.agent_name == "itinerary_planner",
            )
        )
    assert span is not None
    assert span.retry_count >= 1
