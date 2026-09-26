import asyncio

import httpx2

from app.schemas.artist import (
    NetworkEdge,
    NetworkNode,
    SimilarArtistsNetwork,
    SimilarArtistsResponse,
    parse_similar_artists,
)
from app.services.lastfm import RATE_LIMIT_ERROR, LastFMClient, LastFMError


def max_network_calls(limit: int, depth: int) -> int:
    """Worst-case Last.fm calls for a network: 1 + limit + limit² + ... (one per expanded artist).
    Deduplication usually makes it fewer."""
    return sum(limit**level for level in range(depth))


def build_similar_network(
    first_level: SimilarArtistsResponse,
    *deeper_levels: dict[str, SimilarArtistsResponse | None],
) -> SimilarArtistsNetwork:
    """Build the graph from `related_artists.R`, generalised to any depth: the searched artist
    (id 1) links to each similar artist, and each artist in `deeper_levels[i]` (name -> its
    similar artists, or None if the lookup failed) links to its own similar artists.

    Nodes are deduplicated by name and keep the level where they first appear. When an artist
    points to one already in the graph, an edge to the existing node is added so clusters
    connect."""
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

    for level in deeper_levels:
        for name, response in level.items():
            if response is None:
                continue
            source = ids[name]
            child_level = nodes[source - 1].level + 1
            for sub in response.similar:
                add_edge(source, add_node(sub.name, child_level, sub.url), sub.match)

    return SimilarArtistsNetwork(artist=first_level.artist, nodes=nodes, edges=edges)


async def fetch_similar_network(
    client: LastFMClient, artist: str, limit: int, depth: int = 2
) -> SimilarArtistsNetwork:
    """Fetch the searched artist's similar artists, then level by level (each level concurrently)
    the similar artists of every artist that first appeared in the previous level, `depth` levels
    deep. Artists already in the graph aren't looked up again. Call pacing is handled by the
    client's shared rate limiter.

    Errors on the first call propagate. Errors on deeper calls are swallowed so one failing
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
        except (httpx2.HTTPError, ValueError):
            return None

    seen = {first_level.artist}

    def new_names(responses: list[SimilarArtistsResponse | None]) -> list[str]:
        names = []
        for response in responses:
            for similar in response.similar if response else []:
                if similar.name not in seen:
                    seen.add(similar.name)
                    names.append(similar.name)
        return names

    frontier = new_names([first_level])
    deeper_levels = []
    for _ in range(depth - 1):
        results = await asyncio.gather(*(fetch(name) for name in frontier))
        deeper_levels.append(dict(zip(frontier, results, strict=True)))
        frontier = new_names(results)
    return build_similar_network(first_level, *deeper_levels)
