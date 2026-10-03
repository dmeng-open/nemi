from enum import StrEnum

from app.core.exceptions import AppError


class ToolPermission(StrEnum):
    READ_ONLY = "read_only"
    WRITE_LOW_RISK = "write_low_risk"
    WRITE_SENSITIVE = "write_sensitive"


class ToolSpec:
    def __init__(self, name: str, permission: ToolPermission, agents: set[str]) -> None:
        self.name = name
        self.permission = permission
        self.agents = agents


TOOLS: dict[str, ToolSpec] = {
    "search_events": ToolSpec("search_events", ToolPermission.READ_ONLY, {"event_research"}),
    "search_restaurants": ToolSpec(
        "search_restaurants", ToolPermission.READ_ONLY, {"restaurant_research"}
    ),
    "google_calendar.list_events": ToolSpec(
        "google_calendar.list_events",
        ToolPermission.READ_ONLY,
        {"calendar_analysis"},
    ),
    "calendar.find_free_windows": ToolSpec(
        "calendar.find_free_windows",
        ToolPermission.READ_ONLY,
        {"calendar_analysis"},
    ),
    "google_calendar.create_event": ToolSpec(
        "google_calendar.create_event",
        ToolPermission.WRITE_LOW_RISK,
        {"execution"},
    ),
    "calendar.delete_event": ToolSpec(
        "calendar.delete_event",
        ToolPermission.WRITE_SENSITIVE,
        {"execution"},
    ),
}


def tools_for(agent: str) -> list[str]:
    return sorted(name for name, spec in TOOLS.items() if agent in spec.agents)


def authorize(agent: str, tool_name: str) -> ToolSpec:
    spec = TOOLS.get(tool_name)
    if spec is None or agent not in spec.agents:
        raise AppError(
            "That tool is not available to this agent.",
            code="tool_forbidden",
            status_code=403,
        )
    return spec


def note_tool_call(counts: dict[str, int], agent: str, *, limit: int) -> None:
    counts[agent] = counts.get(agent, 0) + 1
    if counts[agent] > limit:
        raise AppError(
            "This agent reached its tool-call limit.",
            code="tool_limit",
            status_code=429,
        )
