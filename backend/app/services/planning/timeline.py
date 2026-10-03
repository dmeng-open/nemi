from app.core.messages import SAFE_MESSAGES


def timeline_label(event_type: str, metadata: dict | None) -> str:
    meta = metadata or {}
    kind = meta.get("kind")
    if event_type == "request_received":
        return "Received your request"
    if event_type == "constraints_parsed":
        if meta.get("needs_clarification"):
            return "Need one more detail"
        return "Understood your request"
    if event_type == "preferences_loaded":
        return "Loaded your preferences"
    if event_type == "calendar_loaded":
        if meta.get("calendar_read") == "unavailable":
            return "Calendar could not be checked"
        return "Checked your schedule"
    if event_type == "search_started":
        return "Searching restaurants" if kind == "restaurants" else "Searching activities"
    if event_type == "search_completed":
        noun = "restaurants" if kind == "restaurants" else "events"
        return f"Found {meta.get('count', 0)} possible {noun}"
    if event_type == "candidates_normalized":
        return "Prepared the options"
    if event_type == "candidates_ranked":
        return "Compared the best fits"
    if event_type == "constraints_verified":
        if meta.get("calendar_read") == "unavailable":
            return "Schedule conflicts were not checked"
        removed = int(meta.get("conflicts_removed") or 0)
        if removed == 1:
            return "Removed 1 conflict"
        if removed > 1:
            return f"Removed {removed} conflicts"
        return "Checked for schedule conflicts"
    if event_type == "recommendations_generated":
        count = int(meta.get("count") or 0)
        if count == 0:
            return "I could not find a good match."
        if count == 1:
            return "I found 1 good option."
        return f"I found {count} good options."
    if event_type == "candidate_selected":
        return "You chose an option"
    if event_type == "approval_requested":
        return "Waiting for your approval"
    if event_type == "approval_received":
        return "Approval received"
    if event_type == "calendar_write_started":
        return "Creating your calendar plan"
    if event_type == "calendar_write_completed":
        return "Scheduled"
    if event_type == "calendar_write_failed":
        return "Could not add this to your schedule"
    if event_type == "planning_failed":
        code = meta.get("error_code")
        if isinstance(code, str) and code in SAFE_MESSAGES:
            return SAFE_MESSAGES[code]
        return "The planning request failed"
    return "Updated the plan"


HIDDEN_WHEN_FOLLOWED_BY = {
    "request_received": "constraints_parsed",
    "search_started": "search_completed",
    "candidates_normalized": "candidates_ranked",
    "calendar_write_started": "calendar_write_completed",
}


def visible_timeline(events: list) -> list[tuple[object, str]]:
    present = {event.event_type for event in events}
    completed = {event.event_type for event in events if event.status == "completed"}
    visible = []
    for event in events:
        follower = HIDDEN_WHEN_FOLLOWED_BY.get(event.event_type)
        if follower and follower in present:
            continue
        if event.status == "started" and event.event_type in completed:
            continue
        visible.append(event)
    folded: list[tuple[object, str]] = []
    last = visible[-1] if visible else None
    for event in visible:
        status = "completed" if event is not last and event.status == "started" else event.status
        folded.append((event, status))
    return folded
