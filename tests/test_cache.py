import httpx2
import pytest

from app.config import get_settings
from app.main import app
from app.services.cache import MB, TTLCache
from app.services.lastfm import LastFMClient, estimated_size
from tests.test_lastfm import MOCK_RESPONSE


async def test_similar_artists_are_cached(lastfm_mock):
    route = lastfm_mock.respond(return_value=httpx2.Response(200, json=MOCK_RESPONSE))
    async with httpx2.AsyncClient(
        base_url="https://ws.audioscrobbler.com/2.0/", transport=lastfm_mock.transport
    ) as http:
        client = LastFMClient(http, "key", cache=TTLCache(ttl=60))
        await client.get_similar_artists("Artist A", limit=5)
        await client.get_similar_artists("artist a", limit=5)
        await client.get_similar_artists("Artist A", limit=10)
    assert route.call_count == 2


def test_ttl_cache_expires():
    cache = TTLCache(ttl=-1)
    cache.set("k", 1)
    assert cache.get("k") is None


@pytest.mark.usefixtures("client")  # starts the app lifespan
def test_cache_budgets_come_from_settings():
    settings = get_settings()
    assert app.state.lastfm_cache._max_cost == settings.lastfm.cache_max_mb * MB
    assert app.state.public_cache._max_cost == settings.examples.cache_max_mb * MB


async def test_images_are_dropped_before_caching(lastfm_mock):
    image = [{"#text": "https://lastfm.freetls.fastly.net/i/u/34s/x.png", "size": "small"}]
    payload = {
        "similarartists": {
            "artist": [{"name": "B", "match": "1", "image": image}],
            "image": image,
            "@attr": {"artist": "A"},
        }
    }
    lastfm_mock.respond(httpx2.Response(200, json=payload))
    cache = TTLCache(ttl=60)
    async with httpx2.AsyncClient(
        base_url="https://ws.audioscrobbler.com/2.0/", transport=lastfm_mock.transport
    ) as http:
        data = await LastFMClient(http, "key", cache=cache).get_similar_artists("A")

    assert data == {
        "similarartists": {"artist": [{"name": "B", "match": "1"}], "@attr": {"artist": "A"}}
    }
    assert cache.get(("artist.getSimilar", "a", None)) == data


def test_ttl_cache_evicts_oldest_until_the_new_entry_fits():
    cache = TTLCache(ttl=60, max_cost=10)
    cache.set("a", 1, cost=4)
    cache.set("b", 2, cost=4)
    cache.set("c", 3, cost=5)  # needs "a" gone (4 + 5 <= 10), not "b"
    assert cache.get("a") is None
    assert (cache.get("b"), cache.get("c")) == (2, 3)
    assert cache.cost == 9


def test_ttl_cache_skips_an_entry_bigger_than_the_budget():
    cache = TTLCache(ttl=60, max_cost=10)
    cache.set("a", 1, cost=4)
    cache.set("huge", 2, cost=11)
    assert cache.get("huge") is None
    assert cache.get("a") == 1  # not evicted for nothing


def test_ttl_cache_replacing_a_key_releases_its_old_cost():
    cache = TTLCache(ttl=60, max_cost=10)
    cache.set("a", 1, cost=6)
    cache.set("a", 2, cost=3)
    assert cache.get("a") == 2
    assert cache.cost == 3


def test_ttl_cache_expired_entry_releases_its_cost():
    cache = TTLCache(ttl=-1, max_cost=10)
    cache.set("a", 1, cost=6)
    assert cache.get("a") is None
    assert cache.cost == 0


def test_ttl_cache_counts_entries_by_default():
    cache = TTLCache(ttl=60, max_cost=2)
    for key in "abc":
        cache.set(key, key)
    assert cache.get("a") is None
    assert cache.cost == 2


async def test_responses_are_cached_at_their_estimated_size(lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))
    cache = TTLCache(ttl=60, max_cost=100 * MB)
    async with httpx2.AsyncClient(
        base_url="https://ws.audioscrobbler.com/2.0/", transport=lastfm_mock.transport
    ) as http:
        data = await LastFMClient(http, "key", cache=cache).get_similar_artists("A")

    assert cache.cost == estimated_size(data) > 0
