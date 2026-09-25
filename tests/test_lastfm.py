import hashlib

from app.schemas.artist import parse_similar_artists
from app.services.lastfm import create_signature

MOCK_RESPONSE = {
    "similarartists": {
        "artist": [
            {"name": "Artist B", "match": "0.9", "mbid": "", "url": "https://last.fm/b"},
            {"name": "Artist C", "match": "0.5", "mbid": "abc", "url": "https://last.fm/c"},
        ],
        "@attr": {"artist": "Artist A"},
    }
}


def test_create_signature_sorts_keys_and_skips_format():
    params = {"method": "auth.getSession", "api_key": "k", "token": "t", "format": "json"}
    expected = hashlib.md5(b"api_keykmethodauth.getSessiontokentsecret").hexdigest()
    assert create_signature(params, "secret") == expected


def test_parse_similar_artists():
    result = parse_similar_artists(MOCK_RESPONSE)
    assert result.artist == "Artist A"
    assert [a.name for a in result.similar] == ["Artist B", "Artist C"]
    assert result.similar[0].match == 0.9
    assert result.similar[0].mbid is None
    assert result.similar[1].mbid == "abc"


def test_parse_similar_artists_empty():
    result = parse_similar_artists({"similarartists": {}})
    assert result.similar == []
