import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # conftest sets these globally for speed; config tests need to see the YAML values.
    monkeypatch.delenv("LASTFM__RATE_LIMIT", raising=False)
    monkeypatch.delenv("LASTFM__RETRY_BACKOFF", raising=False)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)


def load() -> Settings:
    # Skip `.env` so a developer's local file can't affect the result.
    return Settings(_env_file=None)


def test_loads_committed_config_yaml():
    settings = load()
    assert settings.lastfm.base_url == "https://ws.audioscrobbler.com/2.0/"
    assert settings.lastfm.rate_limit == 2.0
    assert settings.lastfm.max_retries == 2
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
        "http:\n"
        "  timeout: 1\n"
        "  user_agent: test\n"
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(custom))
    settings = load()
    assert settings.lastfm.base_url == "http://localhost:9999/"
    assert settings.lastfm.rate_limit == 0.5


def test_missing_config_file_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_CONFIG_FILE", str(tmp_path / "nope.yaml"))
    with pytest.raises(ValidationError, match="lastfm"):
        load()


def test_invalid_value_is_rejected(monkeypatch):
    monkeypatch.setenv("LASTFM__RATE_LIMIT", "0")
    with pytest.raises(ValidationError, match="rate_limit"):
        load()
