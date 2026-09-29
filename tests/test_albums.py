import httpx2

from app.schemas.album import parse_album_info, parse_album_search, parse_album_tags

INFO_RESPONSE = {
    "album": {
        "artist": "Radiohead",
        "mbid": "0b6b4ba0-d36f-47bd-b4ea-6a5b91842d29",
        "name": "OK Computer",
        "url": "https://www.last.fm/music/Radiohead/OK+Computer",
        "listeners": "4916239",
        "playcount": "265860917",
        "tags": {"tag": [{"url": "https://www.last.fm/tag/alternative", "name": "alternative"}]},
        "tracks": {
            "track": [
                {"duration": 284, "url": "https://www.last.fm/music/Radiohead/OK+Computer/Airbag",
                 "name": "Airbag", "@attr": {"rank": 1}},
                {"duration": None, "url": "https://www.last.fm/music/Radiohead/OK+Computer/Paranoid+Android",
                 "name": "Paranoid Android", "@attr": {"rank": 2}},
            ]
        },
    }
}  # fmt: skip

TAGS_RESPONSE = {
    "toptags": {
        "tag": [
            {"count": 100, "name": "alternative rock", "url": "https://www.last.fm/tag/alternative+rock"},
            {"count": 67, "name": "alternative", "url": "https://www.last.fm/tag/alternative"},
        ],
        "@attr": {"artist": "Radiohead", "album": "OK Computer"},
    }
}  # fmt: skip

SEARCH_RESPONSE = {
    "results": {
        "opensearch:totalResults": "4757",
        "albummatches": {
            "album": [
                {"name": "OK Computer", "artist": "Radiohead", "mbid": "ok-computer-mbid",
                 "url": "https://www.last.fm/music/Radiohead/OK+Computer", "streamable": "0"},
                {"name": "OK Computer", "artist": "Various", "mbid": "", "url": "https://www.last.fm/x"},
            ]
        },
        "@attr": {"for": "OK Computer"},
    }
}  # fmt: skip

NOT_FOUND = {"message": "Album not found", "error": 6}


def test_parse_album_info():
    album = parse_album_info(INFO_RESPONSE)
    assert (album.name, album.artist) == ("OK Computer", "Radiohead")
    assert album.listeners == 4916239
    assert album.playcount == 265860917
    assert album.tags == ["alternative"]
    assert [(t.rank, t.name, t.duration) for t in album.tracks] == [
        (1, "Airbag", 284),
        (2, "Paranoid Android", None),
    ]


def test_parse_album_info_single_track_and_no_tags():
    album = parse_album_info(
        {"album": {"name": "Single", "artist": "X", "mbid": "", "tags": "",
                   "tracks": {"track": {"name": "Only", "duration": 0, "@attr": {"rank": 1}}}}}
    )  # fmt: skip
    assert album.mbid is None
    assert album.tags == []
    assert [(t.name, t.duration) for t in album.tracks] == [("Only", None)]


def test_parse_album_tags():
    tags = parse_album_tags(TAGS_RESPONSE, limit=1)
    assert (tags.artist, tags.album) == ("Radiohead", "OK Computer")
    assert [(t.name, t.count) for t in tags.tags] == [("alternative rock", 100)]


def test_parse_album_search():
    result = parse_album_search(SEARCH_RESPONSE)
    assert result.query == "OK Computer"
    assert result.total == 4757
    assert [(a.name, a.artist) for a in result.albums] == [
        ("OK Computer", "Radiohead"),
        ("OK Computer", "Various"),
    ]
    assert result.albums[1].mbid is None


def test_album_info_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=INFO_RESPONSE))

    response = client.get("/albums/info", params={"artist": "Radiohead", "album": "OK Computer"})

    assert response.status_code == 200
    assert len(response.json()["tracks"]) == 2
    sent = route.last_request.url.params
    assert sent["method"] == "album.getInfo"
    assert (sent["artist"], sent["album"]) == ("Radiohead", "OK Computer")
    assert sent["autocorrect"] == "1"


def test_album_info_not_found(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=NOT_FOUND))

    response = client.get("/albums/info", params={"artist": "Radiohead", "album": "nope"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Album not found"


def test_album_info_is_cached(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=INFO_RESPONSE))

    for artist, album in [("Radiohead", "OK Computer"), ("radiohead", "ok computer")]:
        response = client.get("/albums/info", params={"artist": artist, "album": album})
        assert response.status_code == 200
    assert lastfm_mock.call_count == 1


def test_album_info_requires_both_names(client):
    assert client.get("/albums/info", params={"artist": "Radiohead"}).status_code == 422
    assert client.get("/albums/info", params={"album": "OK Computer"}).status_code == 422
    params = {"artist": "Radiohead", "album": " "}
    assert client.get("/albums/info", params=params).status_code == 422


def test_album_tags_route_truncates_locally(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TAGS_RESPONSE))
    params = {"artist": "Radiohead", "album": "OK Computer"}

    for limit in [1, 2]:
        response = client.get("/albums/tags", params=params | {"limit": limit})
        assert len(response.json()["tags"]) == limit
    assert lastfm_mock.call_count == 1
    sent = route.last_request.url.params
    assert sent["method"] == "album.getTopTags"
    assert "limit" not in sent


def test_album_search_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    response = client.get("/albums/search", params={"album": "AC/DC Live", "limit": 2})

    assert response.status_code == 200
    assert response.json()["total"] == 4757
    sent = route.last_request.url.params
    assert sent["method"] == "album.search"
    assert sent["album"] == "AC/DC Live"
    assert sent["limit"] == "2"


def test_album_search_limit_validation(client):
    assert client.get("/albums/search", params={"album": "x", "limit": 101}).status_code == 422
