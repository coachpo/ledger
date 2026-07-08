from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import reset_settings_cache
from app.main import create_app

ALLOWED_ORIGIN = "http://frontend.test"


@pytest.fixture()
def token_client(
    session_factory: object,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("SIGNALDECK_API_TOKEN", "test-token")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    reset_settings_cache()
    app = create_app(init_database=False)

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    reset_settings_cache()


def test_default_client_ignores_ambient_bearer_token(client: TestClient) -> None:
    response = client.get("/api/runs")

    assert response.status_code == 200


def test_api_runs_rejects_missing_bearer_token(token_client: TestClient) -> None:
    response = token_client.get("/api/runs")

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_api_runs_missing_bearer_token_includes_cors_header(
    token_client: TestClient,
) -> None:
    response = token_client.get("/api/runs", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_api_runs_accepts_matching_bearer_token(token_client: TestClient) -> None:
    response = token_client.get("/api/runs", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_health_is_exempt_from_bearer_token(token_client: TestClient) -> None:
    response = token_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
