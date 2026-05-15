from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.runtime_tools import RUNTIME_TOOL_SPECS
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.ledger_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_OWNERSHIP,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
    OwnershipSurfaceGroup,
)
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source

_CANONICAL_TOOL_KEYS = {
    "ledger.market_data.quote_lookup",
    "ledger.reports.lookup",
    "ledger.reports.write",
}


def _surface_text(groups: tuple[OwnershipSurfaceGroup, ...]) -> str:
    return "\n".join(surface for group in groups for surface in group.surfaces)


def test_ledger_finance_ownership_inventory_declares_phase_one_boundary() -> None:
    artifact = FINANCE_WORKSPACE_OWNERSHIP

    assert artifact.extension_key == "ledger.finance"
    assert artifact.label == "Finance Workspace"
    assert artifact.default_enabled is True
    assert artifact.phase == "phase_1_bundled_first_party"
    assert artifact.as_dict()["defaultEnabled"] is True
    assert "backend_api_routes" in artifact.contribution_categories
    assert "native_runtime_tools" in artifact.contribution_categories
    assert "frontend_tool_discovery_contributions" in artifact.contribution_categories

    owned_surfaces = _surface_text(artifact.extension_owned_public_surfaces)
    core_surfaces = _surface_text(artifact.core_retained_surfaces)
    for expected_surface in (
        "/api/v1/portfolios",
        'APIRouter(prefix="/templates")',
        "ledger.social_sentiment.lookup",
        "ledger_reports_write",
        "YahooFinanceQuoteProvider",
        "RedditSocialSentimentAdapter",
        "StockTwitsSocialSentimentAdapter",
        'metadata.analysis.reviewType="agent_memory"',
        "frontend/src/pages/dashboard.tsx",
        "frontend/src/lib/api/reports.ts",
        "frontend/src/hooks/use-workflow-packages.ts: useTools()",
        "docs/ledger-memory-layer-design.md",
        "backend/tests/fixtures/workflow_packages/*.yaml demo package fixtures",
    ):
        assert expected_surface in owned_surfaces

    for expected_surface in (
        "backend/app/api/platform_router.py",
        "GET/POST /api/workflow-packages",
        "backend/app/api/tools.py `GET /api/tools` read-only route host",
        "frontend/src/App.tsx",
        "frontend/src/pages/runs/*.tsx",
        "ledger.workflowPackage/v1 manifest shape",
    ):
        assert expected_surface in core_surfaces


def test_ledger_finance_tool_inventory_matches_catalog_and_runtime() -> None:
    server_declared_keys = {tool.key for tool in SERVER_DECLARED_TOOL_SPECS}
    runtime_keys = {tool.key for tool in RUNTIME_TOOL_SPECS}
    runtime_function_names = {tool.openai_function_name for tool in RUNTIME_TOOL_SPECS}

    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == server_declared_keys
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == runtime_keys
    assert set(FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES) == runtime_function_names


def test_default_tool_catalog_rejects_duplicate_unknown_and_phase_one_memory_keys() -> None:
    catalog = get_default_tool_catalog()

    with pytest.raises(ToolCatalogValidationError) as exc_info:
        _ = catalog.resolve_tool_keys(
            [
                "ledger.reports.lookup",
                "ledger.reports.lookup",
                "ledger.memory.lookup",
                "ledger.memory.write",
            ]
        )

    assert exc_info.value.details == [
        {
            "field": "toolKeys.1",
            "issue": "Duplicate tool key 'ledger.reports.lookup' is not allowed",
        },
        {
            "field": "toolKeys.2",
            "issue": "Unknown server-declared tool 'ledger.memory.lookup'",
        },
        {
            "field": "toolKeys.3",
            "issue": "Unknown server-declared tool 'ledger.memory.write'",
        },
    ]


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert _CANONICAL_TOOL_KEYS <= set(tools_by_key)
    quote_tool = tools_by_key["ledger.market_data.quote_lookup"]
    report_lookup_tool = tools_by_key["ledger.reports.lookup"]
    report_write_tool = tools_by_key["ledger.reports.write"]
    assert quote_tool == {
        "key": "ledger.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
        "module": "app.extensions.ledger_finance.tool_specs",
    }
    assert report_lookup_tool == {
        "key": "ledger.reports.lookup",
        "displayName": "Report Lookup",
        "description": "Read persisted Ledger reports through server-owned report lookups.",
        "module": "app.extensions.ledger_finance.tool_specs",
    }
    assert report_write_tool == {
        "key": "ledger.reports.write",
        "displayName": "Report Memory Write",
        "description": "Create pending agent-memory reports through server-owned memory writes.",
        "module": "app.extensions.ledger_finance.tool_specs",
    }
    assert not any(key.startswith("ledger.memory.") for key in tools_by_key)
    for tool in (quote_tool, report_lookup_tool, report_write_tool):
        assert "toolGrants" not in tool
        assert "toolDefinitions" not in tool


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}


def test_tool_catalog_hides_disabled_extension_tools_and_validation_classifies_them(
    client: TestClient,
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False, "disabledReason": "maintenance"},
    )
    assert response.status_code == 200, response.json()

    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200, tools_response.json()
    tools_body = cast(dict[str, object], tools_response.json())
    assert tools_body["items"] == []

    validation_response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": _valid_package_manifest_source()},
    )
    assert validation_response.status_code == 200, validation_response.json()
    body = cast(dict[str, object], validation_response.json())
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert body["metadata"] is None
    assert any(
        diagnostic["path"] == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
        and diagnostic["message"]
        == (
            "Server-declared tool 'ledger.market_data.quote_lookup' is disabled because "
            "extension 'ledger.finance' is disabled"
        )
        for diagnostic in diagnostics
    )
    assert not any("Unknown server-declared tool" in str(item) for item in diagnostics)
