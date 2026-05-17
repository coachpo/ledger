from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.services.legacy_authoring import (
    LEGACY_AUTHORING_MODULE_CLASSIFICATIONS,
    LEGACY_AUTHORING_RUNTIME_BLOCKED,
    LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    LEGACY_AUTHORING_UPGRADE_ONLY,
)
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
    "/api/runs/{run_id}/fork-draft",
    "/api/runs/{run_id}/forks",
)
LEGACY_BACKEND_FILES = (
    "app/api/orchestration.py",
    "app/api/runtime.py",
    "app/api/studio.py",
    "app/api/tryouts.py",
    "app/services/orchestration_service.py",
    "app/services/agent_runtime_service.py",
    "app/services/skill_service.py",
    "app/services/studio_query_service.py",
    "app/services/tryout_service.py",
    "app/models/orchestration_role.py",
    "app/models/runtime_run.py",
    "app/models/skill.py",
    "app/repositories/skill.py",
    "app/schemas/skill.py",
    "app/api/skills.py",
    "app/agents/skill_registry.py",
    "app/schemas/orchestration.py",
    "app/schemas/runtime.py",
)
DOCUMENTED_PLATFORM_ROUTE_PREFIXES = (
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
EXPECTED_LEGACY_AUTHORING_CLASSIFICATIONS = {
    "app.services.agent_service": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.workflow_service": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.execution_plan_builder": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.capability_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.services.mcp_server_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.services.output_schema_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.db.upgrades": LEGACY_AUTHORING_UPGRADE_ONLY,
}


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


def test_documented_platform_routes_match_openapi(app: FastAPI) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    docs_root = backend_root.parent / "docs"
    api_design = (docs_root / "api-design.md").read_text(encoding="utf-8")
    documented_section = api_design.split("## Platform Compatibility Notes", maxsplit=1)[0]
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    for prefix in DOCUMENTED_PLATFORM_ROUTE_PREFIXES:
        assert prefix in documented_section
        assert any(path.startswith(prefix) for path in route_paths)

    for removed_path in REMOVED_GLOBAL_AUTHORING_ROUTE_PATHS:
        assert removed_path not in documented_section
        assert removed_path not in route_paths


def test_legacy_backend_modules_are_absent() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    missing_files = [
        backend_root / relative_path
        for relative_path in LEGACY_BACKEND_FILES
        if not (backend_root / relative_path).exists()
    ]
    assert len(missing_files) == len(LEGACY_BACKEND_FILES)


def test_live_composition_root_excludes_global_authoring_factories() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    dependency_root = backend_root / "app" / "api" / "dependencies.py"
    source = dependency_root.read_text(encoding="utf-8")

    for factory_name in FORBIDDEN_GLOBAL_AUTHORING_DEPENDENCY_FACTORIES:
        assert factory_name not in source


def test_remaining_legacy_authoring_modules_are_classified() -> None:
    assert LEGACY_AUTHORING_MODULE_CLASSIFICATIONS == EXPECTED_LEGACY_AUTHORING_CLASSIFICATIONS
    for module_name, expected_classification in EXPECTED_LEGACY_AUTHORING_CLASSIFICATIONS.items():
        module = importlib.import_module(module_name)
        assert module.LEGACY_AUTHORING_CLASSIFICATION == expected_classification


def test_legacy_global_authoring_runtime_is_blocked(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = RunService(session, session_factory)
        with pytest.raises(ApiError) as exc_info:
            service.create_target_run("agent", 1, {})

    assert exc_info.value.code == "legacy_global_authoring_runtime_blocked"
    assert exc_info.value.details == [
        {
            "field": "targetKind",
            "issue": "agent is runtime-blocked after the Workflow Package cutover.",
        }
    ]
