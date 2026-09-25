# lastfm-analytics-api

[![CI](https://github.com/TiagoAdriaNunes/lastfm-analytics-api/actions/workflows/ci.yml/badge.svg)](https://github.com/TiagoAdriaNunes/lastfm-analytics-api/actions/workflows/ci.yml)

FastAPI service for music analytics on top of the [Last.fm API](https://www.last.fm/api).

## Setup

1. Get an API key at https://www.last.fm/api/account/create
2. `cp .env.example .env` and fill in `LASTFM_API_KEY` / `LASTFM_API_SECRET`
3. `uv sync`
4. `uv run fastapi dev app/main.py` and open http://127.0.0.1:8000/docs

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Health check |
| GET | `/artists/{artist}/similar?limit=10` | Artists similar to `artist`, with a 0–1 match score |
| GET | `/artists/{artist}/similar/network?limit=5` | Two-level similar-artist network (`nodes` + `edges`) for graph visualisation |

```sh
curl "http://127.0.0.1:8000/artists/Radiohead/similar?limit=3"
curl "http://127.0.0.1:8000/artists/Radiohead/similar/network?limit=3"
```

Network response shape:

```json
{
  "artist": "Radiohead",
  "nodes": [{"id": 1, "name": "Radiohead", "level": 0, "url": null}, {"id": 2, "name": "Thom Yorke", "level": 1, "url": "..."}],
  "edges": [{"from": 1, "to": 2, "weight": 1.0}]
}
```

## Rate limiting

All calls to Last.fm share one limiter: **2 requests/second, evenly spaced** (one call every 0.5s),
well under Last.fm's historical 5 req/s guideline. Responses are cached in memory for an hour, and cache
hits don't count. So an uncached network with `limit=5` (6 calls) takes about 3s, and a repeat is instant.

If Last.fm rate-limits us (error 29) or is temporarily down (8, 11, 16), the call is retried twice with
backoff (1s, 2s); if it still fails, the API returns `503` with `Retry-After: 60`.

Tunable via env vars: `LASTFM_RATE_LIMIT`, `LASTFM_MAX_RETRIES`, `LASTFM_RETRY_BACKOFF`,
`LASTFM_CACHE_TTL`, `USER_AGENT`.

## Tests

```sh
uv run pytest
```
