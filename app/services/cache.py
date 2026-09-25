import time
from collections.abc import Hashable
from typing import Any


class TTLCache:
    """Minimal in-memory cache with per-entry expiry (the `memoise` of the Shiny app)."""

    def __init__(self, ttl: float, maxsize: int = 1024) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._data: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            del self._data[key]
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        if len(self._data) >= self._maxsize:
            # Drop the oldest insertion; dicts preserve insertion order.
            self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + self._ttl, value)
