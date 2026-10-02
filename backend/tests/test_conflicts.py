from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.calendar import CalendarEvent
from app.services.calendar.conflicts import overlaps, propose_slot
from app.services.calendar.windows import free_windows_for_range

CHICAGO = ZoneInfo("America/Chicago")
DAY = datetime(2026, 10, 3, tzinfo=CHICAGO)


def _event(start_hour: int, end_hour: int, title: str = "Busy") -> CalendarEvent:
    return CalendarEvent(
        id=title,
        title=title,
        start=DAY.replace(hour=start_hour),
        end=DAY.replace(hour=end_hour),
    )


def test_touching_events_do_not_overlap() -> None:
    gym = _event(10, 11, "Gym")
    assert overlaps(DAY.replace(hour=11), DAY.replace(hour=12), [gym]) is None


def test_partial_overlap_is_a_conflict() -> None:
    dinner = _event(18, 20, "Dinner")
    assert overlaps(DAY.replace(hour=17), DAY.replace(hour=19), [dinner]) is not None


def test_free_window_removes_busy_time_inside_the_afternoon() -> None:
    windows = free_windows_for_range(
        date_start=DAY.date(),
        date_end=DAY.date(),
        time_start=time(12, 0),
        time_end=time(18, 0),
        busy=[_event(14, 15, "Call")],
        zone=CHICAGO,
    )
    assert [(item.start.hour, item.end.hour) for item in windows] == [(12, 14), (15, 18)]


def test_propose_slot_uses_the_first_open_ninety_minutes() -> None:
    windows = free_windows_for_range(
        date_start=DAY.date(),
        date_end=DAY.date(),
        time_start=time(17, 30),
        time_end=time(21, 0),
        busy=[],
        zone=CHICAGO,
    )
    slot = propose_slot(windows, timedelta(minutes=90))
    assert slot is not None
    start, end = slot
    assert start.hour == 17 and start.minute == 30
    assert end - start == timedelta(minutes=90)
