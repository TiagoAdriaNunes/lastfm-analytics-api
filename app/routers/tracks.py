from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import LastFMDep
from app.routers.common import ArtistQuery, call_lastfm, name_query
from app.schemas.track import (
    SimilarTracksResponse,
    TrackInfo,
    TrackSearchResponse,
    TrackTagsResponse,
    parse_similar_tracks,
    parse_track_info,
    parse_track_search,
    parse_track_tags,
)

router = APIRouter(prefix="/tracks", tags=["tracks"])

TrackQuery = Annotated[str, name_query("Track title, e.g. Creep")]


@router.get("/info", response_model=TrackInfo)
async def get_track_info(artist: ArtistQuery, track: TrackQuery, lastfm: LastFMDep) -> TrackInfo:
    """Track details (`track.getInfo`): album, duration, listener and play counts, tag names."""
    data = await call_lastfm(lastfm.get_track_info(artist, track))
    return parse_track_info(data)


@router.get("/similar", response_model=SimilarTracksResponse)
async def get_similar_tracks(
    artist: ArtistQuery,
    track: TrackQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SimilarTracksResponse:
    """Tracks similar to a track (`track.getSimilar`), with Last.fm's match score."""
    data = await call_lastfm(lastfm.get_similar_tracks(artist, track, limit=limit))
    return parse_similar_tracks(data)


@router.get("/tags", response_model=TrackTagsResponse)
async def get_track_tags(
    artist: ArtistQuery,
    track: TrackQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> TrackTagsResponse:
    """A track's most-applied Last.fm tags (`track.getTopTags`)."""
    data = await call_lastfm(lastfm.get_track_top_tags(artist, track))
    return parse_track_tags(data, limit=limit)


@router.get("/search", response_model=TrackSearchResponse)
async def search_tracks(
    track: TrackQuery,
    lastfm: LastFMDep,
    artist: Annotated[str | None, name_query("Narrow to an artist")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> TrackSearchResponse:
    """Find tracks on Last.fm by title (`track.search`), optionally narrowed to an artist."""
    data = await call_lastfm(lastfm.search_tracks(track, artist=artist, limit=limit))
    return parse_track_search(data)
