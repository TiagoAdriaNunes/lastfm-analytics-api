import httpx2

from app.schemas.artist import SimilarArtist, SimilarArtistsResponse
from app.services.similar_network import build_similar_network


def similar(artist: str, *pairs: tuple[str, float]) -> SimilarArtistsResponse:
    return SimilarArtistsResponse(
        artist=artist, similar=[SimilarArtist(name=n, match=m) for n, m in pairs]
    )


def lastfm_payload(artist: str, *pairs: tuple[str, float]) -> dict:
    return {
        "similarartists": {
            "artist": [{"name": n, "match": str(m), "mbid": "", "url": ""} for n, m in pairs],
            "@attr": {"artist": artist},
        }
    }


def edge_set(network) -> set[tuple[str, str]]:
    names = {n.id: n.name for n in network.nodes}
    return {(names[e.source], names[e.target]) for e in network.edges}


def test_build_network_two_levels():
    network = build_similar_network(
        similar("A", ("B", 0.9), ("C", 0.7)),
        {"B": similar("B", ("D", 0.8)), "C": similar("C", ("E", 0.6))},
    )
    assert [(n.id, n.name, n.level) for n in network.nodes] == [
        (1, "A", 0),
        (2, "B", 1),
        (3, "C", 1),
        (4, "D", 2),
        (5, "E", 2),
    ]
    assert edge_set(network) == {("A", "B"), ("A", "C"), ("B", "D"), ("C", "E")}
    assert network.edges[0].weight == 0.9


def test_build_network_dedupes_nodes_and_links_shared_artists():
    network = build_similar_network(
        similar("A", ("B", 0.9), ("C", 0.7)),
        {
            "B": similar("B", ("A", 0.9), ("C", 0.5), ("D", 0.4)),
            "C": similar("C", ("B", 0.5), ("D", 0.3)),
        },
    )
    assert [n.name for n in network.nodes] == ["A", "B", "C", "D"]
    # B->A and C->B are reverse duplicates and are dropped; shared D is linked from both.
    assert edge_set(network) == {("A", "B"), ("A", "C"), ("B", "C"), ("B", "D"), ("C", "D")}


def test_build_network_skips_failed_second_level():
    network = build_similar_network(similar("A", ("B", 0.9)), {"B": None})
    assert [n.name for n in network.nodes] == ["A", "B"]
    assert len(network.edges) == 1


def test_network_endpoint(client, lastfm_mock):
    responses = {
        "Artist A": httpx2.Response(200, json=lastfm_payload("Artist A", ("B", 0.9), ("C", 0.7))),
        "B": httpx2.Response(200, json=lastfm_payload("B", ("D", 0.8))),
        "C": httpx2.Response(200, json={"error": 6, "message": "not found"}),
    }
    lastfm_mock.respond(side_effect=lambda req: responses[req.url.params["artist"]])

    response = client.get("/artists/Artist A/similar/network", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["artist"] == "Artist A"
    assert [n["name"] for n in body["nodes"]] == ["Artist A", "B", "C", "D"]
    assert body["edges"][0] == {"from": 1, "to": 2, "weight": 0.9}
    assert len(body["edges"]) == 3
    assert all(c.url.params["limit"] == "2" for c in lastfm_mock.requests)


def test_network_endpoint_main_artist_not_found(client, lastfm_mock):
    lastfm_mock.respond(
        return_value=httpx2.Response(200, json={"error": 6, "message": "not found"})
    )
    assert client.get("/artists/nope/similar/network").status_code == 404
