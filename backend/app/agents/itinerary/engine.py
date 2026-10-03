from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.agents.itinerary.artifacts import (
    CalendarAnalysisResult,
    ConstraintCheck,
    CriticIssue,
    CriticResult,
    EventResearchArtifact,
    Itinerary,
    ItineraryConstraints,
    ItineraryItem,
    ResearchCandidate,
    RestaurantResearchArtifact,
    SemanticReview,
    VerificationResult,
    Violation,
)
from app.domain.calendar import CalendarEvent, TimeWindow
from app.domain.candidates import Candidate
from app.services.calendar.conflicts import contained, overlaps

DINNER_MINUTES = 90
RAW_MARKERS = ("sushi", "sashimi", "nigiri", "raw fish", "omakase", "handroll", "hand roll")
COOKED_MARKERS = ("ramen", "cooked", "grill", "skewer", "noodle", "izakaya")


def dietary_status(title: str, description: str | None, restrictions: list[str]) -> str:
    if not restrictions:
        return "ok"
    blob = " ".join(restrictions).lower()
    text = f"{title} {description or ''}".lower()
    if "vegetarian" in blob and any(word in text for word in ("bbq", "grill", "fish", "chicken")):
        return "exclude"
    if "raw" not in blob and "sushi" not in blob:
        return "ok"
    has_raw = any(marker in text for marker in RAW_MARKERS)
    has_cooked = any(marker in text for marker in COOKED_MARKERS)
    if has_raw and not has_cooked:
        return "exclude"
    if has_raw and has_cooked:
        return "uncertain"
    if " raw" in f" {text}":
        return "uncertain"
    return "ok"


def dedupe_candidates(items: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, str]] = set()
    unique: list[Candidate] = []
    for item in items:
        start = item.start_datetime.isoformat() if item.start_datetime else ""
        key = (item.external_id or item.title, start)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def between_minutes(origin: int | None, destination: int | None) -> int:
    start = origin if origin is not None else 15
    end = destination if destination is not None else 15
    return max(5, round((start + end) / 2))


def parallel_speedup(branch_durations_ms: list[int], wall_ms: int) -> float | None:
    if wall_ms <= 0 or not branch_durations_ms:
        return None
    return round(sum(branch_durations_ms) / wall_ms, 3)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    # Published gpt-4o-mini order of magnitude, used only for the developer trace.
    return round((input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000, 6)


def build_itineraries(
    *,
    constraints: ItineraryConstraints,
    calendar: CalendarAnalysisResult | None,
    restaurants: RestaurantResearchArtifact | None,
    events: EventResearchArtifact | None,
    rejected_ids: set[str],
    limit: int = 3,
) -> list[Itinerary]:
    zone = ZoneInfo(constraints.timezone)
    windows = _windows(calendar, constraints, zone)
    busy = _busy(calendar)
    calendar_read = calendar.calendar_read if calendar else "unavailable"
    meal_options = [
        item
        for item in (restaurants.candidate_restaurants if restaurants else [])
        if item.candidate.id not in rejected_ids and item.dietary != "exclude"
    ]
    event_options = [
        item
        for item in (events.candidate_events if events else [])
        if item.candidate.id not in rejected_ids
    ]
    meal_options.sort(key=lambda item: (_diet_rank(item.dietary), -item.score, item.candidate.id))
    event_options.sort(key=lambda item: (-item.score, item.candidate.id))
    drafts: list[Itinerary] = []
    if constraints.wants_restaurant and constraints.wants_event:
        for meal in meal_options:
            for activity in event_options:
                built = _pair(
                    meal,
                    activity,
                    constraints=constraints,
                    windows=windows,
                    busy=busy,
                    calendar_read=calendar_read,
                    zone=zone,
                )
                if built is not None:
                    drafts.append(built)
    elif constraints.wants_restaurant:
        for meal in meal_options:
            built = _meal_only(
                meal,
                constraints=constraints,
                windows=windows,
                busy=busy,
                calendar_read=calendar_read,
                zone=zone,
            )
            if built is not None:
                drafts.append(built)
    elif constraints.wants_event:
        for activity in event_options:
            built = _event_only(
                activity,
                constraints=constraints,
                windows=windows,
                busy=busy,
                calendar_read=calendar_read,
                zone=zone,
            )
            if built is not None:
                drafts.append(built)
    if not drafts and meal_options and constraints.wants_restaurant:
        for meal in meal_options:
            built = _meal_only(
                meal,
                constraints=constraints,
                windows=windows,
                busy=busy,
                calendar_read=calendar_read,
                zone=zone,
                partial_event=constraints.wants_event,
            )
            if built is not None:
                drafts.append(built)
                break
    return _diverse(drafts, limit)


def with_selected_first(
    *,
    constraints: ItineraryConstraints,
    calendar: CalendarAnalysisResult | None,
    restaurants: RestaurantResearchArtifact | None,
    events: EventResearchArtifact | None,
    rejected_ids: set[str],
    limit: int = 3,
) -> list[Itinerary]:
    """Put a placeable selected dinner and/or activity first.

    The remaining cards are the ranker order passed through ``_diverse``.
    This does not drop other candidates and does not change ``selected_id``.
    """

    ranked = build_itineraries(
        constraints=constraints,
        calendar=calendar,
        restaurants=restaurants,
        events=events,
        rejected_ids=rejected_ids,
        limit=limit,
    )
    lead = _place_selected(
        constraints=constraints,
        calendar=calendar,
        restaurants=restaurants,
        events=events,
        rejected_ids=rejected_ids,
    )
    if lead is None:
        return ranked
    rest = [item for item in ranked if item.itinerary_id != lead.itinerary_id]
    return [lead, *rest]


def _selected_member(
    items: list[ResearchCandidate],
    selected_id: str | None,
    rejected_ids: set[str],
    *,
    drop_excluded_diet: bool,
) -> ResearchCandidate | None:
    if not selected_id or selected_id in rejected_ids:
        return None
    for item in items:
        if item.candidate.id != selected_id:
            continue
        if drop_excluded_diet and item.dietary == "exclude":
            return None
        return item
    return None


def _place_selected(
    *,
    constraints: ItineraryConstraints,
    calendar: CalendarAnalysisResult | None,
    restaurants: RestaurantResearchArtifact | None,
    events: EventResearchArtifact | None,
    rejected_ids: set[str],
) -> Itinerary | None:
    zone = ZoneInfo(constraints.timezone)
    windows = _windows(calendar, constraints, zone)
    busy = _busy(calendar)
    calendar_read = calendar.calendar_read if calendar else "unavailable"
    meal = _selected_member(
        restaurants.candidate_restaurants if restaurants else [],
        restaurants.selected_id if restaurants else None,
        rejected_ids,
        drop_excluded_diet=True,
    )
    activity = _selected_member(
        events.candidate_events if events else [],
        events.selected_id if events else None,
        rejected_ids,
        drop_excluded_diet=False,
    )
    shared = {
        "constraints": constraints,
        "windows": windows,
        "busy": busy,
        "calendar_read": calendar_read,
        "zone": zone,
    }
    placed: Itinerary | None = None
    if constraints.wants_restaurant and constraints.wants_event and meal and activity:
        placed = _pair(meal, activity, **shared)
    if placed is None and constraints.wants_restaurant and meal is not None:
        placed = _meal_only(meal, partial_event=constraints.wants_event, **shared)
    if placed is None and constraints.wants_event and activity is not None:
        placed = _event_only(activity, **shared)
    return placed


def validate_itinerary(
    itinerary: Itinerary,
    *,
    constraints: ItineraryConstraints,
    calendar: CalendarAnalysisResult | None,
) -> VerificationResult:
    zone = ZoneInfo(constraints.timezone)
    windows = _windows(calendar, constraints, zone)
    busy = _busy(calendar)
    calendar_read = calendar.calendar_read if calendar else "unavailable"
    hard_end = None
    if constraints.date_start is not None:
        hard_end = datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone)
    checks = _checks(
        itinerary,
        constraints=constraints,
        windows=windows,
        busy=busy,
        calendar_read=calendar_read,
        hard_end=hard_end,
    )
    violations = [
        Violation(type=check.code, message=check.message)
        for check in checks
        if check.status == "fail"
    ]
    return VerificationResult(
        valid=not violations,
        violations=violations,
        limiting_constraint=violations[0].message if violations else None,
    )


def critique(
    itinerary: Itinerary | None,
    *,
    constraints: ItineraryConstraints,
    restaurants: RestaurantResearchArtifact | None,
    force_reject: bool = False,
) -> CriticResult:
    if force_reject:
        return CriticResult(
            status="REVISE",
            issues=[
                CriticIssue(
                    type="DIETARY_CONSTRAINT",
                    severity="high",
                    message="The selected restaurant does not satisfy the dietary constraint.",
                    target_task="restaurant",
                )
            ],
        )
    if itinerary is None:
        return CriticResult(
            status="REVISE",
            issues=[
                CriticIssue(
                    type="MISSING_PLAN",
                    severity="high",
                    message="No itinerary was produced.",
                    target_task="restaurant" if constraints.wants_restaurant else "events",
                )
            ],
        )
    issues: list[CriticIssue] = []
    meal = next((item for item in itinerary.items if item.item_type == "restaurant"), None)
    if meal is not None and constraints.dietary_restrictions:
        match = _find_candidate(restaurants, meal.source_candidate_id)
        status = match.dietary if match is not None else "ok"
        if status == "exclude":
            issues.append(
                CriticIssue(
                    type="DIETARY_CONSTRAINT",
                    severity="high",
                    message=(
                        f"{meal.title} conflicts with the dietary constraint "
                        f"({', '.join(constraints.dietary_restrictions)})."
                    ),
                    target_task="restaurant",
                )
            )
        elif status == "uncertain":
            cooked = _has_dietary_ok(restaurants)
            issues.append(
                CriticIssue(
                    type="DIETARY_CONSTRAINT",
                    severity="high" if cooked else "medium",
                    message=(
                        f"{meal.title} appears to include raw dishes while someone "
                        "in the party does not eat raw fish."
                    ),
                    target_task="restaurant" if cooked else None,
                )
            )
    failed = [check for check in itinerary.checks if check.status == "fail"]
    for check in failed:
        if check.code == "END_TIME_EXCEEDED":
            issues.append(
                CriticIssue(
                    type="END_TIME_EXCEEDED",
                    severity="high",
                    message=check.message,
                    target_task="events",
                )
            )
    high = [issue for issue in issues if issue.severity == "high"]
    return CriticResult(status="REVISE" if high else "PASS", issues=issues)


def review_semantics(
    itineraries: list[Itinerary],
    *,
    constraints: ItineraryConstraints,
    events_failed: bool,
    restaurants_failed: bool,
) -> SemanticReview:
    if not itineraries:
        return SemanticReview(
            complete=False,
            partial=False,
            issues=["No itinerary satisfied the hard constraints."],
        )
    top = itineraries[0]
    kinds = {item.item_type for item in top.items}
    issues: list[str] = []
    partial = False
    if constraints.wants_restaurant and "restaurant" not in kinds:
        issues.append("The plan does not include a meal.")
        partial = True
    if constraints.wants_event and "event" not in kinds:
        if events_failed:
            issues.append("Activity search failed, so this is a partial plan.")
        else:
            issues.append("No activity fit the time window.")
        partial = True
    if restaurants_failed and "restaurant" not in kinds:
        issues.append("Restaurant search failed.")
        partial = True
    for item in top.items:
        if item.item_type == "travel" and not item.travel_time_is_estimate:
            issues.append("A travel block is marked exact without a routing source.")
    return SemanticReview(complete=not issues, partial=partial, issues=issues)


def limiting_message(constraints: ItineraryConstraints, verification: VerificationResult) -> str:
    limit = verification.limiting_constraint or "the combined constraints"
    budget = constraints.budget_max
    if budget is not None and "budget" in limit.lower():
        return (
            "I couldn't build a plan that satisfies every constraint. "
            f"The limiting constraint is the ${budget:.0f} total budget."
        )
    return (
        "I couldn't build a plan that satisfies every constraint. "
        f"The limiting constraint is {limit}."
    )


def _diet_rank(status: str) -> int:
    return {"ok": 0, "uncertain": 1, "exclude": 2}.get(status, 1)


def _has_dietary_ok(restaurants: RestaurantResearchArtifact | None) -> bool:
    if restaurants is None:
        return False
    return any(item.dietary == "ok" for item in restaurants.candidate_restaurants)


def _find_candidate(
    restaurants: RestaurantResearchArtifact | None, candidate_id: str | None
) -> ResearchCandidate | None:
    if restaurants is None or candidate_id is None:
        return None
    return next(
        (item for item in restaurants.candidate_restaurants if item.candidate.id == candidate_id),
        None,
    )


def _windows(
    calendar: CalendarAnalysisResult | None,
    constraints: ItineraryConstraints,
    zone: ZoneInfo,
) -> list[TimeWindow]:
    if calendar and calendar.calendar_read == "ok" and calendar.available_windows:
        return [TimeWindow.model_validate(item.model_dump()) for item in calendar.available_windows]
    if constraints.date_start is None:
        return []
    start = datetime.combine(constraints.date_start, constraints.time_start, tzinfo=zone)
    end = datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone)
    if end <= start:
        return []
    return [TimeWindow(start=start, end=end)]


def _busy(calendar: CalendarAnalysisResult | None) -> list[CalendarEvent]:
    if calendar is None or calendar.calendar_read != "ok":
        return []
    events: list[CalendarEvent] = []
    for item in calendar.existing_events:
        try:
            events.append(CalendarEvent.model_validate(item))
        except ValueError:
            continue
    return events


def _pair(
    meal: ResearchCandidate,
    activity: ResearchCandidate,
    *,
    constraints: ItineraryConstraints,
    windows: list[TimeWindow],
    busy: list[CalendarEvent],
    calendar_read: str,
    zone: ZoneInfo,
) -> Itinerary | None:
    event = activity.candidate
    if event.start_datetime is None or event.end_datetime is None:
        return None
    restaurant = meal.candidate
    to_meal = restaurant.estimated_travel_minutes or 15
    between = between_minutes(restaurant.estimated_travel_minutes, event.estimated_travel_minutes)
    home = event.estimated_travel_minutes or 15
    event_start = event.start_datetime.astimezone(zone)
    event_end = event.end_datetime.astimezone(zone)
    dinner_end = event_start - timedelta(minutes=between)
    dinner_start = dinner_end - timedelta(minutes=DINNER_MINUTES)
    shifted = False
    if constraints.shift_minutes:
        candidate_start = dinner_start + timedelta(minutes=constraints.shift_minutes)
        candidate_end = candidate_start + timedelta(minutes=DINNER_MINUTES)
        if candidate_end + timedelta(minutes=between) <= event_start:
            dinner_start = candidate_start
            dinner_end = candidate_end
            shifted = True
    leave = dinner_start - timedelta(minutes=to_meal)
    day_start = datetime.combine(constraints.date_start, constraints.time_start, tzinfo=zone) if constraints.date_start else leave
    if leave < day_start:
        return None
    home_arrival = event_end + timedelta(minutes=home)
    hard_end = datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone) if constraints.date_start else home_arrival
    items = [
        ItineraryItem(
            item_type="travel",
            title="Leave",
            start_datetime=leave,
            end_datetime=dinner_start,
            location=restaurant.address,
            travel_time_is_estimate=True,
        ),
        ItineraryItem(
            item_type="restaurant",
            title=restaurant.title,
            start_datetime=dinner_start,
            end_datetime=dinner_end,
            location=_place(restaurant),
            estimated_cost=restaurant.price_min,
            source_candidate_id=restaurant.id,
        ),
        ItineraryItem(
            item_type="travel",
            title="Travel",
            start_datetime=dinner_end,
            end_datetime=event_start,
            location=event.venue or event.address,
            travel_time_is_estimate=True,
        ),
        ItineraryItem(
            item_type="event",
            title=event.title,
            start_datetime=event_start,
            end_datetime=event_end,
            location=_place(event),
            estimated_cost=event.price_min,
            source_candidate_id=event.id,
        ),
        ItineraryItem(
            item_type="travel",
            title="Head home",
            start_datetime=event_end,
            end_datetime=home_arrival,
            travel_time_is_estimate=True,
        ),
    ]
    total = (restaurant.price_min or 0) + (event.price_min or 0)
    explanation = (
        f"Dinner at {restaurant.title}, then {event.title}. "
        "Travel times are estimates, not a routed trip."
    )
    if constraints.shift_minutes and not shifted:
        explanation += " The show time is fixed, so the evening could not all move later."
    plan = Itinerary(
        itinerary_id=f"itin_{restaurant.id}_{event.id}",
        items=items,
        estimated_total_cost=round(total, 2),
        start_datetime=leave,
        end_datetime=home_arrival,
        explanation=explanation,
        restaurant_id=restaurant.id,
        event_id=event.id,
    )
    plan.checks = _checks(
        plan,
        constraints=constraints,
        windows=windows,
        busy=busy,
        calendar_read=calendar_read,
        dietary=meal.dietary,
        hard_end=hard_end,
    )
    plan.valid = all(check.status != "fail" for check in plan.checks)
    if not plan.valid:
        return None
    return plan


def _meal_only(
    meal: ResearchCandidate,
    *,
    constraints: ItineraryConstraints,
    windows: list[TimeWindow],
    busy: list[CalendarEvent],
    calendar_read: str,
    zone: ZoneInfo,
    partial_event: bool = False,
) -> Itinerary | None:
    if constraints.date_start is None:
        return None
    restaurant = meal.candidate
    to_meal = restaurant.estimated_travel_minutes or 15
    start = datetime.combine(constraints.date_start, constraints.time_start, tzinfo=zone)
    dinner_start = start + timedelta(minutes=to_meal + constraints.shift_minutes)
    dinner_end = dinner_start + timedelta(minutes=DINNER_MINUTES)
    home = dinner_end + timedelta(minutes=to_meal)
    hard_end = datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone)
    if home > hard_end:
        return None
    items = [
        ItineraryItem(
            item_type="travel",
            title="Leave",
            start_datetime=dinner_start - timedelta(minutes=to_meal),
            end_datetime=dinner_start,
            travel_time_is_estimate=True,
        ),
        ItineraryItem(
            item_type="restaurant",
            title=restaurant.title,
            start_datetime=dinner_start,
            end_datetime=dinner_end,
            location=_place(restaurant),
            estimated_cost=restaurant.price_min,
            source_candidate_id=restaurant.id,
        ),
        ItineraryItem(
            item_type="travel",
            title="Head home",
            start_datetime=dinner_end,
            end_datetime=home,
            travel_time_is_estimate=True,
        ),
    ]
    explanation = f"Dinner at {restaurant.title}."
    if partial_event:
        explanation += " I could not find an activity that fit the rest of the evening."
    plan = Itinerary(
        itinerary_id=f"itin_{restaurant.id}_meal",
        items=items,
        estimated_total_cost=round(restaurant.price_min or 0, 2),
        start_datetime=items[0].start_datetime,
        end_datetime=home,
        explanation=explanation,
        restaurant_id=restaurant.id,
    )
    plan.checks = _checks(
        plan,
        constraints=constraints,
        windows=windows,
        busy=busy,
        calendar_read=calendar_read,
        dietary=meal.dietary,
        hard_end=hard_end,
        missing_event=partial_event,
    )
    plan.valid = all(check.status != "fail" for check in plan.checks)
    return plan if plan.valid else None


def _event_only(
    activity: ResearchCandidate,
    *,
    constraints: ItineraryConstraints,
    windows: list[TimeWindow],
    busy: list[CalendarEvent],
    calendar_read: str,
    zone: ZoneInfo,
) -> Itinerary | None:
    event = activity.candidate
    if event.start_datetime is None or event.end_datetime is None or constraints.date_start is None:
        return None
    home_minutes = event.estimated_travel_minutes or 15
    start = event.start_datetime.astimezone(zone)
    end = event.end_datetime.astimezone(zone)
    leave = start - timedelta(minutes=home_minutes)
    home = end + timedelta(minutes=home_minutes)
    hard_end = datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone)
    items = [
        ItineraryItem(
            item_type="travel",
            title="Leave",
            start_datetime=leave,
            end_datetime=start,
            travel_time_is_estimate=True,
        ),
        ItineraryItem(
            item_type="event",
            title=event.title,
            start_datetime=start,
            end_datetime=end,
            location=_place(event),
            estimated_cost=event.price_min,
            source_candidate_id=event.id,
        ),
        ItineraryItem(
            item_type="travel",
            title="Head home",
            start_datetime=end,
            end_datetime=home,
            travel_time_is_estimate=True,
        ),
    ]
    plan = Itinerary(
        itinerary_id=f"itin_{event.id}_event",
        items=items,
        estimated_total_cost=round(event.price_min or 0, 2),
        start_datetime=leave,
        end_datetime=home,
        explanation=f"{event.title}, with estimated travel.",
        event_id=event.id,
    )
    plan.checks = _checks(
        plan,
        constraints=constraints,
        windows=windows,
        busy=busy,
        calendar_read=calendar_read,
        hard_end=hard_end,
    )
    plan.valid = all(check.status != "fail" for check in plan.checks)
    return plan if plan.valid else None


def _checks(
    itinerary: Itinerary,
    *,
    constraints: ItineraryConstraints,
    windows: list[TimeWindow],
    busy: list[CalendarEvent],
    calendar_read: str,
    dietary: str = "ok",
    hard_end: datetime | None = None,
    missing_event: bool = False,
) -> list[ConstraintCheck]:
    checks: list[ConstraintCheck] = []
    ordered = itinerary.items
    previous_end: datetime | None = None
    overlap = False
    bad_duration = False
    for item in ordered:
        if item.end_datetime <= item.start_datetime:
            bad_duration = True
        if previous_end is not None and item.start_datetime < previous_end:
            overlap = True
        previous_end = item.end_datetime
        if item.item_type in {"restaurant", "event"} and calendar_read == "ok":
            if overlaps(item.start_datetime, item.end_datetime, busy):
                overlap = True
            if windows and not contained(item.start_datetime, item.end_datetime, windows):
                overlap = True
    checks.append(
        ConstraintCheck(
            code="ORDER",
            label="Order",
            status="fail" if overlap or bad_duration else "pass",
            message="The blocks overlap or have an invalid duration."
            if overlap or bad_duration
            else "The blocks are in order.",
        )
    )
    if calendar_read != "ok":
        checks.append(
            ConstraintCheck(
                code="CALENDAR",
                label="Calendar",
                status="soft",
                message="Calendar could not be checked.",
            )
        )
    else:
        checks.append(
            ConstraintCheck(
                code="CALENDAR_OVERLAP",
                label="Calendar",
                status="fail" if overlap else "pass",
                message="A block overlaps the calendar." if overlap else "No calendar conflict.",
            )
        )
    end_at = itinerary.end_datetime
    limit = hard_end
    if limit is not None and end_at > limit:
        checks.append(
            ConstraintCheck(
                code="END_TIME_EXCEEDED",
                label="Home",
                status="fail",
                message=(
                    f"Plan ends at {end_at.strftime('%H:%M')} but the hard end is "
                    f"{limit.strftime('%H:%M')}."
                ),
            )
        )
    else:
        checks.append(
            ConstraintCheck(
                code="END_TIME",
                label="Home",
                status="pass",
                message="Home before the hard end time.",
            )
        )
    budget = constraints.budget_max
    if budget is not None and itinerary.estimated_total_cost > budget:
        checks.append(
            ConstraintCheck(
                code="BUDGET",
                label="Budget",
                status="fail",
                message=(
                    f"Estimated total ${itinerary.estimated_total_cost:.0f} "
                    f"is over the ${budget:.0f} budget."
                ),
            )
        )
    else:
        label = "Within budget." if budget is not None else "No budget was set."
        checks.append(ConstraintCheck(code="BUDGET", label="Budget", status="pass", message=label))
    travel_items = [item for item in itinerary.items if item.item_type == "travel"]
    longest = 0
    for item in travel_items:
        minutes = int((item.end_datetime - item.start_datetime).total_seconds() // 60)
        longest = max(longest, minutes)
    soft = constraints.max_travel_minutes
    hard = constraints.hard_travel_minutes
    if hard is not None and longest > hard:
        travel_status: Literal["pass", "fail", "soft"] = "fail"
        travel_message = f"A trip is about {longest} minutes, over the {hard} minute limit."
    elif soft is not None and longest > soft:
        travel_status = "soft"
        travel_message = f"Travel time is about {longest} minutes, above the {soft} minute preference."
    else:
        travel_status = "pass"
        travel_message = "Travel stays within the preference. Times are estimates."
    checks.append(
        ConstraintCheck(
            code="TRAVEL",
            label="Travel",
            status=travel_status,
            message=travel_message,
        )
    )
    if constraints.dietary_restrictions:
        if dietary == "exclude":
            diet_status: Literal["pass", "fail", "soft"] = "fail"
            diet_message = "The restaurant conflicts with the dietary constraint."
        elif dietary == "uncertain":
            diet_status = "soft"
            diet_message = "The menu may include raw dishes. Confirm before you go."
        else:
            diet_status = "pass"
            diet_message = "Dietary constraint supported."
        checks.append(
            ConstraintCheck(
                code="DIETARY_CONSTRAINT",
                label="Diet",
                status=diet_status,
                message=diet_message,
            )
        )
    if missing_event:
        checks.append(
            ConstraintCheck(
                code="MISSING_ACTIVITY",
                label="Activity",
                status="soft",
                message="No activity fit this window.",
            )
        )
    ids = [item.source_candidate_id for item in itinerary.items if item.source_candidate_id]
    if len(ids) != len(set(ids)):
        checks.append(
            ConstraintCheck(
                code="DUPLICATE",
                label="Activities",
                status="fail",
                message="The plan repeats an activity.",
            )
        )
    return checks


def _diverse(drafts: list[Itinerary], limit: int) -> list[Itinerary]:
    ordered = sorted(
        drafts,
        key=lambda plan: (
            sum(1 for check in plan.checks if check.status == "soft"),
            plan.estimated_total_cost,
            plan.itinerary_id,
        ),
    )

    def take(allow_shared: bool) -> None:
        for plan in ordered:
            if len(chosen) >= limit:
                return
            if any(item.itinerary_id == plan.itinerary_id for item in chosen):
                continue
            meal_used = bool(plan.restaurant_id) and any(
                item.restaurant_id == plan.restaurant_id for item in chosen
            )
            event_used = bool(plan.event_id) and any(
                item.event_id == plan.event_id for item in chosen
            )
            if meal_used and event_used:
                continue
            if not allow_shared and (meal_used or event_used):
                continue
            chosen.append(plan)

    chosen: list[Itinerary] = []
    take(False)
    take(True)
    return chosen


def _place(candidate: Candidate) -> str | None:
    parts = [part for part in (candidate.venue, candidate.address) if part]
    return ", ".join(parts) or None
