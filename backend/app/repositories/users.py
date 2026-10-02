import uuid
from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.preferences import TimeRange, UserPreferences
from app.models.user import LOCAL_USER_EMAIL, LOCAL_USER_ID, User, UserPreference

DEFAULT_TIME_RANGES = [{"start": "12:00:00", "end": "18:00:00", "label": "afternoon"}]


async def ensure_local_user(session: AsyncSession) -> User:
    user = await session.get(User, LOCAL_USER_ID)
    if user is None:
        user = User(id=LOCAL_USER_ID, email=LOCAL_USER_EMAIL, display_name="You")
        session.add(user)
        await session.flush()
    preference = await session.scalar(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    if preference is None:
        session.add(
            UserPreference(
                user_id=user.id,
                preferred_event_categories=["technology", "food", "live_music"],
                preferred_cuisines=["japanese", "italian"],
                disliked_categories=[],
                default_budget=50,
                max_travel_minutes=30,
                preferred_days=["friday", "saturday"],
                preferred_time_ranges=list(DEFAULT_TIME_RANGES),
            )
        )
        await session.flush()
    return user


def preferences_to_domain(row: UserPreference) -> UserPreferences:
    ranges: list[TimeRange] = []
    for item in row.preferred_time_ranges or []:
        ranges.append(
            TimeRange(
                start=time.fromisoformat(item["start"]),
                end=time.fromisoformat(item["end"]),
                label=item.get("label"),
            )
        )
    return UserPreferences(
        preferred_event_categories=list(row.preferred_event_categories or []),
        preferred_cuisines=list(row.preferred_cuisines or []),
        disliked_categories=list(row.disliked_categories or []),
        default_budget=row.default_budget,
        max_travel_minutes=row.max_travel_minutes,
        preferred_days=list(row.preferred_days or []),
        preferred_time_ranges=ranges,
    )


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> UserPreferences:
    row = await session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if row is None:
        raise RuntimeError("Local preferences are missing.")
    return preferences_to_domain(row)


async def get_preference_row(session: AsyncSession, user_id: uuid.UUID) -> UserPreference:
    row = await session.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if row is None:
        raise RuntimeError("Local preferences are missing.")
    return row
