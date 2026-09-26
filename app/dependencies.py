import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from app.config import get_settings
from app.services.cache import TTLCache
from app.services.lastfm import LastFMClient


def _lastfm_client(request: Request, cache: TTLCache) -> LastFMClient:
    settings = get_settings()
    return LastFMClient(
        request.app.state.http_client,
        settings.lastfm_api_key,
        settings.lastfm_api_secret,
        cache=cache,
        limiter=request.app.state.lastfm_limiter,
        max_retries=settings.lastfm.max_retries,
        retry_backoff=settings.lastfm.retry_backoff,
    )


def get_lastfm_client(request: Request) -> LastFMClient:
    return _lastfm_client(request, request.app.state.lastfm_cache)


def get_public_lastfm_client(request: Request) -> LastFMClient:
    """Same client, but with the public endpoints' own cache (see `examples.cache_size`)."""
    return _lastfm_client(request, request.app.state.public_cache)


LastFMDep = Annotated[LastFMClient, Depends(get_lastfm_client)]
PublicLastFMDep = Annotated[LastFMClient, Depends(get_public_lastfm_client)]


def get_client_ip(request: Request) -> str:
    """The caller's IP, for per-client limits. Behind Railway's proxy the socket peer is the proxy,
    and the proxy appends the real peer to `X-Forwarded-For`, so the rightmost entry is the one a
    client can't forge (uvicorn's `--forwarded-allow-ips=*` would take the forgeable leftmost). If
    that entry is ever a proxy instead, all callers share one limit: safe, just less fair."""
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


ClientIP = Annotated[str, Depends(get_client_ip)]


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
