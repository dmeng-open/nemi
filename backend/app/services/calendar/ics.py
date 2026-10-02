from datetime import UTC, datetime

from icalendar import Calendar, Event

from app.domain.calendar import CalendarEvent


def build_ics(event: CalendarEvent, *, description: str | None = None) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//Nemi//Planning//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")

    component = Event()
    component.add("uid", f"{event.id}@nemi.local")
    component.add("dtstamp", datetime.now(UTC))
    component.add("dtstart", event.start)
    component.add("dtend", event.end)
    component.add("summary", event.title)
    body = description if description is not None else event.description
    if body:
        component.add("description", body)
    if event.location:
        component.add("location", event.location)
    if event.source_url:
        component.add("url", event.source_url)
    calendar.add_component(component)
    return calendar.to_ical()
