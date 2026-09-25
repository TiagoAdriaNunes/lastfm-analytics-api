import os

os.environ.setdefault("LASTFM_API_KEY", "test-key")
os.environ.setdefault("LASTFM_API_SECRET", "test-secret")
# Keep tests fast: effectively no pacing and no retry sleeps.
os.environ["LASTFM_RATE_LIMIT"] = "1000"
os.environ["LASTFM_RETRY_BACKOFF"] = "0"

from collections.abc import Callable, Iterable  # noqa: E402
from typing import Self  # noqa: E402

import httpx2  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

Handler = Callable[[httpx2.Request], httpx2.Response]


class LastFMMock:
    """Stand-in for Last.fm built on `httpx2.MockTransport` (respx only supports `httpx`).

    Configure with `respond(response)` or `respond(side_effect=...)`, where `side_effect` is a
    function of the request or an iterable of responses returned in order."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self._handler: Handler | None = None
        self.transport = httpx2.MockTransport(self._handle)

    def respond(
        self,
        return_value: httpx2.Response | None = None,
        *,
        side_effect: Handler | Iterable[httpx2.Response] | None = None,
    ) -> Self:
        if callable(side_effect):
            self._handler = side_effect
        elif side_effect is not None:
            responses = iter(side_effect)
            self._handler = lambda _: next(responses)
        else:
            assert return_value is not None, "pass return_value or side_effect"
            self._handler = lambda _: return_value
        return self

    @property
    def call_count(self) -> int:
        return len(self.requests)

    @property
    def last_request(self) -> httpx2.Request:
        return self.requests[-1]

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self._handler is None:
            raise AssertionError(f"Unexpected Last.fm call: {request.url}")
        return self._handler(request)


@pytest.fixture
def lastfm_mock() -> LastFMMock:
    return LastFMMock()


@pytest.fixture
def client(lastfm_mock: LastFMMock):
    with TestClient(app) as c:
        # Route the app's Last.fm traffic through the mock, keeping the real client's config
        # (base URL, headers such as User-Agent).
        real = app.state.http_client
        app.state.http_client = httpx2.AsyncClient(
            base_url=get_settings().lastfm_base_url,
            headers=real.headers,
            transport=lastfm_mock.transport,
        )
        yield c
