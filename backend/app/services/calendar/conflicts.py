from datetime import datetime, timedelta

from app.domain.calendar import CalendarEvent, TimeWindow


def overlaps(start: datetime, end: datetime, events: list[CalendarEvent]) -> CalendarEvent | None:
    for event in events:
        if start < event.end and end > event.start:
            return event
    return None


def subtract_busy(
    start: datetime,
    end: datetime,
    busy: list[CalendarEvent],
) -> list[TimeWindow]:
    intervals: list[tuple[datetime, datetime]] = [(start, end)]
    for event in sorted(busy, key=lambda item: item.start):
        next_intervals: list[tuple[datetime, datetime]] = []
        for slot_start, slot_end in intervals:
            if event.end <= slot_start or event.start >= slot_end:
                next_intervals.append((slot_start, slot_end))
                continue
            if event.start > slot_start:
                next_intervals.append((slot_start, event.start))
            if event.end < slot_end:
                next_intervals.append((event.end, slot_end))
        intervals = next_intervals
    return [
        TimeWindow(start=slot_start, end=slot_end)
        for slot_start, slot_end in intervals
        if slot_end > slot_start
    ]


def contained(start: datetime, end: datetime, windows: list[TimeWindow]) -> bool:
    return any(start >= window.start and end <= window.end for window in windows)


def ceil_half_hour(moment: datetime) -> datetime:
    if moment.minute in {0, 30} and moment.second == 0 and moment.microsecond == 0:
        return moment
    if moment.minute < 30:
        return moment.replace(minute=30, second=0, microsecond=0)
    return (moment + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


def propose_slot(
    windows: list[TimeWindow],
    duration: timedelta = timedelta(minutes=90),
) -> tuple[datetime, datetime] | None:
    for window in windows:
        if window.end - window.start < duration:
            continue
        snapped = ceil_half_hour(window.start)
        if snapped < window.start:
            snapped = window.start
        if snapped + duration <= window.end:
            return snapped, snapped + duration
        if window.start + duration <= window.end:
            return window.start, window.start + duration
    return None
