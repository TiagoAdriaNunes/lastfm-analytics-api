from collections.abc import Awaitable
from typing import Annotated

import httpx2
from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import LastFMDep
from app.schemas.artist import (
    SimilarArtistsNetwork,
    SimilarArtistsResponse,
    parse_similar_artists,
)
from app.services.lastfm import NOT_FOUND_ERROR, RETRYABLE_ERRORS, LastFMError
from app.services.similar_network import fetch_similar_network

router = APIRouter(prefix="/artists", tags=["artists"])


async def _call_lastfm[T](coro: Awaitable[T]) -> T:
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


@router.get("/{artist}/similar", response_model=SimilarArtistsResponse)
async def get_similar_artists(
    artist: str,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SimilarArtistsResponse:
    data = await _call_lastfm(lastfm.get_similar_artists(artist, limit=limit))
    return parse_similar_artists(data)


@router.get("/{artist}/similar/network", response_model=SimilarArtistsNetwork)
async def get_similar_artists_network(
    artist: str,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=20, description="Similar artists per level")] = 5,
) -> SimilarArtistsNetwork:
    """Two-level similar-artist graph (nodes + edges), ready for a network visualisation."""
    return await _call_lastfm(fetch_similar_network(lastfm, artist, limit))
