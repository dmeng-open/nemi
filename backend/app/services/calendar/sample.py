from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.models.user import LOCAL_USER_ID
from app.repositories.calendar import CalendarRepository
from app.services.planning.dates import resolve_named_day


async def ensure_sample_saturday(
    repository: CalendarRepository,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> list:
    saturday = resolve_named_day("saturday", now.astimezone(zone).date())
    specs = (
        ("sample-gym", "Gym", 10, 0, 11, 0, "Your usual Saturday workout."),
        ("sample-dinner", "Dinner with friends", 18, 0, 20, 0, "Already on the calendar."),
    )
    rows = []
    for prefix, title, start_hour, start_minute, end_hour, end_minute, description in specs:
        start = datetime.combine(saturday, time(start_hour, start_minute), tzinfo=zone)
        end = datetime.combine(saturday, time(end_hour, end_minute), tzinfo=zone)
        rows.append(
            await repository.create_user_event(
                user_id=LOCAL_USER_ID,
                title=title,
                start=start,
                end=end,
                description=description,
                seed_key=f"{prefix}-{saturday.isoformat()}",
            )
        )
    return rows
