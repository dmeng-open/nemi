import hashlib
import json
import time
from typing import Protocol


class DiscoveryCache(Protocol):
    def get(self, key: str) -> object | None: ...

    def set(self, key: str, value: object) -> None: ...


class NullDiscoveryCache:
    def get(self, key: str) -> object | None:
        del key
        return None

    def set(self, key: str, value: object) -> None:
        del key, value


class InMemoryDiscoveryCache:
    def __init__(self, ttl_seconds: float) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[float, object]] = {}

    def get(self, key: str) -> object | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() >= expires_at:
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: object) -> None:
        self._items[key] = (time.monotonic() + self.ttl_seconds, value)


_cache: InMemoryDiscoveryCache | None = None


def get_discovery_cache(ttl_seconds: float) -> InMemoryDiscoveryCache:
    global _cache
    if _cache is None:
        _cache = InMemoryDiscoveryCache(ttl_seconds)
    return _cache


def discovery_cache_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def round_coord(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)
