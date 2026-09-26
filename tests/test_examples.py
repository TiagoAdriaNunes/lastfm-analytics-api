import httpx2
from aiolimiter import AsyncLimiter

from app.main import app
from app.schemas.artist import parse_artist_search

SEARCH_RESPONSE = {
    "results": {
        "opensearch:totalResults": "1234",
        "artistmatches": {
            "artist": [
                {
                    "name": "Radiohead",
                    "listeners": "5000000",
                    "mbid": "a74b",
                    "url": "https://last.fm/r",
                },
                {
                    "name": "Radiohead Tribute",
                    "listeners": "12",
                    "mbid": "",
                    "url": "https://last.fm/t",
                },
            ]
        },
        "@attr": {"for": "radiohead"},
    }
}


def test_parse_artist_search():
    result = parse_artist_search(SEARCH_RESPONSE)
    assert result.query == "radiohead"
    assert result.total == 1234
    assert [a.name for a in result.artists] == ["Radiohead", "Radiohead Tribute"]
    assert result.artists[0].listeners == 5_000_000
    assert result.artists[0].mbid == "a74b"
    assert result.artists[1].mbid is None


def test_parse_artist_search_no_matches():
    result = parse_artist_search(
        {"results": {"opensearch:totalResults": "0", "artistmatches": {"artist": []}}}
    )
    assert result.total == 0
    assert result.artists == []


def test_search_is_public(client, lastfm_mock):
    client.headers.pop("X-API-Key")
    route = lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    response = client.get("/examples/artists/search", params={"artist": "radiohead", "limit": 2})

    assert response.status_code == 200
    assert response.json()["artists"][0] == {
        "name": "Radiohead",
        "listeners": 5_000_000,
        "mbid": "a74b",
        "url": "https://last.fm/r",
    }
    sent = route.last_request.url.params
    assert sent["method"] == "artist.search"
    assert sent["artist"] == "radiohead"
    assert sent["limit"] == "2"


def test_search_does_not_double_encode_plus(client, lastfm_mock):
    # artist.search decodes once, so "+" must go out as a normal "+" (see DOUBLE_DECODED_METHODS).
    route = lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    client.get("/examples/artists/search", params={"artist": "+44"})

    assert route.last_request.url.params["artist"] == "+44"


def test_search_limit_is_capped(client):
    response = client.get("/examples/artists/search", params={"artist": "x", "limit": 11})
    assert response.status_code == 422


def test_search_maps_lastfm_errors(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json={"error": 29, "message": "Rate Limit Exceeded"}))

    response = client.get("/examples/artists/search", params={"artist": "radiohead"})

    assert response.status_code == 503


def test_public_quota_returns_429_and_cache_hits_bypass_it(client, lastfm_mock):
    # Room for exactly one uncached call per minute.
    app.state.public_limiter = AsyncLimiter(1, 60)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    assert client.get("/examples/artists/search", params={"artist": "radiohead"}).status_code == 200
    # Same query: served from cache, doesn't need quota.
    assert client.get("/examples/artists/search", params={"artist": "Radiohead"}).status_code == 200
    # New query: needs Last.fm, but the quota is used up.
    response = client.get("/examples/artists/search", params={"artist": "muse"})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"  # ceil(1 / LASTFM__PUBLIC_RATE_LIMIT=1000)
    assert lastfm_mock.call_count == 1
