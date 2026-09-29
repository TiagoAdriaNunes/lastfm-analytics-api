from aiolimiter import AsyncLimiter

from app.services.cache import TTLCache


class QuotaExceededError(Exception):
    """A public caller's budget of Last.fm calls is used up; retry after `retry_after` seconds."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"Quota exceeded, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class PublicQuota:
    """Budget of uncached Last.fm calls for the public (no API key) endpoints, on top of the shared
    limiter: `rate` calls/s for all anonymous callers together, and `client_rate` calls/s per
    client so one caller can't lock everyone else out. Never waits: `take` either takes a slot
    from both or raises `QuotaExceededError`, so requests don't queue up behind each other."""

    def __init__(self, rate: float, client_rate: float, max_clients: int) -> None:
        self._period = 1 / rate
        self._client_period = 1 / client_rate
        self._limiter = AsyncLimiter(1, self._period)
        # An idle client's limiter is back to full after one period, so it can expire then.
        self._clients = TTLCache(ttl=self._client_period, max_cost=max_clients)

    async def take(self, client: str) -> None:
        client_limiter = self._clients.get(client)
        if client_limiter is None:
            client_limiter = AsyncLimiter(1, self._client_period)
            self._clients.set(client, client_limiter)
        # Check both before taking either, so a refusal doesn't use up the other one.
        if not client_limiter.has_capacity():
            raise QuotaExceededError(self._client_period)
        if not self._limiter.has_capacity():
            raise QuotaExceededError(self._period)
        # Both have capacity, so these return without yielding: no other request can interleave.
        await client_limiter.acquire()
        await self._limiter.acquire()
