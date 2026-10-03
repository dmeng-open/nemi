from datetime import datetime

from pydantic import BaseModel, Field


class InteractionItem(BaseModel):
    id: str
    session_id: str | None = None
    candidate_id: str | None = None
    event_name: str
    topic: str
    properties: dict
    created_at: datetime


class InteractionListResponse(BaseModel):
    items: list[InteractionItem]
    next_cursor: str | None = None


class InteractionQuery(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None
