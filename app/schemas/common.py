"""Parsing helpers and models shared by the artist, album, track and tag schemas."""

from typing import Any

from pydantic import BaseModel


def as_list(value: Any) -> list[dict[str, Any]]:
    """Last.fm sends a lone item as an object instead of a one-item list, and an empty string
    or nothing when there are none."""
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


def optional_int(value: Any) -> int | None:
    # None when Last.fm leaves a stat out, so "unknown" isn't reported as 0.
    return int(value) if value not in (None, "") else None


def optional_seconds(value: Any, *, ms: bool = False) -> int | None:
    # Last.fm uses 0 for an unknown duration; track.getInfo reports milliseconds, others seconds.
    seconds = int(value or 0) // (1000 if ms else 1)
    return seconds or None


def rank(item: dict[str, Any]) -> int:
    return int(item.get("@attr", {}).get("rank") or 0)


def tag_names(tags: Any) -> list[str]:
    """Names from an embedded `{"tag": [...]}` block (e.g. `artist.getInfo`), which can be ""."""
    return [t["name"] for t in as_list((tags or {}).get("tag"))]


class WeightedTag(BaseModel):
    name: str
    count: int  # relative weight, 100 = the most-applied tag
    url: str | None = None


def parse_weighted_tags(payload: dict[str, Any], limit: int | None = None) -> list[WeightedTag]:
    """Tags from a `*.getTopTags` response, most-applied first. Those methods take no `limit`, so
    the list is truncated here."""
    return [
        WeightedTag(name=t["name"], count=int(t.get("count") or 0), url=t.get("url"))
        for t in as_list(payload.get("tag"))[:limit]
    ]


def search_total(results: dict[str, Any]) -> int:
    return int(results.get("opensearch:totalResults") or 0)
