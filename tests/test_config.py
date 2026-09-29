import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # conftest sets these globally for speed; config tests need to see the YAML values.
    monkeypatch.delenv("LASTFM__RATE_LIMIT", raising=False)
    monkeypatch.delenv("LASTFM__RETRY_BACKOFF", raising=False)
    monkeypatch.delenv("EXAMPLES__RATE_LIMIT", raising=False)
    monkeypatch.delenv("EXAMPLES__CLIENT_RATE_LIMIT", raising=False)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)


def load() -> Settings:
    # Skip `.env` so a developer's local file can't affect the result.
    return Settings(_env_file=None)


def test_loads_committed_config_yaml():
    settings = load()
    assert settings.lastfm.base_url == "https://ws.audioscrobbler.com/2.0/"
    assert settings.lastfm.rate_limit == 2.0
    assert settings.lastfm.max_retries == 2
    assert settings.lastfm.cache_max_mb == 200
    assert settings.http.user_agent.startswith("lastfm-analytics-api/")
    assert (PROJECT_ROOT / "config.yaml").is_file()


def test_env_overrides_one_yaml_key_and_keeps_the_rest(monkeypatch):
    monkeypatch.setenv("LASTFM__RATE_LIMIT", "1.5")
    settings = load()
    assert settings.lastfm.rate_limit == 1.5
    assert settings.lastfm.max_retries == 2  # still from YAML


def test_secrets_come_from_env(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "from-env")
    assert load().lastfm_api_key == "from-env"


def test_app_config_file_selects_another_yaml(monkeypatch, tmp_path):
    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "lastfm:\n"
        "  base_url: http://localhost:9999/\n"
        "  rate_limit: 0.5\n"
        "  max_retries: 0\n"
        "  retry_backoff: 0\n"
        "  cache_ttl: 1\n"
        "  cache_max_mb: 3\n"
        "  network_max_calls: 10\n"
        "examples:\n"
        "  rate_limit: 0.1\n"
        "  client_rate_limit: 0.01\n"
        "  max_clients: 10\n"
        "  cache_max_mb: 5\n"
        "http:\n"
        "  timeout: 1\n"
        "  user_agent: test\n"
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(custom))
    settings = load()
    assert settings.lastfm.base_url == "http://localhost:9999/"
    assert settings.lastfm.rate_limit == 0.5
    assert settings.examples.max_clients == 10


def test_missing_config_file_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_CONFIG_FILE", str(tmp_path / "nope.yaml"))
    with pytest.raises(ValidationError, match="lastfm"):
        load()


def test_invalid_value_is_rejected(monkeypatch):
    monkeypatch.setenv("LASTFM__RATE_LIMIT", "0")
    with pytest.raises(ValidationError, match="rate_limit"):
        load()


@pytest.mark.parametrize("value", [None, "", "too-short", "  too-short  \n"])
def test_service_api_key_is_required_and_long(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SERVICE_API_KEY")
    else:
        monkeypatch.setenv("SERVICE_API_KEY", value)
    with pytest.raises(ValidationError, match="service_api_key"):
        load()


def test_service_api_key_is_stripped(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", " a-long-enough-service-key\n")
    assert load().service_api_key == "a-long-enough-service-key"


@pytest.mark.parametrize("client_rate", ["1.5", "2"])
def test_examples_client_rate_must_be_below_global(monkeypatch, client_rate):
    # Committed rate_limit is 1.5; a per-client limit at or above it would never trigger.
    monkeypatch.setenv("EXAMPLES__CLIENT_RATE_LIMIT", client_rate)
    with pytest.raises(ValidationError, match="client_rate_limit must be below"):
        load()
