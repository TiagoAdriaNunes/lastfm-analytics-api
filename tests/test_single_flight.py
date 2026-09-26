import asyncio

import httpx2
import pytest

from app.services.cache import TTLCache
from app.services.lastfm import InFlight, LastFMClient, LastFMError
from tests.test_lastfm import MOCK_RESPONSE

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
NOT_FOUND = {"error": 6, "message": "not found"}


def slow(payload: dict, delay: float = 0.05):
    """Async mock handler, so concurrent callers overlap while the first call is in flight."""

    async def handler(_: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(delay)
        return httpx2.Response(200, json=payload)

    return handler


@pytest.fixture
async def http(lastfm_mock):
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as client:
        yield client


def make_client(http, inflight: InFlight, cache: TTLCache | None = None) -> LastFMClient:
    # A new client per caller, like the per-request dependency; the in-flight map is shared.
    return LastFMClient(http, "key", cache=cache, inflight=inflight)


async def test_identical_concurrent_requests_share_one_call(http, lastfm_mock):
    lastfm_mock.respond(side_effect=slow(MOCK_RESPONSE))
    inflight: InFlight = {}

    results = await asyncio.gather(
        *(make_client(http, inflight).get_similar_artists("Cher", limit=5) for _ in range(5))
    )

    assert lastfm_mock.call_count == 1
    assert all(r == MOCK_RESPONSE for r in results)
    assert inflight == {}  # cleaned up once done


async def test_different_requests_are_not_merged(http, lastfm_mock):
    lastfm_mock.respond(side_effect=slow(MOCK_RESPONSE))
    inflight: InFlight = {}

    await asyncio.gather(
        make_client(http, inflight).get_similar_artists("Cher", limit=5),
        make_client(http, inflight).get_similar_artists("Cher", limit=6),
        make_client(http, inflight).search_artists("Cher", limit=5),
    )

    assert lastfm_mock.call_count == 3


async def test_cancelled_caller_does_not_cancel_the_shared_call(http, lastfm_mock):
    # E.g. the user who triggered the call closes the page while others wait for the same data.
    lastfm_mock.respond(side_effect=slow(MOCK_RESPONSE, delay=0.1))
    inflight: InFlight = {}
    cache = TTLCache(ttl=60)

    first = asyncio.create_task(make_client(http, inflight, cache).get_similar_artists("Cher"))
    second = asyncio.create_task(make_client(http, inflight, cache).get_similar_artists("Cher"))
    await asyncio.sleep(0.02)  # both are now waiting on the same fetch
    first.cancel()

    assert await second == MOCK_RESPONSE
    assert first.cancelled()
    assert lastfm_mock.call_count == 1


async def test_errors_reach_every_waiter_and_are_not_reused(http, lastfm_mock):
    lastfm_mock.respond(side_effect=slow(NOT_FOUND))
    inflight: InFlight = {}

    results = await asyncio.gather(
        make_client(http, inflight).get_similar_artists("nope"),
        make_client(http, inflight).get_similar_artists("nope"),
        return_exceptions=True,
    )

    assert [type(r) for r in results] == [LastFMError, LastFMError]
    assert lastfm_mock.call_count == 1
    # The failure isn't kept: the next request tries Last.fm again.
    with pytest.raises(LastFMError):
        await make_client(http, inflight).get_similar_artists("nope")
    assert lastfm_mock.call_count == 2


async def test_only_the_caller_that_fetches_uses_quota(http, lastfm_mock):
    lastfm_mock.respond(side_effect=slow(MOCK_RESPONSE))
    inflight: InFlight = {}
    quota_calls = 0

    async def quota() -> None:
        nonlocal quota_calls
        quota_calls += 1

    await asyncio.gather(
        *(make_client(http, inflight).search_artists("Cher", quota=quota) for _ in range(3))
    )

    assert quota_calls == 1
    assert lastfm_mock.call_count == 1
