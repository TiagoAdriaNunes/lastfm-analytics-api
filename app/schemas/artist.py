from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    WeightedTag,
    as_list,
    optional_int,
    parse_rank,
    parse_weighted_tags,
    search_total,
    tag_names,
)


class SimilarArtist(BaseModel):
    name: str
    match: float
    mbid: str | None = None
    url: str | None = None


class SimilarArtistsResponse(BaseModel):
    artist: str
    similar: list[SimilarArtist]


def parse_similar_artists(data: dict[str, Any]) -> SimilarArtistsResponse:
    payload = data.get("similarartists", {})
    artists = payload.get("artist", [])
    return SimilarArtistsResponse(
        artist=payload.get("@attr", {}).get("artist", ""),
        similar=[
            SimilarArtist(
                name=a["name"],
                match=float(a["match"]),
                mbid=a.get("mbid") or None,
                url=a.get("url"),
            )
            for a in artists
        ],
    )


class ArtistSearchResult(BaseModel):
    name: str
    listeners: int
    mbid: str | None = None
    url: str | None = None


class ArtistSearchResponse(BaseModel):
    query: str
    total: int  # matches on Last.fm, not just the ones returned
    artists: list[ArtistSearchResult]


def parse_artist_search(data: dict[str, Any]) -> ArtistSearchResponse:
    results = data.get("results", {})
    artists = results.get("artistmatches", {}).get("artist", [])
    return ArtistSearchResponse(
        query=results.get("@attr", {}).get("for", ""),
        total=search_total(results),
        artists=[
            ArtistSearchResult(
                name=a["name"],
                listeners=int(a.get("listeners") or 0),
                mbid=a.get("mbid") or None,
                url=a.get("url"),
            )
            for a in artists
        ],
    )


class NetworkNode(BaseModel):
    id: int
    name: str
    level: int  # 0 = searched artist, 1 = similar, 2 = similar of similar, 3 = one more hop
    url: str | None = None


class NetworkEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: int = Field(alias="from")
    target: int = Field(alias="to")
    weight: float


class SimilarArtistsNetwork(BaseModel):
    artist: str
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


class ArtistInfo(BaseModel):
    name: str
    mbid: str | None = None
    url: str | None = None
    listeners: int | None = None
    playcount: int | None = None
    tags: list[str]


def parse_artist_info(data: dict[str, Any]) -> ArtistInfo:
    artist = data.get("artist", {})
    stats = artist.get("stats") or {}
    return ArtistInfo(
        name=artist.get("name", ""),
        mbid=artist.get("mbid") or None,
        url=artist.get("url"),
        listeners=optional_int(stats.get("listeners")),
        playcount=optional_int(stats.get("playcount")),
        tags=tag_names(artist.get("tags")),
    )


class ArtistTagsResponse(BaseModel):
    artist: str
    tags: list[WeightedTag]


def parse_artist_tags(data: dict[str, Any], limit: int | None = None) -> ArtistTagsResponse:
    payload = data.get("toptags", {})
    return ArtistTagsResponse(
        artist=payload.get("@attr", {}).get("artist", ""),
        tags=parse_weighted_tags(payload, limit),
    )


class ArtistTopAlbum(BaseModel):
    rank: int
    name: str
    playcount: int | None = None
    mbid: str | None = None
    url: str | None = None


class ArtistTopAlbumsResponse(BaseModel):
    artist: str
    total: int  # the artist's albums on Last.fm, not just the ones returned
    albums: list[ArtistTopAlbum]


def parse_artist_top_albums(data: dict[str, Any]) -> ArtistTopAlbumsResponse:
    payload = data.get("topalbums", {})
    attr = payload.get("@attr", {})
    return ArtistTopAlbumsResponse(
        artist=attr.get("artist", ""),
        total=int(attr.get("total") or 0),
        albums=[
            ArtistTopAlbum(
                rank=parse_rank(a),
                name=a["name"],
                playcount=optional_int(a.get("playcount")),
                mbid=a.get("mbid") or None,
                url=a.get("url"),
            )
            for a in as_list(payload.get("album"))
        ],
    )


class ArtistTopTrack(BaseModel):
    rank: int
    name: str
    playcount: int | None = None
    listeners: int | None = None
    mbid: str | None = None
    url: str | None = None


class ArtistTopTracksResponse(BaseModel):
    artist: str
    total: int  # the artist's tracks on Last.fm, not just the ones returned
    tracks: list[ArtistTopTrack]


def parse_artist_top_tracks(data: dict[str, Any]) -> ArtistTopTracksResponse:
    payload = data.get("toptracks", {})
    attr = payload.get("@attr", {})
    return ArtistTopTracksResponse(
        artist=attr.get("artist", ""),
        total=int(attr.get("total") or 0),
        tracks=[
            ArtistTopTrack(
                rank=parse_rank(t),
                name=t["name"],
                playcount=optional_int(t.get("playcount")),
                listeners=optional_int(t.get("listeners")),
                mbid=t.get("mbid") or None,
                url=t.get("url"),
            )
            for t in as_list(payload.get("track"))
        ],
    )
