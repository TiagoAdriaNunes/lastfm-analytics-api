from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import LastFMDep
from app.routers.artists import ArtistQuery, _call_lastfm
from app.schemas.album import (
    AlbumInfo,
    AlbumSearchResponse,
    AlbumTagsResponse,
    parse_album_info,
    parse_album_search,
    parse_album_tags,
)

router = APIRouter(prefix="/albums", tags=["albums"])

# Query parameter for the same reason as `ArtistQuery`: titles can contain "/".
AlbumQuery = Annotated[
    str,
    Query(min_length=1, max_length=200, pattern=r"\S", description="Album title, e.g. OK Computer"),
]


@router.get("/info", response_model=AlbumInfo)
async def get_album_info(artist: ArtistQuery, album: AlbumQuery, lastfm: LastFMDep) -> AlbumInfo:
    """Album details (`album.getInfo`): listener and play counts, tag names, track list."""
    data = await _call_lastfm(lastfm.get_album_info(artist, album))
    return parse_album_info(data)


@router.get("/tags", response_model=AlbumTagsResponse)
async def get_album_tags(
    artist: ArtistQuery,
    album: AlbumQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
) -> AlbumTagsResponse:
    """An album's most-applied Last.fm tags (`album.getTopTags`)."""
    data = await _call_lastfm(lastfm.get_album_top_tags(artist, album))
    return parse_album_tags(data, limit=limit)


@router.get("/search", response_model=AlbumSearchResponse)
async def search_albums(
    album: AlbumQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> AlbumSearchResponse:
    """Find albums on Last.fm by title (`album.search`)."""
    data = await _call_lastfm(lastfm.search_albums(album, limit=limit))
    return parse_album_search(data)
