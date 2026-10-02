from datetime import datetime

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    description: str | None = None
    source_url: str | None = None


class NewCalendarEvent(BaseModel):
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    description: str | None = None
    source_url: str | None = None
    planning_session_id: str | None = None
    seed_key: str | None = None


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class CalendarExecutionResult(BaseModel):
    calendar_event_id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    replayed: bool = False
