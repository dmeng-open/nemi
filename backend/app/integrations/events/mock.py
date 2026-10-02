from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.integrations.events.catalog import EVENT_TEMPLATES
from app.integrations.events.models import EventCandidate, EventSearchQuery

HOME_LATITUDE = 41.9214
HOME_LONGITUDE = -87.648


def _coordinates(travel_minutes: int) -> tuple[float, float]:
    delta = travel_minutes / 1500
    return round(HOME_LATITUDE + delta, 5), round(HOME_LONGITUDE - delta, 5)


class MockEventProvider:
    async def search_events(self, query: EventSearchQuery) -> list[EventCandidate]:
        zone = ZoneInfo(query.timezone)
        found: list[EventCandidate] = []
        day = query.date_start
        while day <= query.date_end:
            for template in EVENT_TEMPLATES:
                if template.weekday != day.weekday():
                    continue
                start = datetime.combine(
                    day,
                    time(template.start_hour, template.start_minute),
                    tzinfo=zone,
                )
                end = datetime.combine(
                    day,
                    time(template.end_hour, template.end_minute),
                    tzinfo=zone,
                )
                latitude, longitude = _coordinates(template.travel_minutes)
                found.append(
                    EventCandidate(
                        id=f"evt_{template.slug}_{day.isoformat()}",
                        title=template.title,
                        description=template.description,
                        categories=list(template.categories),
                        start=start,
                        end=end,
                        venue=template.venue,
                        address=template.address,
                        latitude=latitude,
                        longitude=longitude,
                        distance_km=template.distance_km,
                        travel_minutes=template.travel_minutes,
                        price=template.price,
                        rating=template.rating,
                        url=f"https://example.com/events/{template.slug}",
                        image_url=template.image_url,
                    )
                )
            day += timedelta(days=1)
        found.sort(key=lambda item: (item.start, item.id))
        return found[: query.limit]
