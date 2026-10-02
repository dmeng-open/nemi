from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class CreateCalendarEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: datetime
    end: datetime
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def end_after_start(self) -> "CreateCalendarEventRequest":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    description: str | None = None
    source_url: str | None = None
