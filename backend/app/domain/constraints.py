from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PlanningConstraints(BaseModel):
    plan_type: Literal["event", "restaurant"] | None = None
    date_start: date | None = None
    date_end: date | None = None
    time_of_day: str | None = None
    time_start: time | None = None
    time_end: time | None = None
    categories: list[str] = Field(default_factory=list)
    cuisines: list[str] = Field(default_factory=list)
    budget_amount: float | None = None
    budget_kind: Literal["maximum", "around", "unspecified"] = "unspecified"
    budget_max: float | None = None
    max_travel_minutes: int | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    summary: str = ""


class ConstraintDraft(BaseModel):
    """Shape requested from the model. Dates are finalized in code."""

    plan_type: Literal["event", "restaurant"] | None = None
    day_hint: (
        Literal[
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
            "today",
            "tomorrow",
            "weekend",
        ]
        | None
    ) = None
    date_start: date | None = None
    date_end: date | None = None
    time_of_day: Literal["morning", "afternoon", "evening", "night", "after_work"] | None = None
    time_start: time | None = None
    time_end: time | None = None
    categories: list[str] = Field(default_factory=list)
    cuisines: list[str] = Field(default_factory=list)
    budget_amount: float | None = None
    budget_kind: Literal["maximum", "around", "unspecified"] = "unspecified"
    max_travel_minutes: int | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    summary: str = ""

    @field_validator("budget_amount", "max_travel_minutes")
    @classmethod
    def non_negative(cls, value: float | int | None) -> float | int | None:
        if value is not None and value < 0:
            raise ValueError("must be non-negative")
        return value
