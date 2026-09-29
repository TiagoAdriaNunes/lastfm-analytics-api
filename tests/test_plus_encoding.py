import httpx2
import pytest

from app.services.lastfm import LastFMClient
from tests.test_lastfm import MOCK_RESPONSE

BASE_URL = "https://ws.audioscrobbler.com/2.0/"


async def call_and_get_raw_query(lastfm_mock, method: str, **params) -> str:
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as http:
        await LastFMClient(http, "key").call(method, **params)
    return lastfm_mock.last_request.url.query.decode()


@pytest.mark.parametrize(
    "method",
    [
        "artist.getInfo",
        "artist.getSimilar",
        "artist.getTopAlbums",
        "artist.getTopTags",
        "artist.getTopTracks",
        "track.getInfo",
        "track.getSimilar",
    ],
)
async def test_plus_is_double_encoded_for_double_decoding_methods(lastfm_mock, method):
    query = await call_and_get_raw_query(
        lastfm_mock, method, artist="Florence + The Machine", track="C++"
    )
    assert "artist=Florence+%252B+The+Machine" in query
    assert "track=C%252B%252B" in query


# Verified live: these decode once, and double-encoding breaks them (album.getInfo even answers
# with an empty "Florence %2B The Machine" album instead of an error).
@pytest.mark.parametrize(
    "method",
    [
        "album.getInfo",
        "album.getTopTags",
        "album.search",
        "artist.search",
        "track.getTopTags",
        "track.search",
    ],
)
async def test_plus_is_encoded_once_for_other_methods(lastfm_mock, method):
    query = await call_and_get_raw_query(lastfm_mock, method, artist="+44", album="+", track="1+1")
    assert "artist=%2B44" in query
    assert "album=%2B" in query
    assert "track=1%2B1" in query


# Verified live against Last.fm: all of these resolve correctly with normal (single) encoding,
# so the "+" workaround must leave them untouched.
@pytest.mark.parametrize(
    "name",
    [
        "AC/DC", "R.E.M.", "A$AP Rocky", "#1 Dads", "Panic! at the Disco", "Why?", "*NSYNC",
        "Crosby, Stills, Nash & Young", "[:SITD:]", "=LOVE", "Beyoncé", "Motörhead",
        "坂本龍一", "100%",
    ],
)  # fmt: skip
async def test_other_special_characters_are_sent_as_is(lastfm_mock, name):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))
    async with httpx2.AsyncClient(base_url=BASE_URL, transport=lastfm_mock.transport) as http:
        await LastFMClient(http, "key").call("artist.getSimilar", artist=name)
    assert lastfm_mock.last_request.url.params["artist"] == name


async def test_names_without_plus_are_unchanged(lastfm_mock):
    query = await call_and_get_raw_query(
        lastfm_mock, "artist.getSimilar", artist="Simon & Garfunkel", limit=5
    )
    assert "artist=Simon+%26+Garfunkel" in query
    assert "limit=5" in query


def test_similar_endpoint_sends_plus_double_encoded(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))

    response = client.get("/artists/similar", params={"artist": "+44"})

    assert response.status_code == 200
    assert "artist=%252B44" in lastfm_mock.last_request.url.query.decode()
