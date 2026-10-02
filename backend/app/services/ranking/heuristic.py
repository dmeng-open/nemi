from app.domain.calendar import CalendarEvent, TimeWindow
from app.domain.candidates import Candidate
from app.domain.ranking import RankedCandidate, RankingContext, RankingWeights, ScoreComponents
from app.services.calendar.conflicts import contained, overlaps


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def preference_score(
    categories: list[str],
    requested: list[str],
    preferred: list[str],
    disliked: list[str],
) -> float:
    cats = set(categories)
    if cats & set(disliked):
        return 0.05
    if not requested and not preferred:
        return 0.55
    primary = set(requested) if requested else set(preferred)
    hits = cats & primary
    if not hits:
        base = 0.12
    else:
        base = 0.72 + 0.28 * (len(hits) / len(primary))
    if requested and cats & set(preferred):
        base = min(1.0, base + 0.05)
    return clamp(base)


def distance_score(minutes: int | None, limit: int | None) -> float:
    if minutes is None:
        return 0.5
    if minutes < 0:
        return 0.0
    if limit is None:
        return clamp(1 - (minutes / 90))
    if minutes > limit:
        return 0.0
    return clamp(1 - 0.45 * (minutes / max(limit, 1)))


def price_score(price: float | None, budget: float | None) -> float:
    if price is None:
        return 0.65
    if price < 0:
        return 0.0
    if budget is None:
        return clamp(1 - min(price, 200) / 200)
    if price > budget:
        return 0.0
    if budget == 0:
        return 1.0 if price == 0 else 0.0
    return clamp(1 - 0.25 * (price / budget))


def quality_score(rating: float | None) -> float:
    if rating is None:
        return 0.5
    return clamp(rating / 5)


def schedule_parts(
    candidate: Candidate,
    busy: list[CalendarEvent],
    windows: list[TimeWindow],
) -> tuple[float, bool]:
    start = candidate.start_datetime
    end = candidate.end_datetime
    if start is None or end is None or end <= start:
        return 0.2, False
    if overlaps(start, end, busy):
        return 0.0, False
    if contained(start, end, windows):
        return 1.0, True
    return 0.35, False


def score_components(candidate: Candidate, context: RankingContext) -> tuple[ScoreComponents, bool]:
    interests = (
        context.requested_categories
        if candidate.candidate_type == "event"
        else context.requested_categories
    )
    # Restaurants are matched on cuisines, which the caller puts in requested_categories.
    schedule, compatible = schedule_parts(candidate, context.busy_events, context.free_windows)
    components = ScoreComponents(
        preference=round(
            preference_score(
                candidate.categories,
                interests,
                context.preferred_categories,
                context.disliked_categories,
            ),
            4,
        ),
        schedule=round(schedule, 4),
        distance=round(
            distance_score(candidate.estimated_travel_minutes, context.max_travel_minutes), 4
        ),
        price=round(price_score(candidate.price_min, context.budget_max), 4),
        quality=round(quality_score(candidate.rating), 4),
    )
    return components, compatible


def combine(components: ScoreComponents, weights: RankingWeights) -> float:
    total = (
        components.preference * weights.preference
        + components.schedule * weights.schedule
        + components.distance * weights.distance
        + components.price * weights.price
        + components.quality * weights.quality
    )
    return round(clamp(total), 4)


class HeuristicRanker:
    def __init__(self, weights: RankingWeights) -> None:
        self.weights = weights

    async def rank(
        self,
        candidates: list[Candidate],
        context: RankingContext,
    ) -> list[RankedCandidate]:
        ranked: list[RankedCandidate] = []
        for candidate in candidates:
            components, compatible = score_components(candidate, context)
            ranked.append(
                RankedCandidate(
                    candidate=candidate,
                    final_score=combine(components, self.weights),
                    components=components,
                    schedule_compatible=compatible,
                )
            )
        ranked.sort(key=lambda item: (-item.final_score, item.candidate.id))
        for index, item in enumerate(ranked, start=1):
            item.rank_position = index
        return ranked
