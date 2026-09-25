import asyncio
import hashlib
from typing import Any

import httpx2
from aiolimiter import AsyncLimiter

from app.services.cache import TTLCache

# Last.fm error codes: https://www.last.fm/api/errorcodes
NOT_FOUND_ERROR = 6
RATE_LIMIT_ERROR = 29
RETRYABLE_ERRORS = {8, 11, 16, RATE_LIMIT_ERROR}
SIGNED_METHODS = {"auth.getSession", "track.scrobble"}

# Last.fm decodes the `artist`/`track` params of these methods twice, so a correctly encoded "+"
# (%2B) turns into a space: "+44" is not found and "Florence + The Machine" silently resolves to
# an empty "Florence   The Machine" page. Pre-encoding "+" as "%2B" survives the extra decode.
# Other methods (e.g. album.getInfo, artist.search) decode once and must not get this.
# See https://github.com/navidrome/navidrome/pull/6158
DOUBLE_DECODED_METHODS = {
    "artist.getInfo",
    "artist.getSimilar",
    "artist.getTopTracks",
    "track.getSimilar",
}
DOUBLE_DECODED_PARAMS = {"artist", "track"}


class LastFMError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def create_signature(params: dict[str, Any], secret: str) -> str:
    """Build the Last.fm API signature: every param except `format`, sorted by key,
    concatenated as key+value with the shared secret appended, then MD5'd.
    See https://www.last.fm/api/authspec."""
    base = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "format")
    return hashlib.md5((base + secret).encode("utf-8")).hexdigest()


class LastFMClient:
    def __init__(
        self,
        http: httpx2.AsyncClient,
        api_key: str,
        api_secret: str = "",
        cache: TTLCache | None = None,
        limiter: AsyncLimiter | None = None,
        max_retries: int = 0,
        retry_backoff: float = 1.0,
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._api_secret = api_secret
        self._cache = cache
        self._limiter = limiter
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        query |= {"method": method, "api_key": self._api_key, "format": "json"}
        if method in SIGNED_METHODS:
            query["api_sig"] = create_signature(query, self._api_secret)
        if method in DOUBLE_DECODED_METHODS:
            for key in DOUBLE_DECODED_PARAMS & query.keys():
                query[key] = str(query[key]).replace("+", "%2B")

        for attempt in range(self._max_retries + 1):
            try:
                return await self._request(query)
            except LastFMError as exc:
                if exc.code not in RETRYABLE_ERRORS or attempt == self._max_retries:
                    raise
                await asyncio.sleep(self._retry_backoff * 2**attempt)
        raise AssertionError("unreachable")

    async def _request(self, query: dict[str, Any]) -> dict[str, Any]:
        if self._limiter is not None:
            await self._limiter.acquire()
        response = await self._http.get("", params=query)
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        # Last.fm reports errors in the body, sometimes with a 200 status.
        if "error" in data:
            raise LastFMError(data["error"], data.get("message", "Unknown Last.fm error"))
        response.raise_for_status()
        return data

    async def get_similar_artists(self, artist: str, limit: int | None = None) -> dict[str, Any]:
        key = ("artist.getSimilar", artist.casefold(), limit)
        if self._cache is not None and (cached := self._cache.get(key)) is not None:
            return cached
        data = await self.call("artist.getSimilar", artist=artist, limit=limit, autocorrect=1)
        if self._cache is not None:
            self._cache.set(key, data)
        return data
