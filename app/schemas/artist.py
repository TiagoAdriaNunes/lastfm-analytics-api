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


class NetworkNode(BaseModel):
    id: int
    name: str
    level: int  # 0 = searched artist, 1 = similar, 2 = similar of similar
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
