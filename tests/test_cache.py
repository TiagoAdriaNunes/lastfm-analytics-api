import httpx2
import pytest

from app.config import get_settings
from app.main import app
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


@pytest.mark.usefixtures("client")  # starts the app lifespan
def test_main_cache_size_comes_from_settings():
    assert app.state.lastfm_cache._maxsize == get_settings().lastfm.cache_size


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
