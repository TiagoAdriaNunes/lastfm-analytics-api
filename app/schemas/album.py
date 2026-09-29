from typing import Any

from pydantic import BaseModel

from app.schemas.common import (
    WeightedTag,
    as_list,
    optional_int,
    optional_seconds,
    parse_rank,
    parse_weighted_tags,
    search_total,
    tag_names,
)


class AlbumTrack(BaseModel):
    rank: int
    name: str
    duration: int | None = None  # seconds
    url: str | None = None


class AlbumInfo(BaseModel):
    name: str
    artist: str
    mbid: str | None = None
    url: str | None = None
    listeners: int | None = None
    playcount: int | None = None
    tags: list[str]
    tracks: list[AlbumTrack]


def parse_album_info(data: dict[str, Any]) -> AlbumInfo:
    album = data.get("album", {})
    return AlbumInfo(
        name=album.get("name", ""),
        artist=album.get("artist", ""),
        mbid=album.get("mbid") or None,
        url=album.get("url"),
        listeners=optional_int(album.get("listeners")),
        playcount=optional_int(album.get("playcount")),
        tags=tag_names(album.get("tags")),
        tracks=[
            AlbumTrack(
                rank=parse_rank(t),
                name=t["name"],
                duration=optional_seconds(t.get("duration")),
                url=t.get("url"),
            )
            for t in as_list((album.get("tracks") or {}).get("track"))
        ],
    )


class AlbumTagsResponse(BaseModel):
    artist: str
    album: str
    tags: list[WeightedTag]


def parse_album_tags(data: dict[str, Any], limit: int | None = None) -> AlbumTagsResponse:
    payload = data.get("toptags", {})
    attr = payload.get("@attr", {})
    return AlbumTagsResponse(
        artist=attr.get("artist", ""),
        album=attr.get("album", ""),
        tags=parse_weighted_tags(payload, limit),
    )


class AlbumSearchResult(BaseModel):
    name: str
    artist: str
    mbid: str | None = None
    url: str | None = None


class AlbumSearchResponse(BaseModel):
    query: str
    total: int  # matches on Last.fm, not just the ones returned
    albums: list[AlbumSearchResult]


def parse_album_search(data: dict[str, Any]) -> AlbumSearchResponse:
    results = data.get("results", {})
    return AlbumSearchResponse(
        query=results.get("@attr", {}).get("for", ""),
        total=search_total(results),
        albums=[
            AlbumSearchResult(
                name=a["name"],
                artist=a.get("artist", ""),
                mbid=a.get("mbid") or None,
                url=a.get("url"),
            )
            for a in as_list(results.get("albummatches", {}).get("album"))
        ],
    )
