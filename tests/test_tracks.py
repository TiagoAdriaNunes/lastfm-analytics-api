import httpx2

from app.schemas.track import (
    parse_similar_tracks,
    parse_track_info,
    parse_track_search,
    parse_track_tags,
)

INFO_RESPONSE = {
    "track": {
        "name": "Creep",
        "mbid": "012e70cd-4ef6-37bf-8ebf-02d318fe5151",
        "url": "https://www.last.fm/music/Radiohead/_/Creep",
        "duration": "235000",
        "listeners": "4233075",
        "playcount": "63668486",
        "artist": {"name": "Radiohead", "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711",
                   "url": "https://www.last.fm/music/Radiohead"},
        "album": {"artist": "Radiohead", "title": "Pablo Honey",
                  "url": "https://www.last.fm/music/Radiohead/Pablo+Honey"},
        "toptags": {"tag": [{"name": "alternative", "url": "https://www.last.fm/tag/alternative"}]},
    }
}  # fmt: skip

SIMILAR_RESPONSE = {
    "similartracks": {
        "track": [
            {"name": "No Surprises", "playcount": 57402720, "match": 1.0,
             "url": "https://www.last.fm/music/Radiohead/_/No+Surprises", "duration": 233,
             "artist": {"name": "Radiohead", "url": "https://www.last.fm/music/Radiohead"}},
            {"name": "Let Down", "playcount": 43693222, "mbid": "let-down-mbid",
             "match": 0.881869, "url": "https://www.last.fm/music/Radiohead/_/Let+Down",
             "artist": {"name": "Radiohead", "url": "https://www.last.fm/music/Radiohead"}},
        ],
        "@attr": {"artist": "Radiohead", "track": "Creep"},
    }
}  # fmt: skip

TAGS_RESPONSE = {
    "toptags": {
        "tag": [
            {"count": 100, "name": "alternative", "url": "https://www.last.fm/tag/alternative"},
            {"count": 96, "name": "alternative rock", "url": "https://www.last.fm/tag/alternative+rock"},
        ],
        "@attr": {"artist": "Radiohead", "track": "Creep"},
    }
}  # fmt: skip

SEARCH_RESPONSE = {
    "results": {
        "opensearch:totalResults": "97205",
        "trackmatches": {
            "track": [
                {"name": "Creep", "artist": "Radiohead", "url": "https://www.last.fm/music/Radiohead/_/Creep",
                 "listeners": "4233075", "mbid": "012e70cd-4ef6-37bf-8ebf-02d318fe5151"},
                {"name": "Creep", "artist": "Frost Children", "url": "https://www.last.fm/x",
                 "listeners": "62435", "mbid": ""},
            ]
        },
        "@attr": {"for": "Creep"},
    }
}  # fmt: skip

NOT_FOUND = {"error": 6, "message": "Track not found", "links": []}


def test_parse_track_info():
    track = parse_track_info(INFO_RESPONSE)
    assert (track.name, track.artist, track.album) == ("Creep", "Radiohead", "Pablo Honey")
    assert track.duration == 235  # Last.fm sends milliseconds here
    assert track.listeners == 4233075
    assert track.playcount == 63668486
    assert track.tags == ["alternative"]


def test_parse_track_info_missing_fields():
    track = parse_track_info(
        {"track": {"name": "1+1", "duration": "0", "artist": {"name": "Beyoncé"}, "toptags": ""}}
    )
    assert track.album is None
    assert track.duration is None
    assert track.listeners is None
    assert track.tags == []


def test_parse_similar_tracks():
    result = parse_similar_tracks(SIMILAR_RESPONSE)
    assert (result.artist, result.track) == ("Radiohead", "Creep")
    assert [(t.name, t.artist, t.match) for t in result.similar] == [
        ("No Surprises", "Radiohead", 1.0),
        ("Let Down", "Radiohead", 0.881869),
    ]
    assert result.similar[0].mbid is None
    assert result.similar[1].playcount == 43693222


def test_parse_track_tags():
    tags = parse_track_tags(TAGS_RESPONSE, limit=1)
    assert (tags.artist, tags.track) == ("Radiohead", "Creep")
    assert [t.name for t in tags.tags] == ["alternative"]


def test_parse_track_search():
    result = parse_track_search(SEARCH_RESPONSE)
    assert (result.query, result.total) == ("Creep", 97205)
    assert [(t.name, t.artist, t.listeners) for t in result.tracks] == [
        ("Creep", "Radiohead", 4233075),
        ("Creep", "Frost Children", 62435),
    ]


def test_track_info_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=INFO_RESPONSE))

    response = client.get("/tracks/info", params={"artist": "Radiohead", "track": "Creep"})

    assert response.status_code == 200
    assert response.json()["duration"] == 235
    sent = route.last_request.url.params
    assert sent["method"] == "track.getInfo"
    assert (sent["artist"], sent["track"]) == ("Radiohead", "Creep")
    assert sent["autocorrect"] == "1"


def test_track_info_not_found(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=NOT_FOUND))

    response = client.get("/tracks/info", params={"artist": "Radiohead", "track": "nope"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Track not found"


def test_track_info_requires_both_names(client):
    assert client.get("/tracks/info", params={"artist": "Radiohead"}).status_code == 422
    assert client.get("/tracks/info", params={"track": "Creep"}).status_code == 422


def test_similar_tracks_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=SIMILAR_RESPONSE))

    response = client.get(
        "/tracks/similar", params={"artist": "Radiohead", "track": "Creep", "limit": 2}
    )

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["similar"]] == ["No Surprises", "Let Down"]
    sent = route.last_request.url.params
    assert sent["method"] == "track.getSimilar"
    assert sent["limit"] == "2"


def test_similar_tracks_is_cached(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=SIMILAR_RESPONSE))

    for artist, track in [("Radiohead", "Creep"), ("RADIOHEAD", "creep")]:
        response = client.get("/tracks/similar", params={"artist": artist, "track": track})
        assert response.status_code == 200
    assert lastfm_mock.call_count == 1


def test_track_tags_route_truncates_locally(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TAGS_RESPONSE))
    params = {"artist": "Radiohead", "track": "Creep"}

    for limit in [1, 2]:
        response = client.get("/tracks/tags", params=params | {"limit": limit})
        assert len(response.json()["tags"]) == limit
    assert lastfm_mock.call_count == 1
    sent = route.last_request.url.params
    assert sent["method"] == "track.getTopTags"
    assert "limit" not in sent


def test_track_search_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    response = client.get("/tracks/search", params={"track": "Creep", "limit": 2})

    assert response.status_code == 200
    assert response.json()["total"] == 97205
    sent = route.last_request.url.params
    assert sent["method"] == "track.search"
    assert sent["track"] == "Creep"
    assert "artist" not in sent


def test_track_search_with_artist(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=SEARCH_RESPONSE))

    for artist in [None, "Radiohead"]:
        params = {"track": "Creep"} | ({"artist": artist} if artist else {})
        assert client.get("/tracks/search", params=params).status_code == 200
    # The artist filter is part of the cache key.
    assert lastfm_mock.call_count == 2
    assert lastfm_mock.last_request.url.params["artist"] == "Radiohead"


def test_track_search_validation(client):
    assert client.get("/tracks/search").status_code == 422
    assert client.get("/tracks/search", params={"track": "x", "artist": " "}).status_code == 422
    assert client.get("/tracks/search", params={"track": "x", "limit": 0}).status_code == 422
