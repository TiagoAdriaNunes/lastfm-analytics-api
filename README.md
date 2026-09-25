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
| GET | `/artists/similar?artist=Radiohead&limit=10` | Artists similar to `artist`, with a 0–1 match score |
| GET | `/artists/similar/network?artist=Radiohead&limit=5` | Two-level similar-artist network (`nodes` + `edges`) for graph visualisation |

```sh
curl "http://127.0.0.1:8000/artists/similar?artist=Radiohead&limit=3"
curl "http://127.0.0.1:8000/artists/similar/network?artist=Radiohead&limit=3"
# Names with special characters must be URL-encoded (curl can do it for you):
curl -G "http://127.0.0.1:8000/artists/similar" --data-urlencode "artist=AC/DC"
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

## Configuration

- **`config.yaml`** (committed): all non-secret settings (rate limit, retries, cache TTL, timeout,
  User-Agent), with comments.
- **`.env` / environment variables**: secrets (`LASTFM_API_KEY`, `LASTFM_API_SECRET`), never in YAML.
- **Overrides**: environment variables beat `config.yaml`. Join the section and key with `__`,
  e.g. `LASTFM__RATE_LIMIT=1` or `HTTP__TIMEOUT=5`.
- **Another file**: `APP_CONFIG_FILE=path/to/other.yaml`.

## Tests

```sh
uv run pytest
```
