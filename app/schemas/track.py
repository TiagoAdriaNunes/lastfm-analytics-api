from typing import Any

from pydantic import BaseModel

from app.schemas.common import (
    WeightedTag,
    as_list,
    optional_int,
    optional_seconds,
    parse_weighted_tags,
    search_total,
    tag_names,
)


class TrackInfo(BaseModel):
    name: str
    artist: str
    album: str | None = None
    mbid: str | None = None
    url: str | None = None
    duration: int | None = None  # seconds
    listeners: int | None = None
    playcount: int | None = None
    tags: list[str]


def parse_track_info(data: dict[str, Any]) -> TrackInfo:
    track = data.get("track", {})
    return TrackInfo(
        name=track.get("name", ""),
        artist=(track.get("artist") or {}).get("name", ""),
        album=(track.get("album") or {}).get("title") or None,
        mbid=track.get("mbid") or None,
        url=track.get("url"),
        duration=optional_seconds(track.get("duration"), ms=True),
        listeners=optional_int(track.get("listeners")),
        playcount=optional_int(track.get("playcount")),
        tags=tag_names(track.get("toptags")),
    )


class SimilarTrack(BaseModel):
    name: str
    artist: str
    match: float
    playcount: int | None = None
    mbid: str | None = None
    url: str | None = None


class SimilarTracksResponse(BaseModel):
    artist: str
    track: str
    similar: list[SimilarTrack]


def parse_similar_tracks(data: dict[str, Any]) -> SimilarTracksResponse:
    payload = data.get("similartracks", {})
    attr = payload.get("@attr", {})
    return SimilarTracksResponse(
        artist=attr.get("artist", ""),
        track=attr.get("track", ""),
        similar=[
            SimilarTrack(
                name=t["name"],
                artist=(t.get("artist") or {}).get("name", ""),
                match=float(t.get("match") or 0),
                playcount=optional_int(t.get("playcount")),
                mbid=t.get("mbid") or None,
                url=t.get("url"),
            )
            for t in as_list(payload.get("track"))
        ],
    )


class TrackTagsResponse(BaseModel):
    artist: str
    track: str
    tags: list[WeightedTag]


def parse_track_tags(data: dict[str, Any], limit: int | None = None) -> TrackTagsResponse:
    payload = data.get("toptags", {})
    attr = payload.get("@attr", {})
    return TrackTagsResponse(
        artist=attr.get("artist", ""),
        track=attr.get("track", ""),
        tags=parse_weighted_tags(payload, limit),
    )


class TrackSearchResult(BaseModel):
    name: str
    artist: str
    listeners: int | None = None
    mbid: str | None = None
    url: str | None = None


class TrackSearchResponse(BaseModel):
    query: str
    total: int  # matches on Last.fm, not just the ones returned
    tracks: list[TrackSearchResult]


def parse_track_search(data: dict[str, Any]) -> TrackSearchResponse:
    results = data.get("results", {})
    return TrackSearchResponse(
        query=results.get("@attr", {}).get("for", ""),
        total=search_total(results),
        tracks=[
            TrackSearchResult(
                name=t["name"],
                artist=t.get("artist", ""),
                listeners=optional_int(t.get("listeners")),
                mbid=t.get("mbid") or None,
                url=t.get("url"),
            )
            for t in as_list(results.get("trackmatches", {}).get("track"))
        ],
    )
