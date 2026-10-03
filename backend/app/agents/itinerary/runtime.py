import asyncio
import uuid

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from app.agents.itinerary.graph import ItineraryDeps, compile_itinerary_graph
from app.agents.itinerary.persist import DbSpanLog, persist_itinerary_state
from app.agents.itinerary.structured_output import OpenAIStructuredOutput
from app.core.exceptions import PlanStateError
from app.models.planning import PlanningSession
from app.models.user import LOCAL_USER_ID
from app.providers.factory import (
    build_calendar_provider,
    build_event_provider,
    build_restaurant_provider,
)
from app.providers.http import bind_plan_id, reset_plan_id
from app.repositories.users import get_preferences
from app.services.planning.orchestrator import _compose_request, _invoke, _latest_run, _owned_plan
from app.services.ranking.heuristic import HeuristicRanker


async def run_itinerary_discovery(orchestrator, plan_id: uuid.UUID) -> None:
    token = bind_plan_id(str(plan_id))
    try:
        async with orchestrator.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            run = await _latest_run(session, plan_id)
            if run is None:
                raise PlanStateError("This plan has no agent run.")
            deps = await _deps(orchestrator, session, run)
            graph = compile_itinerary_graph(deps, orchestrator.checkpointer)
            config: RunnableConfig = {
                "configurable": {"thread_id": str(plan_id)},
                "recursion_limit": 80,
            }
            final = await _invoke(
                graph,
                {
                    "session_id": str(plan.id),
                    "user_id": str(plan.user_id),
                    "user_request": _compose_request(plan),
                    "approved": False,
                    "errors": [],
                    "trace_events": [],
                    "branch_reports": [],
                    "tasks": [],
                    "status": "processing",
                    "replan_count": 0,
                },
                config,
            )
            await _save(session, plan.id, run.id, final)
    except Exception as exc:
        if isinstance(exc, PlanStateError):
            raise
        import logging

        logging.getLogger(__name__).exception("itinerary_failed")
        await orchestrator.mark_failed(plan_id, exc)
    finally:
        reset_plan_id(token)


async def resume_itinerary(orchestrator, plan_id: uuid.UUID, decision: dict) -> None:
    token = bind_plan_id(str(plan_id))
    try:
        async with orchestrator.session_factory() as session:
            plan = await _owned_plan(session, plan_id)
            action = decision.get("action")
            if action == "approve" and plan.status == "scheduled":
                return
            if plan.status != "awaiting_approval":
                raise PlanStateError("This plan is not waiting for approval.")
            run = await _latest_run(session, plan_id)
            if run is None:
                raise PlanStateError("This plan has no agent run.")
            deps = await _deps(orchestrator, session, run)
            graph = compile_itinerary_graph(deps, orchestrator.checkpointer)
            config: RunnableConfig = {
                "configurable": {"thread_id": str(plan_id)},
                "recursion_limit": 80,
            }
            final = await _invoke(graph, Command(resume=decision), config)
            await _save(session, plan.id, run.id, final)
    finally:
        reset_plan_id(token)


async def _save(session, plan_id, run_id, final: dict) -> None:
    plan = await session.get(PlanningSession, plan_id)
    from app.models.agent import AgentRun

    run = await session.get(AgentRun, run_id)
    if plan is None or run is None:
        raise PlanStateError("This plan could not be saved.")
    await persist_itinerary_state(session, plan, run, final)
    await session.commit()


async def _deps(orchestrator, session, run) -> ItineraryDeps:
    async def load_preferences():
        return await get_preferences(session, LOCAL_USER_ID)

    preferences = await load_preferences()
    zone = orchestrator.settings.zone()
    if preferences.timezone:
        from zoneinfo import ZoneInfo

        zone = ZoneInfo(preferences.timezone)
    lock = asyncio.Lock()
    return ItineraryDeps(
        events=build_event_provider(orchestrator.settings),
        restaurants=build_restaurant_provider(orchestrator.settings),
        calendar=build_calendar_provider(orchestrator.settings, session, LOCAL_USER_ID),
        ranker=HeuristicRanker(orchestrator.settings.ranking_weights),
        log=DbSpanLog(session, run.id, run.session_id, lock),
        clock=orchestrator.clock,
        zone=zone,
        load_preferences=load_preferences,
        settings=orchestrator.settings,
        event_provider_name=orchestrator.settings.event_provider,
        place_provider_name=orchestrator.settings.place_provider,
        session_lock=lock,
        output=OpenAIStructuredOutput(orchestrator.settings),
    )
