import json
import logging

import httpx2
import pytest
from loguru import logger

from app.config import get_settings
from app.logs import InterceptHandler, setup_logging
from tests.conftest import TEST_SERVICE_API_KEY
from tests.test_lastfm import MOCK_RESPONSE


def messages(logs, level: str | None = None) -> list[str]:
    return [r["message"] for r in logs if level is None or r["level"].name == level]


def find(logs, prefix: str):
    [record] = [r for r in logs if r["message"].startswith(prefix)]
    return record


def assert_no_secrets(logs):
    secrets = [get_settings().lastfm_api_key, TEST_SERVICE_API_KEY, "api_key", "api_sig"]
    dumped = "\n".join(r["message"] + repr(r["extra"]) for r in logs)
    for secret in secrets:
        assert secret not in dumped


def test_request_is_logged_with_status_duration_and_client(client, lastfm_mock, logs):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))

    client.get(
        "/artists/similar",
        params={"artist": "Radiohead"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )

    record = find(logs, "GET /artists/similar?artist=Radiohead -> 200 in ")
    assert record["level"].name == "INFO"
    assert record["extra"]["status"] == 200
    assert record["extra"]["client_ip"] == "1.2.3.4"
    assert record["extra"]["duration_ms"] >= 0
    assert_no_secrets(logs)


def test_rejected_request_is_logged_without_the_key(client, logs):
    client.get("/artists/similar", params={"artist": "x"}, headers={"X-API-Key": "wrong-key"})

    assert find(logs, "GET /artists/similar")["extra"]["status"] == 401
    assert "wrong-key" not in repr([r["extra"] for r in logs])


def test_health_checks_only_log_at_debug(client, logs):
    client.get("/health")

    assert find(logs, "GET /health -> 200")["level"].name == "DEBUG"


def test_crash_is_logged_as_a_500(client, lastfm_mock, logs):
    def boom(_request):
        raise RuntimeError("boom")

    lastfm_mock.respond(side_effect=boom)

    with pytest.raises(RuntimeError):
        client.get("/artists/similar", params={"artist": "Radiohead"})

    record = find(logs, "GET /artists/similar?artist=Radiohead -> 500")
    assert record["level"].name == "WARNING"


def test_lastfm_call_is_logged_without_the_api_key(client, lastfm_mock, logs):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))

    client.get("/artists/similar", params={"artist": "+44", "limit": 3})

    record = find(logs, "Last.fm artist.getSimilar -> 200 in ")
    assert record["extra"]["lastfm_method"] == "artist.getSimilar"
    # The caller's input, not the "%2B"-encoded value actually sent.
    assert record["extra"]["params"] == {"artist": "+44", "limit": 3, "autocorrect": 1}
    assert "wait_ms" in record["extra"]
    assert_no_secrets(logs)


def test_lastfm_error_is_logged(client, lastfm_mock, logs):
    lastfm_mock.respond(
        httpx2.Response(
            200, json={"error": 6, "message": "The artist you supplied could not be found"}
        )
    )

    client.get("/artists/similar", params={"artist": "nope"})

    record = find(logs, "Last.fm artist.getSimilar -> error 6: The artist you supplied")
    assert record["level"].name == "WARNING"
    assert record["extra"]["error_code"] == 6


def test_retries_are_logged(client, lastfm_mock, logs):
    rate_limited = httpx2.Response(200, json={"error": 29, "message": "Rate limit exceeded"})
    lastfm_mock.respond(side_effect=[rate_limited, httpx2.Response(200, json=MOCK_RESPONSE)])

    assert client.get("/artists/similar", params={"artist": "Radiohead"}).status_code == 200

    record = find(logs, "Retrying Last.fm artist.getSimilar")
    assert record["extra"]["error_code"] == 29
    assert record["extra"]["retry"] == 1


def test_transport_error_logs_the_type_not_the_url(client, lastfm_mock, logs):
    def fail(request):
        raise httpx2.ConnectError("connection refused", request=request)

    lastfm_mock.respond(side_effect=fail)

    assert client.get("/artists/similar", params={"artist": "Radiohead"}).status_code == 502

    record = find(logs, "Last.fm artist.getSimilar failed: ConnectError")
    assert record["level"].name == "WARNING"
    assert_no_secrets(logs)


def test_cache_hits_are_logged_at_debug(client, lastfm_mock, logs):
    lastfm_mock.respond(httpx2.Response(200, json=MOCK_RESPONSE))

    for _ in range(2):
        client.get("/artists/similar", params={"artist": "Radiohead"})

    assert len(messages(logs, "DEBUG")) >= 1
    assert any(
        m.startswith("Cache hit for ('artist.getSimilar', 'radiohead'") for m in messages(logs)
    )


def test_json_format_writes_flat_fields(capsys):
    try:
        setup_logging("INFO", "json")
        logger.info("Hello {name}", name="Björk", status=200)
        line = capsys.readouterr().out.strip().splitlines()[-1]
    finally:
        setup_logging("INFO", "text")

    entry = json.loads(line)
    assert entry["message"] == "Hello Björk"
    assert entry["level"] == "info"
    assert (entry["name"], entry["status"]) == ("Björk", 200)
    assert "time" in entry


def test_json_format_includes_exceptions(capsys):
    try:
        setup_logging("INFO", "json")
        try:
            raise ValueError("bad")
        except ValueError:
            logger.exception("It failed")
        entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    finally:
        setup_logging("INFO", "text")

    assert "ValueError: bad" in entry["exception"]


def test_level_filters_our_sink(capsys):
    try:
        setup_logging("WARNING", "text")
        logger.info("quiet")
        logger.warning("loud")
        out = capsys.readouterr().out
    finally:
        setup_logging("INFO", "text")

    assert "loud" in out
    assert "quiet" not in out


def test_uvicorn_logs_are_routed_into_loguru(logs):
    setup_logging("INFO", "text")

    # WARNING: outside a real server nothing sets uvicorn's loggers to INFO (uvicorn does in prod).
    logging.getLogger("uvicorn.error").warning("Uvicorn says hi")

    assert "Uvicorn says hi" in messages(logs)


def test_httpx_and_root_loggers_are_not_intercepted():
    # httpx2 logs request URLs, which carry our api_key: it must never reach our sink.
    setup_logging("INFO", "text")

    for name in ["", "httpx2"]:
        handlers = logging.getLogger(name).handlers
        assert not any(isinstance(h, InterceptHandler) for h in handlers)


def test_uvicorn_access_log_is_silenced():
    # Uvicorn only writes access lines while this logger has handlers; our middleware replaces it.
    setup_logging("INFO", "text")

    access = logging.getLogger("uvicorn.access")
    assert not access.hasHandlers()
