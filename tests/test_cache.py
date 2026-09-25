import httpx2

from app.services.cache import TTLCache
from app.services.lastfm import LastFMClient
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
