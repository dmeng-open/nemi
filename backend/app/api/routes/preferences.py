from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.agent import InteractionEvent
from app.models.user import LOCAL_USER_ID
from app.repositories.users import ensure_local_user, get_preference_row, preferences_to_domain
from app.schemas.preferences import PreferencesPayload

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesPayload)
async def read_preferences(session: AsyncSession = Depends(get_db)) -> PreferencesPayload:
    await ensure_local_user(session)
    row = await get_preference_row(session, LOCAL_USER_ID)
    domain = preferences_to_domain(row)
    return PreferencesPayload.model_validate(domain.model_dump())


@router.put("", response_model=PreferencesPayload)
async def update_preferences(
    body: PreferencesPayload,
    session: AsyncSession = Depends(get_db),
) -> PreferencesPayload:
    await ensure_local_user(session)
    row = await get_preference_row(session, LOCAL_USER_ID)
    row.preferred_event_categories = body.preferred_event_categories
    row.preferred_cuisines = body.preferred_cuisines
    row.disliked_categories = body.disliked_categories
    row.default_budget = body.default_budget
    row.max_travel_minutes = body.max_travel_minutes
    row.preferred_days = list(body.preferred_days)
    row.preferred_time_ranges = [
        {"start": item.start.isoformat(), "end": item.end.isoformat(), "label": item.label}
        for item in body.preferred_time_ranges
    ]
    session.add(
        InteractionEvent(
            user_id=LOCAL_USER_ID,
            event_name="preference_updated",
            topic="user.preference.updated",
            properties={},
        )
    )
    return body
