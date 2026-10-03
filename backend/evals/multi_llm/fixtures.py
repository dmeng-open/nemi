"""Frozen evening used by the golden checks.

The clock is the suite's Friday, 2026-10-02, so "Saturday" is 2026-10-03.
The set does not follow the wall clock. It does not cover a missing date.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.candidates import Candidate
from evals.multi_llm import DATASET_VERSION

FROZEN_TODAY = date(2026, 10, 2)
EVENING = date(2026, 10, 3)
TIMEZONE = "America/Chicago"
ZONE = ZoneInfo(TIMEZONE)
RETRIEVED_AT = datetime(2026, 10, 2, 15, 0, tzinfo=ZONE)

LEGAL_RESTAURANT_ID = "nori-ramen"
REJECTABLE_RESTAURANT_ID = "kura-sushi-grill"
OVER_BUDGET_RESTAURANT_ID = "ginza-grill"
DIET_EXCLUDED_RESTAURANT_ID = "sushi-counter"
LEGAL_EVENT_ID = "early-jazz"
LATE_EVENT_ID = "late-jazz"
FAILED_BRANCH = "restaurant"

REQUEST_TEXT = (
    "Plan a date night this Saturday.\n"
    "We're free after 5 PM.\n"
    "Budget is $120 total.\n"
    "We want Japanese food, but one person doesn't eat raw fish.\n"
    "After dinner we'd like jazz.\n"
    "We need to be home before 11 PM.\n"
)

ILLEGAL_IDS = frozenset(
    {
        OVER_BUDGET_RESTAURANT_ID,
        DIET_EXCLUDED_RESTAURANT_ID,
        LATE_EVENT_ID,
    }
)


class GoldenCase:
    def __init__(
        self,
        case_id: str,
        restaurants: tuple[Candidate, ...],
        events: tuple[Candidate, ...],
        *,
        failed_branch: str | None = None,
    ) -> None:
        self.case_id = case_id
        self.request_text = REQUEST_TEXT
        self.today = FROZEN_TODAY
        self.timezone = TIMEZONE
        self.restaurants = restaurants
        self.events = events
        self.illegal_ids = ILLEGAL_IDS
        self.failed_branch = failed_branch
        self.dataset_version = DATASET_VERSION


def _restaurant(
    candidate_id: str,
    title: str,
    description: str,
    *,
    price: float,
    rating: float,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        candidate_type="restaurant",
        title=title,
        description=description,
        categories=["japanese"],
        estimated_travel_minutes=10,
        price_min=price,
        price_max=price,
        rating=rating,
        source="frozen",
        provider="frozen",
        external_id=candidate_id,
        retrieved_at=RETRIEVED_AT,
        travel_time_is_estimate=True,
    )


def _event(
    candidate_id: str,
    title: str,
    *,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    price: float,
    rating: float,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        candidate_type="event",
        title=title,
        description="A small-room jazz set.",
        categories=["live_music"],
        start_datetime=datetime(EVENING.year, EVENING.month, EVENING.day, start_hour, start_minute, tzinfo=ZONE),
        end_datetime=datetime(EVENING.year, EVENING.month, EVENING.day, end_hour, end_minute, tzinfo=ZONE),
        venue="The Blue Lantern",
        address="2124 N Lincoln Ave, Chicago",
        estimated_travel_minutes=12,
        price_min=price,
        price_max=price,
        rating=rating,
        source="frozen",
        provider="frozen",
        external_id=candidate_id,
        retrieved_at=RETRIEVED_AT,
        travel_time_is_estimate=True,
    )


def _legal_dinner() -> Candidate:
    return _restaurant(
        LEGAL_RESTAURANT_ID,
        "Nori Ramen House",
        "A cooked ramen shop.",
        price=28,
        rating=4.2,
    )


def _over_budget() -> Candidate:
    return _restaurant(
        OVER_BUDGET_RESTAURANT_ID,
        "Ginza Grill",
        "A cooked grill tasting menu.",
        price=180,
        rating=4.8,
    )


def _diet_excluded() -> Candidate:
    return _restaurant(
        DIET_EXCLUDED_RESTAURANT_ID,
        "Sushi Counter",
        "Nigiri and sashimi only.",
        price=40,
        rating=4.8,
    )


def _rejectable_dinner() -> Candidate:
    return _restaurant(
        REJECTABLE_RESTAURANT_ID,
        "Kura Sushi Grill",
        "Nigiri plus a cooked grill.",
        price=48,
        rating=4.9,
    )


def _legal_event() -> Candidate:
    return _event(
        LEGAL_EVENT_ID,
        "Early Jazz Set",
        start_hour=20,
        start_minute=0,
        end_hour=21,
        end_minute=30,
        price=25,
        rating=4.6,
    )


def _late_event() -> Candidate:
    return _event(
        LATE_EVENT_ID,
        "Late Jazz Set",
        start_hour=22,
        start_minute=0,
        end_hour=23,
        end_minute=30,
        price=30,
        rating=4.4,
    )


DATE_NIGHT = GoldenCase(
    "date-night",
    (_legal_dinner(), _over_budget(), _diet_excluded()),
    (_legal_event(), _late_event()),
)

CRITIC_REPLAN = GoldenCase(
    "critic-replan",
    (_rejectable_dinner(), _legal_dinner(), _over_budget(), _diet_excluded()),
    (_legal_event(), _late_event()),
    failed_branch=FAILED_BRANCH,
)
