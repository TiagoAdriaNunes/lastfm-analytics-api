from typing import Any

from pydantic import BaseModel

from app.schemas.common import as_list, rank

# Popular Last.fm tags that describe the listener or their collection rather than the music, left
# out of the genre list (same list as the R version).
NON_GENRE_TAGS = frozenset(
    {
        "albums i own",
        "awesome",
        "beautiful",
        "bookmark",
        "cover",
        "covers",
        "favorite",
        "favorites",
        "favourite",
        "favourites",
        "female vocalist",
        "female vocalists",
        "love",
        "male vocalist",
        "male vocalists",
        "mellow",
        "seen live",
    }
)


class TopTag(BaseModel):
    name: str
    reach: int  # listeners who used the tag
    taggings: int  # times it was applied
    url: str | None = None


class TopTagsResponse(BaseModel):
    tags: list[TopTag]


def parse_top_tags(data: dict[str, Any], genres_only: bool = False) -> TopTagsResponse:
    tags = as_list(data.get("tags", {}).get("tag"))
    if genres_only:
        tags = [t for t in tags if t["name"].casefold() not in NON_GENRE_TAGS]
    return TopTagsResponse(
        tags=[
            TopTag(
                name=t["name"],
                reach=int(t.get("reach") or 0),
                taggings=int(t.get("taggings") or 0),
                url=t.get("url"),
            )
            for t in tags
        ]
    )


class TagArtist(BaseModel):
    rank: int
    name: str
    mbid: str | None = None
    url: str | None = None


class TagArtistsResponse(BaseModel):
    tag: str
    total: int  # artists with this tag on Last.fm, not just the ones returned
    artists: list[TagArtist]


def parse_tag_artists(data: dict[str, Any]) -> TagArtistsResponse:
    # Last.fm answers an unknown tag with an empty list rather than an error.
    payload = data.get("topartists", {})
    attr = payload.get("@attr", {})
    return TagArtistsResponse(
        tag=attr.get("tag", ""),
        total=int(attr.get("total") or 0),
        artists=[
            TagArtist(
                rank=rank(a),
                name=a["name"],
                mbid=a.get("mbid") or None,
                url=a.get("url"),
            )
            for a in as_list(payload.get("artist"))
        ],
    )
