import httpx2

from tests.test_lastfm import MOCK_RESPONSE


def test_similar_artists(client, lastfm_mock):
    route = lastfm_mock.respond(return_value=httpx2.Response(200, json=MOCK_RESPONSE))

    response = client.get("/artists/Artist A/similar", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["artist"] == "Artist A"
    assert [a["name"] for a in body["similar"]] == ["Artist B", "Artist C"]
    sent = route.last_request.url.params
    assert sent["method"] == "artist.getSimilar"
    assert sent["artist"] == "Artist A"
    assert sent["limit"] == "2"
    assert sent["format"] == "json"


def test_similar_artists_not_found(client, lastfm_mock):
    lastfm_mock.respond(
        return_value=httpx2.Response(
            200, json={"error": 6, "message": "The artist you supplied could not be found"}
        )
    )

    response = client.get("/artists/nope/similar")

    assert response.status_code == 404
    assert response.json()["detail"] == "The artist you supplied could not be found"


def test_similar_artists_upstream_error(client, lastfm_mock):
    lastfm_mock.respond(
        return_value=httpx2.Response(403, json={"error": 10, "message": "Invalid API key"})
    )

    response = client.get("/artists/anyone/similar")

    assert response.status_code == 502


def test_similar_artists_limit_validation(client):
    assert client.get("/artists/x/similar", params={"limit": 0}).status_code == 422
