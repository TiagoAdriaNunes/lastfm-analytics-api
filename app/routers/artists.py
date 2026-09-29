from collections.abc import Awaitable
from typing import Annotated

import httpx2
from fastapi import APIRouter, HTTPException, Query, status

from app.config import get_settings
from app.dependencies import LastFMDep
from app.schemas.artist import (
    ArtistInfo,
    ArtistSearchResponse,
    ArtistTagsResponse,
    ArtistTopAlbumsResponse,
    ArtistTopTracksResponse,
    SimilarArtistsNetwork,
    SimilarArtistsResponse,
    parse_artist_info,
    parse_artist_search,
    parse_artist_tags,
    parse_artist_top_albums,
    parse_artist_top_tracks,
    parse_similar_artists,
)
from app.services.lastfm import NOT_FOUND_ERROR, RETRYABLE_ERRORS, LastFMError
from app.services.similar_network import fetch_similar_network, max_network_calls

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


# Query parameter, not a path segment: artist names can contain "/" (e.g. "AC/DC"), which would
# split the URL path and never match a route, even when percent-encoded.
ArtistQuery = Annotated[
    str,
    Query(min_length=1, max_length=200, pattern=r"\S", description="Artist name, e.g. AC/DC"),
]


@router.get("/search", response_model=ArtistSearchResponse)
async def search_artists(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ArtistSearchResponse:
    """Find artists on Last.fm by name (`artist.search`), with listener counts."""
    data = await _call_lastfm(lastfm.search_artists(artist, limit=limit))
    return parse_artist_search(data)


@router.get("/info", response_model=ArtistInfo)
async def get_artist_info(artist: ArtistQuery, lastfm: LastFMDep) -> ArtistInfo:
    """Artist details (`artist.getInfo`): listener and play counts, top tag names."""
    data = await _call_lastfm(lastfm.get_artist_info(artist))
    return parse_artist_info(data)


@router.get("/tags", response_model=ArtistTagsResponse)
async def get_artist_tags(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> ArtistTagsResponse:
    """An artist's most-applied Last.fm tags (`artist.getTopTags`), usable as genres."""
    data = await _call_lastfm(lastfm.get_artist_top_tags(artist))
    return parse_artist_tags(data, limit=limit)


@router.get("/albums", response_model=ArtistTopAlbumsResponse)
async def get_artist_top_albums(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ArtistTopAlbumsResponse:
    """An artist's most played albums (`artist.getTopAlbums`)."""
    data = await _call_lastfm(lastfm.get_artist_top_albums(artist, limit=limit))
    return parse_artist_top_albums(data)


@router.get("/tracks", response_model=ArtistTopTracksResponse)
async def get_artist_top_tracks(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ArtistTopTracksResponse:
    """An artist's most played tracks (`artist.getTopTracks`)."""
    data = await _call_lastfm(lastfm.get_artist_top_tracks(artist, limit=limit))
    return parse_artist_top_tracks(data)


@router.get("/similar", response_model=SimilarArtistsResponse)
async def get_similar_artists(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SimilarArtistsResponse:
    data = await _call_lastfm(lastfm.get_similar_artists(artist, limit=limit))
    return parse_similar_artists(data)


@router.get("/similar/network", response_model=SimilarArtistsNetwork)
async def get_similar_artists_network(
    artist: ArtistQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=20, description="Similar artists per level")] = 5,
    depth: Annotated[int, Query(ge=1, le=3, description="Levels around the searched artist")] = 2,
) -> SimilarArtistsNetwork:
    """Similar-artist graph (nodes + edges), `depth` levels deep, ready for a network
    visualisation. Deeper graphs need more Last.fm calls: up to 1 + limit + limit² for depth 3,
    capped by `lastfm.network_max_calls` (e.g. depth 3 works up to limit 7)."""
    max_calls = get_settings().lastfm.network_max_calls
    if (calls := max_network_calls(limit, depth)) > max_calls:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"limit={limit} with depth={depth} can need {calls} Last.fm calls (max {max_calls}); "
            "lower limit or depth",
        )
    return await _call_lastfm(fetch_similar_network(lastfm, artist, limit, depth))
