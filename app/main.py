from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import get_settings
from app.routers import artists


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url=settings.lastfm_base_url, timeout=settings.lastfm_timeout
    ) as client:
        app.state.http_client = client
        yield


app = FastAPI(title="Last.fm Analytics API", version="0.1.0", lifespan=lifespan)
app.include_router(artists.router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
