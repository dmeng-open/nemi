"""Baseline and live runners on the same frozen cases.

The baseline calls regex constraints, ``decompose_tasks``, ranker order,
``build_itineraries``, ``validate_itinerary``, and ``critique()``.
Calendar writes are the restaurant and activity blocks one approve would schedule.
Travel blocks are not writes.

The live path calls a replaceable structured-output port for supervisor, research,
and critic. It does not send itinerary-planner or verifier prompt text, and it does
not read PLANNER_MODEL. Importing this module does not call OpenAI.
"""

from typing import Protocol

from app.agents.itinerary.artifacts import (
    CriticResult,
    EventResearchArtifact,
    Itinerary,
    ItineraryConstraints,
    ResearchCandidate,
    RestaurantResearchArtifact,
    TaskStatus,
    VerificationResult,
    dump,
)
from app.agents.itinerary.engine import build_itineraries, critique, validate_itinerary
from app.agents.itinerary.judgments import (
    CriticJudgment,
    candidate_user,
    critic_system,
    critic_user,
    event_system,
    merge_critic,
    restaurant_system,
    selected_id_schema,
    supervisor_schema,
    supervisor_system,
)
from app.agents.itinerary.routing import (
    apply_critic_replan,
    decompose_tasks,
    parse_itinerary_request,
)
from app.agents.itinerary.structured_output import StructuredOutputPort
from app.domain.preferences import UserPreferences
from app.domain.ranking import RankingContext, RankingWeights
from app.services.ranking.heuristic import HeuristicRanker
from evals.multi_llm.fixtures import GoldenCase
from evals.multi_llm.gate import model_evals_enabled
from evals.multi_llm.outcome import Outcome
from pydantic import BaseModel, ValidationError

# The shared cap stays in the unit tests. This runner only allows the one replan
# the golden replan case needs, using the same ceiling the product already uses.
_REPLAN_CEILING = 3
_ALLOWED_ROLES = frozenset({"supervisor", "research", "critic"})
_REQUIRED_TASKS = {
    "calendar": ("calendar_analysis", "calendar_analysis"),
    "restaurant": ("restaurant_research", "restaurant_research"),
    "events": ("event_research", "event_research"),
    "itinerary": ("itinerary_generation", "itinerary_planner"),
}


class Judgments(Protocol):
    async def supervisor(self, constraints: ItineraryConstraints) -> str | None:
        """Return an error when the live proposal cannot be kept. None accepts code tasks."""

    async def select_restaurant(self, ranked: list[ResearchCandidate]) -> str: ...

    async def select_event(self, ranked: list[ResearchCandidate]) -> str: ...

    async def critic(
        self,
        *,
        code: CriticResult,
        verification: VerificationResult,
        itinerary: Itinerary,
    ) -> CriticResult: ...


class BaselineJudgments:
    async def supervisor(self, constraints: ItineraryConstraints) -> str | None:
        del constraints
        return None

    async def select_restaurant(self, ranked: list[ResearchCandidate]) -> str:
        return ranked[0].candidate.id

    async def select_event(self, ranked: list[ResearchCandidate]) -> str:
        return ranked[0].candidate.id

    async def critic(
        self,
        *,
        code: CriticResult,
        verification: VerificationResult,
        itinerary: Itinerary,
    ) -> CriticResult:
        del itinerary
        return merge_critic(code, verification, None)


class LiveJudgments:
    def __init__(self, port: StructuredOutputPort, request_text: str) -> None:
        self._port = port
        self._request_text = request_text

    async def supervisor(self, constraints: ItineraryConstraints) -> str | None:
        schema = supervisor_schema(constraints)
        parsed = await self._complete("supervisor", supervisor_system(), self._request_text, schema)
        try:
            proposal = schema.model_validate(parsed)
        except ValidationError:
            return "supervisor output did not match the task schema"
        return _supervisor_error(proposal)

    async def select_restaurant(self, ranked: list[ResearchCandidate]) -> str:
        return await self._select(ranked, restaurant_system())

    async def select_event(self, ranked: list[ResearchCandidate]) -> str:
        return await self._select(ranked, event_system())

    async def _select(self, ranked: list[ResearchCandidate], system: str) -> str:
        allowed = {item.candidate.id for item in ranked}
        schema = selected_id_schema(allowed)
        parsed = await self._complete("research", system, candidate_user(ranked), schema)
        try:
            chosen = schema.model_validate(parsed)
        except ValidationError:
            return ""
        return str(chosen.selected_id)  # type: ignore[attr-defined]

    async def critic(
        self,
        *,
        code: CriticResult,
        verification: VerificationResult,
        itinerary: Itinerary,
    ) -> CriticResult:
        parsed = await self._complete(
            "critic",
            critic_system(),
            critic_user(itinerary, code, verification),
            CriticJudgment,
        )
        try:
            model = CriticJudgment.model_validate(parsed)
        except ValidationError:
            model = None
        return merge_critic(code, verification, model)

    async def _complete(
        self,
        role: str,
        system_text: str,
        user_text: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        if not model_evals_enabled():
            raise RuntimeError("Live multi-LLM golden eval was not run.")
        if role not in _ALLOWED_ROLES:
            raise RuntimeError(f"Refusing model role {role}.")
        completion = await self._port.complete(
            role=role,
            system=system_text,
            user=user_text,
            schema=schema,
            deterministic=_live_has_no_deterministic,
        )
        return completion.parsed  # type: ignore[return-value]


def _live_has_no_deterministic() -> object:
    raise RuntimeError("Live multi-LLM golden eval was not run.")


async def run_baseline(case: GoldenCase) -> Outcome:
    return await _run(case, BaselineJudgments())


async def run_live(case: GoldenCase, port: StructuredOutputPort) -> Outcome:
    if not model_evals_enabled():
        raise RuntimeError("Live multi-LLM golden eval was not run.")
    return await _run(case, LiveJudgments(port, case.request_text))


async def _run(case: GoldenCase, judgments: Judgments) -> Outcome:
    constraints = parse_itinerary_request(
        case.request_text,
        today=case.today,
        timezone=case.timezone,
    )
    if constraints.needs_clarification or constraints.date_start is None:
        raise RuntimeError("golden fixture resolved no date")
    if constraints.budget_max is None:
        raise RuntimeError("golden fixture is missing a budget")
    tasks = decompose_tasks(constraints)
    task_ids = [item["task_id"] for item in tasks]
    if task_ids != ["calendar", "restaurant", "events", "itinerary"]:
        raise RuntimeError(f"decompose_tasks returned {task_ids}")
    supervisor_error = await judgments.supervisor(constraints)
    if supervisor_error:
        return _blank(case, constraints, tasks, (supervisor_error,))

    preferences = UserPreferences()
    restaurants = _filter_restaurants(case.restaurants, constraints, set(), preferences)
    events = _filter_events(case.events, constraints, set(), preferences)
    restaurants.candidate_restaurants = await _rerank(
        restaurants.candidate_restaurants, constraints, preferences, cuisine=True
    )
    events.candidate_events = await _rerank(
        events.candidate_events, constraints, preferences, cuisine=False
    )
    wave1_restaurant_ids = {item.candidate.id for item in restaurants.candidate_restaurants}
    wave1_event_ids = {item.candidate.id for item in events.candidate_events}

    chosen: set[str] = set()
    errors: list[str] = []
    meal = await _take(restaurants.candidate_restaurants, judgments.select_restaurant, "restaurant", chosen, errors)
    activity = await _take(events.candidate_events, judgments.select_event, "event", chosen, errors)
    itinerary = _build(constraints, restaurants, events, meal, activity, set())
    completed = _completed(tasks)
    status = _status_map(completed)
    if itinerary is None:
        return _finish(
            case,
            constraints,
            itinerary=None,
            chosen=chosen,
            errors=errors,
            meal=meal,
            status=status,
            reopened=(),
            new_ids=(),
            stopped=True,
            replan_attempted=False,
        )

    verification = validate_itinerary(itinerary, constraints=constraints, calendar=None)
    code = critique(itinerary, constraints=constraints, restaurants=restaurants)
    judged = await judgments.critic(code=code, verification=verification, itinerary=itinerary)
    state = _critic_state(completed, itinerary, judged, verification, restaurants, events, rejected=[])
    if judged.status != "REVISE":
        return _finish(
            case,
            constraints,
            itinerary=itinerary,
            chosen=chosen,
            errors=errors,
            meal=meal,
            status=status,
            reopened=(),
            new_ids=(),
            stopped=True,
            replan_attempted=False,
        )

    update = apply_critic_replan(state, max_replan=_REPLAN_CEILING)
    reopened = _reopened(status, _status_map(update.get("tasks") or completed))
    after_status = _status_map(update.get("tasks") or completed)
    if update.get("supervisor_decision") != "REPLAN":
        return _finish(
            case,
            constraints,
            itinerary=itinerary,
            chosen=chosen,
            errors=errors,
            meal=meal,
            status=after_status,
            reopened=reopened,
            new_ids=(),
            stopped=True,
            replan_attempted=False,
        )

    rejected = set(update.get("rejected_candidate_ids") or [])
    next_restaurants = restaurants
    next_events = events
    new_ids: set[str] = set()
    if "restaurant" in reopened:
        next_restaurants = _filter_restaurants(case.restaurants, constraints, rejected, preferences)
        next_restaurants.candidate_restaurants = await _rerank(
            next_restaurants.candidate_restaurants, constraints, preferences, cuisine=True
        )
        new_ids |= {item.candidate.id for item in next_restaurants.candidate_restaurants} - wave1_restaurant_ids
        meal = await _take(
            next_restaurants.candidate_restaurants,
            judgments.select_restaurant,
            "restaurant",
            chosen,
            errors,
        )
    if "events" in reopened:
        next_events = _filter_events(case.events, constraints, rejected, preferences)
        next_events.candidate_events = await _rerank(
            next_events.candidate_events, constraints, preferences, cuisine=False
        )
        new_ids |= {item.candidate.id for item in next_events.candidate_events} - wave1_event_ids
        activity = await _take(
            next_events.candidate_events,
            judgments.select_event,
            "event",
            chosen,
            errors,
        )
    second = _build(constraints, next_restaurants, next_events, meal, activity, rejected)
    final = second or itinerary
    stopped = True
    if second is not None:
        second_verification = validate_itinerary(second, constraints=constraints, calendar=None)
        second_code = critique(second, constraints=constraints, restaurants=next_restaurants)
        second_judged = await judgments.critic(
            code=second_code,
            verification=second_verification,
            itinerary=second,
        )
        if second_judged.status == "REVISE":
            follow = apply_critic_replan(
                _critic_state(
                    update.get("tasks") or completed,
                    second,
                    second_judged,
                    second_verification,
                    next_restaurants,
                    next_events,
                    rejected=list(rejected),
                    replan_count=int(update.get("replan_count") or 1),
                ),
                max_replan=_REPLAN_CEILING,
            )
            stopped = follow.get("supervisor_decision") != "REPLAN"
    elif new_ids:
        stopped = False
    return _finish(
        case,
        constraints,
        itinerary=final,
        chosen=chosen,
        errors=errors,
        meal=meal,
        status=after_status,
        reopened=reopened,
        new_ids=tuple(sorted(new_ids)),
        stopped=stopped,
        replan_attempted=True,
    )


def _supervisor_error(proposal: BaseModel) -> str | None:
    seen: set[str] = set()
    for task in proposal.tasks:
        expected = _REQUIRED_TASKS.get(task.task_id)
        if expected is None:
            return f"supervisor proposed unknown task {task.task_id}"
        task_type, agent = expected
        if task.task_type != task_type or task.assigned_agent != agent:
            return f"supervisor mismatched {task.task_id}"
        if any(item not in _REQUIRED_TASKS for item in task.dependencies):
            return f"supervisor dependency for {task.task_id} is outside the known tasks"
        seen.add(task.task_id)
    missing = set(_REQUIRED_TASKS) - seen
    if missing:
        return "supervisor omitted " + ", ".join(sorted(missing))
    return None


def _filter_restaurants(candidates, constraints, rejected: set[str], preferences: UserPreferences):
    from app.agents.itinerary.graph import _restaurant_artifact

    return _restaurant_artifact(list(candidates), constraints, preferences, rejected, [])


def _filter_events(candidates, constraints, rejected: set[str], preferences: UserPreferences):
    from app.agents.itinerary.graph import _event_artifact

    return _event_artifact(list(candidates), constraints, preferences, rejected, [])


async def _rerank(items, constraints, preferences: UserPreferences, *, cuisine: bool):
    if not items:
        return items
    context = RankingContext(
        requested_categories=list(constraints.cuisines if cuisine else constraints.categories),
        preferred_categories=list(
            preferences.preferred_cuisines if cuisine else preferences.preferred_event_categories
        ),
        disliked_categories=list(preferences.disliked_categories),
        budget_max=constraints.budget_max,
        max_travel_minutes=constraints.hard_travel_minutes,
        timezone=constraints.timezone,
        calendar_read="unavailable",
    )
    ranked = await HeuristicRanker(RankingWeights()).rank([item.candidate for item in items], context)
    scores = {item.candidate.id: item.final_score for item in ranked}
    updated = [
        item.model_copy(update={"score": scores.get(item.candidate.id, item.score)}) for item in items
    ]
    updated.sort(key=lambda item: (-item.score, item.candidate.id))
    return updated


async def _take(ranked, choose, label: str, chosen: set[str], errors: list[str]):
    if not ranked:
        errors.append(f"no filtered {label} candidates")
        return None
    selected_id = await choose(ranked)
    chosen.add(selected_id)
    match = next((item for item in ranked if item.candidate.id == selected_id), None)
    if match is None:
        errors.append(f"{label} selected_id {selected_id} is outside the filtered set")
    return match


def _build(
    constraints: ItineraryConstraints,
    restaurants: RestaurantResearchArtifact,
    events: EventResearchArtifact,
    meal: ResearchCandidate | None,
    activity: ResearchCandidate | None,
    rejected: set[str],
) -> Itinerary | None:
    if meal is None or activity is None:
        return None
    plans = build_itineraries(
        constraints=constraints,
        calendar=None,
        restaurants=restaurants.model_copy(update={"candidate_restaurants": [meal]}),
        events=events.model_copy(update={"candidate_events": [activity]}),
        rejected_ids=rejected,
    )
    return plans[0] if plans else None


def _completed(tasks: list[dict]) -> list[dict]:
    return [{**task, "status": TaskStatus.COMPLETED.value, "error": None, "result": None} for task in tasks]


def _status_map(tasks: list[dict]) -> dict[str, str]:
    return {task["task_id"]: str(task["status"]) for task in tasks}


def _reopened(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        task_id
        for task_id, status in after.items()
        if status == TaskStatus.PENDING.value and before.get(task_id) != TaskStatus.PENDING.value
    )


def _critic_state(
    tasks,
    itinerary: Itinerary,
    judged: CriticResult,
    verification: VerificationResult,
    restaurants: RestaurantResearchArtifact,
    events: EventResearchArtifact,
    *,
    rejected: list[str],
    replan_count: int = 0,
) -> dict:
    return {
        "replan_count": replan_count,
        "tasks": tasks,
        "itineraries": [dump(itinerary)],
        "critic_result": dump(judged),
        "verification": dump(verification),
        "rejected_candidate_ids": list(rejected),
        "restaurant_research": dump(restaurants),
        "event_research": dump(events),
    }


def _calendar_writes(itinerary: Itinerary | None) -> int:
    if itinerary is None:
        return 0
    return sum(1 for item in itinerary.items if item.item_type in {"restaurant", "event"})


def _blank(case: GoldenCase, constraints, tasks, errors: tuple[str, ...]) -> Outcome:
    return Outcome(
        itinerary=None,
        constraints=constraints,
        illegal_ids=case.illegal_ids,
        selection_errors=errors,
        task_status=_status_map(tasks),
        dataset_version=case.dataset_version,
    )


def _finish(
    case: GoldenCase,
    constraints,
    *,
    itinerary: Itinerary | None,
    chosen: set[str],
    errors: list[str],
    meal: ResearchCandidate | None,
    status: dict[str, str],
    reopened: tuple[str, ...],
    new_ids: tuple[str, ...],
    stopped: bool,
    replan_attempted: bool,
) -> Outcome:
    source_ids = set()
    if itinerary is not None:
        source_ids = {item.source_candidate_id for item in itinerary.items if item.source_candidate_id}
    return Outcome(
        itinerary=itinerary,
        constraints=constraints,
        illegal_ids=case.illegal_ids,
        chosen_ids=frozenset(chosen | source_ids),
        selection_errors=tuple(errors),
        meal_dietary=None if meal is None else meal.dietary,
        write_count=_calendar_writes(itinerary),
        task_status=status,
        reopened_task_ids=reopened,
        second_wave_new_ids=new_ids,
        stopped=stopped,
        replan_attempted=replan_attempted,
        dataset_version=case.dataset_version,
    )

