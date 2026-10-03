TICKETMASTER_NOT_CONFIGURED = (
    "Ticketmaster is selected but no API key is configured. Demo results were not substituted."
)
TICKETMASTER_FAILED = "Ticketmaster could not be reached. Demo results were not substituted."
PLACES_NOT_CONFIGURED = (
    "Google Places is selected but no API key is configured. Demo results were not substituted."
)
PLACES_FAILED = "Google Places could not be reached. Demo results were not substituted."
CALENDAR_NOT_CONFIGURED = "Google Calendar is selected but no OAuth client is configured."

SAFE_MESSAGES = {
    "parse_failed": "Could not understand that request. Try adding a day and whether you want an activity or a meal.",
    "date_unclear": "Could not understand the requested date.",
    "no_events": "No events matched your constraints.",
    "no_restaurants": "No restaurants matched your budget.",
    "no_matches": "No options matched your constraints.",
    "schedule_conflict": "Your selected option conflicts with another calendar event.",
    "planning_failed": "The planning request failed.",
    "openai_timeout": "OpenAI request timed out.",
    "openai_unconfigured": "Add your OpenAI API key to plan with Nemi.",
    "provider_failed": "The search failed. You can try again.",
    "provider_unavailable": "That provider is not available in this local setup.",
    "provider_not_configured": "That provider is not configured.",
    "approval_required": "Approve the plan before it is added to your schedule.",
    "city_required": "Add a home city in Preferences, then continue this plan. Event search needs a city.",
    "location_required": "Add latitude and longitude in Preferences, then continue this plan. Restaurant search needs coordinates.",
    "calendar_not_connected": "Connect Google Calendar to add this plan.",
    "calendar_read_failed": "Nemi could not re-check your calendar, so this was not added. Download the .ics file to add it yourself.",
    "calendar_write_unconfirmed": "Nemi could not confirm the calendar event. Download the .ics file to add it yourself.",
    "partial_success": "Part of this plan was added to your calendar. You can retry the rest, keep what was added, or remove it.",
    "tool_forbidden": "That action is not available.",
    "tool_limit": "Planning stopped because an agent made too many tool calls.",
}
