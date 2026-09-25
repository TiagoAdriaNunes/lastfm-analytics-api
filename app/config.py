from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lastfm_api_key: str
    lastfm_api_secret: str = ""
    lastfm_base_url: str = "https://ws.audioscrobbler.com/2.0/"
    lastfm_timeout: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
