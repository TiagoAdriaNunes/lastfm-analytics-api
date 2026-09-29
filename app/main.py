import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx2
from aiolimiter import AsyncLimiter
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from loguru import logger

from app.config import APP_VERSION, get_settings
from app.dependencies import get_client_ip, require_api_key
from app.logs import setup_logging
from app.routers import albums, artists, examples, tags, tracks
from app.services.cache import MB, TTLCache
from app.services.quota import PublicQuota


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting lastfm-analytics-api {version}: Last.fm at {rate_limit} req/s, "
        "cache {cache_max_mb} MB",
        version=APP_VERSION,
        rate_limit=settings.lastfm.rate_limit,
        cache_max_mb=settings.lastfm.cache_max_mb,
    )
    async with httpx2.AsyncClient(
        base_url=settings.lastfm.base_url,
        timeout=settings.http.timeout,
        headers={"User-Agent": settings.http.user_agent},
    ) as client:
        app.state.http_client = client
        app.state.lastfm_cache = TTLCache(
            ttl=settings.lastfm.cache_ttl, max_cost=settings.lastfm.cache_max_mb * MB
        )
        # One call every 1/rate seconds, shared by every request (max_rate=1 disables bursts).
        app.state.lastfm_limiter = AsyncLimiter(1, 1 / settings.lastfm.rate_limit)
        # Last.fm fetches in progress, so identical concurrent requests share one call.
        app.state.lastfm_inflight = {}
        # Public example endpoints: their own cache and call budget (on top of the shared limiter).
        app.state.public_cache = TTLCache(
            ttl=settings.lastfm.cache_ttl, max_cost=settings.examples.cache_max_mb * MB
        )
        app.state.public_quota = PublicQuota(
            settings.examples.rate_limit,
            settings.examples.client_rate_limit,
            settings.examples.max_clients,
        )
        yield


# At import, before uvicorn logs "Started server process", so every line uses our format.
setup_logging(get_settings().log.level, get_settings().log.format)

REPO_URL = "https://github.com/TiagoAdriaNunes/lastfm-analytics-api"

app = FastAPI(
    title="Last.fm Analytics API",
    version=APP_VERSION,
    description=(
        "All endpoints except `/health` and `/examples/*` require the `X-API-Key` header. "
        "Click **Authorize** and paste your key to try them here. "
        "The `/examples` endpoints are public so you can try the API without a key."
    ),
    openapi_external_docs={"description": "Source code on GitHub", "url": REPO_URL},
    license_info={"name": "MIT", "url": f"{REPO_URL}/blob/main/LICENSE"},
    lifespan=lifespan,
    # Keep the key entered via "Authorize" across page reloads (stored in the browser).
    swagger_ui_parameters={"persistAuthorization": True},
)
# /health stays public (platform health checks); everything else needs the X-API-Key header.
protected = APIRouter(
    dependencies=[Depends(require_api_key)],
    responses={401: {"description": "Invalid or missing `X-API-Key` header"}},
)
protected.include_router(artists.router)
protected.include_router(albums.router)
protected.include_router(tracks.router)
protected.include_router(tags.router)
app.include_router(protected)
# Public on purpose: a no-key way to try the API. Protected by `PublicQuota` instead.
app.include_router(examples.router)


# Health checks hit this every few seconds; only log them at DEBUG.
QUIET_PATHS = {"/health"}


@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """One line per request (replaces uvicorn's access log, which has no duration). Never logs
    headers, so the `X-API-Key` stays out of the logs."""
    start = time.perf_counter()
    status = 500  # if the app raises, uvicorn answers 500 and logs the traceback itself
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        path = request.url.path
        target = f"{path}?{request.url.query}" if request.url.query else path
        level = "DEBUG" if path in QUIET_PATHS else "WARNING" if status >= 500 else "INFO"
        logger.log(
            level,
            "{method} {target} -> {status} in {duration_ms} ms",
            method=request.method,
            target=target,
            status=status,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            client_ip=get_client_ip(request),
        )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
