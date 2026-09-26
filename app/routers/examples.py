"""Public endpoints (no API key) for trying the API. They get a small quota of their own on top
of the shared Last.fm limiter, so anonymous traffic can't starve the authenticated endpoints."""

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.config import get_settings
from app.dependencies import LastFMDep
from app.routers.artists import ArtistQuery, _call_lastfm
from app.schemas.artist import ArtistSearchResponse, parse_artist_search
from app.services.lastfm import QuotaExceededError

router = APIRouter(prefix="/examples", tags=["examples (public)"])


@router.get(
    "/artists/search",
    response_model=ArtistSearchResponse,
    responses={429: {"description": "Public quota used up; retry after `Retry-After` seconds"}},
)
async def search_artists(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> ArtistSearchResponse:
    """Find artists on Last.fm by name (`artist.search`), with listener counts. No key needed."""
    try:
        data = await _call_lastfm(
            lastfm.search_artists(artist, limit=limit, quota=request.app.state.public_limiter)
        )
    except QuotaExceededError:
        retry_after = math.ceil(1 / get_settings().lastfm.public_rate_limit)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Public example quota exceeded, try again shortly",
            headers={"Retry-After": str(retry_after)},
        ) from None
    return parse_artist_search(data)
