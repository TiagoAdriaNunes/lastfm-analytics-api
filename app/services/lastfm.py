import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any

import httpx2
from aiolimiter import AsyncLimiter
from loguru import logger

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
    "artist.getTopAlbums",
    "artist.getTopTags",
    "artist.getTopTracks",
    "track.getInfo",
    "track.getSimilar",
}
DOUBLE_DECODED_PARAMS = {"artist", "track"}

# A decoded Last.fm JSON body (not to be confused with `httpx2.Response`).
LastFMPayload = dict[str, Any]
# Cache key -> the Last.fm fetch currently running for it (see `LastFMClient._cached`).
InFlight = dict[Hashable, asyncio.Task[LastFMPayload]]


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


def _drop_images(obj: dict[str, Any]) -> dict[str, Any]:
    """`json.loads` hook: strip every `image` list while parsing. We never return images, and on
    a limit=100 list they are ~70-90% of the payload's memory, which would otherwise sit in the
    cache (artist images are only Last.fm's placeholder star anyway)."""
    obj.pop("image", None)
    return obj


def estimated_size(data: LastFMPayload) -> int:
    """Rough memory footprint of a parsed response, in bytes: 4x its JSON length. Measured RSS
    per cached entry was 1.4-3.6x the JSON length (small dicts ~1.5x, 100-item lists ~3.5x), so
    this errs on the safe side for the cache's MB budget."""
    return 4 * len(json.dumps(data))


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


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
        inflight: InFlight | None = None,
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._api_secret = api_secret
        self._cache = cache
        self._limiter = limiter
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._inflight = inflight

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        # What the caller asked for, for the logs: taken before `api_key`/`api_sig` are added and
        # before the "+" pre-encoding, so it's safe to log and reads like the input.
        log_params = dict(query)
        query |= {"method": method, "api_key": self._api_key, "format": "json"}
        if method in SIGNED_METHODS:
            query["api_sig"] = create_signature(query, self._api_secret)
        if method in DOUBLE_DECODED_METHODS:
            for key in DOUBLE_DECODED_PARAMS & query.keys():
                query[key] = str(query[key]).replace("+", "%2B")

        for attempt in range(self._max_retries + 1):
            try:
                return await self._request(method, query, log_params)
            except LastFMError as exc:
                if exc.code not in RETRYABLE_ERRORS or attempt == self._max_retries:
                    raise
                delay = self._retry_backoff * 2**attempt
                logger.warning(
                    "Retrying Last.fm {lastfm_method} in {delay}s after error {error_code} "
                    "(retry {retry} of {max_retries})",
                    lastfm_method=method,
                    delay=delay,
                    error_code=exc.code,
                    retry=attempt + 1,
                    max_retries=self._max_retries,
                )
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def _request(
        self, method: str, query: dict[str, Any], log_params: dict[str, Any]
    ) -> dict[str, Any]:
        queued = time.perf_counter()
        if self._limiter is not None:
            await self._limiter.acquire()
        started = time.perf_counter()
        # Never log `query` or an httpx error's text: both contain the URL with our `api_key`.
        fields: dict[str, Any] = {
            "lastfm_method": method,
            "params": log_params,
            "wait_ms": round((started - queued) * 1000, 1),
        }
        try:
            response = await self._http.get("", params=query)
        except httpx2.HTTPError as exc:
            logger.warning(
                "Last.fm {lastfm_method} failed: {error}",
                error=type(exc).__name__,
                duration_ms=_ms_since(started),
                **fields,
            )
            raise
        fields |= {"status": response.status_code, "duration_ms": _ms_since(started)}
        try:
            data = response.json(object_hook=_drop_images)
        except ValueError:
            logger.warning("Last.fm {lastfm_method} -> HTTP {status}, not JSON", **fields)
            response.raise_for_status()
            raise
        # Last.fm reports errors in the body, sometimes with a 200 status.
        if "error" in data:
            error = LastFMError(data["error"], data.get("message", "Unknown Last.fm error"))
            logger.warning(
                "Last.fm {lastfm_method} -> error {error_code}: {error_message}",
                error_code=error.code,
                error_message=error.message,
                **fields,
            )
            raise error
        if response.is_error:
            logger.warning("Last.fm {lastfm_method} -> HTTP {status}", **fields)
            response.raise_for_status()
        logger.info("Last.fm {lastfm_method} -> {status} in {duration_ms} ms", **fields)
        return data

    async def _cached(
        self, key: Hashable, fetch: Callable[[], Awaitable[LastFMPayload]]
    ) -> LastFMPayload:
        """Return the cached response for `key`, or fetch and cache it. With an `inflight` map
        (shared app-wide), concurrent misses for the same key share one fetch ("single-flight")
        instead of each calling Last.fm. Errors reach every waiter and are never cached."""
        if self._cache is not None and (cached := self._cache.get(key)) is not None:
            logger.debug("Cache hit for {cache_key}", cache_key=key)
            return cached
        if self._inflight is None:
            data = await fetch()
        else:
            data = await asyncio.shield(self._join_or_start(key, fetch))
        # The shared fetch caches in its starter's cache; a caller that joined it may use another
        # (public vs keyed endpoints), so cache here as well.
        self._store(key, data)
        return data

    def _store(self, key: Hashable, data: LastFMPayload) -> None:
        if self._cache is not None and self._cache.get(key) is None:
            self._cache.set(key, data, cost=estimated_size(data))

    def _join_or_start(
        self, key: Hashable, fetch: Callable[[], Awaitable[LastFMPayload]]
    ) -> asyncio.Task[LastFMPayload]:
        assert self._inflight is not None
        inflight = self._inflight
        task = inflight.get(key)
        # A finished task can linger until its done-callback runs; don't hand out its (possibly
        # failed) result, start a fresh fetch instead.
        if task is not None and not task.done():
            logger.debug("Joining in-flight Last.fm fetch for {cache_key}", cache_key=key)
            return task

        async def run() -> LastFMPayload:
            data = await fetch()
            # Cache here too, not only in the waiters: if every waiter was cancelled, the call
            # has still been made and its result should serve the next request.
            self._store(key, data)
            return data

        task = asyncio.ensure_future(run())
        inflight[key] = task

        def done(finished: asyncio.Task[LastFMPayload]) -> None:
            if inflight.get(key) is finished:  # don't remove a newer fetch for the same key
                del inflight[key]
            if not finished.cancelled():
                finished.exception()  # mark as retrieved even if every waiter was cancelled

        task.add_done_callback(done)
        return task

    async def get_similar_artists(self, artist: str, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("artist.getSimilar", artist.casefold(), limit),
            lambda: self.call("artist.getSimilar", artist=artist, limit=limit, autocorrect=1),
        )

    async def get_artist_info(self, artist: str) -> LastFMPayload:
        return await self._cached(
            ("artist.getInfo", artist.casefold()),
            lambda: self.call("artist.getInfo", artist=artist, autocorrect=1),
        )

    async def get_artist_top_tags(self, artist: str) -> LastFMPayload:
        # No `limit` on Last.fm's side: it always returns the full list, so callers truncate.
        return await self._cached(
            ("artist.getTopTags", artist.casefold()),
            lambda: self.call("artist.getTopTags", artist=artist, autocorrect=1),
        )

    async def get_artist_top_albums(self, artist: str, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("artist.getTopAlbums", artist.casefold(), limit),
            lambda: self.call("artist.getTopAlbums", artist=artist, limit=limit, autocorrect=1),
        )

    async def get_artist_top_tracks(self, artist: str, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("artist.getTopTracks", artist.casefold(), limit),
            lambda: self.call("artist.getTopTracks", artist=artist, limit=limit, autocorrect=1),
        )

    async def get_album_info(self, artist: str, album: str) -> LastFMPayload:
        return await self._cached(
            ("album.getInfo", artist.casefold(), album.casefold()),
            lambda: self.call("album.getInfo", artist=artist, album=album, autocorrect=1),
        )

    async def get_album_top_tags(self, artist: str, album: str) -> LastFMPayload:
        # Like artist.getTopTags: no `limit`, callers truncate.
        return await self._cached(
            ("album.getTopTags", artist.casefold(), album.casefold()),
            lambda: self.call("album.getTopTags", artist=artist, album=album, autocorrect=1),
        )

    async def search_albums(self, album: str, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("album.search", album.casefold(), limit),
            lambda: self.call("album.search", album=album, limit=limit),
        )

    async def get_track_info(self, artist: str, track: str) -> LastFMPayload:
        return await self._cached(
            ("track.getInfo", artist.casefold(), track.casefold()),
            lambda: self.call("track.getInfo", artist=artist, track=track, autocorrect=1),
        )

    async def get_similar_tracks(
        self, artist: str, track: str, limit: int | None = None
    ) -> LastFMPayload:
        return await self._cached(
            ("track.getSimilar", artist.casefold(), track.casefold(), limit),
            lambda: self.call(
                "track.getSimilar", artist=artist, track=track, limit=limit, autocorrect=1
            ),
        )

    async def get_track_top_tags(self, artist: str, track: str) -> LastFMPayload:
        # Like artist.getTopTags: no `limit`, callers truncate.
        return await self._cached(
            ("track.getTopTags", artist.casefold(), track.casefold()),
            lambda: self.call("track.getTopTags", artist=artist, track=track, autocorrect=1),
        )

    async def search_tracks(
        self, track: str, artist: str | None = None, limit: int | None = None
    ) -> LastFMPayload:
        return await self._cached(
            ("track.search", track.casefold(), artist.casefold() if artist else None, limit),
            lambda: self.call("track.search", track=track, artist=artist, limit=limit),
        )

    async def get_top_tags(self, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("chart.getTopTags", limit), lambda: self.call("chart.getTopTags", limit=limit)
        )

    async def get_tag_top_artists(self, tag: str, limit: int | None = None) -> LastFMPayload:
        return await self._cached(
            ("tag.getTopArtists", tag.casefold(), limit),
            lambda: self.call("tag.getTopArtists", tag=tag, limit=limit),
        )

    async def search_artists(
        self,
        artist: str,
        limit: int | None = None,
        quota: Callable[[], Awaitable[None]] | None = None,
    ) -> LastFMPayload:
        """`artist.search`. `quota` runs only when this caller actually calls Last.fm (cache
        miss and no identical fetch already running); public routes pass `PublicQuota.take`,
        which raises `QuotaExceededError` to refuse the call."""

        async def fetch() -> LastFMPayload:
            if quota is not None:
                await quota()
            return await self.call("artist.search", artist=artist, limit=limit)

        return await self._cached(("artist.search", artist.casefold(), limit), fetch)
