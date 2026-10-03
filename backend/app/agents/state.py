import operator
from typing import Annotated, Any, TypedDict


class PlanningState(TypedDict, total=False):
    session_id: str
    user_id: str
    user_request: str
    plan_type: str | None
    constraints: dict[str, Any] | None
    user_preferences: dict[str, Any] | None
    calendar_events: list[dict[str, Any]]
    free_windows: list[dict[str, Any]]
    calendar_read: str
    candidates: list[dict[str, Any]]
    ranked_candidates: list[dict[str, Any]]
    selected_candidate_id: str | None
    approved: bool
    execution_result: dict[str, Any] | None
    errors: Annotated[list[str], operator.add]
    status: str
    clarification_question: str | None
    summary: str | None
    error_code: str | None
    conflicts_removed: int
