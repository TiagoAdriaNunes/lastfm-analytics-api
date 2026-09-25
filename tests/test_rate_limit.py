import time

import httpx2
import pytest
from aiolimiter import AsyncLimiter

from app.services.lastfm import LastFMClient, LastFMError
from tests.test_lastfm import MOCK_RESPONSE

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
RATE_LIMITED = httpx2.Response(200, json={"error": 29, "message": "Rate Limit Exceded"})


async def test_limiter_spaces_calls(lastfm_mock):
    lastfm_mock.respond(return_value=httpx2.Response(200, json=MOCK_RESPONSE))
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as http:
        client = LastFMClient(http, "key", limiter=AsyncLimiter(1, 0.05))
        start = time.monotonic()
        for _ in range(3):
            await client.call("artist.getSimilar", artist="A")
    # First call is immediate, then one every 0.05s.
    assert time.monotonic() - start >= 0.09


async def test_retries_rate_limited_then_succeeds(lastfm_mock):
    route = lastfm_mock.respond(
        side_effect=[RATE_LIMITED, httpx2.Response(200, json=MOCK_RESPONSE)]
    )
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as http:
        client = LastFMClient(http, "key", max_retries=2, retry_backoff=0)
        data = await client.call("artist.getSimilar", artist="A")
    assert data == MOCK_RESPONSE
    assert route.call_count == 2


async def test_does_not_retry_non_retryable_errors(lastfm_mock):
    route = lastfm_mock.respond(
        return_value=httpx2.Response(200, json={"error": 6, "message": "not found"})
    )
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as http:
        client = LastFMClient(http, "key", max_retries=2, retry_backoff=0)
        with pytest.raises(LastFMError):
            await client.call("artist.getSimilar", artist="A")
    assert route.call_count == 1


def test_rate_limited_returns_503_after_retries(client, lastfm_mock):
    route = lastfm_mock.respond(return_value=RATE_LIMITED)

    response = client.get("/artists/A/similar")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert route.call_count == 3  # 1 attempt + 2 retries


def test_network_rate_limited_on_second_level_returns_503(client, lastfm_mock):
    first = {
        "similarartists": {
            "artist": [{"name": "B", "match": "0.9"}],
            "@attr": {"artist": "A"},
        }
    }
    lastfm_mock.respond(
        side_effect=lambda req: (
            httpx2.Response(200, json=first) if req.url.params["artist"] == "A" else RATE_LIMITED
        )
    )
    assert client.get("/artists/A/similar/network").status_code == 503


def test_user_agent_is_sent(client, lastfm_mock):
    route = lastfm_mock.respond(return_value=httpx2.Response(200, json=MOCK_RESPONSE))
    client.get("/artists/A/similar")
    assert route.last_request.headers["User-Agent"].startswith("lastfm-analytics-api/")
