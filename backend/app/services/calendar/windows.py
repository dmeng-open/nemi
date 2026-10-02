from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.calendar import CalendarEvent, TimeWindow
from app.services.calendar.conflicts import subtract_busy


def free_windows_for_range(
    *,
    date_start: date,
    date_end: date,
    time_start: time,
    time_end: time,
    busy: list[CalendarEvent],
    zone: ZoneInfo,
) -> list[TimeWindow]:
    windows: list[TimeWindow] = []
    day = date_start
    while day <= date_end:
        start = datetime.combine(day, time_start, tzinfo=zone)
        end = datetime.combine(day, time_end, tzinfo=zone)
        if end > start:
            windows.extend(subtract_busy(start, end, busy))
        day += timedelta(days=1)
    return windows
