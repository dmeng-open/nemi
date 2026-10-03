import re
from datetime import date, datetime, time

from app.agents.itinerary.artifacts import (
    AgentTask,
    ItineraryConstraints,
    SupervisorDecision,
    TaskStatus,
    TaskType,
    dump,
)
from app.services.planning.dates import budget_ceiling, resolve_named_day
from app.services.planning.taxonomy import CUISINE_ALIASES, normalize_token

_MEAL = ("dinner", "lunch", "breakfast", "restaurant")
_OUTING = ("jazz", "comedy", "concert", "exhibition", "art event", "show")
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _flat(text: str) -> str:
    return " ".join(text.lower().split())


def is_itinerary_request(text: str) -> bool:
    lowered = _flat(text)
    if "date night" in lowered or "after dinner" in lowered or "after lunch" in lowered:
        return True
    if "afternoon and evening" in lowered or "evening and afternoon" in lowered:
        return True
    meal = any(word in lowered for word in _MEAL)
    outing = any(word in lowered for word in _OUTING)
    return meal and outing


def _clock(match: re.Match[str]) -> time:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower().replace(".", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def _find_day(lowered: str, today: date) -> date | None:
    if "tomorrow" in lowered:
        from datetime import timedelta

        return today + timedelta(days=1)
    if re.search(r"\btoday\b", lowered):
        return today
    for name in _WEEKDAYS:
        if name in lowered:
            return resolve_named_day(name, today)
    return None


def parse_itinerary_request(text: str, *, today: date, timezone: str) -> ItineraryConstraints:
    lowered = _flat(text)
    day = _find_day(lowered, today)
    budget_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    amount = float(budget_match.group(1)) if budget_match else None
    kind = "unspecified"
    if amount is not None:
        kind = "around" if re.search(r"around\s*\$\s*\d", lowered) else "maximum"
    after = re.search(
        r"(?:free\s+)?after\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)",
        lowered,
    )
    before = re.search(
        r"(?:home\s+)?before\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)",
        lowered,
    )
    time_start = _clock(after) if after else time(17, 0)
    time_end = _clock(before) if before else time(23, 0)
    if "afternoon and evening" in lowered and after is None:
        time_start = time(12, 0)
    cuisines: list[str] = []
    for alias in CUISINE_ALIASES:
        if alias in {"sushi", "ramen", "izakaya"}:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            token = normalize_token(alias, cuisine=True)
            if token not in cuisines:
                cuisines.append(token)
    categories: list[str] = []
    for word, token in (
        ("jazz", "live_music"),
        ("comedy", "comedy"),
        ("art", "arts"),
        ("exhibition", "arts"),
        ("concert", "live_music"),
    ):
        if word in lowered and token not in categories:
            categories.append(token)
    dietary: list[str] = []
    if "raw fish" in lowered or "no sushi" in lowered or "doesn't eat raw" in lowered:
        dietary.append("no raw fish")
    if "vegetarian" in lowered:
        dietary.append("vegetarian")
    wants_restaurant = any(word in lowered for word in ("dinner", "lunch", "restaurant", "breakfast"))
    wants_event = bool(categories) or "after dinner" in lowered or "after lunch" in lowered
    if "afternoon and evening" in lowered:
        wants_restaurant = True
        wants_event = True
    if "date night" in lowered:
        wants_restaurant = True
        wants_event = True
    soft = "or something" in lowered or " or " in lowered
    question = None
    if day is None:
        question = "Which day should I plan?"
    summary_bits = []
    if day is not None:
        summary_bits.append(day.strftime("%A, %B %d"))
    if cuisines:
        summary_bits.append(", ".join(cuisines))
    if categories:
        summary_bits.append(", ".join(categories))
    return ItineraryConstraints(
        date_start=day,
        date_end=day,
        time_start=time_start,
        time_end=time_end,
        cuisines=cuisines,
        categories=categories,
        category_match_required=bool(categories) and not soft,
        dietary_restrictions=dietary,
        budget_amount=amount,
        budget_max=budget_ceiling(amount, kind) if amount is not None else None,
        budget_kind=kind,  # type: ignore[arg-type]
        wants_restaurant=wants_restaurant,
        wants_event=wants_event,
        timezone=timezone,
        summary=" · ".join(summary_bits) or "Evening plan",
        needs_clarification=question is not None,
        clarification_question=question,
    )


def _task(task_id: str, task_type: TaskType, agent: str, dependencies: list[str]) -> dict:
    return dump(
        AgentTask(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            dependencies=dependencies,
            assigned_agent=agent,
        )
    )


def decompose_tasks(constraints: ItineraryConstraints) -> list[dict]:
    tasks = [
        _task("calendar", TaskType.CALENDAR_ANALYSIS, "calendar_analysis", []),
    ]
    research: list[str] = ["calendar"]
    if constraints.wants_restaurant:
        tasks.append(
            _task("restaurant", TaskType.RESTAURANT_RESEARCH, "restaurant_research", [])
        )
        research.append("restaurant")
    if constraints.wants_event:
        tasks.append(_task("events", TaskType.EVENT_RESEARCH, "event_research", []))
        research.append("events")
    tasks.append(
        _task("itinerary", TaskType.ITINERARY_GENERATION, "itinerary_planner", research)
    )
    return tasks


def task_map(tasks: list[dict]) -> dict[str, dict]:
    return {item["task_id"]: item for item in tasks}


def pending_research(tasks: list[dict]) -> list[dict]:
    by_id = task_map(tasks)
    ready: list[dict] = []
    for task in tasks:
        if task["task_type"] not in {
            TaskType.CALENDAR_ANALYSIS.value,
            TaskType.RESTAURANT_RESEARCH.value,
            TaskType.EVENT_RESEARCH.value,
        }:
            continue
        if task["status"] != TaskStatus.PENDING.value:
            continue
        if all(by_id.get(dep, {}).get("status") == TaskStatus.COMPLETED.value for dep in task["dependencies"]):
            ready.append(task)
    return ready


def decide_branch_retry(tasks: list[dict]) -> str | None:
    for task in tasks:
        if (
            task["status"] == TaskStatus.FAILED.value
            and task.get("retryable")
            and int(task.get("retry_count") or 0) < 1
        ):
            return task["task_id"]
    return None


def mark_retry(tasks: list[dict], task_id: str) -> list[dict]:
    updated: list[dict] = []
    for task in tasks:
        if task["task_id"] == task_id:
            updated.append(
                {
                    **task,
                    "status": TaskStatus.PENDING.value,
                    "retry_count": int(task.get("retry_count") or 0) + 1,
                    "error": None,
                    "retryable": False,
                }
            )
        else:
            updated.append(task)
    return updated


def targets_for_issues(issues: list[dict]) -> list[str]:
    targets: list[str] = []
    for issue in issues:
        target = issue.get("target_task")
        if target and target not in targets:
            targets.append(target)
    return targets


def _ids_of_type(itineraries: list[dict], item_type: str) -> list[str]:
    found: list[str] = []
    for plan in itineraries:
        for item in plan.get("items") or []:
            if item.get("item_type") == item_type and item.get("source_candidate_id"):
                candidate_id = item["source_candidate_id"]
                if candidate_id not in found:
                    found.append(candidate_id)
    return found


def interpret_revision(message: str, state: dict, *, replan_count: int, max_replan: int) -> dict:
    if replan_count >= max_replan:
        return {
            "supervisor_decision": SupervisorDecision.ASK_USER.value,
            "summary": (
                "I couldn't revise this plan again without dropping a constraint. "
                "Tell me which limit to relax."
            ),
            "status": "awaiting_approval",
        }
    text = _flat(message)
    constraints = dict(state.get("constraints") or {})
    rejected = list(state.get("rejected_candidate_ids") or [])
    itineraries = list(state.get("itineraries") or [])
    targets: list[str] = []
    if any(phrase in text for phrase in ("cheaper", "less expensive", "lower budget")):
        current = constraints.get("budget_max")
        if isinstance(current, (int, float)) and current > 0:
            tightened = round(float(current) * 0.8, 2)
            constraints["budget_max"] = tightened
            constraints["budget_amount"] = tightened
            constraints["budget_kind"] = "maximum"
    elif any(phrase in text for phrase in ("restaurant", "dinner", "place to eat")):
        targets = ["restaurant"]
        rejected.extend(_ids_of_type(itineraries, "restaurant"))
    elif any(phrase in text for phrase in ("quieter", "activity", "event", "show", "jazz", "comedy")):
        targets = ["events"]
        rejected.extend(_ids_of_type(itineraries, "event"))
        if "quieter" in text and "live_music" not in (constraints.get("categories") or []):
            constraints["categories"] = [*(constraints.get("categories") or []), "live_music"]
    elif any(phrase in text for phrase in ("later", "one hour")):
        constraints["shift_minutes"] = int(constraints.get("shift_minutes") or 0) + 60
    else:
        targets = ["restaurant", "events"]
        rejected.extend(_ids_of_type(itineraries, "restaurant"))
        rejected.extend(_ids_of_type(itineraries, "event"))
    tasks = _reopen(list(state.get("tasks") or []), targets)
    return {
        "constraints": constraints,
        "tasks": tasks,
        "rejected_candidate_ids": rejected,
        "restaurant_research": None if "restaurant" in targets else state.get("restaurant_research"),
        "event_research": None if "events" in targets else state.get("event_research"),
        "supervisor_decision": SupervisorDecision.REPLAN.value,
        "status": "replanning",
        "replan_count": replan_count + 1,
        "revision_message": message.strip(),
    }


def apply_critic_replan(state: dict, *, max_replan: int) -> dict:
    replan_count = int(state.get("replan_count") or 0)
    if replan_count >= max_replan:
        return {
            "supervisor_decision": SupervisorDecision.PARTIAL_RESULT.value,
            "limiting_constraint": state.get("limiting_constraint")
            or "the revision limit",
        }
    issues = list((state.get("critic_result") or {}).get("issues") or [])
    issues.extend(
        {"target_task": _violation_target(item.get("type"))}
        for item in (state.get("verification") or {}).get("violations") or []
    )
    targets = targets_for_issues(issues)
    rejected = list(state.get("rejected_candidate_ids") or [])
    added = False
    for candidate_id in _ids_of_type(list(state.get("itineraries") or []), "restaurant"):
        if "restaurant" in targets and candidate_id not in rejected:
            rejected.append(candidate_id)
            added = True
    for candidate_id in _ids_of_type(list(state.get("itineraries") or []), "event"):
        if "events" in targets and candidate_id not in rejected:
            rejected.append(candidate_id)
            added = True
    if not targets or not added:
        return {
            "supervisor_decision": SupervisorDecision.PARTIAL_RESULT.value,
            "limiting_constraint": _limiting_text(issues),
        }
    return {
        "tasks": _reopen(list(state.get("tasks") or []), targets),
        "rejected_candidate_ids": rejected,
        "restaurant_research": None if "restaurant" in targets else state.get("restaurant_research"),
        "event_research": None if "events" in targets else state.get("event_research"),
        "supervisor_decision": SupervisorDecision.REPLAN.value,
        "replan_count": replan_count + 1,
        "status": "replanning",
    }


def _violation_target(kind: str | None) -> str | None:
    if kind in {"DIETARY_CONSTRAINT", "BUDGET"}:
        return "restaurant"
    if kind in {"END_TIME_EXCEEDED", "EVENT_TIME"}:
        return "events"
    return None


def _limiting_text(issues: list[dict]) -> str:
    if not issues:
        return "the combined constraints"
    message = issues[0].get("message")
    return str(message or "the combined constraints")


def _reopen(tasks: list[dict], targets: list[str]) -> list[dict]:
    updated: list[dict] = []
    for task in tasks:
        if task["task_id"] in targets or (
            task["task_id"] == "itinerary" and targets is not None
        ):
            updated.append(
                {
                    **task,
                    "status": TaskStatus.PENDING.value,
                    "error": None,
                    "result": None,
                }
            )
        else:
            updated.append(task)
    return updated


def research_epoch() -> float:
    return datetime.now().timestamp()
