from app.domain.calendar import CalendarEvent, TimeWindow
from app.domain.constraints import PlanningConstraints
from app.domain.preferences import UserPreferences
from app.domain.ranking import RankingContext


def ranking_context(state: dict, zone_key: str) -> RankingContext:
    constraints = PlanningConstraints.model_validate(state["constraints"])
    preferences = UserPreferences.model_validate(state["user_preferences"])
    if constraints.plan_type == "restaurant":
        requested = constraints.cuisines
        preferred = preferences.preferred_cuisines
    else:
        requested = constraints.categories
        preferred = preferences.preferred_event_categories
    return RankingContext(
        requested_categories=requested,
        preferred_categories=preferred,
        disliked_categories=preferences.disliked_categories,
        budget_max=constraints.budget_max,
        max_travel_minutes=constraints.max_travel_minutes,
        free_windows=[TimeWindow.model_validate(item) for item in state.get("free_windows", [])],
        busy_events=[
            CalendarEvent.model_validate(item) for item in state.get("calendar_events", [])
        ],
        preferred_time_start=constraints.time_start,
        preferred_time_end=constraints.time_end,
        timezone=zone_key,
        calendar_read=_calendar_read(state),
    )


def _calendar_read(state: dict) -> str:
    value = state.get("calendar_read")
    if value == "unavailable":
        return "unavailable"
    return "ok"
