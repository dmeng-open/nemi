from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HealthSnapshot:
    ok: bool
    at: datetime


class InMemoryProviderHealth:
    def __init__(self) -> None:
        self._last: dict[str, HealthSnapshot] = {}

    def record(self, provider: str, *, ok: bool, at: datetime) -> None:
        self._last[provider] = HealthSnapshot(ok=ok, at=at)

    def unhealthy(self, provider: str, *, now: datetime, window_seconds: float) -> bool:
        snap = self._last.get(provider)
        if snap is None or snap.ok:
            return False
        return (now - snap.at).total_seconds() <= window_seconds


_health: InMemoryProviderHealth | None = None


def get_provider_health() -> InMemoryProviderHealth:
    global _health
    if _health is None:
        _health = InMemoryProviderHealth()
    return _health
