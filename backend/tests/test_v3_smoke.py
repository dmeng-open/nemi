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
