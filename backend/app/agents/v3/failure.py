EVENT_PROVIDER_TIMEOUT = "EVENT_PROVIDER_TIMEOUT"
RESTAURANT_PROVIDER_FAILURE = "RESTAURANT_PROVIDER_FAILURE"
CALENDAR_READ_FAILURE = "CALENDAR_READ_FAILURE"
CALENDAR_WRITE_FAILURE = "CALENDAR_WRITE_FAILURE"
PLANNER_INVALID_OUTPUT = "PLANNER_INVALID_OUTPUT"
CRITIC_REJECT = "CRITIC_REJECT"
SUPERVISOR_RETRY = "SUPERVISOR_RETRY"


def active_injection(settings) -> str | None:
    reader = getattr(settings, "active_failure_injection", None)
    if callable(reader):
        return reader()
    raw = getattr(settings, "failure_injection", "") or ""
    if getattr(settings, "environment", "local") == "production":
        return None
    text = str(raw).strip()
    return text or None
