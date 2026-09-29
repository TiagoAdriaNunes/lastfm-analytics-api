import time
from collections.abc import Hashable
from typing import Any

MB = 2**20


class TTLCache:
    """Minimal in-memory cache with per-entry expiry (the `memoise` of the Shiny app).

    Bounded by the total `cost` of its entries, dropping the oldest first. Each entry costs 1 by
    default, so `max_cost` is an entry count; the Last.fm response caches pass an estimated size
    in bytes instead, because their entries range from ~1 KB to ~130 KB."""

    def __init__(self, ttl: float, max_cost: int = 1024) -> None:
        self._ttl = ttl
        self._max_cost = max_cost
        self._cost = 0
        self._data: dict[Hashable, tuple[float, Any, int]] = {}

    @property
    def cost(self) -> int:
        return self._cost

    def get(self, key: Hashable) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value, _ = entry
        if expires_at < time.monotonic():
            self._remove(key)
            return None
        return value

    def set(self, key: Hashable, value: Any, cost: int = 1) -> None:
        # Re-insert at the end, so a refreshed entry is the newest and its old cost is released.
        self._remove(key)
        if cost > self._max_cost:
            return  # would evict everything and still not fit
        while self._cost + cost > self._max_cost:
            # Dicts preserve insertion order, and every entry has the same TTL, so the first one
            # is both the oldest and the next to expire.
            self._remove(next(iter(self._data)))
        self._data[key] = (time.monotonic() + self._ttl, value, cost)
        self._cost += cost

    def _remove(self, key: Hashable) -> None:
        entry = self._data.pop(key, None)
        if entry is not None:
            self._cost -= entry[2]
