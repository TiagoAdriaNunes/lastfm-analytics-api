import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, PositiveFloat, PositiveInt, StringConstraints, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def config_file() -> Path:
    return Path(os.environ.get("APP_CONFIG_FILE", PROJECT_ROOT / "config.yaml"))


class LastFMSettings(BaseModel):
    base_url: str
    rate_limit: PositiveFloat
    max_retries: int
    retry_backoff: float
    cache_ttl: float


class ExamplesSettings(BaseModel):
    rate_limit: PositiveFloat
    client_rate_limit: PositiveFloat
    max_clients: PositiveInt
    cache_size: PositiveInt

    @model_validator(mode="after")
    def client_rate_below_global(self) -> Self:
        # Otherwise the per-client limit never triggers and one caller can take the whole budget.
        if self.client_rate_limit >= self.rate_limit:
            raise ValueError("examples.client_rate_limit must be below examples.rate_limit")
        return self


class HTTPSettings(BaseModel):
    timeout: PositiveFloat
    user_agent: str


class Settings(BaseSettings):
    """Non-secret settings come from `config.yaml`; secrets from `.env` / environment variables.
    Precedence (highest first): environment variables, `.env`, `config.yaml`."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Secrets: environment / .env only.
    lastfm_api_key: str
    lastfm_api_secret: str = ""
    # Clients must send this in the `X-API-Key` header. Required, so the app never starts open.
    # Stripped because values pasted into a hosting dashboard often carry a stray newline/space.
    service_api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=16)]

    lastfm: LastFMSettings
    examples: ExamplesSettings
    http: HTTPSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=config_file()),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
