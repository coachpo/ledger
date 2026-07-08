from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import (
    DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
    DEFAULT_DATABASE_URL,
    Settings,
    reset_settings_cache,
)
from app.main import create_app

PRODUCTION_DATABASE_URL = "postgresql+psycopg://user:pass@db:5432/signaldeck"
PRODUCTION_ENCRYPTION_KEY = "real-production-secret-key"


def clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIGNALDECK_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AGENT_PLATFORM_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SIGNALDECK_API_TOKEN", raising=False)
    reset_settings_cache()


def test_local_runtime_allows_safe_development_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    settings = Settings()

    assert settings.runtime_mode == "local"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.agent_platform_encryption_key == DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY


def test_production_runtime_requires_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", PRODUCTION_ENCRYPTION_KEY)
    with pytest.raises(ValidationError, match="DATABASE_URL must be explicitly configured"):
        _ = Settings()


def test_production_runtime_rejects_placeholder_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_DATABASE_URL)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY)
    with pytest.raises(
        ValidationError,
        match="AGENT_PLATFORM_ENCRYPTION_KEY must be explicitly configured",
    ):
        _ = Settings()


def test_production_runtime_accepts_explicit_non_placeholder_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_DATABASE_URL)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", PRODUCTION_ENCRYPTION_KEY)
    settings = Settings()

    assert settings.runtime_mode == "production"
    assert settings.database_url == PRODUCTION_DATABASE_URL
    assert settings.agent_platform_encryption_key == PRODUCTION_ENCRYPTION_KEY


def test_production_runtime_warns_when_api_token_missing(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setenv("SIGNALDECK_RUNTIME_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_DATABASE_URL)
    monkeypatch.setenv("AGENT_PLATFORM_ENCRYPTION_KEY", PRODUCTION_ENCRYPTION_KEY)

    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        settings = Settings()

    assert settings.api_token is None
    assert "SIGNALDECK_API_TOKEN is not configured" in caplog.text


def test_health_endpoint_is_liveness_only(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_reports_database_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setattr("app.main._database_is_ready", lambda: True)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_readiness_endpoint_fails_closed_when_database_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_runtime_env(monkeypatch)
    monkeypatch.setattr("app.main._database_is_ready", lambda: False)
    app = create_app(init_database=False)

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
