from app.domain.ranking import RankedCandidate


def exclusion_reason(
    item: RankedCandidate, *, budget_max: float | None, max_travel: int | None
) -> str | None:
    candidate = item.candidate
    if item.components.schedule == 0:
        return "conflict"
    travel = candidate.estimated_travel_minutes
    if max_travel is not None and travel is not None and travel > max_travel:
        return "travel"
    price = candidate.price_min
    if budget_max is not None and price is not None and price > budget_max:
        return "budget"
    if not item.schedule_compatible:
        return "outside_window"
    return None


def apply_exclusions(
    ranked: list[RankedCandidate],
    *,
    budget_max: float | None,
    max_travel: int | None,
    limit: int = 3,
) -> tuple[list[RankedCandidate], int]:
    conflicts = 0
    for item in ranked:
        reason = exclusion_reason(item, budget_max=budget_max, max_travel=max_travel)
        item.exclusion_reason = reason
        item.shown = False
        if reason == "conflict":
            conflicts += 1
    eligible = [item for item in ranked if item.exclusion_reason is None]
    for item in eligible[:limit]:
        item.shown = True
    return ranked, conflicts
