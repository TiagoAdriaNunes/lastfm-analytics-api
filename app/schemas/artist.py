from typing import Any

from pydantic import BaseModel


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
