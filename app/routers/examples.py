"""Public endpoints (no API key) for trying the API. They have their own cache and a call budget
(`PublicQuota`: global + per client) on top of the shared Last.fm limiter, so anonymous traffic
can't starve the authenticated endpoints or push their entries out of the main cache."""

import math
from functools import partial
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.dependencies import ClientIP, PublicLastFMDep
from app.routers.artists import ArtistQuery, _call_lastfm
from app.schemas.artist import ArtistSearchResponse, parse_artist_search
from app.services.quota import QuotaExceededError

router = APIRouter(prefix="/examples", tags=["examples (public)"])


@router.get(
    "/artists/search",
    response_model=ArtistSearchResponse,
    responses={429: {"description": "Public quota used up; retry after `Retry-After` seconds"}},
)
async def search_artists(
    artist: ArtistQuery,
    lastfm: PublicLastFMDep,
    client_ip: ClientIP,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> ArtistSearchResponse:
    """Find artists on Last.fm by name (`artist.search`), with listener counts. No key needed."""
    quota = partial(request.app.state.public_quota.take, client_ip)
    try:
        data = await _call_lastfm(lastfm.search_artists(artist, limit=limit, quota=quota))
    except QuotaExceededError as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Public example quota exceeded, try again shortly",
            headers={"Retry-After": str(math.ceil(exc.retry_after))},
        ) from None
    return parse_artist_search(data)
