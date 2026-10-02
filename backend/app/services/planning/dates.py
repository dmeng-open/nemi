from datetime import date, time, timedelta

from app.domain.constraints import ConstraintDraft, PlanningConstraints
from app.services.planning.taxonomy import normalize_list

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

TIME_WINDOWS: dict[str, tuple[time, time]] = {
    "morning": (time(8, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(18, 0)),
    "evening": (time(17, 0), time(21, 30)),
    "after_work": (time(17, 30), time(21, 0)),
    "night": (time(20, 0), time(23, 0)),
}

AROUND_BUDGET_FACTOR = 1.2
MAX_RANGE_DAYS = 31


def resolve_named_day(name: str, today: date) -> date:
    target = WEEKDAYS[name]
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta)


def upcoming_weekend(today: date) -> tuple[date, date]:
    weekday = today.weekday()
    if weekday == 6:
        return today, today
    if weekday == 5:
        return today, today + timedelta(days=1)
    saturday = today + timedelta(days=5 - weekday)
    return saturday, saturday + timedelta(days=1)


def budget_ceiling(amount: float | None, kind: str) -> float | None:
    if amount is None or kind == "unspecified":
        return None
    if kind == "around":
        return round(amount * AROUND_BUDGET_FACTOR, 2)
    return round(amount, 2)


def apply_day_hint(draft: ConstraintDraft, today: date) -> tuple[date | None, date | None]:
    hint = draft.day_hint
    if hint == "today":
        return today, today
    if hint == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    if hint == "weekend":
        return upcoming_weekend(today)
    if hint in WEEKDAYS:
        day = resolve_named_day(hint, today)
        return day, day
    start = draft.date_start
    end = draft.date_end or start
    return start, end


def _question(missing_type: bool, missing_date: bool, supplied: str | None) -> str:
    if supplied and len(supplied) <= 180:
        return supplied.strip()
    if missing_type and missing_date:
        return "What day should I plan, and do you want an activity or a restaurant?"
    if missing_type:
        return "Would you like an activity or a restaurant?"
    return "Which day should I plan for?"


def finalize_constraints(draft: ConstraintDraft, today: date) -> PlanningConstraints:
    if draft.budget_amount is not None and draft.budget_amount < 0:
        raise ValueError("budget must be non-negative")
    if draft.max_travel_minutes is not None and draft.max_travel_minutes < 0:
        raise ValueError("travel minutes must be non-negative")

    categories = normalize_list(draft.categories)
    cuisines = normalize_list(draft.cuisines, cuisine=True)
    if draft.plan_type == "restaurant":
        moved = [
            token
            for token in categories
            if token
            in {
                "japanese",
                "italian",
                "thai",
                "indian",
                "korean",
                "mexican",
                "canadian",
                "cafe",
                "cocktail_bar",
            }
        ]
        categories = [token for token in categories if token not in moved]
        for token in moved:
            if token not in cuisines:
                cuisines.append(token)

    date_start, date_end = apply_day_hint(draft, today)
    if date_start and date_end and date_end < date_start:
        date_start, date_end = date_end, date_start
    if date_start and date_end and (date_end - date_start).days > MAX_RANGE_DAYS:
        date_end = date_start + timedelta(days=MAX_RANGE_DAYS)

    time_start = draft.time_start
    time_end = draft.time_end
    if draft.time_of_day and (time_start is None or time_end is None):
        time_start, time_end = TIME_WINDOWS[draft.time_of_day]
    if time_start and time_end and time_end <= time_start:
        time_start, time_end = None, None

    missing_type = draft.plan_type is None
    missing_date = date_start is None
    needs = missing_type or missing_date
    question = (
        _question(missing_type, missing_date, draft.clarification_question) if needs else None
    )

    return PlanningConstraints(
        plan_type=draft.plan_type,
        date_start=date_start,
        date_end=date_end,
        time_of_day=draft.time_of_day,
        time_start=time_start,
        time_end=time_end,
        categories=categories,
        cuisines=cuisines,
        budget_amount=draft.budget_amount,
        budget_kind=draft.budget_kind,
        budget_max=budget_ceiling(draft.budget_amount, draft.budget_kind),
        max_travel_minutes=draft.max_travel_minutes,
        needs_clarification=needs,
        clarification_question=question,
        summary=draft.summary.strip()[:240],
    )


def merge_preferences(
    constraints: PlanningConstraints,
    *,
    default_budget: float | None,
    max_travel_minutes: int | None,
    preferred_time_start: time | None,
    preferred_time_end: time | None,
) -> PlanningConstraints:
    """Fill only gaps. A request that named a limit keeps that limit."""

    update: dict[str, object] = {}
    if constraints.budget_max is None and default_budget is not None:
        update["budget_max"] = default_budget
        update["budget_kind"] = "maximum"
        update["budget_amount"] = default_budget
    if constraints.max_travel_minutes is None and max_travel_minutes is not None:
        update["max_travel_minutes"] = max_travel_minutes
    if (
        constraints.time_start is None
        and constraints.time_end is None
        and preferred_time_start
        and preferred_time_end
        and preferred_time_end > preferred_time_start
    ):
        update["time_start"] = preferred_time_start
        update["time_end"] = preferred_time_end
    if not update:
        return constraints
    return constraints.model_copy(update=update)


def format_summary(constraints: PlanningConstraints) -> str:
    parts: list[str] = []
    if constraints.date_start:
        if constraints.date_end and constraints.date_end != constraints.date_start:
            start_label = constraints.date_start.strftime("%a %b %d")
            end_label = constraints.date_end.strftime("%a %b %d")
            parts.append(f"{start_label}–{end_label}")
        else:
            parts.append(constraints.date_start.strftime("%A, %b %d"))
    if constraints.time_of_day:
        parts.append(constraints.time_of_day.replace("_", " "))
    elif constraints.time_start and constraints.time_end:
        parts.append(
            f"{constraints.time_start.strftime('%H:%M')}–{constraints.time_end.strftime('%H:%M')}"
        )
    if constraints.budget_max is not None:
        parts.append(f"under ${constraints.budget_max:.0f}")
    if constraints.max_travel_minutes is not None:
        parts.append(f"within {constraints.max_travel_minutes} min")
    interests = (
        constraints.cuisines if constraints.plan_type == "restaurant" else constraints.categories
    )
    if interests:
        parts.append(", ".join(interests[:4]).replace("_", " "))
    return " · ".join(parts)
