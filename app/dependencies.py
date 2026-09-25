from typing import Annotated

from fastapi import Depends, Request

from app.config import get_settings
from app.services.lastfm import LastFMClient


def get_lastfm_client(request: Request) -> LastFMClient:
    settings = get_settings()
    return LastFMClient(
        request.app.state.http_client, settings.lastfm_api_key, settings.lastfm_api_secret
    )


LastFMDep = Annotated[LastFMClient, Depends(get_lastfm_client)]
