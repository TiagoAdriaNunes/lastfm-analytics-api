import httpx2

from tests.test_lastfm import MOCK_RESPONSE


def test_similar_artists(client, lastfm_mock):
    route = lastfm_mock.respond(return_value=httpx2.Response(200, json=MOCK_RESPONSE))

    response = client.get("/artists/similar", params={"artist": "Artist A", "limit": 2})

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

    response = client.get("/artists/similar", params={"artist": "nope"})

    assert response.status_code == 404
    assert response.json()["detail"] == "The artist you supplied could not be found"


def test_similar_artists_upstream_error(client, lastfm_mock):
    lastfm_mock.respond(
        return_value=httpx2.Response(403, json={"error": 10, "message": "Invalid API key"})
    )

    response = client.get("/artists/similar", params={"artist": "anyone"})

    assert response.status_code == 502


def test_similar_artists_limit_validation(client):
    assert client.get("/artists/similar", params={"artist": "x", "limit": 0}).status_code == 422


def test_artist_name_with_slash(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))

    response = client.get("/artists/similar", params={"artist": "AC/DC"})

    assert response.status_code == 200
    assert route.last_request.url.params["artist"] == "AC/DC"


def test_artist_network_name_with_slash(client, lastfm_mock):
    route = lastfm_mock.respond(
        httpx2.Response(200, json={"similarartists": {"artist": [], "@attr": {"artist": "AC/DC"}}})
    )

    response = client.get("/artists/similar/network", params={"artist": "AC/DC"})

    assert response.status_code == 200
    assert response.json()["nodes"][0]["name"] == "AC/DC"
    assert route.last_request.url.params["artist"] == "AC/DC"


def test_artist_is_required_and_not_blank(client):
    assert client.get("/artists/similar").status_code == 422
    assert client.get("/artists/similar", params={"artist": ""}).status_code == 422
    assert client.get("/artists/similar", params={"artist": "   "}).status_code == 422
    assert client.get("/artists/similar", params={"artist": "x" * 201}).status_code == 422
