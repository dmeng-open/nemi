"""Locked checks. Each one can fail on its own.

Missing-date behavior, the shared replan cap, invalid-output retry, and fail-closed
retries stay in the unit tests. This module does not score them.
"""

from app.agents.itinerary.engine import validate_itinerary
from evals.multi_llm.outcome import Outcome

_RESEARCH_BRANCHES = frozenset({"restaurant", "events"})


def dinner_and_activity_failures(outcome: Outcome) -> list[str]:
    if outcome.selection_errors:
        return list(outcome.selection_errors)
    if outcome.itinerary is None:
        return ["itinerary does not contain dinner and an activity"]
    kinds = {item.item_type for item in outcome.itinerary.items}
    missing: list[str] = []
    if "restaurant" not in kinds:
        missing.append("dinner")
    if "event" not in kinds:
        missing.append("an activity")
    if missing:
        return [f"itinerary does not contain {' and '.join(missing)}"]
    return []


def hard_constraint_failures(outcome: Outcome) -> list[str]:
    failures: list[str] = []
    failures.extend(outcome.selection_errors)
    overlap = outcome.chosen_ids & outcome.illegal_ids
    if overlap:
        names = ", ".join(sorted(overlap))
        failures.append(f"hard-constraint candidate remains: {names}")
    if outcome.itinerary is None:
        failures.append("no itinerary remained to check for hard constraints")
        return failures
    verification = validate_itinerary(
        outcome.itinerary,
        constraints=outcome.constraints,
        calendar=None,
    )
    failures.extend(item.message for item in verification.violations)
    if outcome.meal_dietary == "exclude":
        failures.append("a diet-excluded restaurant remains on the itinerary")
    return failures


def failed_branch_failures(outcome: Outcome, *, failed_branch: str) -> list[str]:
    """The replan may reopen the failed research branch and the itinerary task."""

    failures: list[str] = []
    if outcome.itinerary is None:
        failures.append("replan did not leave an itinerary")
    if outcome.task_status.get("calendar") != "completed":
        failures.append("calendar task was not left completed")
    if "calendar" in outcome.reopened_task_ids:
        failures.append("replan reopened calendar")
    other = _RESEARCH_BRANCHES - {failed_branch}
    for branch in sorted(other):
        if branch in outcome.reopened_task_ids:
            failures.append(f"replan reopened {branch}")
        if outcome.task_status.get(branch) != "completed":
            failures.append(f"{branch} was not left completed")
    allowed = {failed_branch, "itinerary"}
    extra = [task_id for task_id in outcome.reopened_task_ids if task_id not in allowed]
    if extra:
        failures.append("replan reopened " + ", ".join(extra))
    if outcome.reopened_task_ids and failed_branch not in outcome.reopened_task_ids:
        failures.append(f"replan did not reopen the failed {failed_branch} branch")
    if outcome.second_wave_new_ids:
        names = ", ".join(outcome.second_wave_new_ids)
        failures.append(f"second wave introduced a new id: {names}")
    if not outcome.stopped:
        failures.append("second wave did not stop")
    return failures


def write_count_failures(outcome: Outcome) -> list[str]:
    """One approve writes the restaurant block and the activity block. Travel is not written."""

    restaurants = 0
    events = 0
    if outcome.itinerary is not None:
        restaurants = sum(1 for item in outcome.itinerary.items if item.item_type == "restaurant")
        events = sum(1 for item in outcome.itinerary.items if item.item_type == "event")
    if restaurants != 1 or events != 1 or outcome.write_count != 2:
        return [
            "calendar write count is "
            f"{outcome.write_count}; one approve writes one restaurant event "
            "and one activity event"
        ]
    return []
