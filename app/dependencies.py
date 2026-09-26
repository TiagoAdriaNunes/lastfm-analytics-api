import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.services.lastfm import LastFMClient


def get_lastfm_client(request: Request) -> LastFMClient:
    settings = get_settings()
    return LastFMClient(
        request.app.state.http_client,
        settings.lastfm_api_key,
        settings.lastfm_api_secret,
        cache=request.app.state.lastfm_cache,
        limiter=request.app.state.lastfm_limiter,
        max_retries=settings.lastfm.max_retries,
        retry_backoff=settings.lastfm.retry_backoff,
    )


LastFMDep = Annotated[LastFMClient, Depends(get_lastfm_client)]


# auto_error=False so a missing header gets the same 401 as a wrong one (FastAPI's default is 403).
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: Annotated[str | None, Security(api_key_header)]) -> None:
    expected = get_settings().service_api_key
    if api_key is None or not secrets.compare_digest(api_key.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
