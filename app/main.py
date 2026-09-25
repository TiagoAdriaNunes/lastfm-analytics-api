from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from aiolimiter import AsyncLimiter
from fastapi import FastAPI

from app.config import get_settings
from app.routers import artists
from app.services.cache import TTLCache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx2.AsyncClient(
        base_url=settings.lastfm_base_url,
        timeout=settings.lastfm_timeout,
        headers={"User-Agent": settings.user_agent},
    ) as client:
        app.state.http_client = client
        app.state.lastfm_cache = TTLCache(ttl=settings.lastfm_cache_ttl)
        # One call every 1/rate seconds, shared by every request (max_rate=1 disables bursts).
        app.state.lastfm_limiter = AsyncLimiter(1, 1 / settings.lastfm_rate_limit)
        yield


app = FastAPI(title="Last.fm Analytics API", version="0.1.0", lifespan=lifespan)
app.include_router(artists.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
