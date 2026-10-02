from datetime import UTC, datetime

from app.domain.calendar import CalendarEvent
from app.domain.candidates import Candidate
from app.domain.ranking import RankedCandidate, RankingContext, ScoreComponents
from app.services.calendar.ics import build_ics
from app.services.recommendations.explanations import merge_explanations


def test_ics_contains_the_event_fields() -> None:
    event = CalendarEvent(
        id="abc",
        title="AI Builders Workshop",
        start=datetime(2026, 10, 3, 19, 0, tzinfo=UTC),
        end=datetime(2026, 10, 3, 21, 0, tzinfo=UTC),
        location="Catalyst Hall",
        description="Planned with Nemi.",
        source_url="https://example.com/events/ai-builders-workshop",
    )
    payload = build_ics(event).decode()
    assert "BEGIN:VCALENDAR" in payload
    assert "SUMMARY:AI Builders Workshop" in payload
    assert "LOCATION:Catalyst Hall" in payload
    assert "Planned with Nemi." in payload
    assert "example.com/events/ai-builders-workshop" in payload
    assert "abc@nemi.local" in payload


def test_explanations_cannot_reorder_or_invent_candidates() -> None:
    candidate = Candidate(
        id="kept",
        candidate_type="event",
        title="Kept",
        categories=["technology"],
        source="test",
    )
    shown = [
        RankedCandidate(
            candidate=candidate,
            final_score=0.8,
            components=ScoreComponents(
                preference=0.8,
                schedule=1,
                distance=0.8,
                price=0.8,
                quality=0.8,
            ),
            schedule_compatible=True,
            shown=True,
            rank_position=1,
        )
    ]
    fallback = {"kept": "Fallback reason."}
    merged = merge_explanations(
        shown,
        {"other": "Ignore me.", "kept": "A real reason."},
        fallback,
    )
    assert list(merged) == ["kept"]
    assert merged["kept"] == "A real reason."
    context = RankingContext()
    assert "Kept" in __import__(
        "app.services.recommendations.explanations", fromlist=["template_explanation"]
    ).template_explanation(shown[0], context)
