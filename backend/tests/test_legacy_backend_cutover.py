from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.services.run_service import RunService

REMOVED_GLOBAL_AUTHORING_ROUTE_PATHS = (
    "/api/agents",
    "/api/workflows",
    "/api/capabilities",
    "/api/mcp-servers",
    "/api/output-schemas",
)
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
    "/api/skills",
    "/api/skills/1",
    "/api/skills/1/activate",
    "/api/v2/personas",
    "/api/v1/templates/seed",
    "/api/workflows/{workflow_id}/runs",
)
LIVE_PLATFORM_ROUTE_PREFIXES = (
    "/api/workflow-packages",
    "/api/model-connections",
    "/api/tools",
    "/api/runs",
)
FORBIDDEN_GLOBAL_AUTHORING_DEPENDENCY_FACTORIES = (
    "get_agent_service",
    "get_workflow_service",
    "get_mcp_server_service",
    "get_capability_service",
    "get_output_schema_service",
)


@pytest.mark.parametrize("path", LEGACY_ROUTE_PATHS)
def test_legacy_backend_routes_return_404(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404


@pytest.mark.parametrize("path", REMOVED_GLOBAL_AUTHORING_ROUTE_PATHS)
def test_clean_break_removes_global_authoring_routes(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404
    assert client.post(path, json={}).status_code == 404


def test_legacy_backend_routes_are_not_registered(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert route_paths.isdisjoint((*LEGACY_ROUTE_PATHS, *REMOVED_GLOBAL_AUTHORING_ROUTE_PATHS))


def test_live_platform_routes_match_openapi(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    openapi = cast(dict[str, object], app.openapi())
    openapi_paths = set(cast(dict[str, object], openapi["paths"]))

    for prefix in LIVE_PLATFORM_ROUTE_PREFIXES:
        assert any(path.startswith(prefix) for path in route_paths)
        assert any(path.startswith(prefix) for path in openapi_paths)

    for removed_path in REMOVED_GLOBAL_AUTHORING_ROUTE_PATHS:
        assert removed_path not in route_paths
        assert not any(path.startswith(f"{removed_path}/") for path in openapi_paths)
        assert removed_path not in openapi_paths


def test_live_composition_root_excludes_global_authoring_factories() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    dependency_root = backend_root / "app" / "api" / "dependencies.py"
    source = dependency_root.read_text(encoding="utf-8")

    for factory_name in FORBIDDEN_GLOBAL_AUTHORING_DEPENDENCY_FACTORIES:
        assert factory_name not in source


def test_legacy_global_authoring_runtime_is_blocked(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = RunService(session, session_factory)
        with pytest.raises(ApiError) as exc_info:
            _ = service.create_target_run("agent", 1, {})

    assert exc_info.value.code == "legacy_global_authoring_runtime_blocked"
    assert exc_info.value.details == [
        {
            "field": "targetKind",
            "issue": "agent is runtime-blocked after the Workflow Package cutover.",
        }
    ]
