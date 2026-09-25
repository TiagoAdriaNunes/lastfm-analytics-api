from typing import Annotated

from fastapi import Depends, Request

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
