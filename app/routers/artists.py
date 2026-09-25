from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import LastFMDep
from app.schemas.artist import SimilarArtistsResponse, parse_similar_artists
from app.services.lastfm import NOT_FOUND_ERROR, LastFMError

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("/{artist}/similar", response_model=SimilarArtistsResponse)
async def get_similar_artists(
    artist: str,
    lastfm: LastFMDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> SimilarArtistsResponse:
    try:
        data = await lastfm.get_similar_artists(artist, limit=limit)
    except LastFMError as exc:
        if exc.code == NOT_FOUND_ERROR:
            raise HTTPException(status.HTTP_404_NOT_FOUND, exc.message) from exc
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    return parse_similar_artists(data)
