from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import LastFMDep
from app.routers.common import call_lastfm, name_query
from app.schemas.tag import TagArtistsResponse, TopTagsResponse, parse_tag_artists, parse_top_tags

router = APIRouter(prefix="/tags", tags=["tags"])

TagQuery = Annotated[str, name_query("Last.fm tag, e.g. rock")]


@router.get("/top", response_model=TopTagsResponse)
async def get_top_tags(
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Tags requested from Last.fm")] = 100,
    genres_only: Annotated[
        bool, Query(description="Drop tags that aren't genres, e.g. 'seen live'")
    ] = True,
) -> TopTagsResponse:
    """Most used tags on Last.fm (`chart.getTopTags`). With `genres_only`, a few non-genre tags
    are filtered out after fetching, so fewer than `limit` may be returned."""
    data = await call_lastfm(lastfm.get_top_tags(limit=limit))
    return parse_top_tags(data, genres_only=genres_only)


@router.get("/artists", response_model=TagArtistsResponse)
async def get_tag_artists(
    tag: TagQuery,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TagArtistsResponse:
    """Top artists for a tag (`tag.getTopArtists`). An unknown tag returns an empty list."""
    data = await call_lastfm(lastfm.get_tag_top_artists(tag, limit=limit))
    return parse_tag_artists(data)
