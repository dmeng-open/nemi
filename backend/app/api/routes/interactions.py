import base64
import binascii
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError
from app.models.agent import InteractionEvent
from app.models.user import LOCAL_USER_ID
from app.repositories.users import ensure_local_user
from app.schemas.interactions import InteractionItem, InteractionListResponse
from app.services.calendar.time import as_utc

router = APIRouter(prefix="/interactions", tags=["interactions"])

_HIDDEN_PROPERTY_KEYS = {
    "score",
    "final_score",
    "components",
    "preference_score",
    "schedule_score",
    "distance_score",
    "price_score",
    "quality_score",
    "refresh_token",
    "access_token",
    "authorization",
    "code",
}


@router.get("", response_model=InteractionListResponse)
async def list_interactions(
    session: AsyncSession = Depends(get_db),
    limit: int = 50,
    cursor: str | None = None,
) -> InteractionListResponse:
    await ensure_local_user(session)
    bounded = min(max(limit, 1), 100)
    stmt = (
        select(InteractionEvent)
        .where(InteractionEvent.user_id == LOCAL_USER_ID)
        .order_by(InteractionEvent.created_at.desc(), InteractionEvent.id.desc())
    )
    if cursor:
        created_at, event_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                InteractionEvent.created_at < created_at,
                and_(
                    InteractionEvent.created_at == created_at,
                    InteractionEvent.id < event_id,
                ),
            )
        )
    rows = list((await session.scalars(stmt.limit(bounded + 1))).all())
    next_cursor = None
    if len(rows) > bounded:
        last = rows[bounded - 1]
        rows = rows[:bounded]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return InteractionListResponse(
        items=[_item(row) for row in rows],
        next_cursor=next_cursor,
    )


def _item(row: InteractionEvent) -> InteractionItem:
    properties = {
        key: value
        for key, value in (row.properties or {}).items()
        if key not in _HIDDEN_PROPERTY_KEYS
    }
    return InteractionItem(
        id=str(row.id),
        session_id=str(row.session_id) if row.session_id else None,
        candidate_id=row.candidate_id,
        event_name=row.event_name,
        topic=row.topic,
        properties=properties,
        created_at=row.created_at,
    )


def _encode_cursor(created_at: datetime, event_id) -> str:
    raw = f"{as_utc(created_at).isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, object]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        created_raw, id_raw = decoded.split("|", 1)
        created_at = as_utc(datetime.fromisoformat(created_raw))
        from uuid import UUID

        event_id = UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise AppError(
            "That page cursor is not valid.",
            code="validation_error",
            status_code=422,
        ) from exc
    return created_at, event_id
