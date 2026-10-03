import asyncio
import operator
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as clock_time
from typing import Annotated, Any, TypedDict
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from app.agents.nodes import EventLog
from app.agents.itinerary.artifacts import (
    CalendarAnalysisResult,
    CriticResult,
    EventResearchArtifact,
    ExecutionActionResult,
    ExecutionReport,
    Itinerary,
    ItineraryConstraints,
    ResearchCandidate,
    RestaurantResearchArtifact,
    VerificationResult,
    dump,
)
from app.agents.itinerary.engine import (
    build_itineraries,
    critique,
    dietary_status,
    limiting_message,
    parallel_speedup,
    review_semantics,
    validate_itinerary,
)
from app.agents.itinerary.failure import (
    CALENDAR_READ_FAILURE,
    CALENDAR_WRITE_FAILURE,
    CRITIC_REJECT,
    EVENT_PROVIDER_TIMEOUT,
    PLANNER_INVALID_OUTPUT,
    RESTAURANT_PROVIDER_FAILURE,
    SUPERVISOR_RETRY,
    active_injection,
)
from app.agents.itinerary.permissions import authorize, note_tool_call
from app.agents.itinerary.prompts import (
    CRITIC_POLICY_VERSION,
    EVENT_POLICY_VERSION,
    PLANNER_POLICY_VERSION,
    RESTAURANT_POLICY_VERSION,
    SUPERVISOR_POLICY_VERSION,
    VERIFIER_POLICY_VERSION,
)
from app.agents.itinerary.reducers import merge_tasks
from app.agents.itinerary.routing import (
    apply_critic_replan,
    decide_branch_retry,
    decompose_tasks,
    interpret_revision,
    mark_retry,
    parse_itinerary_request,
    pending_research,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.exceptions import ProviderError, ScheduleConflictError
from app.domain.preferences import UserPreferences
from app.domain.ranking import RankingContext
from app.integrations.events.models import EventSearchQuery
from app.integrations.restaurants.models import RestaurantSearchQuery
from app.services.calendar.blocks import schedule_block
from app.services.calendar.windows import free_windows_for_range
from app.services.ranking.heuristic import HeuristicRanker


class RootPlanningState(TypedDict, total=False):
    session_id: str
    user_id: str
    user_request: str
    constraints: dict | None
    user_preferences: dict | None
    tasks: Annotated[list[dict], merge_tasks]
    calendar_result: dict | None
    restaurant_research: dict | None
    event_research: dict | None
    itineraries: list[dict]
    verification: dict | None
    semantic_review: dict | None
    critic_result: dict | None
    approved: bool
    approved_itinerary_id: str | None
    replan_count: int
    supervisor_steps: int
    supervisor_decision: str
    errors: Annotated[list[dict], operator.add]
    trace_events: Annotated[list[dict], operator.add]
    branch_reports: Annotated[list[dict], operator.add]
    status: str
    clarification_question: str | None
    summary: str | None
    error_code: str | None
    rejected_candidate_ids: list[str]
    execution_result: dict | None
    revision_message: str | None
    research_started_at: float | None
    research_wave: int
    parallel_speedup: float | None
    limiting_constraint: str | None


@dataclass
class ItineraryDeps:
    events: object
    restaurants: object
    calendar: object
    ranker: HeuristicRanker
    log: EventLog
    clock: Clock
    zone: ZoneInfo
    load_preferences: Callable[[], Awaitable[UserPreferences]]
    settings: Settings
    event_provider_name: str = "mock"
    place_provider_name: str = "mock"
    branch_delay_seconds: float = 0.0
    counters: dict[str, int] = field(default_factory=dict)
    tool_counts: dict[str, int] = field(default_factory=dict)
    write_attempts: int = 0
    extra_event_providers: list[Any] = field(default_factory=list)
    extra_restaurant_providers: list[Any] = field(default_factory=list)
    invalid_planner_attempts: int = 0
    session_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _ms(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


def _task(state: dict, task_type: str) -> dict:
    for task in state.get("tasks") or []:
        if task.get("task_type") == task_type:
            return task
    return {"task_id": task_type, "task_type": task_type, "status": "pending", "retry_count": 0}


async def _use_tool(deps: ItineraryDeps, agent: str, tool_name: str, operation):
    authorize(agent, tool_name)
    note_tool_call(
        deps.tool_counts,
        agent,
        limit=deps.settings.max_tool_calls_per_agent,
    )
    return await operation()


async def _trace(
    deps: ItineraryDeps,
    agent: str,
    status: str,
    started: float,
    detail: str,
    tools: list[str],
    *,
    error: str | None = None,
    retry: int = 0,
    policy: str | None = None,
) -> dict:
    duration = _ms(started)
    deps.counters[agent] = deps.counters.get(agent, 0) + 1
    event_status = "failed" if status == "failed" else "completed"
    await deps.log.emit(
        f"agent_{agent}",
        event_status,
        {"agent": agent, "detail": detail, "tools": tools},
        duration_ms=duration,
        error_code=error,
    )
    span = getattr(deps.log, "span", None)
    if span is not None:
        await span(
            agent=agent,
            status=status,
            duration_ms=duration,
            detail=detail,
            tools=tools,
            error_code=error,
            retry_count=retry,
            policy_version=policy,
            model="deterministic",
        )
    return {
        "agent": agent,
        "status": status,
        "duration_ms": duration,
        "detail": detail,
        "tools": tools,
        "error": error,
        "model": "deterministic",
        "policy_version": policy,
        "retry_count": retry,
    }


def _send_ready(state: RootPlanningState):
    ready = pending_research(list(state.get("tasks") or []))
    if not ready:
        return "aggregate"
    return [Send(task["task_type"], state) for task in ready]


def compile_itinerary_graph(deps: ItineraryDeps, checkpointer=None):
    graph = StateGraph(RootPlanningState)

    async def understand(state: RootPlanningState) -> dict:
        started = time.perf_counter()
        constraints = parse_itinerary_request(
            state.get("user_request") or "",
            today=deps.clock.now().astimezone(deps.zone).date(),
            timezone=deps.zone.key,
        )
        status = "awaiting_clarification" if constraints.needs_clarification else "processing"
        trace = await _trace(
            deps,
            "supervisor",
            "completed",
            started,
            "Understanding your plan",
            [],
            policy=SUPERVISOR_POLICY_VERSION,
        )
        await deps.log.emit(
            "constraints_parsed",
            "completed",
            {"plan_type": "itinerary", "needs_clarification": constraints.needs_clarification},
        )
        return {
            "constraints": dump(constraints),
            "status": status,
            "summary": constraints.summary,
            "clarification_question": constraints.clarification_question,
            "trace_events": [trace],
            "replan_count": 0,
            "supervisor_steps": 0,
            "research_wave": 0,
            "rejected_candidate_ids": [],
        }

    async def load_preferences(state: RootPlanningState) -> dict:
        preferences = await deps.load_preferences()
        constraints = ItineraryConstraints.model_validate(state["constraints"])
        if preferences.max_travel_minutes:
            constraints.max_travel_minutes = preferences.max_travel_minutes
            constraints.hard_travel_minutes = preferences.max_travel_minutes + 15
        if constraints.budget_max is None and preferences.default_budget:
            constraints.budget_amount = preferences.default_budget
            constraints.budget_max = preferences.default_budget
            constraints.budget_kind = "maximum"
        return {
            "user_preferences": preferences.model_dump(mode="json"),
            "constraints": dump(constraints),
        }

    async def decompose(state: RootPlanningState) -> dict:
        started = time.perf_counter()
        constraints = ItineraryConstraints.model_validate(state["constraints"])
        tasks = decompose_tasks(constraints)
        steps = int(state.get("supervisor_steps") or 0) + 1
        if constraints.wants_restaurant and constraints.wants_event:
            detail = "Understanding your plan"
        elif constraints.wants_restaurant:
            detail = "Understanding your dinner plan"
        else:
            detail = "Understanding your activity plan"
        trace = await _trace(
            deps,
            "supervisor",
            "completed",
            started,
            detail,
            [],
            policy=SUPERVISOR_POLICY_VERSION,
        )
        return {
            "tasks": tasks,
            "supervisor_steps": steps,
            "supervisor_decision": "CONTINUE",
            "research_started_at": time.time(),
            "research_wave": int(state.get("research_wave") or 0),
            "trace_events": [trace],
        }

    async def calendar_analysis(state: RootPlanningState) -> dict:
        return await _calendar(state, deps)

    async def restaurant_research(state: RootPlanningState) -> dict:
        return await _restaurants(state, deps)

    async def event_research(state: RootPlanningState) -> dict:
        return await _events(state, deps)

    async def aggregate(state: RootPlanningState) -> dict:
        tasks = list(state.get("tasks") or [])
        steps = int(state.get("supervisor_steps") or 0)
        wave = int(state.get("research_wave") or 0)
        retry_id = decide_branch_retry(tasks)
        reports = [
            item
            for item in state.get("branch_reports") or []
            if item.get("wave") == wave
        ]
        started_at = state.get("research_started_at") or time.time()
        wall_ms = max(1, int((time.time() - started_at) * 1000))
        speedup = parallel_speedup([int(item["duration_ms"]) for item in reports], wall_ms)
        if retry_id and steps < deps.settings.max_supervisor_steps:
            return {
                "tasks": mark_retry(tasks, retry_id),
                "supervisor_decision": "RETRY_BRANCH",
                "supervisor_steps": steps + 1,
                "research_started_at": time.time(),
                "research_wave": wave + 1,
                "parallel_speedup": speedup,
            }
        if state.get("status") == "awaiting_location" or state.get("error_code") in {
            "location_required",
            "city_required",
        }:
            return {
                "supervisor_decision": "ASK_USER",
                "parallel_speedup": speedup,
            }
        research = [
            task
            for task in tasks
            if task["task_type"] != "itinerary_generation"
        ]
        if research and all(task["status"] == "failed" for task in research):
            return {"supervisor_decision": "FAIL", "parallel_speedup": speedup}
        return {"supervisor_decision": "CONTINUE", "parallel_speedup": speedup}

    async def plan(state: RootPlanningState) -> dict:
        return await _plan(state, deps)

    async def constraint_engine(state: RootPlanningState) -> dict:
        constraints = ItineraryConstraints.model_validate(state["constraints"])
        calendar = _calendar_model(state.get("calendar_result"))
        kept: list[dict] = []
        violations = []
        for raw in state.get("itineraries") or []:
            itinerary = Itinerary.model_validate(raw)
            result = validate_itinerary(itinerary, constraints=constraints, calendar=calendar)
            if result.valid:
                kept.append(dump(itinerary))
            else:
                violations.extend(result.violations)
        verification = VerificationResult(
            valid=bool(kept),
            violations=violations,
            limiting_constraint=violations[0].message if violations and not kept else None,
        )
        update: dict[str, Any] = {
            "itineraries": kept,
            "verification": dump(verification),
        }
        if not kept and violations:
            update["limiting_constraint"] = violations[0].message
        return update

    async def verify_semantics(state: RootPlanningState) -> dict:
        started = time.perf_counter()
        constraints = ItineraryConstraints.model_validate(state["constraints"])
        itineraries = [Itinerary.model_validate(item) for item in state.get("itineraries") or []]
        tasks = {task["task_id"]: task for task in state.get("tasks") or []}
        review = review_semantics(
            itineraries,
            constraints=constraints,
            events_failed=tasks.get("events", {}).get("status") == "failed",
            restaurants_failed=tasks.get("restaurant", {}).get("status") == "failed",
        )
        detail = "Checked the plan against your request" if review.complete else "The plan is only partial"
        trace = await _trace(
            deps,
            "verifier",
            "completed",
            started,
            detail,
            [],
            policy=VERIFIER_POLICY_VERSION,
        )
        return {"semantic_review": dump(review), "trace_events": [trace]}

    async def critique_plan(state: RootPlanningState) -> dict:
        started = time.perf_counter()
        constraints = ItineraryConstraints.model_validate(state["constraints"])
        itineraries = [Itinerary.model_validate(item) for item in state.get("itineraries") or []]
        restaurants = _restaurant_model(state.get("restaurant_research"))
        force = (
            active_injection(deps.settings) == CRITIC_REJECT
            and int(state.get("replan_count") or 0) == 0
        )
        result = critique(
            itineraries[0] if itineraries else None,
            constraints=constraints,
            restaurants=restaurants,
            force_reject=force,
        )
        if not itineraries and not force:
            result = CriticResult(status="PASS", issues=[])
        detail = "Reviewing plan quality" if result.status == "PASS" else "Asking for a revision"
        trace = await _trace(
            deps,
            "critic",
            "completed",
            started,
            detail,
            [],
            policy=CRITIC_POLICY_VERSION,
            retry=int(state.get("replan_count") or 0),
        )
        return {"critic_result": dump(result), "trace_events": [trace]}

    async def apply_replan(state: RootPlanningState) -> dict:
        started = time.perf_counter()
        update = apply_critic_replan(state, max_replan=deps.settings.max_replan_attempts)
        update["supervisor_steps"] = int(state.get("supervisor_steps") or 0) + 1
        update["research_started_at"] = time.time()
        update["research_wave"] = int(state.get("research_wave") or 0) + 1
        trace = await _trace(
            deps,
            "supervisor",
            "completed",
            started,
            "Replanning the part that failed",
            [],
            policy=SUPERVISOR_POLICY_VERSION,
            retry=int(update.get("replan_count") or state.get("replan_count") or 0),
        )
        update["trace_events"] = [trace]
        return update

    async def prepare_approval(state: RootPlanningState) -> dict:
        count = len(state.get("itineraries") or [])
        summary = state.get("summary") or "Here is the plan I built."
        if state.get("supervisor_decision") != "ASK_USER":
            if count == 1:
                summary = "Here's the plan I built."
            elif count > 1:
                summary = f"Here are {count} plans I built."
        return {"status": "awaiting_approval", "summary": summary}

    async def human_approval(state: RootPlanningState) -> dict:
        decision = interrupt(
            {
                "kind": "itinerary_approval",
                "itinerary_ids": [
                    item["itinerary_id"] for item in state.get("itineraries") or []
                ],
            }
        )
        if not isinstance(decision, dict):
            decision = {"action": "cancel"}
        action = decision.get("action")
        if action == "approve":
            options = list(state.get("itineraries") or [])
            ids = [item["itinerary_id"] for item in options]
            chosen = decision.get("itinerary_id")
            if chosen not in ids:
                if chosen or len(ids) != 1:
                    return {
                        "approved": False,
                        "status": "awaiting_approval",
                        "error_code": "invalid_selection",
                        "supervisor_decision": "ASK_USER",
                    }
                chosen = ids[0]
            return {
                "approved": True,
                "approved_itinerary_id": chosen,
                "status": "scheduling",
                "error_code": None,
            }
        if action == "revise":
            update = interpret_revision(
                str(decision.get("message") or ""),
                state,
                replan_count=int(state.get("replan_count") or 0),
                max_replan=deps.settings.max_replan_attempts,
            )
            update["supervisor_steps"] = int(state.get("supervisor_steps") or 0) + 1
            update["research_started_at"] = time.time()
            update["research_wave"] = int(state.get("research_wave") or 0) + 1
            return update
        return {"approved": False, "status": "cancelled"}

    async def execute(state: RootPlanningState) -> dict:
        return await _execute(state, deps)

    async def finalize(state: RootPlanningState) -> dict:
        status = state.get("status") or "processing"
        if status in {"processing", "replanning"}:
            if state.get("error_code") in {"location_required", "city_required"}:
                status = "awaiting_location"
            elif state.get("itineraries"):
                status = "awaiting_approval"
            else:
                status = "no_matches"
        constraints = None
        if state.get("constraints"):
            constraints = ItineraryConstraints.model_validate(state["constraints"])
        verification = VerificationResult.model_validate(state.get("verification") or {"valid": False})
        summary = state.get("summary")
        if status == "no_matches" and constraints is not None:
            summary = limiting_message(constraints, verification)
        return {
            "status": status,
            "summary": summary,
            "limiting_constraint": state.get("limiting_constraint") or verification.limiting_constraint,
        }

    def after_understand(state: RootPlanningState) -> str:
        if state.get("status") == "awaiting_clarification":
            return "stop"
        return "continue"

    def after_aggregate(state: RootPlanningState):
        decision = state.get("supervisor_decision")
        if decision == "RETRY_BRANCH":
            return _send_ready(state)
        if decision in {"ASK_USER", "FAIL"}:
            return "finalize"
        return "plan"

    def after_critic(state: RootPlanningState) -> str:
        if int(state.get("supervisor_steps") or 0) >= deps.settings.max_supervisor_steps:
            return "prepare_approval" if state.get("itineraries") else "finalize"
        critic = state.get("critic_result") or {}
        verification = state.get("verification") or {}
        needs_replan = critic.get("status") == "REVISE" or (
            verification.get("valid") is False and bool(state.get("itineraries"))
        )
        if needs_replan and int(state.get("replan_count") or 0) < deps.settings.max_replan_attempts:
            return "apply_replan"
        if state.get("itineraries"):
            return "prepare_approval"
        return "finalize"

    def after_replan(state: RootPlanningState):
        over_step_cap = int(state.get("supervisor_steps") or 0) > deps.settings.max_supervisor_steps
        if state.get("supervisor_decision") != "REPLAN" or over_step_cap:
            return "prepare_approval" if state.get("itineraries") else "finalize"
        return _send_ready(state)

    def after_human(state: RootPlanningState):
        if state.get("status") == "scheduling":
            return "execute"
        if state.get("status") == "cancelled":
            return END
        if state.get("supervisor_decision") == "REPLAN" and state.get("status") == "replanning":
            return _send_ready(state)
        if state.get("itineraries") and state.get("status") == "awaiting_approval":
            return "prepare_approval"
        return "finalize"

    graph.add_node("understand", understand)
    graph.add_node("load_preferences", load_preferences)
    graph.add_node("decompose", decompose)
    graph.add_node("calendar_analysis", calendar_analysis)
    graph.add_node("restaurant_research", restaurant_research)
    graph.add_node("event_research", event_research)
    graph.add_node("aggregate", aggregate)
    graph.add_node("plan", plan)
    graph.add_node("constraint_engine", constraint_engine)
    graph.add_node("verify_semantics", verify_semantics)
    graph.add_node("critique", critique_plan)
    graph.add_node("apply_replan", apply_replan)
    graph.add_node("prepare_approval", prepare_approval)
    graph.add_node("human_approval", human_approval)
    graph.add_node("execute", execute)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "understand")
    graph.add_conditional_edges(
        "understand",
        after_understand,
        {"stop": END, "continue": "load_preferences"},
    )
    graph.add_edge("load_preferences", "decompose")
    destinations = [
        "calendar_analysis",
        "restaurant_research",
        "event_research",
        "aggregate",
        "plan",
        "finalize",
        "prepare_approval",
        "apply_replan",
        "execute",
        END,
    ]
    graph.add_conditional_edges("decompose", _send_ready, destinations)
    graph.add_edge("calendar_analysis", "aggregate")
    graph.add_edge("restaurant_research", "aggregate")
    graph.add_edge("event_research", "aggregate")
    graph.add_conditional_edges("aggregate", after_aggregate, destinations)
    graph.add_edge("plan", "constraint_engine")
    graph.add_edge("constraint_engine", "verify_semantics")
    graph.add_edge("verify_semantics", "critique")
    graph.add_conditional_edges(
        "critique",
        after_critic,
        {"apply_replan": "apply_replan", "prepare_approval": "prepare_approval", "finalize": "finalize"},
    )
    graph.add_conditional_edges("apply_replan", after_replan, destinations)
    graph.add_edge("prepare_approval", "human_approval")
    graph.add_conditional_edges("human_approval", after_human, destinations)
    graph.add_edge("execute", END)
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


async def _calendar(state: dict, deps: ItineraryDeps) -> dict:
    started = time.perf_counter()
    await deps.log.emit("agent_calendar_analysis", "started", {"agent": "calendar_analysis"})
    task = _task(state, "calendar_analysis")
    constraints = ItineraryConstraints.model_validate(state["constraints"])
    tools = ["google_calendar.list_events", "calendar.find_free_windows"]
    wave = int(state.get("research_wave") or 0)

    async def work() -> CalendarAnalysisResult:
        if deps.branch_delay_seconds:
            await asyncio.sleep(deps.branch_delay_seconds)
        if active_injection(deps.settings) == CALENDAR_READ_FAILURE:
            return CalendarAnalysisResult(
                calendar_read="unavailable",
                uncertainties=["Calendar could not be read."],
                constraints={"hard_end": constraints.time_end.isoformat()},
            )
        if constraints.date_start is None:
            raise ProviderError("The plan is missing a date.", retryable=False)
        zone = ZoneInfo(constraints.timezone)
        start = datetime.combine(constraints.date_start, clock_time.min, tzinfo=zone)
        end = datetime.combine(constraints.date_end or constraints.date_start, clock_time.max, tzinfo=zone)

        async def read():
            async with deps.session_lock:
                return await deps.calendar.get_events(start, end)  # type: ignore[attr-defined]

        events = await _use_tool(deps, "calendar_analysis", "google_calendar.list_events", read)

        def windows():
            return free_windows_for_range(
                date_start=constraints.date_start,
                date_end=constraints.date_end or constraints.date_start,
                time_start=constraints.time_start,
                time_end=constraints.time_end,
                busy=events,
                zone=zone,
            )

        async def find_windows():
            return windows()

        found = await _use_tool(
            deps, "calendar_analysis", "calendar.find_free_windows", find_windows
        )
        return CalendarAnalysisResult(
            available_windows=[{"start": item.start, "end": item.end} for item in found],
            existing_events=[item.model_dump(mode="json") for item in events],
            constraints={
                "hard_start": constraints.time_start.isoformat(),
                "hard_end": constraints.time_end.isoformat(),
            },
            calendar_read="ok",
        )

    try:
        result = await asyncio.wait_for(work(), timeout=deps.settings.specialist_timeout_seconds)
        detail = (
            "Calendar could not be checked"
            if result.calendar_read != "ok"
            else f"Free after {_clock_label(constraints.time_start)}"
        )
        trace = await _trace(
            deps,
            "calendar_analysis",
            "completed",
            started,
            detail,
            tools,
            policy="calendar_analysis_v1",
        )
        return {
            "calendar_result": dump(result),
            "tasks": [{**task, "status": "completed", "error": None, "result": {"calendar_read": result.calendar_read}}],
            "trace_events": [trace],
            "branch_reports": [{"agent": "calendar_analysis", "duration_ms": trace["duration_ms"], "wave": wave}],
        }
    except TimeoutError:
        return await _failed_branch(
            deps, task, "calendar_analysis", started, tools, "branch_timeout", wave, retryable=True
        )
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", "calendar_failed")
        return await _failed_branch(
            deps,
            task,
            "calendar_analysis",
            started,
            tools,
            str(code),
            wave,
            retryable=bool(getattr(exc, "retryable", False)),
        )


async def _restaurants(state: dict, deps: ItineraryDeps) -> dict:
    started = time.perf_counter()
    await deps.log.emit("agent_restaurant_research", "started", {"agent": "restaurant_research"})
    task = _task(state, "restaurant_research")
    constraints = ItineraryConstraints.model_validate(state["constraints"])
    preferences = UserPreferences.model_validate(state.get("user_preferences") or {})
    tools = ["search_restaurants"]
    wave = int(state.get("research_wave") or 0)
    if deps.place_provider_name == "google" and (
        preferences.latitude is None or preferences.longitude is None
    ):
        trace = await _trace(
            deps,
            "restaurant_research",
            "failed",
            started,
            "Needs a saved location",
            tools,
            error="location_required",
            policy=RESTAURANT_POLICY_VERSION,
        )
        return {
            "status": "awaiting_location",
            "error_code": "location_required",
            "tasks": [{**task, "status": "failed", "error": "location_required"}],
            "trace_events": [trace],
            "branch_reports": [{"agent": "restaurant_research", "duration_ms": trace["duration_ms"], "wave": wave}],
        }

    async def work() -> RestaurantResearchArtifact:
        if deps.branch_delay_seconds:
            await asyncio.sleep(deps.branch_delay_seconds)
        injection = active_injection(deps.settings)
        if injection == RESTAURANT_PROVIDER_FAILURE:
            raise ProviderError("Injected restaurant failure.", retryable=False)
        query = RestaurantSearchQuery(
            timezone=constraints.timezone,
            cuisines=constraints.cuisines,
            budget_max=constraints.budget_max,
            max_travel_minutes=constraints.hard_travel_minutes,
            latitude=preferences.latitude,
            longitude=preferences.longitude,
            radius_km=preferences.default_radius_km or 10,
            date_start=constraints.date_start,
            date_end=constraints.date_end,
        )
        found, failures = await _fanout(
            deps,
            "restaurant_research",
            "search_restaurants",
            [deps.restaurants, *deps.extra_restaurant_providers],
            lambda provider: provider.search_restaurants(query),
        )
        candidates = [item.to_candidate() for item in found]
        artifact = _restaurant_artifact(
            candidates,
            constraints,
            preferences,
            set(state.get("rejected_candidate_ids") or []),
            failures,
        )
        artifact.candidate_restaurants = await _apply_rank(
            deps, artifact.candidate_restaurants, constraints, preferences, cuisine=True
        )
        return artifact

    try:
        artifact = await asyncio.wait_for(work(), timeout=deps.settings.specialist_timeout_seconds)
        detail = f"Found {len(artifact.candidate_restaurants)} suitable options"
        trace = await _trace(
            deps,
            "restaurant_research",
            "completed",
            started,
            detail,
            tools,
            policy=RESTAURANT_POLICY_VERSION,
        )
        return {
            "restaurant_research": dump(artifact),
            "tasks": [{**task, "status": "completed", "error": None}],
            "trace_events": [trace],
            "branch_reports": [{"agent": "restaurant_research", "duration_ms": trace["duration_ms"], "wave": wave}],
        }
    except TimeoutError:
        return await _failed_branch(
            deps, task, "restaurant_research", started, tools, "branch_timeout", wave, retryable=True
        )
    except Exception as exc:  # noqa: BLE001
        return await _failed_branch(
            deps,
            task,
            "restaurant_research",
            started,
            tools,
            getattr(exc, "code", "provider_failed"),
            wave,
            retryable=bool(getattr(exc, "retryable", False)),
        )


async def _events(state: dict, deps: ItineraryDeps) -> dict:
    started = time.perf_counter()
    await deps.log.emit("agent_event_research", "started", {"agent": "event_research"})
    task = _task(state, "event_research")
    constraints = ItineraryConstraints.model_validate(state["constraints"])
    preferences = UserPreferences.model_validate(state.get("user_preferences") or {})
    tools = ["search_events"]
    wave = int(state.get("research_wave") or 0)
    if deps.event_provider_name == "ticketmaster" and not (preferences.home_city or "").strip():
        trace = await _trace(
            deps,
            "event_research",
            "failed",
            started,
            "Needs a home city",
            tools,
            error="city_required",
            policy=EVENT_POLICY_VERSION,
        )
        return {
            "status": "awaiting_location",
            "error_code": "city_required",
            "tasks": [{**task, "status": "failed", "error": "city_required"}],
            "trace_events": [trace],
            "branch_reports": [{"agent": "event_research", "duration_ms": trace["duration_ms"], "wave": wave}],
        }

    async def work() -> EventResearchArtifact:
        if deps.branch_delay_seconds:
            await asyncio.sleep(deps.branch_delay_seconds)
        injection = active_injection(deps.settings)
        if injection == EVENT_PROVIDER_TIMEOUT:
            raise ProviderError("Injected event timeout.", retryable=False, code="provider_failed")
        if injection == SUPERVISOR_RETRY and int(task.get("retry_count") or 0) == 0:
            raise ProviderError("Injected retryable event failure.", retryable=True, code="provider_failed")
        query = EventSearchQuery(
            date_start=constraints.date_start,
            date_end=constraints.date_end or constraints.date_start,
            timezone=constraints.timezone,
            categories=constraints.categories,
            budget_max=constraints.budget_max,
            max_travel_minutes=constraints.hard_travel_minutes,
            city=preferences.home_city,
            latitude=preferences.latitude,
            longitude=preferences.longitude,
            radius_km=preferences.default_radius_km or 10,
        )
        found, failures = await _fanout(
            deps,
            "event_research",
            "search_events",
            [deps.events, *deps.extra_event_providers],
            lambda provider: provider.search_events(query),
        )
        candidates = [item.to_candidate() for item in found]
        artifact = _event_artifact(
            candidates,
            constraints,
            preferences,
            set(state.get("rejected_candidate_ids") or []),
            failures,
        )
        artifact.candidate_events = await _apply_rank(
            deps, artifact.candidate_events, constraints, preferences, cuisine=False
        )
        return artifact

    try:
        artifact = await asyncio.wait_for(work(), timeout=deps.settings.specialist_timeout_seconds)
        detail = f"Found {len(artifact.candidate_events)} evening activities"
        trace = await _trace(
            deps,
            "event_research",
            "completed",
            started,
            detail,
            tools,
            policy=EVENT_POLICY_VERSION,
            retry=int(task.get("retry_count") or 0),
        )
        return {
            "event_research": dump(artifact),
            "tasks": [{**task, "status": "completed", "error": None, "retryable": False}],
            "trace_events": [trace],
            "branch_reports": [{"agent": "event_research", "duration_ms": trace["duration_ms"], "wave": wave}],
        }
    except TimeoutError:
        return await _failed_branch(
            deps, task, "event_research", started, tools, "branch_timeout", wave, retryable=True
        )
    except Exception as exc:  # noqa: BLE001
        return await _failed_branch(
            deps,
            task,
            "event_research",
            started,
            tools,
            getattr(exc, "code", "provider_failed"),
            wave,
            retryable=bool(getattr(exc, "retryable", False)),
        )


async def _plan(state: dict, deps: ItineraryDeps) -> dict:
    started = time.perf_counter()
    await deps.log.emit("agent_itinerary_planner", "started", {"agent": "itinerary_planner"})
    constraints = ItineraryConstraints.model_validate(state["constraints"])
    task = _task(state, "itinerary_generation")
    last_error: Exception | None = None
    itineraries: list[Itinerary] = []
    attempts = 0
    while attempts < 3:
        attempts += 1
        if (
            active_injection(deps.settings) == PLANNER_INVALID_OUTPUT
            and deps.invalid_planner_attempts < 2
        ):
            deps.invalid_planner_attempts += 1
            try:
                Itinerary.model_validate({"itinerary_id": "bad"})
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        itineraries = build_itineraries(
            constraints=constraints,
            calendar=_calendar_model(state.get("calendar_result")),
            restaurants=_restaurant_model(state.get("restaurant_research")),
            events=_event_model(state.get("event_research")),
            rejected_ids=set(state.get("rejected_candidate_ids") or []),
        )
        break
    else:
        itineraries = []
    detail = f"Built {len(itineraries)} itineraries" if itineraries else "No itinerary fit every constraint"
    trace = await _trace(
        deps,
        "itinerary_planner",
        "completed" if itineraries or last_error is None else "failed",
        started,
        detail,
        [],
        policy=PLANNER_POLICY_VERSION,
        retry=max(0, attempts - 1),
        error=None if itineraries or last_error is None else "planner_invalid_output",
    )
    payload: dict = {
        "tasks": [{**task, "status": "completed"}],
        "trace_events": [trace],
    }
    if itineraries or not state.get("itineraries"):
        payload["itineraries"] = [dump(item) for item in itineraries]
    return payload


async def _execute(state: dict, deps: ItineraryDeps) -> dict:
    started = time.perf_counter()
    await deps.log.emit("agent_execution", "started", {"agent": "execution"})
    if not state.get("approved"):
        trace = await _trace(
            deps,
            "execution",
            "failed",
            started,
            "Approval is required",
            [],
            error="approval_required",
        )
        return {
            "status": "awaiting_approval",
            "error_code": "approval_required",
            "trace_events": [trace],
        }
    chosen = state.get("approved_itinerary_id")
    raw_plans = list(state.get("itineraries") or [])
    raw = next((item for item in raw_plans if item.get("itinerary_id") == chosen), None)
    if raw is None and not chosen and len(raw_plans) == 1:
        raw = raw_plans[0]
    if raw is None:
        return {"status": "awaiting_approval", "error_code": "invalid_selection", "approved": False}
    itinerary = Itinerary.model_validate(raw)
    actions: list[ExecutionActionResult] = []
    for item in itinerary.items:
        if item.item_type not in {"restaurant", "event"}:
            continue
        item_id = f"{itinerary.itinerary_id}:{item.item_type}:{item.source_candidate_id}"

        async def write(item=item, item_id=item_id):
            if active_injection(deps.settings) == CALENDAR_WRITE_FAILURE:
                deps.write_attempts += 1
                if deps.write_attempts >= 2:
                    raise ProviderError("Injected calendar write failure.", retryable=True)
            return await schedule_block(
                deps.calendar,
                approved=True,
                plan_id=str(state.get("session_id")),
                item_id=item_id,
                title=item.title,
                start=item.start_datetime,
                end=item.end_datetime,
                location=item.location,
                description="Planned with Nemi.\n\nTravel times on this itinerary are estimates.",
            )

        try:
            result = await _use_tool(deps, "execution", "google_calendar.create_event", write)
            actions.append(
                ExecutionActionResult(
                    item_id=item_id,
                    title=item.title,
                    status="completed",
                    calendar_event_id=result.calendar_event_id,
                    replayed=result.replayed,
                )
            )
        except ScheduleConflictError:
            actions.append(
                ExecutionActionResult(
                    item_id=item_id,
                    title=item.title,
                    status="failed",
                    error_code="schedule_conflict",
                )
            )
        except Exception as exc:  # noqa: BLE001
            actions.append(
                ExecutionActionResult(
                    item_id=item_id,
                    title=item.title,
                    status="failed",
                    error_code=getattr(exc, "code", "calendar_write_failed"),
                )
            )
    succeeded = [item for item in actions if item.status == "completed"]
    failed = [item for item in actions if item.status == "failed"]
    if actions and not failed:
        report_status = "success"
        plan_status = "scheduled"
    elif succeeded:
        report_status = "partial_success"
        plan_status = "partial_success"
    else:
        report_status = "failed"
        plan_status = "failed"
    report = ExecutionReport(status=report_status, actions=actions)
    detail = {
        "success": "Scheduled successfully",
        "partial_success": "Part of the plan was added to the calendar",
        "failed": "Could not add this plan to the calendar",
    }[report_status]
    trace = await _trace(
        deps,
        "execution",
        "completed" if report_status == "success" else "failed",
        started,
        detail,
        ["google_calendar.create_event"],
        error=None if report_status == "success" else report_status,
    )
    return {
        "execution_result": dump(report),
        "status": plan_status,
        "error_code": None if report_status == "success" else report_status,
        "trace_events": [trace],
    }


async def _failed_branch(
    deps: ItineraryDeps,
    task: dict,
    agent: str,
    started: float,
    tools: list[str],
    error: str,
    wave: int,
    *,
    retryable: bool,
) -> dict:
    trace = await _trace(
        deps,
        agent,
        "failed",
        started,
        "This part of the research failed",
        tools,
        error=error,
        retry=int(task.get("retry_count") or 0),
    )
    return {
        "tasks": [
            {
                **task,
                "status": "failed",
                "error": error,
                "retryable": retryable,
            }
        ],
        "errors": [{"agent": agent, "error": error}],
        "trace_events": [trace],
        "branch_reports": [{"agent": agent, "duration_ms": trace["duration_ms"], "wave": wave}],
    }


async def _fanout(deps: ItineraryDeps, agent: str, tool_name: str, providers: list, call) -> tuple[list, list[str]]:
    async def one(provider):
        async def operation(provider=provider):
            return await call(provider)

        return await _use_tool(deps, agent, tool_name, operation)

    groups = await asyncio.gather(*[one(provider) for provider in providers], return_exceptions=True)
    found: list = []
    failures: list[str] = []
    for group in groups:
        if isinstance(group, Exception):
            failures.append(getattr(group, "code", "provider_failed"))
            continue
        found.extend(group)
    if not found and failures:
        raise ProviderError("The search failed.", retryable=False, code=failures[0])
    return found, failures


def _restaurant_artifact(candidates, constraints, preferences, rejected: set[str], failures: list[str]):
    included: list[ResearchCandidate] = []
    excluded: list[dict] = []
    uncertainties: list[str] = []
    for candidate in candidates:
        if candidate.id in rejected:
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "rejected"})
            continue
        if constraints.cuisines and not set(candidate.categories) & set(constraints.cuisines):
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "cuisine"})
            continue
        if (
            constraints.budget_max is not None
            and candidate.price_min is not None
            and candidate.price_min > constraints.budget_max
        ):
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "budget"})
            continue
        diet = dietary_status(candidate.title, candidate.description, constraints.dietary_restrictions)
        if diet == "exclude":
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "dietary"})
            continue
        if diet == "uncertain":
            uncertainties.append(f"{candidate.title} may include raw dishes.")
        included.append(ResearchCandidate(candidate=candidate, dietary=diet, score=0))
    included = _score_included(included, constraints, preferences, cuisine=True)
    return RestaurantResearchArtifact(
        candidate_restaurants=included,
        excluded_candidates=excluded,
        uncertainties=uncertainties,
        provider_failures=failures,
    )


def _event_artifact(candidates, constraints, preferences, rejected: set[str], failures: list[str]):
    included: list[ResearchCandidate] = []
    excluded: list[dict] = []
    zone = ZoneInfo(constraints.timezone)
    start_bound = (
        datetime.combine(constraints.date_start, constraints.time_start, tzinfo=zone)
        if constraints.date_start
        else None
    )
    end_bound = (
        datetime.combine(constraints.date_start, constraints.time_end, tzinfo=zone)
        if constraints.date_start
        else None
    )
    for candidate in candidates:
        if candidate.id in rejected:
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "rejected"})
            continue
        if candidate.start_datetime and start_bound and candidate.start_datetime < start_bound:
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "starts_too_early"})
            continue
        if candidate.end_datetime and end_bound and candidate.end_datetime > end_bound:
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "ends_too_late"})
            continue
        if (
            constraints.budget_max is not None
            and candidate.price_min is not None
            and candidate.price_min > constraints.budget_max
        ):
            excluded.append({"id": candidate.id, "title": candidate.title, "reason": "budget"})
            continue
        if constraints.category_match_required and constraints.categories:
            if not set(candidate.categories) & set(constraints.categories):
                excluded.append({"id": candidate.id, "title": candidate.title, "reason": "category"})
                continue
        included.append(ResearchCandidate(candidate=candidate, score=0))
    included = _score_included(included, constraints, preferences, cuisine=False)
    return EventResearchArtifact(
        candidate_events=included,
        excluded_candidates=excluded,
        uncertainties=["Travel times are estimates."] if included else [],
        provider_failures=failures,
    )


def _score_included(items: list[ResearchCandidate], constraints, preferences, *, cuisine: bool):
    # Ranking happens in the node via the ranker when a loop is available.
    # A local score keeps ordering deterministic even before that call.
    requested = set(constraints.cuisines if cuisine else constraints.categories)
    preferred = set(
        preferences.preferred_cuisines if cuisine else preferences.preferred_event_categories
    )
    scored: list[ResearchCandidate] = []
    for item in items:
        cats = set(item.candidate.categories)
        score = 0.2
        if requested and cats & requested:
            score += 0.5
        elif not requested:
            score += 0.3
        if preferred and cats & preferred:
            score += 0.1
        if item.candidate.rating:
            score += item.candidate.rating / 50
        travel = item.candidate.estimated_travel_minutes
        if travel is not None and constraints.max_travel_minutes:
            score += max(0, 0.2 - (travel / max(constraints.hard_travel_minutes or 60, 1)))
        scored.append(item.model_copy(update={"score": round(score, 4)}))
    scored.sort(key=lambda item: (-item.score, item.candidate.id))
    return scored


async def _apply_rank(deps: ItineraryDeps, items: list[ResearchCandidate], constraints, preferences, *, cuisine: bool):
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
    ranked = await deps.ranker.rank([item.candidate for item in items], context)
    scores = {item.candidate.id: item.final_score for item in ranked}
    updated = [
        item.model_copy(update={"score": scores.get(item.candidate.id, item.score)}) for item in items
    ]
    updated.sort(key=lambda item: (-item.score, item.candidate.id))
    return updated


def _calendar_model(raw: dict | None) -> CalendarAnalysisResult | None:
    if not raw:
        return None
    return CalendarAnalysisResult.model_validate(raw)


def _restaurant_model(raw: dict | None) -> RestaurantResearchArtifact | None:
    if not raw:
        return None
    return RestaurantResearchArtifact.model_validate(raw)


def _event_model(raw: dict | None) -> EventResearchArtifact | None:
    if not raw:
        return None
    return EventResearchArtifact.model_validate(raw)


def _clock_label(value: clock_time) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    if value.minute:
        return f"{hour}:{value.minute:02d} {suffix}"
    return f"{hour} {suffix}"
