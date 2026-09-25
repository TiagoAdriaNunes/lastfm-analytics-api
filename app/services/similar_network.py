import asyncio

import httpx

from app.schemas.artist import (
    NetworkEdge,
    NetworkNode,
    SimilarArtistsNetwork,
    SimilarArtistsResponse,
    parse_similar_artists,
)
from app.services.lastfm import RATE_LIMIT_ERROR, LastFMClient, LastFMError


def build_similar_network(
    first_level: SimilarArtistsResponse,
    second_level: dict[str, SimilarArtistsResponse | None],
) -> SimilarArtistsNetwork:
    """Build the two-level graph from `related_artists.R`: the searched artist (id 1) links to
    each similar artist, and each similar artist links to its own similar artists.

    Nodes are deduplicated by name. When a similar artist points to an artist that is already in
    the graph, an edge to the existing node is added so the clusters connect."""
    nodes: list[NetworkNode] = []
    edges: list[NetworkEdge] = []
    ids: dict[str, int] = {}
    seen_edges: set[tuple[int, int]] = set()

    def add_node(name: str, level: int, url: str | None = None) -> int:
        if name not in ids:
            ids[name] = len(nodes) + 1
            nodes.append(NetworkNode(id=ids[name], name=name, level=level, url=url))
        return ids[name]

    def add_edge(source: int, target: int, weight: float) -> None:
        # Skip self-loops and reverse duplicates (A->B and B->A are the same similarity link).
        if source == target or (source, target) in seen_edges or (target, source) in seen_edges:
            return
        seen_edges.add((source, target))
        edges.append(NetworkEdge(source=source, target=target, weight=weight))

    root = add_node(first_level.artist, level=0)
    for artist in first_level.similar:
        add_edge(root, add_node(artist.name, 1, artist.url), artist.match)

    for artist in first_level.similar:
        second = second_level.get(artist.name)
        if second is None:
            continue
        source = ids[artist.name]
        for sub in second.similar:
            add_edge(source, add_node(sub.name, 2, sub.url), sub.match)

    return SimilarArtistsNetwork(artist=first_level.artist, nodes=nodes, edges=edges)


async def fetch_similar_network(
    client: LastFMClient, artist: str, limit: int
) -> SimilarArtistsNetwork:
    """Fetch the searched artist's similar artists, then (concurrently) each of theirs.
    Call pacing is handled by the client's shared rate limiter.

    Errors on the first call propagate. Errors on second-level calls are swallowed so one failing
    artist doesn't break the whole graph (same as the `tryCatch` in the Shiny app), except rate
    limiting, which propagates instead of returning a silently incomplete graph."""
    first_level = parse_similar_artists(await client.get_similar_artists(artist, limit=limit))
    first_level.artist = first_level.artist or artist

    async def fetch(name: str) -> SimilarArtistsResponse | None:
        try:
            return parse_similar_artists(await client.get_similar_artists(name, limit=limit))
        except LastFMError as exc:
            if exc.code == RATE_LIMIT_ERROR:
                raise
            return None
        except (httpx.HTTPError, ValueError):
            return None

    names = [a.name for a in first_level.similar]
    results = await asyncio.gather(*(fetch(name) for name in names))
    return build_similar_network(first_level, dict(zip(names, results, strict=True)))
