import hashlib
from typing import Any

import httpx

# Last.fm error codes: https://www.last.fm/api/errorcodes
NOT_FOUND_ERROR = 6
SIGNED_METHODS = {"auth.getSession", "track.scrobble"}


class LastFMError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def create_signature(params: dict[str, Any], secret: str) -> str:
    """Build the Last.fm API signature: every param except `format`, sorted by key,
    concatenated as key+value with the shared secret appended, then MD5'd.
    See https://www.last.fm/api/authspec."""
    base = "".join(f"{k}{params[k]}" for k in sorted(params) if k != "format")
    return hashlib.md5((base + secret).encode("utf-8")).hexdigest()


class LastFMClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str, api_secret: str = "") -> None:
        self._http = http
        self._api_key = api_key
        self._api_secret = api_secret

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        query = {k: v for k, v in params.items() if v is not None}
        query |= {"method": method, "api_key": self._api_key, "format": "json"}
        if method in SIGNED_METHODS:
            query["api_sig"] = create_signature(query, self._api_secret)

        response = await self._http.get("", params=query)
        data = response.json()
        # Last.fm reports errors in the body, sometimes with a 200 status.
        if "error" in data:
            raise LastFMError(data["error"], data.get("message", "Unknown Last.fm error"))
        response.raise_for_status()
        return data

    async def get_similar_artists(self, artist: str, limit: int | None = None) -> dict[str, Any]:
        return await self.call("artist.getSimilar", artist=artist, limit=limit, autocorrect=1)
