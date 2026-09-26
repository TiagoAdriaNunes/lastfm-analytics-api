import asyncio

import httpx2
import pytest

from app.main import app
from app.schemas.artist import parse_artist_search
from app.services.quota import PublicQuota, QuotaExceededError

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


def search(client, artist: str, ip: str | None = None) -> httpx2.Response:
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.get("/examples/artists/search", params={"artist": artist}, headers=headers)


def test_client_quota_returns_429_and_cache_hits_bypass_it(client, lastfm_mock):
    # Global budget is plentiful; each client gets one uncached call per minute.
    app.state.public_quota = PublicQuota(rate=1000, client_rate=1 / 60, max_clients=10)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    assert search(client, "radiohead").status_code == 200
    # Same query: served from cache, doesn't need quota.
    assert search(client, "Radiohead").status_code == 200
    # New query: needs Last.fm, but this client's quota is used up.
    response = search(client, "muse")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert lastfm_mock.call_count == 1


def test_one_client_cannot_lock_out_others(client, lastfm_mock):
    app.state.public_quota = PublicQuota(rate=1000, client_rate=1 / 60, max_clients=10)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    assert search(client, "radiohead", ip="1.1.1.1").status_code == 200
    assert search(client, "muse", ip="1.1.1.1").status_code == 429
    assert search(client, "muse", ip="2.2.2.2").status_code == 200


def test_global_quota_caps_all_clients_together(client, lastfm_mock):
    app.state.public_quota = PublicQuota(rate=1 / 60, client_rate=1000, max_clients=10)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    assert search(client, "radiohead", ip="1.1.1.1").status_code == 200
    response = search(client, "muse", ip="2.2.2.2")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_client_ip_uses_leftmost_forwarded_for(client, lastfm_mock):
    # Railway puts the real client first and may append its own internal hops after it.
    app.state.public_quota = PublicQuota(rate=1000, client_rate=1 / 60, max_clients=10)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    assert search(client, "radiohead", ip="1.1.1.1, 100.64.0.1").status_code == 200
    assert search(client, "muse", ip="1.1.1.1, 100.64.0.2").status_code == 429
    assert search(client, "muse", ip="2.2.2.2, 100.64.0.1").status_code == 200


async def test_global_refusal_does_not_use_up_the_client_slot():
    quota = PublicQuota(rate=20, client_rate=1 / 60, max_clients=10)  # global: every 0.05s
    await quota.take("a")
    with pytest.raises(QuotaExceededError):
        await quota.take("b")  # global is full
    await asyncio.sleep(0.06)
    await quota.take("b")  # b's own slot (one per minute) must still be free


async def test_client_refusal_does_not_use_up_the_global_slot():
    quota = PublicQuota(rate=5, client_rate=1 / 60, max_clients=10)  # global: every 0.2s
    await quota.take("a")
    await asyncio.sleep(0.25)
    with pytest.raises(QuotaExceededError):
        await quota.take("a")  # a's own slot is used up
    await quota.take("b")  # the global slot must still be free


def test_public_results_use_their_own_cache(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    search(client, "radiohead")
    client.get("/artists/search", params={"artist": "radiohead", "limit": 5})

    # Same query and limit, but the caches are separate: two Last.fm calls.
    assert lastfm_mock.call_count == 2


def test_refusal_is_logged_with_client_ip(client, lastfm_mock, caplog):
    app.state.public_quota = PublicQuota(rate=1000, client_rate=1 / 60, max_clients=10)
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    search(client, "radiohead", ip="1.1.1.1")
    with caplog.at_level("INFO", logger="uvicorn.error"):
        search(client, "muse", ip="1.1.1.1")

    assert "Public quota refused 1.1.1.1" in caplog.text
