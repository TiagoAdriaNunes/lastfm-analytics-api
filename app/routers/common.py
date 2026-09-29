"""Helpers shared by every router that calls Last.fm."""

from collections.abc import Awaitable
from typing import Annotated, Any

import httpx2
from fastapi import HTTPException, Query, status

from app.services.lastfm import NOT_FOUND_ERROR, RETRYABLE_ERRORS, LastFMError


async def call_lastfm[T](coro: Awaitable[T]) -> T:
    """Translate Last.fm / transport failures into HTTP errors."""
    try:
        return await coro
    except LastFMError as exc:
        if exc.code == NOT_FOUND_ERROR:
            raise HTTPException(status.HTTP_404_NOT_FOUND, exc.message) from exc
        if exc.code in RETRYABLE_ERRORS:
            # Rate limited or temporarily down, and still failing after the client's retries.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, exc.message, headers={"Retry-After": "60"}
            ) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    except httpx2.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Last.fm request failed") from exc


def name_query(description: str) -> Any:
    """Query parameter for a free-text name (artist, album, track, tag). A query parameter, not a
    path segment: names can contain "/" (e.g. "AC/DC"), which would split the URL path and never
    match a route, even when percent-encoded."""
    return Query(min_length=1, max_length=200, pattern=r"\S", description=description)


ArtistQuery = Annotated[str, name_query("Artist name, e.g. AC/DC")]
