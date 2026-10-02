from collections.abc import Awaitable, Callable

from app.core.exceptions import ProviderError


async def call_with_retries[T](operation: Callable[[], Awaitable[T]], attempts: int = 3) -> T:
    last_error: ProviderError | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except ProviderError as exc:
            last_error = exc
            if not exc.retryable or attempt == attempts - 1:
                raise
    assert last_error is not None
    raise last_error
