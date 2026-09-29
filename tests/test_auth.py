import pytest

from app.config import APP_VERSION


def test_health_is_public(client):
    client.headers.pop("X-API-Key")
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_artists_require_valid_api_key(client, lastfm_mock, headers):
    client.headers.pop("X-API-Key")

    response = client.get("/artists/similar", params={"artist": "Radiohead"}, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"
    assert lastfm_mock.call_count == 0


def test_openapi_documents_api_key_scheme(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }


def test_openapi_marks_protected_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    similar = paths["/artists/similar"]["get"]
    assert similar["security"] == [{"APIKeyHeader": []}]
    assert "401" in similar["responses"]
    assert "security" not in paths["/health"]["get"]


PUBLIC_PATHS = {"/health", "/examples/artists/search"}


def test_every_non_public_route_requires_api_key(client):
    # Catches a new router included without `dependencies=[Depends(require_api_key)]`.
    paths = client.get("/openapi.json").json()["paths"]
    unprotected = [
        f"{method.upper()} {path}"
        for path, operations in paths.items()
        if path not in PUBLIC_PATHS
        for method, operation in operations.items()
        if operation.get("security") != [{"APIKeyHeader": []}]
    ]
    assert unprotected == []


def test_openapi_links_to_source_repo(client):
    schema = client.get("/openapi.json").json()
    repo = "https://github.com/TiagoAdriaNunes/lastfm-analytics-api"
    assert schema["externalDocs"]["url"] == repo
    assert schema["info"]["license"] == {"name": "MIT", "url": f"{repo}/blob/main/LICENSE"}


def test_openapi_reports_the_app_version(client):
    assert client.get("/openapi.json").json()["info"]["version"] == APP_VERSION
