from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lastfm_api_key: str
    lastfm_api_secret: str = ""
    lastfm_base_url: str = "https://ws.audioscrobbler.com/2.0/"
    lastfm_timeout: float = 10.0
    lastfm_cache_ttl: float = 3600.0
    # Last.fm's ToS historically allowed 5 req/s averaged over 5 minutes; we stay well under it
    # with evenly spaced calls (no bursts) shared across the whole app.
    lastfm_rate_limit: float = 2.0
    # Retries for rate-limited (29) and temporary (8, 11, 16) Last.fm errors.
    lastfm_max_retries: int = 2
    lastfm_retry_backoff: float = 1.0
    user_agent: str = (
        "lastfm-analytics-api/0.1.0 (+https://github.com/TiagoAdriaNunes/lastfm-analytics-api)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
