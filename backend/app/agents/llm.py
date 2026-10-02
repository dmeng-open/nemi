import logging
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.agents.prompts.explain import EXPLAIN_SYSTEM, explain_user_message
from app.agents.prompts.parse_request import PARSE_SYSTEM, parse_user_message
from app.core.config import Settings
from app.core.exceptions import AppError, LLMTimeoutError, LLMValidationError
from app.core.messages import SAFE_MESSAGES
from app.domain.constraints import ConstraintDraft, PlanningConstraints
from app.domain.ranking import RankedCandidate, RankingContext
from app.services.planning.dates import finalize_constraints
from app.services.recommendations.explanations import merge_explanations, template_explanation

logger = logging.getLogger(__name__)


class ConstraintParser(Protocol):
    async def parse(
        self,
        text: str,
        *,
        now: datetime,
        zone: ZoneInfo,
    ) -> PlanningConstraints: ...


class Explainer(Protocol):
    async def explain(
        self,
        ranked: list[RankedCandidate],
        context: RankingContext,
    ) -> dict[str, str]: ...


class UnconfiguredParser:
    async def parse(
        self,
        text: str,
        *,
        now: datetime,
        zone: ZoneInfo,
    ) -> PlanningConstraints:
        del text, now, zone
        raise AppError(
            SAFE_MESSAGES["openai_unconfigured"],
            code="openai_unconfigured",
            status_code=400,
        )


class OpenAIGateway:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.openai_model
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

    async def parse(self, *, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        try:
            response = await self.client.responses.parse(
                model=self.model,
                instructions=system,
                input=user,
                text_format=schema,
                store=False,
            )
        except (APITimeoutError, APIConnectionError) as exc:
            raise LLMTimeoutError() from exc
        parsed = response.output_parsed
        if parsed is None:
            raise LLMValidationError()
        return parsed


class OpenAIConstraintParser:
    def __init__(self, gateway: OpenAIGateway) -> None:
        self.gateway = gateway

    async def parse(
        self,
        text: str,
        *,
        now: datetime,
        zone: ZoneInfo,
    ) -> PlanningConstraints:
        local_now = now.astimezone(zone)
        user = parse_user_message(
            text,
            today_label=local_now.strftime("%A, %B %d, %Y"),
            timezone=zone.key,
        )
        last_error: Exception | None = None
        for attempt in range(3):
            prompt = user
            if last_error is not None:
                prompt = f"{user}\n\nThe previous output was invalid: {last_error}"
            try:
                draft = await self.gateway.parse(
                    system=PARSE_SYSTEM,
                    user=prompt,
                    schema=ConstraintDraft,
                )
                if not isinstance(draft, ConstraintDraft):
                    draft = ConstraintDraft.model_validate(draft)
                return finalize_constraints(draft, local_now.date())
            except (LLMValidationError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.info("constraint_parse_retry", extra={"attempt": attempt + 1})
            except LLMTimeoutError:
                if attempt == 2:
                    raise
        raise LLMValidationError()


class _ExplanationItem(BaseModel):
    candidate_id: str
    explanation: str


class _ExplanationBatch(BaseModel):
    items: list[_ExplanationItem]


class OpenAIExplainer:
    def __init__(self, gateway: OpenAIGateway) -> None:
        self.gateway = gateway

    async def explain(
        self,
        ranked: list[RankedCandidate],
        context: RankingContext,
    ) -> dict[str, str]:
        shown = [item for item in ranked if item.shown]
        fallback = {item.candidate.id: template_explanation(item, context) for item in shown}
        payload = {
            "interests": context.requested_categories,
            "budget_max": context.budget_max,
            "max_travel_minutes": context.max_travel_minutes,
            "candidates": [
                {
                    "candidate_id": item.candidate.id,
                    "title": item.candidate.title,
                    "categories": item.candidate.categories,
                    "price": item.candidate.price_min,
                    "travel_minutes": item.candidate.estimated_travel_minutes,
                    "fits_schedule": item.schedule_compatible,
                }
                for item in shown
            ],
        }
        try:
            batch = await self.gateway.parse(
                system=EXPLAIN_SYSTEM,
                user=explain_user_message(payload),
                schema=_ExplanationBatch,
            )
        except Exception:
            logger.warning("explanation_fallback")
            return fallback
        if not isinstance(batch, _ExplanationBatch):
            batch = _ExplanationBatch.model_validate(batch)
        generated = {item.candidate_id: item.explanation for item in batch.items}
        return merge_explanations(shown, generated, fallback)
