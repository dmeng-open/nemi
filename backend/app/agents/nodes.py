import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import time as clock_time
from zoneinfo import ZoneInfo

from langgraph.types import interrupt

from app.agents.llm import ConstraintParser, Explainer
from app.core.clock import Clock
from app.core.exceptions import ApprovalRequired, InvalidSelection
from app.core.messages import SAFE_MESSAGES
from app.domain.calendar import CalendarExecutionResult
from app.domain.candidates import Candidate
from app.domain.constraints import PlanningConstraints
from app.domain.preferences import UserPreferences
from app.domain.ranking import RankedCandidate
from app.integrations.events.models import EventSearchQuery
from app.integrations.restaurants.models import RestaurantSearchQuery
from app.providers.retry import call_with_retries
from app.services.calendar.conflicts import propose_slot
from app.services.calendar.windows import free_windows_for_range
from app.services.planning.context import ranking_context
from app.services.planning.dates import format_summary, merge_preferences
from app.services.planning.verify import apply_exclusions
from app.services.ranking.heuristic import HeuristicRanker


class EventLog:
    async def emit(
        self,
        event_type: str,
        status: str,
        metadata: dict | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        del event_type, status, metadata, duration_ms, error_code


@dataclass
class PlanningDeps:
    parser: ConstraintParser
    explainer: Explainer
    events: object
    restaurants: object
    calendar: object
    ranker: HeuristicRanker
    log: EventLog
    clock: Clock
    zone: ZoneInfo
    load_preferences: Callable[[], Awaitable[UserPreferences]]
    schedule: Callable[[dict], Awaitable[CalendarExecutionResult]]
    event_provider_name: str = "mock"
    place_provider_name: str = "mock"


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _zone(state: dict, deps: PlanningDeps) -> ZoneInfo:
    from zoneinfo import ZoneInfoNotFoundError

    preferences = state.get("user_preferences") or {}
    name = preferences.get("timezone") if isinstance(preferences, dict) else None
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except ZoneInfoNotFoundError:
            return deps.zone
    return deps.zone


def make_nodes(deps: PlanningDeps) -> dict[str, Callable]:
    async def parse_request(state: dict) -> dict:
        started = time.perf_counter()
        constraints = await deps.parser.parse(
            state["user_request"],
            now=deps.clock.now(),
            zone=deps.zone,
        )
        status = "awaiting_clarification" if constraints.needs_clarification else "processing"
        await deps.log.emit(
            "constraints_parsed",
            "completed",
            {
                "plan_type": constraints.plan_type,
                "needs_clarification": constraints.needs_clarification,
            },
            duration_ms=_ms(started),
        )
        return {
            "constraints": constraints.model_dump(mode="json"),
            "plan_type": constraints.plan_type,
            "clarification_question": constraints.clarification_question,
            "status": status,
            "summary": format_summary(constraints),
            "error_code": None,
        }

    async def load_user_preferences(state: dict) -> dict:
        started = time.perf_counter()
        preferences = await deps.load_preferences()
        constraints = PlanningConstraints.model_validate(state["constraints"])
        time_range = (
            preferences.preferred_time_ranges[0] if preferences.preferred_time_ranges else None
        )
        merged = merge_preferences(
            constraints,
            default_budget=preferences.default_budget,
            max_travel_minutes=preferences.max_travel_minutes,
            preferred_time_start=time_range.start if time_range else None,
            preferred_time_end=time_range.end if time_range else None,
        )
        await deps.log.emit("preferences_loaded", "completed", {}, duration_ms=_ms(started))
        return {
            "user_preferences": preferences.model_dump(mode="json"),
            "constraints": merged.model_dump(mode="json"),
            "summary": format_summary(merged),
        }

    async def get_calendar_availability(state: dict) -> dict:
        started = time.perf_counter()
        constraints = PlanningConstraints.model_validate(state["constraints"])
        if constraints.date_start is None or constraints.date_end is None:
            raise InvalidSelection("The plan is missing a date.")
        time_start = constraints.time_start or clock_time(8, 0)
        time_end = constraints.time_end or clock_time(22, 0)
        zone = _zone(state, deps)
        start = datetime.combine(constraints.date_start, clock_time.min, tzinfo=zone)
        end = datetime.combine(constraints.date_end, clock_time.max, tzinfo=zone)
        try:
            events = await call_with_retries(
                lambda: deps.calendar.get_events(start, end),
                base_delay=0.25,
            )
        except Exception as exc:
            from app.core.exceptions import ProviderError

            if not isinstance(exc, ProviderError):
                raise
            await deps.log.emit(
                "calendar_loaded",
                "completed",
                {"calendar_read": "unavailable"},
                duration_ms=_ms(started),
            )
            return {
                "calendar_events": [],
                "free_windows": [],
                "calendar_read": "unavailable",
            }
        windows = free_windows_for_range(
            date_start=constraints.date_start,
            date_end=constraints.date_end,
            time_start=time_start,
            time_end=time_end,
            busy=events,
            zone=zone,
        )
        await deps.log.emit(
            "calendar_loaded",
            "completed",
            {
                "event_count": len(events),
                "free_windows": len(windows),
                "calendar_read": "ok",
            },
            duration_ms=_ms(started),
        )
        return {
            "calendar_events": [event.model_dump(mode="json") for event in events],
            "free_windows": [window.model_dump(mode="json") for window in windows],
            "calendar_read": "ok",
        }

    async def determine_plan_type(state: dict) -> dict:
        return {"plan_type": state["constraints"]["plan_type"]}

    async def search_events(state: dict) -> dict:
        return await _search(state, kind="events")

    async def search_restaurants(state: dict) -> dict:
        return await _search(state, kind="restaurants")

    async def _search(state: dict, *, kind: str) -> dict:
        constraints = PlanningConstraints.model_validate(state["constraints"])
        preferences = UserPreferences.model_validate(state.get("user_preferences") or {})
        if kind == "events" and deps.event_provider_name == "ticketmaster":
            if not (preferences.home_city or "").strip():
                return {
                    "status": "awaiting_location",
                    "error_code": "city_required",
                    "candidates": [],
                }
        if kind == "restaurants" and deps.place_provider_name == "google":
            if preferences.latitude is None or preferences.longitude is None:
                return {
                    "status": "awaiting_location",
                    "error_code": "location_required",
                    "candidates": [],
                }
        zone = _zone(state, deps)
        radius = preferences.default_radius_km or 10
        await deps.log.emit("search_started", "started", {"kind": kind})
        started = time.perf_counter()
        if kind == "events":
            query = EventSearchQuery(
                date_start=constraints.date_start,
                date_end=constraints.date_end or constraints.date_start,
                timezone=zone.key,
                categories=constraints.categories,
                budget_max=constraints.budget_max,
                max_travel_minutes=constraints.max_travel_minutes,
                city=preferences.home_city,
                latitude=preferences.latitude,
                longitude=preferences.longitude,
                radius_km=radius,
            )
            found = await call_with_retries(
                lambda: deps.events.search_events(query),
                base_delay=0.25,
            )
            candidates = [item.to_candidate() for item in found]
        else:
            query = RestaurantSearchQuery(
                timezone=zone.key,
                cuisines=constraints.cuisines,
                budget_max=constraints.budget_max,
                max_travel_minutes=constraints.max_travel_minutes,
                latitude=preferences.latitude,
                longitude=preferences.longitude,
                radius_km=radius,
                date_start=constraints.date_start,
                date_end=constraints.date_end or constraints.date_start,
            )
            found = await call_with_retries(
                lambda: deps.restaurants.search_restaurants(query),
                base_delay=0.25,
            )
            candidates = [item.to_candidate() for item in found]
        await deps.log.emit(
            "search_completed",
            "completed",
            {"kind": kind, "count": len(candidates)},
            duration_ms=_ms(started),
        )
        return {"candidates": [item.model_dump(mode="json") for item in candidates]}

    async def normalize_candidates(state: dict) -> dict:
        started = time.perf_counter()
        checked = state.get("calendar_read", "ok") == "ok"
        candidates = [Candidate.model_validate(item) for item in state.get("candidates", [])]
        if state.get("plan_type") == "restaurant":
            from datetime import timedelta

            from app.domain.calendar import TimeWindow

            zone = _zone(state, deps)
            if checked:
                windows = [TimeWindow.model_validate(item) for item in state.get("free_windows", [])]
            else:
                constraints = PlanningConstraints.model_validate(state["constraints"])
                day = constraints.date_start
                time_start = constraints.time_start or clock_time(8, 0)
                time_end = constraints.time_end or clock_time(22, 0)
                windows = []
                if day is not None and time_end > time_start:
                    windows = [
                        TimeWindow(
                            start=datetime.combine(day, time_start, tzinfo=zone),
                            end=datetime.combine(day, time_end, tzinfo=zone),
                        )
                    ]
            slot = propose_slot(windows, timedelta(minutes=90))
            if slot is not None:
                start, end = slot
                candidates = [
                    item.model_copy(
                        update={
                            "start_datetime": start,
                            "end_datetime": end,
                            "calendar_checked": checked,
                        }
                    )
                    for item in candidates
                ]
            else:
                candidates = [
                    item.model_copy(update={"calendar_checked": checked}) for item in candidates
                ]
        else:
            candidates = [
                item.model_copy(update={"calendar_checked": checked}) for item in candidates
            ]
        await deps.log.emit(
            "candidates_normalized",
            "completed",
            {"count": len(candidates)},
            duration_ms=_ms(started),
        )
        return {"candidates": [item.model_dump(mode="json") for item in candidates]}

    async def rank_candidates(state: dict) -> dict:
        started = time.perf_counter()
        candidates = [Candidate.model_validate(item) for item in state.get("candidates", [])]
        ranked = await deps.ranker.rank(candidates, ranking_context(state, _zone(state, deps).key))
        await deps.log.emit(
            "candidates_ranked",
            "completed",
            {"count": len(ranked)},
            duration_ms=_ms(started),
        )
        return {"ranked_candidates": [item.model_dump(mode="json") for item in ranked]}

    async def verify_candidates(state: dict) -> dict:
        started = time.perf_counter()
        constraints = PlanningConstraints.model_validate(state["constraints"])
        ranked = [
            RankedCandidate.model_validate(item) for item in state.get("ranked_candidates", [])
        ]
        ranked, conflicts = apply_exclusions(
            ranked,
            budget_max=constraints.budget_max,
            max_travel=constraints.max_travel_minutes,
        )
        await deps.log.emit(
            "constraints_verified",
            "completed",
            {
                "conflicts_removed": conflicts,
                "remaining": sum(1 for item in ranked if item.exclusion_reason is None),
                "calendar_read": state.get("calendar_read", "ok"),
            },
            duration_ms=_ms(started),
        )
        return {
            "ranked_candidates": [item.model_dump(mode="json") for item in ranked],
            "conflicts_removed": conflicts,
        }

    async def generate_recommendations(state: dict) -> dict:
        started = time.perf_counter()
        ranked = [
            RankedCandidate.model_validate(item) for item in state.get("ranked_candidates", [])
        ]
        shown = [item for item in ranked if item.shown]
        if not shown:
            code = "no_restaurants" if state.get("plan_type") == "restaurant" else "no_events"
            await deps.log.emit(
                "recommendations_generated",
                "completed",
                {"count": 0},
                duration_ms=_ms(started),
            )
            return {
                "ranked_candidates": [item.model_dump(mode="json") for item in ranked],
                "status": "no_matches",
                "error_code": code,
                "errors": [code],
            }
        context = ranking_context(state, _zone(state, deps).key)
        explanations = await deps.explainer.explain(ranked, context)
        for item in ranked:
            if item.candidate.id in explanations:
                item.explanation = explanations[item.candidate.id]
        await deps.log.emit(
            "recommendations_generated",
            "completed",
            {"count": len(shown)},
            duration_ms=_ms(started),
        )
        return {
            "ranked_candidates": [item.model_dump(mode="json") for item in ranked],
            "status": "awaiting_selection",
            "error_code": None,
        }

    async def wait_for_user_selection(state: dict) -> dict:
        if state.get("selected_candidate_id"):
            return {"status": "awaiting_approval"}
        selected = interrupt({"status": "awaiting_selection"})
        return {"selected_candidate_id": selected, "status": "awaiting_approval"}

    async def wait_for_user_approval(state: dict) -> dict:
        if state.get("approved"):
            return {}
        approved = interrupt({"status": "awaiting_approval"})
        if not approved:
            return {"approved": False, "status": "cancelled"}
        return {"approved": True, "status": "scheduling"}

    async def create_calendar_plan(state: dict) -> dict:
        if not state.get("approved"):
            raise ApprovalRequired()
        await deps.log.emit("calendar_write_started", "started", {})
        try:
            result = await deps.schedule(state)
        except Exception as exc:
            code = getattr(exc, "code", "calendar_write_failed")
            await deps.log.emit(
                "calendar_write_failed",
                "failed",
                {"error_code": code},
                error_code=code,
            )
            raise
        await deps.log.emit("calendar_write_completed", "completed", {})
        return {
            "execution_result": result.model_dump(mode="json"),
            "status": "scheduled",
        }

    return {
        "parse_request": parse_request,
        "load_user_preferences": load_user_preferences,
        "get_calendar_availability": get_calendar_availability,
        "determine_plan_type": determine_plan_type,
        "search_events": search_events,
        "search_restaurants": search_restaurants,
        "normalize_candidates": normalize_candidates,
        "rank_candidates": rank_candidates,
        "verify_candidates": verify_candidates,
        "generate_recommendations": generate_recommendations,
        "wait_for_user_selection": wait_for_user_selection,
        "wait_for_user_approval": wait_for_user_approval,
        "create_calendar_plan": create_calendar_plan,
    }


def default_schedule(deps: PlanningDeps) -> Callable[[dict], Awaitable[CalendarExecutionResult]]:
    from app.services.calendar.scheduling import schedule_approved_plan

    async def schedule(state: dict) -> CalendarExecutionResult:
        if not state.get("approved"):
            raise ApprovalRequired()
        ranked = [
            RankedCandidate.model_validate(item) for item in state.get("ranked_candidates", [])
        ]
        selected = state.get("selected_candidate_id")
        match = next((item for item in ranked if item.candidate.id == selected), None)
        if match is None:
            raise InvalidSelection()
        return await schedule_approved_plan(
            deps.calendar,
            approved=True,
            plan_id=state["session_id"],
            candidate=match.candidate,
            explanation=match.explanation,
        )

    return schedule


def no_match_message(code: str | None) -> str:
    if code and code in SAFE_MESSAGES:
        return SAFE_MESSAGES[code]
    return SAFE_MESSAGES["no_matches"]
