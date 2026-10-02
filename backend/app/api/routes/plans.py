import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_orchestrator
from app.schemas.plans import (
    ApproveRequest,
    ClarifyRequest,
    CreatePlanRequest,
    PlanCreatedResponse,
    PlanResponse,
    PlanSummaryResponse,
    SelectRequest,
    TimelineResponse,
)
from app.services.calendar.ics import build_ics
from app.services.planning.orchestrator import PlanningOrchestrator
from app.services.planning.present import (
    build_plan_response,
    build_timeline_response,
    ics_event_for_plan,
    list_plan_summaries,
)

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("", status_code=202, response_model=PlanCreatedResponse)
async def create_plan(
    body: CreatePlanRequest,
    background: BackgroundTasks,
    orchestrator: PlanningOrchestrator = Depends(get_orchestrator),
) -> PlanCreatedResponse:
    plan_id = await orchestrator.create_plan(body.message)
    background.add_task(orchestrator.run_discovery, plan_id)
    return PlanCreatedResponse(plan_id=str(plan_id), status="processing")


@router.get("", response_model=list[PlanSummaryResponse])
async def list_plans(
    session: AsyncSession = Depends(get_db),
    limit: int = 20,
) -> list[PlanSummaryResponse]:
    bounded = min(max(limit, 1), 50)
    return await list_plan_summaries(session, bounded)


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> PlanResponse:
    return await build_plan_response(session, plan_id)


@router.get("/{plan_id}/timeline", response_model=TimelineResponse)
async def get_timeline(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> TimelineResponse:
    return await build_timeline_response(session, plan_id)


@router.post("/{plan_id}/clarify", response_model=PlanCreatedResponse)
async def clarify_plan(
    plan_id: uuid.UUID,
    body: ClarifyRequest,
    background: BackgroundTasks,
    orchestrator: PlanningOrchestrator = Depends(get_orchestrator),
) -> PlanCreatedResponse:
    await orchestrator.clarify(plan_id, body.message)
    background.add_task(orchestrator.run_discovery, plan_id)
    return PlanCreatedResponse(plan_id=str(plan_id), status="processing")


@router.post("/{plan_id}/select", response_model=PlanResponse)
async def select_candidate(
    plan_id: uuid.UUID,
    body: SelectRequest,
    orchestrator: PlanningOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db),
) -> PlanResponse:
    await orchestrator.select(plan_id, body.candidate_id)
    return await build_plan_response(session, plan_id)


@router.delete("/{plan_id}/selection", response_model=PlanResponse)
async def clear_selection(
    plan_id: uuid.UUID,
    orchestrator: PlanningOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db),
) -> PlanResponse:
    await orchestrator.clear_selection(plan_id)
    return await build_plan_response(session, plan_id)


@router.post("/{plan_id}/approve", response_model=PlanResponse)
async def approve_plan(
    plan_id: uuid.UUID,
    body: ApproveRequest,
    orchestrator: PlanningOrchestrator = Depends(get_orchestrator),
    session: AsyncSession = Depends(get_db),
) -> PlanResponse:
    await orchestrator.approve(plan_id, body.approved)
    session.expire_all()
    return await build_plan_response(session, plan_id)


@router.get("/{plan_id}/ics")
async def download_ics(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    event = await ics_event_for_plan(session, plan_id)
    payload = build_ics(event, description=event.description)
    filename = f"nemi-{plan_id}.ics"
    return Response(
        content=payload,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
