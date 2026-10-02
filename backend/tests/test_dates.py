from datetime import date, time

import pytest
from app.domain.constraints import ConstraintDraft
from app.services.planning.dates import (
    budget_ceiling,
    finalize_constraints,
    merge_preferences,
    resolve_named_day,
    upcoming_weekend,
)
from pydantic import ValidationError

TODAY = date(2026, 10, 2)  # Friday


def test_resolve_named_day_uses_the_upcoming_weekday() -> None:
    assert resolve_named_day("saturday", TODAY) == date(2026, 10, 3)
    assert resolve_named_day("friday", TODAY) == TODAY


def test_weekend_from_friday_is_saturday_and_sunday() -> None:
    assert upcoming_weekend(TODAY) == (date(2026, 10, 3), date(2026, 10, 4))


def test_around_budget_is_wider_than_a_hard_maximum() -> None:
    assert budget_ceiling(50, "maximum") == 50
    assert budget_ceiling(50, "around") == 60
    assert budget_ceiling(None, "around") is None


def test_finalize_uses_day_hint_instead_of_inventing_a_date() -> None:
    draft = ConstraintDraft(
        plan_type="event",
        day_hint="saturday",
        time_of_day="afternoon",
        categories=["tech", "live music", "food"],
        budget_amount=50,
        budget_kind="maximum",
        max_travel_minutes=20,
    )
    result = finalize_constraints(draft, TODAY)
    assert result.needs_clarification is False
    assert result.date_start == date(2026, 10, 3)
    assert result.date_end == date(2026, 10, 3)
    assert result.time_start == time(12, 0)
    assert result.categories == ["technology", "live_music", "food"]
    assert result.budget_max == 50


def test_missing_day_asks_one_question_and_does_not_invent_a_date() -> None:
    draft = ConstraintDraft(plan_type="event", categories=["food"])
    result = finalize_constraints(draft, TODAY)
    assert result.date_start is None
    assert result.needs_clarification is True
    assert result.clarification_question == "Which day should I plan for?"


def test_negative_budget_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ConstraintDraft(
            plan_type="event", day_hint="saturday", budget_amount=-5, budget_kind="maximum"
        )


def test_merge_fills_only_missing_limits() -> None:
    parsed = finalize_constraints(
        ConstraintDraft(
            plan_type="restaurant", day_hint="friday", time_of_day="after_work", cuisines=["sushi"]
        ),
        TODAY,
    )
    merged = merge_preferences(
        parsed,
        default_budget=50,
        max_travel_minutes=30,
        preferred_time_start=time(12, 0),
        preferred_time_end=time(18, 0),
    )
    assert merged.budget_max == 50
    assert merged.max_travel_minutes == 30
    assert merged.time_start == time(17, 30)
    assert merged.cuisines == ["japanese"]
