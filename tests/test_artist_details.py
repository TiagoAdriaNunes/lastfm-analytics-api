import httpx2
import pytest

from app.schemas.artist import (
    parse_artist_info,
    parse_artist_tags,
    parse_artist_top_albums,
    parse_artist_top_tracks,
)
from app.schemas.common import as_list

INFO_RESPONSE = {
    "artist": {
        "name": "Radiohead",
        "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711",
        "url": "https://www.last.fm/music/Radiohead",
        "stats": {"listeners": "8455164", "playcount": "3426075923"},
        "tags": {
            "tag": [
                {"name": "rock", "url": "https://www.last.fm/tag/rock"},
                {"name": "alternative", "url": "https://www.last.fm/tag/alternative"},
            ]
        },
    }
}

TAGS_RESPONSE = {
    "toptags": {
        "tag": [
            {"count": 100, "name": "rock", "url": "https://www.last.fm/tag/rock"},
            {"count": 54, "name": "alternative", "url": "https://www.last.fm/tag/alternative"},
            {"count": 40, "name": "electronic", "url": "https://www.last.fm/tag/electronic"},
        ],
        "@attr": {"artist": "Radiohead"},
    }
}


def test_as_list():
    assert as_list([{"a": 1}]) == [{"a": 1}]
    assert as_list({"a": 1}) == [{"a": 1}]
    assert as_list("") == []
    assert as_list(None) == []


def test_parse_artist_info():
    info = parse_artist_info(INFO_RESPONSE)
    assert info.name == "Radiohead"
    assert info.listeners == 8455164
    assert info.playcount == 3426075923  # past 2**31
    assert info.tags == ["rock", "alternative"]


def test_parse_artist_info_missing_fields():
    info = parse_artist_info({"artist": {"name": "Nobody", "mbid": "", "tags": ""}})
    assert info.mbid is None
    assert info.listeners is None
    assert info.playcount is None
    assert info.tags == []


def test_parse_artist_tags_truncates():
    tags = parse_artist_tags(TAGS_RESPONSE, limit=2)
    assert tags.artist == "Radiohead"
    assert [(t.name, t.count) for t in tags.tags] == [("rock", 100), ("alternative", 54)]


def test_parse_artist_tags_none():
    assert parse_artist_tags({"toptags": {"tag": [], "@attr": {"artist": "x"}}}).tags == []


def test_artist_info_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=INFO_RESPONSE))

    response = client.get("/artists/info", params={"artist": "radiohead"})

    assert response.status_code == 200
    assert response.json()["playcount"] == 3426075923
    sent = route.last_request.url.params
    assert sent["method"] == "artist.getInfo"
    assert sent["artist"] == "radiohead"
    assert sent["autocorrect"] == "1"


def test_artist_info_not_found(client, lastfm_mock):
    lastfm_mock.respond(
        httpx2.Response(
            200, json={"error": 6, "message": "The artist you supplied could not be found"}
        )
    )
    assert client.get("/artists/info", params={"artist": "nope"}).status_code == 404


def test_artist_info_is_cached(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=INFO_RESPONSE))

    for artist in ["Radiohead", "radiohead"]:
        assert client.get("/artists/info", params={"artist": artist}).status_code == 200
    assert lastfm_mock.call_count == 1


def test_artist_tags_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TAGS_RESPONSE))

    response = client.get("/artists/tags", params={"artist": "Radiohead", "limit": 1})

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tags"]] == ["rock"]
    sent = route.last_request.url.params
    assert sent["method"] == "artist.getTopTags"
    assert "limit" not in sent  # not supported by Last.fm; truncated locally


def test_artist_tags_different_limits_share_one_call(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=TAGS_RESPONSE))

    for limit in [1, 3]:
        response = client.get("/artists/tags", params={"artist": "Radiohead", "limit": limit})
        assert len(response.json()["tags"]) == limit
    assert lastfm_mock.call_count == 1


def test_artist_tags_limit_validation(client):
    assert client.get("/artists/tags", params={"artist": "x", "limit": 0}).status_code == 422


TOP_ALBUMS_RESPONSE = {
    "topalbums": {
        "album": [
            {"name": "OK Computer", "playcount": 265860917, "mbid": "ok-computer-mbid",
             "url": "https://www.last.fm/music/Radiohead/OK+Computer", "@attr": {"rank": "1"}},
            {"name": "Pablo Honey", "playcount": 96823615, "mbid": "",
             "url": "https://www.last.fm/music/Radiohead/Pablo+Honey", "@attr": {"rank": "2"}},
        ],
        "@attr": {"artist": "Radiohead", "page": "1", "perPage": "2", "total": "230428"},
    }
}  # fmt: skip

TOP_TRACKS_RESPONSE = {
    "toptracks": {
        "track": [
            {"name": "Creep", "playcount": "63668486", "listeners": "4233075",
             "mbid": "012e70cd-4ef6-37bf-8ebf-02d318fe5151",
             "url": "https://www.last.fm/music/Radiohead/_/Creep", "@attr": {"rank": "1"}},
            {"name": "No Surprises", "playcount": "57402720", "listeners": "3470755", "mbid": "",
             "url": "https://www.last.fm/music/Radiohead/_/No+Surprises", "@attr": {"rank": "2"}},
        ],
        "@attr": {"artist": "Radiohead", "page": "1", "perPage": "2", "total": "462181"},
    }
}  # fmt: skip


def test_parse_artist_top_albums():
    result = parse_artist_top_albums(TOP_ALBUMS_RESPONSE)
    assert (result.artist, result.total) == ("Radiohead", 230428)
    assert [(a.rank, a.name, a.playcount) for a in result.albums] == [
        (1, "OK Computer", 265860917),
        (2, "Pablo Honey", 96823615),
    ]
    assert result.albums[1].mbid is None


def test_parse_artist_top_tracks():
    result = parse_artist_top_tracks(TOP_TRACKS_RESPONSE)
    assert (result.artist, result.total) == ("Radiohead", 462181)
    assert [(t.rank, t.name, t.listeners) for t in result.tracks] == [
        (1, "Creep", 4233075),
        (2, "No Surprises", 3470755),
    ]


def test_artist_top_albums_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TOP_ALBUMS_RESPONSE))

    response = client.get("/artists/albums", params={"artist": "Radiohead", "limit": 2})

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["albums"]] == ["OK Computer", "Pablo Honey"]
    sent = route.last_request.url.params
    assert sent["method"] == "artist.getTopAlbums"
    assert sent["limit"] == "2"
    assert sent["autocorrect"] == "1"


def test_artist_top_tracks_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TOP_TRACKS_RESPONSE))

    response = client.get("/artists/tracks", params={"artist": "Radiohead", "limit": 2})

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tracks"]] == ["Creep", "No Surprises"]
    sent = route.last_request.url.params
    assert sent["method"] == "artist.getTopTracks"
    assert sent["limit"] == "2"


def test_artist_top_limit_validation(client):
    for path in ["/artists/albums", "/artists/tracks"]:
        assert client.get(path, params={"artist": "x", "limit": 101}).status_code == 422


@pytest.mark.parametrize("path", ["/artists/tags", "/artists/albums", "/artists/tracks"])
def test_artist_routes_not_found(client, lastfm_mock, path):
    lastfm_mock.respond(
        httpx2.Response(
            200, json={"error": 6, "message": "The artist you supplied could not be found"}
        )
    )
    assert client.get(path, params={"artist": "nope"}).status_code == 404
