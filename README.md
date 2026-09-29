# lastfm-analytics-api

[![CI](https://github.com/TiagoAdriaNunes/lastfm-analytics-api/actions/workflows/ci.yml/badge.svg)](https://github.com/TiagoAdriaNunes/lastfm-analytics-api/actions/workflows/ci.yml)

FastAPI service for music analytics on top of the [Last.fm API](https://www.last.fm/api).

## Setup

1. Get an API key at https://www.last.fm/api/account/create
2. `cp .env.example .env` and fill in `LASTFM_API_KEY` / `LASTFM_API_SECRET`, plus a
   `SERVICE_API_KEY` (generate one with `make key`)
3. `make install` (or `uv sync`)
4. `make dev` (or `uv run fastapi dev app/main.py`) and open http://127.0.0.1:8000/docs

Run `make` to list all shortcuts: `dev`, `run`, `test`, `lint`, `format`, `check` (same as CI),
`lock`, `key`. Each is a thin wrapper around a `uv` command, so `make` is optional.

## Endpoints

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Health check (public) |
| GET | `/examples/artists/search?artist=Radiohead&limit=5` | Search artists by name, with listener counts (public, `limit` 1–10) |
| GET | `/artists/search?artist=Radiohead&limit=10` | Search artists by name, with listener counts (`limit` 1–100) |
| GET | `/artists/similar?artist=Radiohead&limit=10` | Artists similar to `artist`, with a 0–1 match score |
| GET | `/artists/similar/network?artist=Radiohead&limit=5&depth=2` | Similar-artist network (`nodes` + `edges`) for graph visualisation, `depth` 1–3 levels (default 2) |
| GET | `/artists/info?artist=Radiohead` | Listener and play counts, tag names |
| GET | `/artists/tags?artist=Radiohead&limit=5` | Most-applied tags (usable as genres), with a relative weight |
| GET | `/artists/albums?artist=Radiohead&limit=10` | Most played albums |
| GET | `/artists/tracks?artist=Radiohead&limit=10` | Most played tracks |
| GET | `/albums/info?artist=Radiohead&album=OK Computer` | Listener and play counts, tag names, track list |
| GET | `/albums/tags?artist=Radiohead&album=OK Computer&limit=5` | Most-applied tags for an album |
| GET | `/albums/search?album=OK Computer&limit=10` | Search albums by title |
| GET | `/tracks/info?artist=Radiohead&track=Creep` | Album, duration (seconds), listener and play counts, tag names |
| GET | `/tracks/similar?artist=Radiohead&track=Creep&limit=10` | Similar tracks, with a 0–1 match score |
| GET | `/tracks/tags?artist=Radiohead&track=Creep&limit=5` | Most-applied tags for a track |
| GET | `/tracks/search?track=Creep&artist=Radiohead&limit=10` | Search tracks by title; `artist` is optional |
| GET | `/tags/top?limit=100&genres_only=true` | Most used tags on Last.fm; `genres_only` drops tags like "seen live" |
| GET | `/tags/artists?tag=rock&limit=20` | Top artists for a tag (empty list for an unknown tag) |

Every `limit` is 1–100 unless noted. Names go in query parameters, not the path, because they can
contain `/` (e.g. "AC/DC").

```sh
curl "http://127.0.0.1:8000/examples/artists/search?artist=Radiohead"   # no key needed
curl "http://127.0.0.1:8000/artists/similar?artist=Radiohead&limit=3"
curl -G "http://127.0.0.1:8000/albums/info" --data-urlencode "artist=Radiohead" --data-urlencode "album=OK Computer"
curl "http://127.0.0.1:8000/artists/similar/network?artist=Radiohead&limit=3"
curl "http://127.0.0.1:8000/artists/similar/network?artist=Radiohead&limit=5&depth=3"   # ~77 nodes
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
Identical requests that arrive while the first is still waiting on Last.fm share its call instead of
making their own, so e.g. two users opening the same artist at once cost one set of calls.

If Last.fm rate-limits us (error 29) or is temporarily down (8, 11, 16), the call is retried twice with
backoff (1s, 2s); if it still fails, the API returns `503` with `Retry-After: 60`.

The public `/examples` endpoints have extra limits on top of that (`examples` in `config.yaml`):
**1.5 uncached Last.fm calls per second** for all anonymous callers together, and **one per second per
client IP** (so one caller can't take it all; the app refuses to start if the per-client limit isn't
below the global one). Beyond either they return `429` with `Retry-After` right away instead of queueing. They
also have their own small cache, so anonymous traffic can't push out the entries the authenticated
endpoints rely on. Cached searches are always served.

## Authentication

Every endpoint except `/health` and `/examples/*` requires the `X-API-Key` header to match `SERVICE_API_KEY` (at least 16
characters; the app refuses to start without it). Otherwise it returns `401`.

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"   # generate a key
curl -H "X-API-Key: $SERVICE_API_KEY" "http://127.0.0.1:8000/artists/similar?artist=Radiohead"
```

In `/docs`, click **Authorize** and paste the key to try the endpoints.

## Configuration

- **`config.yaml`** (committed): all non-secret settings (rate limit, retries, cache TTL, timeout,
  User-Agent), with comments.
- **`.env` / environment variables**: secrets (`LASTFM_API_KEY`, `LASTFM_API_SECRET`, `SERVICE_API_KEY`),
  never in YAML.
- **Overrides**: environment variables beat `config.yaml`. Join the section and key with `__`,
  e.g. `LASTFM__RATE_LIMIT=1` or `HTTP__TIMEOUT=5`.
- **Another file**: `APP_CONFIG_FILE=path/to/other.yaml`.

## Logging

Logs go to stdout via [loguru](https://github.com/Delgan/loguru), one line per event:

- every request: method, path + query, status, duration, client IP (`/health` only at `DEBUG`);
- every Last.fm call: method, params, status, duration, time spent waiting for the rate limiter;
- Last.fm errors, retries and connection failures as warnings; cache hits at `DEBUG`;
- uvicorn's own messages, in the same format (its access log is replaced by the request line).

API keys are never logged: not the `X-API-Key` header, nor the Last.fm `api_key` (httpx's own
request logs, which include it in the URL, are deliberately not collected).

Settings (`log` in `config.yaml`): `LOG__LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`; default
`INFO`) and `LOG__FORMAT` (`text` or `json`). **On Railway set `LOG__FORMAT=json`**: each line is
one JSON object whose fields you can filter on in the log explorer, e.g. `@status:502`,
`@lastfm_method:artist.getInfo` or `@level:warning`.

## Tests

```sh
make test     # or: uv run pytest
make check    # everything CI runs: locked sync, ruff lint + format check, tests
```
