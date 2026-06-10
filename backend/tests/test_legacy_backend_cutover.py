from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.services.run_service import RunService

RETIRED_GLOBAL_AUTHORING_IMPORT_MODULES = frozenset(
    {
        "app.models.agent",
        "app.models.workflow",
        "app.models.capability",
        "app.models.mcp_server",
        "app.models.output_schema",
        "app.models.platform_reference",
        "app.repositories.agent",
        "app.repositories.workflow",
        "app.repositories.capability",
        "app.repositories.mcp_server",
        "app.repositories.output_schema",
        "app.services.agent_service",
        "app.services.workflow_service",
        "app.services.capability_service",
        "app.services.mcp_server_service",
        "app.services.output_schema_service",
        "app.services.agent_manifest_compiler",
        "app.services.agent_manifest_decompiler",
        "app.services.agent_manifest_backfill",
        "app.services.workflow_manifest_compiler",
        "app.services.workflow_manifest_decompiler",
        "app.services.workflow_manifest_backfill",
        "app.services.execution_plan_builder",
    }
)
RETIRED_GLOBAL_AUTHORING_QUARANTINE_MODULES = frozenset(
    {
        "repositories.agent",
        "repositories.workflow",
        "repositories.capability",
        "repositories.mcp_server",
        "repositories.output_schema",
        "services.agent_service",
        "services.workflow_service",
        "services.capability_service",
        "services.mcp_server_service",
        "services.output_schema_service",
        "services.agent_manifest_compiler",
        "services.agent_manifest_decompiler",
        "services.agent_manifest_backfill",
        "services.workflow_manifest_compiler",
        "services.workflow_manifest_decompiler",
        "services.workflow_manifest_backfill",
        "services.execution_plan_builder",
    }
)

REMOVED_BACKEND_ROUTE_PATHS = (
    "/api/agents",
    "/api/workflows",
    "/api/capabilities",
    "/api/mcp-servers",
    "/api/output-schemas",
    "/api/v1/templates/seed",
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
    "/api/workflows/{workflow_id}/runs",
)
REMOVED_BACKEND_ROUTE_PREFIXES = (
    "/api/skills",
    "/api/v2/",
)
LIVE_BACKEND_ROUTE_PREFIXES = (
    "/api/workflow-packages",
    "/api/schedules",
    "/api/model-connections",
    "/api/extensions",
    "/api/memory",
    "/api/tools",
    "/api/runs",
    "/api/v1/portfolios",
    "/api/v1/templates",
    "/api/v1/reports",
)
REMOVED_OPENAPI_TAGS = (
    "agents",
    "workflows",
    "capabilities",
    "mcp-servers",
    "output-schemas",
    "skills",
    "orchestration",
    "runtime-v2",
    "studio",
    "tryouts",
    "agent-specs",
    "workflow-specs",
    "personas",
)
REMOVED_OPENAPI_OPERATION_ID_FRAGMENTS = (
    "api_agents",
    "api_workflows",
    "api_capabilities",
    "api_mcp_servers",
    "api_output_schemas",
    "api_skills",
    "api_v1_templates_seed",
    "api_v1_orchestration",
    "api_v2_runtime",
    "api_v2_studio",
    "api_v2_tryouts",
    "api_v2_agent_specs",
    "api_v2_workflow_specs",
    "api_v2_capabilities",
    "api_v2_personas",
)
REMOVED_OPENAPI_SCHEMA_COMPONENT_NAMES = (
    "AgentCreate",
    "AgentListRead",
    "AgentRead",
    "AgentUpdate",
    "AgentSpecCreate",
    "AgentSpecRead",
    "CapabilityCreate",
    "CapabilityListRead",
    "CapabilityRead",
    "CapabilityUpdate",
    "McpServerCreate",
    "McpServerRead",
    "OutputSchemaCreate",
    "OutputSchemaRead",
    "PersonaCreate",
    "PersonaRead",
    "SkillCreate",
    "SkillRead",
    "StudioRunRead",
    "TryoutRead",
    "WorkflowCreate",
    "WorkflowListRead",
    "WorkflowRead",
    "WorkflowSpecCreate",
    "WorkflowSpecRead",
    "WorkflowUpdate",
)


@pytest.mark.parametrize("path", REMOVED_BACKEND_ROUTE_PATHS)
def test_legacy_backend_routes_return_404(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404


@pytest.mark.parametrize("path", REMOVED_BACKEND_ROUTE_PATHS)
def test_clean_break_removes_global_authoring_routes(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404
    assert client.post(path, json={}).status_code == 404


def test_legacy_backend_routes_are_not_registered(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    for removed_path in REMOVED_BACKEND_ROUTE_PATHS:
        assert removed_path not in route_paths
        assert not any(path.startswith(f"{removed_path}/") for path in route_paths)

    for prefix in REMOVED_BACKEND_ROUTE_PREFIXES:
        assert not any(path.startswith(prefix) for path in route_paths)


def test_live_platform_routes_match_openapi(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    openapi = cast(dict[str, object], app.openapi())
    openapi_paths = set(cast(dict[str, object], openapi["paths"]))

    for prefix in LIVE_BACKEND_ROUTE_PREFIXES:
        assert any(path.startswith(prefix) for path in route_paths)
        assert any(path.startswith(prefix) for path in openapi_paths)


def test_removed_backend_surfaces_are_absent_from_openapi_contract(
    app: FastAPI,
) -> None:
    openapi = cast(dict[str, object], app.openapi())
    openapi_paths = cast(dict[str, object], openapi["paths"])
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, object], components["schemas"])
    openapi_tags: set[str] = set()
    operation_ids: list[str] = []

    for path_item in openapi_paths.values():
        operations = cast(dict[str, dict[str, object]], path_item)
        for operation in operations.values():
            openapi_tags.update(cast(list[str], operation.get("tags", [])))
            operation_id = operation.get("operationId")
            if isinstance(operation_id, str):
                operation_ids.append(operation_id.lower())

    for removed_path in REMOVED_BACKEND_ROUTE_PATHS:
        assert removed_path not in openapi_paths
        assert not any(path.startswith(f"{removed_path}/") for path in openapi_paths)

    for prefix in REMOVED_BACKEND_ROUTE_PREFIXES:
        assert not any(path.startswith(prefix) for path in openapi_paths)

    assert openapi_tags.isdisjoint(REMOVED_OPENAPI_TAGS)

    for operation_id in operation_ids:
        assert not any(
            fragment in operation_id for fragment in REMOVED_OPENAPI_OPERATION_ID_FRAGMENTS
        )

    assert set(schemas).isdisjoint(REMOVED_OPENAPI_SCHEMA_COMPONENT_NAMES)


def test_legacy_global_authoring_runtime_entrypoint_is_removed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = RunService(session, session_factory)

    assert not hasattr(service, "create_target_run")


def test_current_backend_app_modules_do_not_import_retired_global_authoring_modules() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    violations: list[str] = []

    for path in sorted(app_root.rglob("*.py")):
        module_name = path.relative_to(app_root).with_suffix("").as_posix().replace("/", ".")
        if module_name in RETIRED_GLOBAL_AUTHORING_QUARANTINE_MODULES:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            relative_path = path.relative_to(app_root)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module in RETIRED_GLOBAL_AUTHORING_IMPORT_MODULES
            ):
                violations.append(f"{relative_path}:{node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in RETIRED_GLOBAL_AUTHORING_IMPORT_MODULES:
                        violations.append(f"{relative_path}:{node.lineno}: import {alias.name}")

    assert violations == []
