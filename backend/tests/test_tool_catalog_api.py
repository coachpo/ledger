from __future__ import annotations

from collections.abc import Callable
from datetime import date
from importlib import import_module
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import ToolCatalogValidationError, get_default_tool_catalog
from app.agents.runtime_tools import get_default_runtime_tool_registry
from app.agents.runtime_tools.memory import (
    MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MEMORY_WRITE_OPENAI_FUNCTION_NAME,
)
from app.agents.runtime_tools.types import RuntimeToolWarning
from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_SPECS
from app.extensions.signaldeck_digital_oracle.ownership import (
    DIGITAL_ORACLE_EXTENSION_KEY,
    DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES,
    DIGITAL_ORACLE_RUNTIME_TOOL_KEYS,
)
from app.extensions.signaldeck_digital_oracle.provider_inventory import (
    DEFERRED_PROVIDER_INVENTORY,
    IN_SCOPE_PROVIDER_INVENTORY,
    NO_NEW_RUNTIME_KEYS_REGISTERED,
    RATES_LOOKUP_DEFERRED_TOOL_KEY,
)
from app.extensions.signaldeck_digital_oracle.runtime_types import (
    NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS,
    RuntimeMarketSentimentLookupResult,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFilingsLookupResult,
)
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.schemas.memory import MEMORY_CORE_RUNTIME_TOOL_KEYS
from app.services.extension_service import ExtensionService

_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS = (
    "signaldeck.prediction_markets.lookup",
    "signaldeck.sec_filings.lookup",
    "signaldeck.market_sentiment.lookup",
)
_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES = (
    "signaldeck_prediction_markets_lookup",
    "signaldeck_sec_filings_lookup",
    "signaldeck_market_sentiment_lookup",
)
_DIGITAL_ORACLE_TOOL_KEYS = set(DIGITAL_ORACLE_RUNTIME_TOOL_KEYS)
_FINANCE_PRICE_HISTORY_TOOL_KEYS = {
    "signaldeck.market_data.history_lookup",
    "signaldeck.market_data.ohlcv_lookup",
}
_REQUIRED_FINANCE_TOOL_KEYS = {
    "signaldeck.market_data.quote_lookup",
    "signaldeck.reports.lookup",
    *_FINANCE_PRICE_HISTORY_TOOL_KEYS,
}
_REQUIRED_CORE_TOOL_KEYS = set(MEMORY_CORE_RUNTIME_TOOL_KEYS)
_DEFERRED_DIGITAL_ORACLE_TOOL_KEYS = {
    "signaldeck.rates.lookup",
    "signaldeck.macro.lookup",
    "signaldeck.derivatives.lookup",
    "signaldeck.crypto.lookup",
    "signaldeck.cftc.lookup",
    "signaldeck.web.lookup",
    "signaldeck.price_history.lookup",
}


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


def _warning_payload() -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="provider_unavailable",
        message="Fixture provider is unavailable.",
        details={"provider": "fixture", "operation": "contract_freeze"},
    )


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

    assert DIGITAL_ORACLE_RUNTIME_TOOL_KEYS == _EXPECTED_DIGITAL_ORACLE_TOOL_KEYS
    assert NATIVE_RUNTIME_DIGITAL_ORACLE_TOOL_KEYS == _EXPECTED_DIGITAL_ORACLE_TOOL_KEYS
    assert DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES == (_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES)
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_server_declared_keys
    assert set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS) == finance_runtime_keys
    assert set(FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES) == finance_runtime_function_names
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= finance_server_declared_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS <= finance_runtime_keys
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert _FINANCE_PRICE_HISTORY_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)
    assert set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS) == digital_oracle_server_declared_keys
    assert set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS) == digital_oracle_runtime_keys
    assert set(_EXPECTED_DIGITAL_ORACLE_OPENAI_FUNCTION_NAMES) == (
        digital_oracle_runtime_function_names
    )
    assert _DEFERRED_DIGITAL_ORACLE_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert _DEFERRED_DIGITAL_ORACLE_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)
    assert _REQUIRED_CORE_TOOL_KEYS <= core_server_declared_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= core_runtime_keys
    assert _REQUIRED_CORE_TOOL_KEYS.isdisjoint(finance_server_declared_keys)
    assert _REQUIRED_CORE_TOOL_KEYS.isdisjoint(digital_oracle_server_declared_keys)
    assert finance_server_declared_keys.isdisjoint(digital_oracle_server_declared_keys)


def test_digital_oracle_runtime_response_aliases_and_warnings_are_stable() -> None:
    warning = _warning_payload()
    prediction_markets = RuntimePredictionMarketsLookupResult(
        query="election markets",
        events=[],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    sec_filings = RuntimeSecFilingsLookupResult(
        ticker="AAPL",
        filings=[],
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    market_sentiment = RuntimeMarketSentimentLookupResult(
        indicator="fear_greed",
        as_of_date=date(2026, 6, 7),
        provider="fear_greed",
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)

    assert set(prediction_markets) == {"toolKey", "query", "events", "warnings"}
    assert prediction_markets["toolKey"] == "signaldeck.prediction_markets.lookup"
    assert set(sec_filings) == {
        "toolKey",
        "ticker",
        "cik",
        "entityName",
        "filings",
        "warnings",
    }
    assert sec_filings["toolKey"] == "signaldeck.sec_filings.lookup"
    assert set(market_sentiment) == {
        "toolKey",
        "indicator",
        "asOfDate",
        "provider",
        "score",
        "label",
        "previousClose",
        "weekAgo",
        "monthAgo",
        "yearAgo",
        "sourceUrl",
        "warnings",
    }
    assert market_sentiment["toolKey"] == "signaldeck.market_sentiment.lookup"
    for payload in (prediction_markets, sec_filings, market_sentiment):
        assert payload["warnings"] == [
            {
                "code": "provider_unavailable",
                "message": "Fixture provider is unavailable.",
                "details": {"provider": "fixture", "operation": "contract_freeze"},
            }
        ]


def test_digital_oracle_upstream_provider_inventory_freezes_migration_scope(
    client: TestClient,
) -> None:
    api_tool_keys = _api_tool_keys(client)
    runtime_specs = get_default_runtime_tool_registry().list_specs()
    digital_oracle_runtime_keys = {
        spec.key
        for spec in runtime_specs
        if spec.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    }
    in_scope_by_provider = {item.upstream_provider: item for item in IN_SCOPE_PROVIDER_INVENTORY}
    deferred_modules_by_family = {
        item.capability_family: {
            module.rsplit(".", maxsplit=1)[-1]
            for module in (
                provider.upstream_module
                for provider in DEFERRED_PROVIDER_INVENTORY
                if provider.capability_family == item.capability_family
            )
        }
        for item in DEFERRED_PROVIDER_INVENTORY
    }
    deferred_tool_keys = {
        item.signaldeck_tool_key
        for item in DEFERRED_PROVIDER_INVENTORY
        if item.signaldeck_tool_key is not None
    }

    assert set(in_scope_by_provider) == {
        "PolymarketProvider",
        "KalshiProvider",
        "EdgarProvider",
        "FearGreedProvider",
        "methodology/package patterns",
    }
    assert in_scope_by_provider["PolymarketProvider"].signaldeck_tool_key == (
        "signaldeck.prediction_markets.lookup"
    )
    assert in_scope_by_provider["KalshiProvider"].signaldeck_tool_key == (
        "signaldeck.prediction_markets.lookup"
    )
    assert in_scope_by_provider["EdgarProvider"].signaldeck_tool_key == (
        "signaldeck.sec_filings.lookup"
    )
    assert in_scope_by_provider["FearGreedProvider"].signaldeck_tool_key == (
        "signaldeck.market_sentiment.lookup"
    )
    assert in_scope_by_provider["methodology/package patterns"].signaldeck_tool_key is None
    assert in_scope_by_provider["methodology/package patterns"].capability_family == (
        "Workflow Package methodology"
    )
    assert deferred_modules_by_family == {
        "rates/macro": {"treasury", "bis", "worldbank", "cme_fedwatch"},
        "derivatives/crypto": {"deribit", "coingecko", "yahoo", "yfinance_provider"},
        "CFTC positioning": {"cftc"},
        "generic web": {"web"},
        "price/history": {"prices", "stooq"},
    }
    assert NO_NEW_RUNTIME_KEYS_REGISTERED is True
    assert deferred_tool_keys == {RATES_LOOKUP_DEFERRED_TOOL_KEY}
    assert RATES_LOOKUP_DEFERRED_TOOL_KEY == "signaldeck.rates.lookup"
    assert _DIGITAL_ORACLE_TOOL_KEYS == set(_EXPECTED_DIGITAL_ORACLE_TOOL_KEYS)
    assert _DEFERRED_DIGITAL_ORACLE_TOOL_KEYS.isdisjoint(api_tool_keys)
    assert _DEFERRED_DIGITAL_ORACLE_TOOL_KEYS.isdisjoint(digital_oracle_runtime_keys)


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
    history_tool = tools_by_key["signaldeck.market_data.history_lookup"]
    ohlcv_tool = tools_by_key["signaldeck.market_data.ohlcv_lookup"]
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
    assert history_tool == {
        "key": "signaldeck.market_data.history_lookup",
        "displayName": "Market Data History Lookup",
        "description": "Read trusted historical market series from server-owned integrations.",
    }
    assert ohlcv_tool == {
        "key": "signaldeck.market_data.ohlcv_lookup",
        "displayName": "OHLCV Lookup",
        "description": "Read server-owned OHLCV market data for supported symbols and ranges.",
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
        history_tool,
        ohlcv_tool,
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


def test_api_tools_keep_core_memory_visible_when_bundled_extensions_are_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    for extension_key in (FINANCE_WORKSPACE_EXTENSION_KEY, DIGITAL_ORACLE_EXTENSION_KEY):
        response = client.patch(f"/api/extensions/{extension_key}", json={"enabled": False})
        assert response.status_code == 200, response.json()

    tools_response = client.get("/api/tools")
    assert tools_response.status_code == 200, tools_response.json()
    body = cast(dict[str, object], tools_response.json())
    items = cast(list[dict[str, object]], body["items"])
    visible_keys = {str(item["key"]) for item in items}
    assert visible_keys == _REQUIRED_CORE_TOOL_KEYS
    assert all(set(item) == {"key", "displayName", "description"} for item in items)

    with session_factory() as session:
        service = ExtensionService(session)
        catalog_keys = {tool.key for tool in service.get_tool_catalog().list_registered_tools()}
        runtime_registry = service.get_runtime_tool_registry()
        runtime_keys = {spec.key for spec in runtime_registry.list_enabled_specs()}
        runtime_function_names = {
            str(tool["name"])
            for tool in runtime_registry.get_openai_tools(_REQUIRED_CORE_TOOL_KEYS)
        }

    assert catalog_keys == _REQUIRED_CORE_TOOL_KEYS
    assert runtime_keys == _REQUIRED_CORE_TOOL_KEYS
    assert runtime_function_names == {
        MEMORY_WRITE_OPENAI_FUNCTION_NAME,
        MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    }


def test_tools_catalog_route_is_get_only(client: TestClient) -> None:
    response = client.post("/api/tools", json={})

    assert response.status_code == 405
    openapi = cast(dict[str, object], client.get("/openapi.json").json())
    paths = cast(dict[str, object], openapi["paths"])
    schemas = cast(
        dict[str, dict[str, object]],
        cast(dict[str, object], openapi["components"])["schemas"],
    )
    assert "/api/tools" in paths
    tools_path = cast(dict[str, object], paths["/api/tools"])
    assert set(tools_path) == {"get"}

    get_operation = cast(dict[str, object], tools_path["get"])
    get_responses = cast(dict[str, object], get_operation["responses"])
    ok_response = cast(dict[str, object], get_responses["200"])
    ok_content = cast(dict[str, object], ok_response["content"])
    ok_json = cast(dict[str, object], ok_content["application/json"])
    assert ok_json["schema"] == {"$ref": "#/components/schemas/ToolCatalogListRead"}
    assert set(cast(dict[str, object], schemas["ToolCatalogItemRead"]["properties"])) == {
        "key",
        "displayName",
        "description",
    }
    list_properties = cast(dict[str, object], schemas["ToolCatalogListRead"]["properties"])
    assert set(list_properties) == {"items"}
    assert cast(list[str], schemas["ToolCatalogListRead"]["required"]) == ["items"]


def test_tool_catalog_hides_disabled_extension_tools_and_validation_stays_artifact_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
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
    assert not visible_keys & _FINANCE_PRICE_HISTORY_TOOL_KEYS
    assert _DIGITAL_ORACLE_TOOL_KEYS <= visible_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= visible_keys

    with session_factory() as session:
        disabled_service = ExtensionService(session)
        disabled_catalog_keys = {
            tool.key for tool in disabled_service.get_tool_catalog().list_registered_tools()
        }
        disabled_runtime_keys = {
            spec.key for spec in disabled_service.get_runtime_tool_registry().list_enabled_specs()
        }

    assert not disabled_catalog_keys & _FINANCE_PRICE_HISTORY_TOOL_KEYS
    assert not disabled_runtime_keys & _FINANCE_PRICE_HISTORY_TOOL_KEYS
    assert _DIGITAL_ORACLE_TOOL_KEYS <= disabled_catalog_keys
    assert _DIGITAL_ORACLE_TOOL_KEYS <= disabled_runtime_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= disabled_catalog_keys
    assert _REQUIRED_CORE_TOOL_KEYS <= disabled_runtime_keys

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
    preflight = client.post(
        f"/api/workflow-packages/{created.json()['id']}/preflight",
        json={"workflowKey": None, "parameters": {"ticker": "AAPL"}},
    )
    assert preflight.status_code == 200, preflight.json()
