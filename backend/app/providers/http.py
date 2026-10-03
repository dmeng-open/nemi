import logging
from contextvars import ContextVar, Token

import httpx

from app.core.exceptions import ProviderError, ProviderNotConfigured

logger = logging.getLogger(__name__)

# Transport libraries log full URLs. Ticketmaster puts the API key in the query string.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_plan_id: ContextVar[str | None] = ContextVar("nemi_plan_id", default=None)


def bind_plan_id(plan_id: str | None) -> Token[str | None]:
    return _plan_id.set(plan_id)


def reset_plan_id(token: Token[str | None]) -> None:
    _plan_id.reset(token)


def current_plan_id() -> str | None:
    return _plan_id.get()


def log_provider_call(
    *,
    provider: str,
    operation: str,
    status_code: int | None,
    error_code: str | None = None,
    cache: str | None = None,
    count: int | None = None,
    skipped: int | None = None,
) -> None:
    extra: dict[str, object] = {
        "provider": provider,
        "operation": operation,
        "status_code": status_code,
        "plan_id": current_plan_id(),
    }
    if error_code is not None:
        extra["error_code"] = error_code
    if cache is not None:
        extra["cache"] = cache
    if count is not None:
        extra["count"] = count
    if skipped:
        extra["skipped"] = skipped
    logger.info("provider_call", extra=extra)


def not_configured(message: str) -> ProviderNotConfigured:
    return ProviderNotConfigured(message)


def failed(message: str) -> ProviderError:
    return ProviderError(message, retryable=False, code="provider_failed", status_code=502)


def unavailable(message: str) -> ProviderError:
    return ProviderError(message, retryable=True, code="provider_unavailable", status_code=503)


def error_from_status(
    status_code: int,
    *,
    provider: str,
    operation: str,
    not_configured_message: str,
    failed_message: str,
    quota: bool = False,
) -> ProviderError:
    if status_code in {401, 403} and not quota:
        log_provider_call(
            provider=provider,
            operation=operation,
            status_code=status_code,
            error_code="provider_not_configured",
        )
        return not_configured(not_configured_message)
    if status_code == 400:
        log_provider_call(
            provider=provider,
            operation=operation,
            status_code=status_code,
            error_code="provider_failed",
        )
        return failed(failed_message)
    if status_code in {429, 500, 502, 503} or status_code >= 500 or quota:
        log_provider_call(
            provider=provider,
            operation=operation,
            status_code=status_code,
            error_code="provider_unavailable",
        )
        return unavailable(failed_message)
    log_provider_call(
        provider=provider,
        operation=operation,
        status_code=status_code,
        error_code="provider_failed",
    )
    return failed(failed_message)


def error_from_transport(
    *,
    provider: str,
    operation: str,
    failed_message: str,
) -> ProviderError:
    log_provider_call(
        provider=provider,
        operation=operation,
        status_code=None,
        error_code="provider_unavailable",
    )
    return unavailable(failed_message)
