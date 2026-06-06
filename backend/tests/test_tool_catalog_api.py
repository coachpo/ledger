from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.runtime_tools import get_default_runtime_tool_registry
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.signaldeck_digital_oracle.ownership import (
    DIGITAL_ORACLE_EXTENSION_KEY,
    DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES,
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.schemas.memory import MEMORY_CORE_RUNTIME_TOOL_KEYS
from app.services.extension_service import ExtensionService

_DIGITAL_ORACLE_TOOL_KEYS = set(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS)
_REQUIRED_FINANCE_TOOL_KEYS = {
    "signaldeck.market_data.quote_lookup",
    "signaldeck.reports.lookup",
}
_REQUIRED_CORE_TOOL_KEYS = set(MEMORY_CORE_RUNTIME_TOOL_KEYS)


def _valid_manifest_source() -> str:
    module = import_module("tests.test_workflow_package_manifest_parser")
    source_factory = cast(Callable[[], str], module.__dict__["_valid_package_manifest_source"])
    return source_factory()


def _api_tool_keys(client: TestClient) -> set[str]:
    response = client.get("/api/tools")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    return {str(item["key"]) for item in items}


def test_extension_tool_inventories_match_catalog_and_runtime() -> None:
    finance_server_declared_keys = {
        tool.key
        for tool in SERVER_DECLARED_TOOL_SPECS
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_server_declared_keys = {
        tool.key
        for tool in SERVER_DECLARED_TOOL_SPECS
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }
    core_server_declared_keys = {
        tool.key for tool in SERVER_DECLARED_TOOL_SPECS if tool.owner_extension_key is None
    }
    runtime_specs = get_default_runtime_tool_registry().list_specs()
    finance_runtime_keys = {
        tool.key
        for tool in runtime_specs
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_runtime_keys = {
        tool.key
        for tool in runtime_specs
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }
    core_runtime_keys = {tool.key for tool in runtime_specs if tool.owner_extension_key is None}
    finance_runtime_function_names = {
        tool.openai_function_name
        for tool in runtime_specs
        if tool.owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    }
    digital_oracle_runtime_function_names = {
        tool.openai_function_name
        for tool in runtime_specs
        if tool.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }

    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_server_declared_keys
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_runtime_keys
    assert set(FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES) == finance_runtime_function_names
    assert set(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS) == digital_oracle_server_declared_keys
    assert set(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS) == digital_oracle_runtime_keys
    assert set(DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES) == digital_oracle_runtime_function_names
    assert _REQUIRED_CORE_TOOL_KEYS <= core_server_declared_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= core_runtime_keys
    assert _REQUIRED_CORE_TOOL_KEYS.isdisjoint(finance_server_declared_keys)
    assert _REQUIRED_CORE_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert finance_server_declared_keys.isdisjoint(digital_oracle_server_declared_keys)


def test_default_tool_catalog_rejects_duplicate_and_unknown_keys() -> None:
    catalog = get_default_tool_catalog()

    with pytest.raises(ToolCatalogValidationError) as exc_info:
        _ = catalog.resolve_tool_keys(
            [
                "signaldeck.reports.lookup",
                "signaldeck.reports.lookup",
                "signaldeck.unknown.lookup",
            ]
        )

    assert exc_info.value.details == [
        {
            "field": "toolKeys.1",
            "issue": "Duplicate tool key 'signaldeck.reports.lookup' is not allowed",
        },
        {
            "field": "toolKeys.2",
            "issue": "Unknown server-declared tool 'signaldeck.unknown.lookup'",
        },
    ]


def test_get_tools_lists_server_declared_catalog(client: TestClient) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    tools_by_key = {str(item["key"]): item for item in items}

    assert not any("module" in item for item in items)
    assert _REQUIRED_FINANCE_TOOL_KEYS <= set(tools_by_key)
    assert _DIGITAL_ORACLE_TOOL_KEYS <= set(tools_by_key)
    assert _REQUIRED_CORE_TOOL_KEYS <= set(tools_by_key)
    assert MEMORY_CORE_RUNTIME_TOOL_KEYS == (
        "signaldeck.memory.write",
        "signaldeck.memory.lookup",
    )
    assert not set(MEMORY_CORE_RUNTIME_TOOL_KEYS) & set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS)
    memory_write_tool = tools_by_key["signaldeck.memory.write"]
    memory_lookup_tool = tools_by_key["signaldeck.memory.lookup"]
    quote_tool = tools_by_key["signaldeck.market_data.quote_lookup"]
    report_lookup_tool = tools_by_key["signaldeck.reports.lookup"]
    prediction_markets_tool = tools_by_key["signaldeck.prediction_markets.lookup"]
    sec_filings_tool = tools_by_key["signaldeck.sec_filings.lookup"]
    market_sentiment_tool = tools_by_key["signaldeck.market_sentiment.lookup"]
    assert memory_write_tool == {
        "key": "signaldeck.memory.write",
        "displayName": "Memory Write",
        "description": "Write platform-core memory entries through server-owned memory storage.",
    }
    assert memory_lookup_tool == {
        "key": "signaldeck.memory.lookup",
        "displayName": "Memory Lookup",
        "description": "Read bounded, scoped platform-core memory snippets.",
    }
    assert quote_tool == {
        "key": "signaldeck.market_data.quote_lookup",
        "displayName": "Market Data Quote Lookup",
        "description": "Read trusted market quote snapshots from server-owned integrations.",
    }
    assert report_lookup_tool == {
        "key": "signaldeck.reports.lookup",
        "displayName": "Report Lookup",
        "description": "Read persisted SignalDeck reports through server-owned report lookups.",
    }
    assert prediction_markets_tool == {
        "key": "signaldeck.prediction_markets.lookup",
        "displayName": "Prediction Markets Lookup",
        "description": (
            "Read normalized prediction-market signals from Digital Oracle market "
            "lookups with structured warnings for partial coverage."
        ),
    }
    assert sec_filings_tool == {
        "key": "signaldeck.sec_filings.lookup",
        "displayName": "SEC Filings Lookup",
        "description": (
            "Read normalized SEC filing signals from Digital Oracle filing lookups "
            "with structured warnings for partial coverage."
        ),
    }
    assert market_sentiment_tool == {
        "key": "signaldeck.market_sentiment.lookup",
        "displayName": "Market Sentiment Lookup",
        "description": (
            "Read normalized market sentiment signals from Digital Oracle sentiment "
            "lookups with structured warnings for partial coverage."
        ),
    }
    for tool in (
        memory_write_tool,
        memory_lookup_tool,
        quote_tool,
        report_lookup_tool,
        prediction_markets_tool,
        sec_filings_tool,
        market_sentiment_tool,
    ):
        assert "module" not in tool
        assert "ownerExtensionKey" not in tool
        assert "contributionCategories" not in tool
        assert "toolGrants" not in tool
        assert "toolDefinitions" not in tool


def test_digital_oracle_api_tools_follow_extension_state_in_catalog_and_runtime(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    enabled_api_tool_keys = _api_tool_keys(client)
    assert _DIGITAL_ORACLE_TOOL_KEYS <= enabled_api_tool_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= enabled_api_tool_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= enabled_api_tool_keys

    with session_factory() as session:
        enabled_service = ExtensionService(session)
        enabled_catalog_keys = {
            tool.key for tool in enabled_service.get_tool_catalog().list_registered_tools()
        }
        enabled_runtime_registry = enabled_service.get_runtime_tool_registry()
        enabled_runtime_keys = {spec.key for spec in enabled_runtime_registry.list_enabled_specs()}
        enabled_descriptor_keys = {
            descriptor.tool_key
            for descriptor in enabled_runtime_registry.get_execution_descriptors(
                _DIGITAL_ORACLE_TOOL_KEYS
            )
        }

    assert _DIGITAL_ORACLE_TOOL_KEYS <= enabled_catalog_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= enabled_catalog_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= enabled_catalog_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= enabled_runtime_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= enabled_runtime_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= enabled_runtime_keys
    assert enabled_descriptor_keys == _DIGITAL_ORACLE_TOOL_KEYS

    response = client.patch(
        f"/api/extensions/{DIGITAL_ORACLE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert response.status_code == 200, response.json()

    disabled_api_tool_keys = _api_tool_keys(client)
    assert not _DIGITAL_ORACLE_TOOL_KEYS & disabled_api_tool_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= disabled_api_tool_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= disabled_api_tool_keys

    with session_factory() as session:
        disabled_service = ExtensionService(session)
        disabled_catalog_keys = {
            tool.key for tool in disabled_service.get_tool_catalog().list_registered_tools()
        }
        disabled_runtime_registry = disabled_service.get_runtime_tool_registry()
        disabled_runtime_keys = {
            spec.key for spec in disabled_runtime_registry.list_enabled_specs()
        }
        requested_descriptor_keys = (
            _DIGITAL_ORACLE_TOOL_KEYS | _REQUIRED_FINANCE_TOOL_KEYS | _REQUIRED_CORE_TOOL_KEYS
        )
        disabled_descriptor_keys = {
            descriptor.tool_key
            for descriptor in disabled_runtime_registry.get_execution_descriptors(
                requested_descriptor_keys
            )
        }

    assert not _DIGITAL_ORACLE_TOOL_KEYS & disabled_catalog_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= disabled_catalog_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= disabled_catalog_keys
    assert not _DIGITAL_ORACLE_TOOL_KEYS & disabled_runtime_keys
    assert _REQUIRED_FINANCE_TOOL_KEYS <= disabled_runtime_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= disabled_runtime_keys
    assert disabled_descriptor_keys == _REQUIRED_FINANCE_TOOL_KEYS | _REQUIRED_CORE_TOOL_KEYS


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}


def test_tool_catalog_hides_disabled_extension_tools_and_validation_stays_artifact_only(
    client: TestClient,
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert response.status_code == 200, response.json()

    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200, tools_response.json()
    tools_body = cast(dict[str, object], tools_response.json())
    visible_items = cast(list[dict[str, object]], tools_body["items"])
    visible_keys = {str(item["key"]) for item in visible_items}
    assert not visible_keys & set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS)
    assert _DIGITAL_ORACLE_TOOL_KEYS <= visible_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= visible_keys

    manifest_source = _valid_manifest_source()
    validation_response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": manifest_source},
    )
    assert validation_response.status_code == 200, validation_response.json()
    body = cast(dict[str, object], validation_response.json())
    metadata = cast(dict[str, object], body["metadata"])
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert diagnostics == []
    assert metadata["key"] == "tradingagents_research"
    assert body["packageDefinition"] is not None
    assert body["compiledPlan"] is not None

    created = client.post("/api/workflow-packages", json={"manifestSource": manifest_source})
    assert created.status_code == 201, created.json()
    preflight = client.post(f"/api/workflow-packages/{created.json()['id']}/preflight")
    assert preflight.status_code == 200, preflight.json()
