from app.domain.ranking import RankedCandidate, RankingContext
from app.services.planning.taxonomy import humanize


def _join(reasons: list[str]) -> str:
    if len(reasons) == 1:
        return f"It {reasons[0]}."
    if len(reasons) == 2:
        return f"It {reasons[0]} and {reasons[1]}."
    return f"It {', '.join(reasons[:-1])}, and {reasons[-1]}."


def template_explanation(item: RankedCandidate, context: RankingContext) -> str:
    candidate = item.candidate
    liked = [
        token
        for token in candidate.categories
        if token in set(context.requested_categories) | set(context.preferred_categories)
    ]
    if liked:
        first = f"You said you enjoy {humanize(liked)}."
    else:
        first = f"{candidate.title} stood out among the nearby options."
    reasons: list[str] = []
    if item.schedule_compatible:
        reasons.append("fits your open time")
    if (
        context.budget_max is not None
        and candidate.price_min is not None
        and candidate.price_min <= context.budget_max
    ):
        reasons.append("fits your budget")
    if candidate.estimated_travel_minutes is not None:
        reasons.append(f"is about {candidate.estimated_travel_minutes} minutes away")
    second = _join(reasons) if reasons else "It is one of the stronger matches from this search."
    return f"{first} {second}"


def merge_explanations(
    shown: list[RankedCandidate],
    generated: dict[str, str],
    fallback: dict[str, str],
) -> dict[str, str]:
    merged: dict[str, str] = {}
    allowed = {item.candidate.id for item in shown}
    for item in shown:
        candidate_id = item.candidate.id
        text = generated.get(candidate_id, "").strip()
        if candidate_id not in allowed or not text:
            text = fallback[candidate_id]
        merged[candidate_id] = text[:400]
    return merged


class TemplateExplainer:
    async def explain(
        self,
        ranked: list[RankedCandidate],
        context: RankingContext,
    ) -> dict[str, str]:
        return {
            item.candidate.id: template_explanation(item, context) for item in ranked if item.shown
        }
