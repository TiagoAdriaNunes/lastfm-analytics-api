import httpx2

from app.schemas.tag import parse_tag_artists, parse_top_tags

TOP_TAGS_RESPONSE = {
    "tags": {
        "tag": [
            {"name": "rock", "url": "https://www.last.fm/tag/rock", "reach": "403376",
             "taggings": "4076304", "streamable": "1", "wiki": {}},
            {"name": "Seen Live", "url": "https://www.last.fm/tag/seen+live", "reach": "82567",
             "taggings": "2199763", "streamable": "1", "wiki": {}},
            {"name": "electronic", "url": "https://www.last.fm/tag/electronic", "reach": "262814",
             "taggings": "2508526", "streamable": "1", "wiki": {}},
        ],
        "@attr": {"page": "1", "perPage": "3", "totalPages": "964780", "total": "2894338"},
    }
}  # fmt: skip

TAG_ARTISTS_RESPONSE = {
    "topartists": {
        "artist": [
            {"name": "Radiohead", "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711",
             "url": "https://www.last.fm/music/Radiohead", "@attr": {"rank": "1"}},
            {"name": "Paramore", "mbid": "", "url": "https://www.last.fm/music/Paramore",
             "@attr": {"rank": "2"}},
        ],
        "@attr": {"tag": "rock", "page": "1", "perPage": "2", "totalPages": "500", "total": "1000"},
    }
}  # fmt: skip

EMPTY_TAG_RESPONSE = {
    "topartists": {
        "artist": [],
        "@attr": {"tag": "zzqq", "page": "1", "perPage": "2", "totalPages": "0", "total": "0"},
    }
}


def test_parse_top_tags():
    tags = parse_top_tags(TOP_TAGS_RESPONSE)
    assert [t.name for t in tags.tags] == ["rock", "Seen Live", "electronic"]
    assert tags.tags[0].reach == 403376
    assert tags.tags[0].taggings == 4076304


def test_parse_top_tags_genres_only_is_case_insensitive():
    tags = parse_top_tags(TOP_TAGS_RESPONSE, genres_only=True)
    assert [t.name for t in tags.tags] == ["rock", "electronic"]


def test_parse_tag_artists():
    result = parse_tag_artists(TAG_ARTISTS_RESPONSE)
    assert result.tag == "rock"
    assert result.total == 1000
    assert [(a.rank, a.name) for a in result.artists] == [(1, "Radiohead"), (2, "Paramore")]
    assert result.artists[1].mbid is None


def test_parse_tag_artists_unknown_tag():
    result = parse_tag_artists(EMPTY_TAG_RESPONSE)
    assert result.artists == []
    assert result.total == 0


def test_top_tags_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TOP_TAGS_RESPONSE))

    response = client.get("/tags/top", params={"limit": 3})

    assert response.status_code == 200
    assert [t["name"] for t in response.json()["tags"]] == ["rock", "electronic"]
    sent = route.last_request.url.params
    assert sent["method"] == "chart.getTopTags"
    assert sent["limit"] == "3"


def test_top_tags_route_all_tags(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=TOP_TAGS_RESPONSE))

    response = client.get("/tags/top", params={"genres_only": False})

    assert len(response.json()["tags"]) == 3


def test_tag_artists_route(client, lastfm_mock):
    route = lastfm_mock.respond(httpx2.Response(200, json=TAG_ARTISTS_RESPONSE))

    response = client.get("/tags/artists", params={"tag": "hip-hop/rap", "limit": 2})

    assert response.status_code == 200
    assert [a["name"] for a in response.json()["artists"]] == ["Radiohead", "Paramore"]
    sent = route.last_request.url.params
    assert sent["method"] == "tag.getTopArtists"
    assert sent["tag"] == "hip-hop/rap"
    assert sent["limit"] == "2"


def test_tag_artists_unknown_tag_is_empty_not_404(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=EMPTY_TAG_RESPONSE))

    response = client.get("/tags/artists", params={"tag": "zzqq"})

    assert response.status_code == 200
    assert response.json()["artists"] == []


def test_tag_artists_is_cached(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(200, json=TAG_ARTISTS_RESPONSE))

    for tag in ["Rock", "rock"]:
        assert client.get("/tags/artists", params={"tag": tag}).status_code == 200
    assert lastfm_mock.call_count == 1


def test_tag_artists_validation(client):
    assert client.get("/tags/artists").status_code == 422
    assert client.get("/tags/artists", params={"tag": " "}).status_code == 422
    assert client.get("/tags/artists", params={"tag": "rock", "limit": 101}).status_code == 422


def test_tags_upstream_error(client, lastfm_mock):
    lastfm_mock.respond(httpx2.Response(403, json={"error": 10, "message": "Invalid API key"}))
    assert client.get("/tags/top").status_code == 502
