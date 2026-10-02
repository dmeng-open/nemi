from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.domain.calendar import CalendarEvent, TimeWindow
from app.domain.candidates import Candidate
from app.domain.ranking import RankingContext, RankingWeights
from app.services.ranking.heuristic import HeuristicRanker, combine, price_score

CHICAGO = ZoneInfo("America/Chicago")
START = datetime(2026, 10, 3, 14, 0, tzinfo=CHICAGO)


def _candidate(candidate_id: str, **kwargs) -> Candidate:
    data = {
        "id": candidate_id,
        "candidate_type": "event",
        "title": candidate_id,
        "categories": ["technology"],
        "start_datetime": START,
        "end_datetime": START + timedelta(hours=2),
        "estimated_travel_minutes": 10,
        "price_min": 20,
        "rating": 4,
        "source": "test",
    }
    data.update(kwargs)
    return Candidate(**data)


def _context(**kwargs) -> RankingContext:
    data = {
        "requested_categories": ["technology"],
        "free_windows": [TimeWindow(start=START.replace(hour=12), end=START.replace(hour=18))],
        "budget_max": 50,
        "max_travel_minutes": 20,
    }
    data.update(kwargs)
    return RankingContext(**data)


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        RankingWeights(preference=0.5, schedule=0.5, distance=0.5, price=0.1, quality=0.1)


def test_combine_applies_the_preference_weight() -> None:
    from app.domain.ranking import ScoreComponents

    components = ScoreComponents(preference=1, schedule=0, distance=0, price=0, quality=0)
    assert combine(components, RankingWeights()) == 0.35


def test_price_above_budget_scores_zero() -> None:
    assert price_score(80, 50) == 0
    assert price_score(25, 50) > 0


@pytest.mark.asyncio
async def test_conflict_ranks_below_a_free_match() -> None:
    busy = CalendarEvent(
        id="gym",
        title="Gym",
        start=START,
        end=START + timedelta(hours=1),
        location=None,
    )
    ranker = HeuristicRanker(RankingWeights())
    ranked = await ranker.rank(
        [
            _candidate("busy"),
            _candidate(
                "free", start_datetime=START.replace(hour=15), end_datetime=START.replace(hour=16)
            ),
        ],
        _context(busy_events=[busy]),
    )
    assert ranked[0].candidate.id == "free"
    busy_row = next(item for item in ranked if item.candidate.id == "busy")
    assert busy_row.components.schedule == 0
    assert busy_row.schedule_compatible is False


@pytest.mark.asyncio
async def test_tie_breaks_on_candidate_id() -> None:
    ranker = HeuristicRanker(RankingWeights())
    ranked = await ranker.rank([_candidate("b"), _candidate("a")], _context())
    assert [item.candidate.id for item in ranked] == ["a", "b"]
    assert ranked[0].final_score == ranked[1].final_score
