from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

LEGACY_ROUTE_PATHS = (
    "/api/v1/orchestration/roles",
    "/api/v1/orchestration/characters",
    "/api/v1/orchestration/mentions/catalog",
    "/api/v2/runtime/runs",
    "/api/v2/studio/runs",
    "/api/v2/tryouts",
    "/api/v2/agent-specs",
    "/api/v2/workflow-specs",
    "/api/v2/capabilities",
    "/api/v2/personas",
)
LEGACY_BACKEND_FILES = (
    "app/api/orchestration.py",
    "app/api/runtime.py",
    "app/api/studio.py",
    "app/api/tryouts.py",
    "app/services/orchestration_service.py",
    "app/services/agent_runtime_service.py",
    "app/services/studio_query_service.py",
    "app/services/tryout_service.py",
    "app/models/orchestration_role.py",
    "app/models/runtime_run.py",
    "app/schemas/orchestration.py",
    "app/schemas/runtime.py",
)

@pytest.mark.parametrize("path", LEGACY_ROUTE_PATHS)
def test_legacy_backend_routes_return_404(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404


def test_legacy_backend_routes_are_not_registered(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert route_paths.isdisjoint(LEGACY_ROUTE_PATHS)


def test_legacy_backend_modules_are_absent() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    missing_files = [
        backend_root / relative_path
        for relative_path in LEGACY_BACKEND_FILES
        if not (backend_root / relative_path).exists()
    ]
    assert len(missing_files) == len(LEGACY_BACKEND_FILES)
