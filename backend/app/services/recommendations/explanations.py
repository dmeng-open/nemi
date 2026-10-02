import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.candidates import Candidate
from app.domain.ranking import RankedCandidate, RankingContext
from app.services.planning.taxonomy import humanize

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_FREE_CLAIM = re.compile(r"free slot|open time|no conflict", re.IGNORECASE)
_AT_PLACE = re.compile(r"\bat\s+([A-Z][^.,;\n]+)")


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
    if (
        item.schedule_compatible
        and context.calendar_read == "ok"
        and item.candidate.calendar_checked
    ):
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
    context: RankingContext | None = None,
) -> dict[str, str]:
    zone = _zone(context.timezone if context is not None else "America/Chicago")
    merged: dict[str, str] = {}
    allowed = {item.candidate.id for item in shown}
    for item in shown:
        candidate_id = item.candidate.id
        text = generated.get(candidate_id, "").strip()
        if candidate_id not in allowed or not text or not explanation_is_grounded(text, item, zone):
            text = fallback[candidate_id]
        merged[candidate_id] = text[:400]
    return merged


def explanation_is_grounded(text: str, item: RankedCandidate, zone: ZoneInfo) -> bool:
    if not _numbers_allowed(text, item.candidate, zone):
        return False
    if not item.candidate.calendar_checked and _FREE_CLAIM.search(text):
        return False
    if _mentions_unknown_place(text, item.candidate):
        return False
    return True


def _numbers_allowed(text: str, candidate: Candidate, zone: ZoneInfo) -> bool:
    allowed = _allowed_numbers(candidate, zone)
    for raw in _NUMBER.findall(text):
        if _normalize_number(raw) not in allowed:
            return False
    return True


def _normalize_number(raw: str) -> str:
    if "." in raw:
        return f"{float(raw):.1f}"
    return str(int(raw))


def _allowed_numbers(candidate: Candidate, zone: ZoneInfo) -> set[str]:
    allowed: set[str] = set()
    if candidate.estimated_travel_minutes is not None:
        allowed.add(str(int(candidate.estimated_travel_minutes)))
    if candidate.rating is not None:
        allowed.add(f"{float(candidate.rating):.1f}")
    for moment in (candidate.start_datetime, candidate.end_datetime):
        if moment is None:
            continue
        local = moment.astimezone(zone) if moment.tzinfo is not None else moment.replace(tzinfo=zone)
        allowed.add(str(local.hour))
        allowed.add(str(local.minute))
        allowed.add(str(local.hour % 12 or 12))
    return allowed


def _mentions_unknown_place(text: str, candidate: Candidate) -> bool:
    allowed = " ".join(
        part
        for part in (
            candidate.title,
            candidate.venue,
            candidate.address,
            " ".join(candidate.categories),
        )
        if part
    ).lower()
    for match in _AT_PLACE.finditer(text):
        phrase = match.group(1).strip().lower()
        if phrase and phrase not in allowed:
            return True
    return False


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


class TemplateExplainer:
    async def explain(
        self,
        ranked: list[RankedCandidate],
        context: RankingContext,
    ) -> dict[str, str]:
        return {
            item.candidate.id: template_explanation(item, context) for item in ranked if item.shown
        }
