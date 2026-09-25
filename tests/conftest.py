import os

os.environ.setdefault("LASTFM_API_KEY", "test-key")
os.environ.setdefault("LASTFM_API_SECRET", "test-secret")
# Keep tests fast: effectively no pacing and no retry sleeps.
os.environ["LASTFM_RATE_LIMIT"] = "1000"
os.environ["LASTFM_RETRY_BACKOFF"] = "0"

import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def lastfm_mock():
    with respx.mock(base_url=get_settings().lastfm_base_url, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def client(lastfm_mock):
    with TestClient(app) as c:
        yield c
