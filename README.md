# lastfm-analytics-api

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

```sh
curl "http://127.0.0.1:8000/artists/Radiohead/similar?limit=3"
```

## Tests

```sh
uv run pytest
```
