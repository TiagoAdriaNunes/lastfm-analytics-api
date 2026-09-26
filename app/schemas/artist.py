from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
        total=int(results.get("opensearch:totalResults") or 0),
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
