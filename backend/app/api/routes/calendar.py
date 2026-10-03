import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_settings
from app.core.config import Settings
from app.core.exceptions import AppError, PlanNotFound
from app.integrations.calendar.local import row_to_event
from app.models.user import LOCAL_USER_ID
from app.providers.factory import build_calendar_provider
from app.repositories.calendar import CalendarRepository
from app.repositories.users import ensure_local_user
from app.schemas.calendar import CalendarEventResponse, CreateCalendarEventRequest
from app.services.calendar.sample import ensure_sample_saturday
from app.services.calendar.time import as_utc

router = APIRouter(prefix="/calendar", tags=["calendar"])


def _response(row) -> CalendarEventResponse:
    event = row_to_event(row)
    return CalendarEventResponse(
        id=event.id,
        title=event.title,
        start=event.start,
        end=event.end,
        location=event.location,
        description=event.description,
        source_url=event.source_url,
    )


@router.get("/window", response_model=list[CalendarEventResponse])
async def calendar_window(
    start: datetime,
    end: datetime,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[CalendarEventResponse]:
    if start.tzinfo is None or end.tzinfo is None:
        raise AppError(
            "Include a timezone on the start and end times.",
            code="validation_error",
            status_code=422,
        )
    if end <= start:
        raise AppError(
            "end must be after start",
            code="validation_error",
            status_code=422,
        )
    await ensure_local_user(session)
    provider = build_calendar_provider(settings, session, LOCAL_USER_ID)
    events = await provider.get_events(start, end)
    return [
        CalendarEventResponse(
            id=event.id,
            title=event.title,
            start=event.start,
            end=event.end,
            location=event.location,
            description=event.description,
            source_url=event.source_url,
        )
        for event in events
    ]


@router.get("/events", response_model=list[CalendarEventResponse])
async def list_events(session: AsyncSession = Depends(get_db)) -> list[CalendarEventResponse]:
    await ensure_local_user(session)
    rows = await CalendarRepository(session).list_for_user(LOCAL_USER_ID)
    return [_response(row) for row in rows]


@router.post("/events", status_code=201, response_model=CalendarEventResponse)
async def create_event(
    body: CreateCalendarEventRequest,
    session: AsyncSession = Depends(get_db),
) -> CalendarEventResponse:
    if body.start.tzinfo is None or body.end.tzinfo is None:
        raise AppError(
            "Include a timezone on the start and end times.",
            code="validation_error",
            status_code=422,
        )
    await ensure_local_user(session)
    row = await CalendarRepository(session).create_user_event(
        user_id=LOCAL_USER_ID,
        title=body.title.strip(),
        start=as_utc(body.start),
        end=as_utc(body.end),
        location=body.location,
        description=body.description,
    )
    return _response(row)


@router.post("/sample", response_model=list[CalendarEventResponse])
async def create_sample(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[CalendarEventResponse]:
    await ensure_local_user(session)
    rows = await ensure_sample_saturday(
        CalendarRepository(session),
        now=datetime.now(UTC),
        zone=settings.zone(),
    )
    return [_response(row) for row in rows]


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    deleted = await CalendarRepository(session).delete_event(event_id, LOCAL_USER_ID)
    if not deleted:
        raise PlanNotFound("That calendar event could not be found.")
