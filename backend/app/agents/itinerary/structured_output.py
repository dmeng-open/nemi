"""Replaceable structured output for itinerary roles."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.agents.itinerary.engine import estimate_cost_usd
from app.core.config import Settings
from app.core.exceptions import AppError, LLMTimeoutError, LLMValidationError

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_PRICED_MODEL = "gpt-4o-mini"
_INVALID_NOTE = "\n\nThe previous output was invalid: "


@dataclass(frozen=True)
class StructuredUsage:
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    retry_count: int
    attempts: int
    prompt_sent: bool
    safe_metadata: dict[str, bool]


@dataclass(frozen=True)
class StructuredCompletion:
    parsed: object
    usage: StructuredUsage


class StructuredOutputPort(Protocol):
    """What itinerary deps will own. Tests pass a fake."""

    async def complete(
        self,
        *,
        role: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        deterministic: Callable[[], object],
    ) -> StructuredCompletion:
        """Return a parsed object and its usage."""


class StructuredOutputFailed(AppError):
    """The model output was still invalid after the allowed attempts."""

    code = "structured_output_invalid"
    status_code = 502

    def __init__(self, *, attempts: int, usage: StructuredUsage | None) -> None:
        super().__init__("The model returned an invalid structured result.")
        self.attempts = attempts
        self.retry_count = max(0, attempts - 1)
        self.usage = usage


class AttemptRefused(Exception):
    """No budget slot remains. This attempt must not call the provider."""


class ModelRequestFailed(AppError):
    """A provider API failure with a stable message and no chained provider text."""

    code = "model_request_failed"
    status_code = 502

    def __init__(self) -> None:
        super().__init__("The model request failed.")


class StructuredOutputTimeout(LLMTimeoutError):
    """The last allowed attempt timed out."""

    def __init__(self, *, attempts: int) -> None:
        super().__init__()
        self.attempts = attempts
        self.retry_count = max(0, attempts - 1)
        self.usage = None


class _RejectedOutput(Exception):
    def __init__(self, reason: Exception, usage: StructuredUsage) -> None:
        super().__init__(str(reason))
        self.reason = reason
        self.usage = usage


class OpenAIStructuredOutput:
    """OpenAI adapter. An empty key never constructs a client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncOpenAI | None = None
        if not settings.openai_configured:
            return
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

    async def complete(
        self,
        *,
        role: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        deterministic: Callable[[], object],
        reserve: Callable[[], Awaitable[None]] | None = None,
    ) -> StructuredCompletion:
        if self._client is None:
            return _deterministic_completion(deterministic())
        last_error: Exception | None = None
        last_usage: StructuredUsage | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if reserve is not None:
                try:
                    await reserve()
                except AttemptRefused:
                    if attempt == 1:
                        raise
                    raise StructuredOutputFailed(attempts=attempt - 1, usage=last_usage) from None
            prompt = user if last_error is None else f"{user}{_INVALID_NOTE}{last_error}"
            try:
                parsed, usage = await self._request(
                    role=role,
                    system=system,
                    user=prompt,
                    schema=schema,
                    attempt=attempt,
                )
            except _RejectedOutput as exc:
                last_error = exc.reason
                last_usage = exc.usage
                logger.info(
                    "structured_output_retry",
                    extra={"attempt": attempt, "role": role},
                )
            except (LLMValidationError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.info(
                    "structured_output_retry",
                    extra={"attempt": attempt, "role": role},
                )
            except LLMTimeoutError as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise StructuredOutputTimeout(attempts=attempt) from exc
            else:
                return StructuredCompletion(parsed=parsed, usage=usage)
        raise StructuredOutputFailed(attempts=_MAX_ATTEMPTS, usage=last_usage)

    async def _request(
        self,
        *,
        role: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        attempt: int,
    ) -> tuple[BaseModel, StructuredUsage]:
        client = self._client
        if client is None:
            raise RuntimeError("OpenAI client is not configured.")
        model = self._settings.model_for(role)
        try:
            response = await client.responses.parse(
                model=model,
                instructions=system,
                input=user,
                text_format=schema,
                store=False,
            )
        except (APITimeoutError, APIConnectionError) as exc:
            raise LLMTimeoutError() from exc
        except APIError:
            logger.warning("role=%s code=model_request_failed", role)
            raise ModelRequestFailed() from None
        usage = _usage_for(model, response, attempt)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise _RejectedOutput(LLMValidationError("Structured output was empty."), usage)
        if isinstance(parsed, schema):
            return parsed, usage
        try:
            validated = schema.model_validate(parsed)
        except (ValidationError, ValueError) as exc:
            raise _RejectedOutput(exc, usage) from exc
        return validated, usage


def _deterministic_completion(parsed: object) -> StructuredCompletion:
    return StructuredCompletion(
        parsed=parsed,
        usage=StructuredUsage(
            model="deterministic",
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            retry_count=0,
            attempts=0,
            prompt_sent=False,
            safe_metadata={},
        ),
    )


def _token_count(value: object) -> int | None:
    if type(value) is not int:
        return None
    return value


def _tokens(response: object) -> tuple[int, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    incoming = _token_count(getattr(usage, "input_tokens", None))
    outgoing = _token_count(getattr(usage, "output_tokens", None))
    if incoming is None or outgoing is None:
        return None
    return incoming, outgoing


def _usage_for(model: str, response: object, attempts: int) -> StructuredUsage:
    metadata: dict[str, bool] = {}
    counted = _tokens(response)
    if counted is None:
        incoming = 0
        outgoing = 0
        metadata["tokens_unreported"] = True
    else:
        incoming, outgoing = counted
    if model == _PRICED_MODEL:
        cost = estimate_cost_usd(incoming, outgoing)
    else:
        cost = 0.0
        metadata["cost_unpriced"] = True
    return StructuredUsage(
        model=model,
        input_tokens=incoming,
        output_tokens=outgoing,
        estimated_cost_usd=cost,
        retry_count=max(0, attempts - 1),
        attempts=attempts,
        prompt_sent=True,
        safe_metadata=metadata,
    )
