from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp import McpClientBoundary, McpConnectionTestResult
from app.api.dependencies import get_mcp_connection_tester, get_quote_provider
from app.db.session import init_db, validate_supported_database_engine
from app.models.market_quote import MarketQuote
from app.models.symbol_name_cache import SymbolNameCache
from app.services.quote_provider import (
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderQuote,
    QuoteProviderError,
)
from app.services.run_service import RunService
from tests.agent_platform_stock_analysis import (
    STOCK_ANALYSIS_MCP_SERVER_KEY,
    STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
    STOCK_ANALYSIS_SKILL_KEY,
    STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
    TRADING_DECISION_SCHEMA_KEY,
    build_stock_analysis_note,
    build_trading_decision,
    make_stock_analysis_stub_invoke,
    stock_analysis_agent_payload,
    stock_analysis_note_schema,
    stock_analysis_synthesizer_payload,
    stock_analysis_workflow_payload,
    trading_decision_schema,
)

UTC_TZ = timezone.utc  # noqa: UP017
_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def _assert_logfire_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_ID_PATTERN.fullmatch(value) is not None


class UnsupportedEngine:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = DefaultDialect()
        self.dialect.name = dialect_name


def portfolio_slug_for_name(name: str) -> str:
    return "_".join(name.strip().lower().replace("-", " ").split()) or "portfolio"


def create_portfolio(
    client: TestClient,
    *,
    name: str = "Core Portfolio",
    slug: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/portfolios",
        json={
            "name": name,
            "slug": slug or portfolio_slug_for_name(name),
            "description": f"{name} description",
            "baseCurrency": "USD",
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_balance(
    client: TestClient,
    portfolio_id: str,
    *,
    label: str = "Cash",
    amount: str = "1000.00",
    operation_type: str = "DEPOSIT",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/balances",
        json={"label": label, "amount": amount, "operationType": operation_type},
    )
    assert response.status_code == 201
    return response.json()


def create_position(
    client: TestClient,
    portfolio_id: str,
    *,
    symbol: str = "AAPL",
    quantity: str = "10",
    average_cost: str = "185.50",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": symbol,
            "name": f"{symbol} Holdings",
            "quantity": quantity,
            "averageCost": average_cost,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_template(
    client: TestClient,
    *,
    name: str = "Daily Summary",
    content: str = "# Summary\n\n{{portfolios}}",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_output_schema(
    client: TestClient,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post("/api/output-schemas", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def activate_output_schema(client: TestClient, schema_id: int | str) -> dict[str, object]:
    response = client.post(f"/api/output-schemas/{schema_id}/activate")
    assert response.status_code == 200, response.json()
    return response.json()


class _FakeMcpConnectionTester:
    def __init__(self, *, ok: bool = True, message: str = "connection ok") -> None:
        self.ok = ok
        self.message = message
        self.boundaries: list[McpClientBoundary] = []

    def test(self, boundary: McpClientBoundary) -> McpConnectionTestResult:
        self.boundaries.append(boundary)
        return McpConnectionTestResult(ok=self.ok, message=self.message)


def create_skill(
    client: TestClient,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post("/api/skills", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def activate_skill(client: TestClient, skill_id: int | str) -> dict[str, object]:
    response = client.post(f"/api/skills/{skill_id}/activate")
    assert response.status_code == 200, response.json()
    return response.json()


def create_mcp_server(
    client: TestClient,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post("/api/mcp-servers", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def activate_mcp_server(client: TestClient, server_id: int | str) -> dict[str, object]:
    response = client.post(f"/api/mcp-servers/{server_id}/activate")
    assert response.status_code == 200, response.json()
    return response.json()


def mcp_stdio_payload(
    *,
    key: str,
    name: str,
    description: str = "",
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "key": key,
        "name": name,
        "description": description,
        "enabled": enabled,
        "transport": "stdio",
        "command": command,
        "args": args,
        "env": env or {},
    }


def mcp_http_sse_payload(
    *,
    key: str,
    name: str,
    description: str = "",
    url: str,
    headers: dict[str, str] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "key": key,
        "name": name,
        "description": description,
        "enabled": enabled,
        "transport": "http-sse",
        "url": url,
        "headers": headers or {},
    }


def create_agent(
    client: TestClient,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post("/api/agents", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def create_workflow(
    client: TestClient,
    *,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post("/api/workflows", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def _wait_for_agent_platform_run(
    client: TestClient,
    run_id: int,
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.json()
        body = response.json()
        assert isinstance(body, dict)
        last_body = body
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    assert last_body is not None
    raise AssertionError(f"Run {run_id} did not finish in time: {last_body}")


def _seed_stock_analysis_platform(
    client: TestClient,
    *,
    optional_agents: set[str] | None = None,
) -> None:
    created_note_schema = create_output_schema(
        client,
        payload={
            "key": STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
            "name": "Stock Analysis Note",
            "jsonSchema": stock_analysis_note_schema(),
        },
    )
    activate_output_schema(client, cast(int, created_note_schema["id"]))
    created_decision_schema = create_output_schema(
        client,
        payload={
            "key": TRADING_DECISION_SCHEMA_KEY,
            "name": "TradingDecision",
            "jsonSchema": trading_decision_schema(),
        },
    )
    activate_output_schema(client, cast(int, created_decision_schema["id"]))
    created_skill = create_skill(
        client,
        payload={
            "key": STOCK_ANALYSIS_SKILL_KEY,
            "name": "Stock Analysis Tools",
            "toolDefinitions": [
                {"tool": "ledger.market_data.quote_lookup"},
                {"tool": "ledger.market_data.history_lookup"},
            ],
        },
    )
    activate_skill(client, cast(int, created_skill["id"]))
    created_mcp_server = create_mcp_server(
        client,
        payload=mcp_http_sse_payload(
            key=STOCK_ANALYSIS_MCP_SERVER_KEY,
            name="Stock Analysis Data",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer secret-token"},
        ),
    )
    activate_mcp_server(client, cast(int, created_mcp_server["id"]))
    for agent_key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS:
        create_agent(client, payload=stock_analysis_agent_payload(agent_key))
    create_agent(
        client,
        payload=stock_analysis_synthesizer_payload(optional_agents=optional_agents or set()),
    )


def test_agent_platform_routes_mount_under_api_without_v3_shims(app: FastAPI) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert {
        "/api/agents",
        "/api/agents/{agent_id}",
        "/api/agents/{agent_id}/test-panel",
        "/api/skills",
        "/api/skills/{skill_id}",
        "/api/skills/{skill_id}/activate",
        "/api/mcp-servers",
        "/api/mcp-servers/{server_id}",
        "/api/mcp-servers/{server_id}/activate",
        "/api/mcp-servers/{server_id}/connection-test",
        "/api/output-schemas",
        "/api/output-schemas/{schema_id}",
        "/api/output-schemas/{schema_id}/activate",
        "/api/workflows",
        "/api/workflows/{workflow_id}",
        "/api/workflows/{workflow_id}/runs",
        "/api/runs",
        "/api/runs/{run_id}",
    } <= route_paths
    assert not any(path.startswith("/api/v3") for path in route_paths)


@pytest.mark.parametrize(
    "path",
    [
        "/api/agents",
        "/api/skills",
        "/api/mcp-servers",
        "/api/output-schemas",
        "/api/workflows",
        "/api/runs",
    ],
)
def test_agent_platform_routes_list_endpoints_return_camel_case_contracts(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 200, response.json()
    assert response.json() == {"items": []}
    assert "total_count" not in response.json()


def test_agent_platform_routes_validation_errors_preserve_shared_error_envelope(
    client: TestClient,
) -> None:
    response = client.get("/api/workflows/not-an-int")

    assert response.status_code == 422, response.json()
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["details"] == [
        {
            "field": "workflow_id",
            "issue": body["details"][0]["issue"],
        }
    ]
    assert "valid integer" in body["details"][0]["issue"]


def test_agent_platform_output_schema_save_round_trips_builder_json_and_pins_registry_refs(
    client: TestClient,
) -> None:
    shared_action = create_output_schema(
        client,
        payload={
            "key": "action_type",
            "kind": "shared",
            "name": "Action Type",
            "jsonSchema": {
                "type": "string",
                "enum": ["buy", "hold", "sell"],
            },
        },
    )
    activated_action = activate_output_schema(client, str(shared_action["id"]))
    assert activated_action["status"] == "published"

    created = create_output_schema(
        client,
        payload={
            "key": "trading_decision",
            "name": "Trading Decision",
            "description": "Decision payload",
            "builder": {
                "kind": "object",
                "fields": [
                    {"name": "summary", "required": True, "schema": {"kind": "string"}},
                    {
                        "name": "action",
                        "required": True,
                        "schema": {"kind": "ref", "schemaKey": "action_type"},
                    },
                ],
            },
            "jsonSchema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "action": {"$ref": "registry://action_type"},
                },
                "required": ["summary", "action"],
            },
        },
    )

    assert created["status"] == "draft"
    assert created["kind"] == "standalone"
    assert created["registryRefs"] == ["action_type"]

    created_json_schema = cast(dict[str, object], created["jsonSchema"])
    created_properties = cast(dict[str, object], created_json_schema["properties"])
    created_action_property = cast(dict[str, object], created_properties["action"])
    assert created_json_schema["additionalProperties"] is False
    assert created_action_property["$ref"] == "registry://action_type@1"

    created_builder = cast(dict[str, object], created["builder"])
    created_fields = cast(list[dict[str, object]], created_builder["fields"])
    action_field = next(field for field in created_fields if field["name"] == "action")
    action_field_schema = cast(dict[str, object], action_field["schema"])
    assert action_field_schema["kind"] == "ref"
    assert action_field_schema["schemaKey"] == "action_type"
    assert action_field_schema["schemaVersion"] == 1

    fetched = client.get(f"/api/output-schemas/{created['id']}")
    assert fetched.status_code == 200

    fetched_body = fetched.json()
    fetched_json_schema = cast(dict[str, object], fetched_body["jsonSchema"])
    assert cast(dict[str, object], fetched_json_schema["properties"]) == created_properties
    assert sorted(cast(list[str], fetched_json_schema["required"])) == sorted(
        cast(list[str], created_json_schema["required"])
    )
    assert fetched_json_schema["additionalProperties"] is False

    fetched_builder = cast(dict[str, object], fetched_body["builder"])
    fetched_fields = cast(list[dict[str, object]], fetched_builder["fields"])
    fetched_field_map = {field["name"]: field for field in fetched_fields}
    created_field_map = {field["name"]: field for field in created_fields}
    assert fetched_builder["kind"] == created_builder["kind"]
    assert fetched_builder["allowAdditionalProperties"] is False
    assert fetched_field_map == created_field_map


@pytest.mark.parametrize(
    ("json_schema", "expected_field", "expected_issue"),
    [
        (
            {"allOf": [{"type": "string"}, {"type": "integer"}]},
            "jsonSchema.allOf",
            "allOf is not supported",
        ),
        (
            {
                "type": "object",
                "properties": {},
                "patternProperties": {"^x": {"type": "string"}},
            },
            "jsonSchema.patternProperties",
            "patternProperties is not supported",
        ),
        (
            {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            "jsonSchema.anyOf",
            "Undiscriminated unions are not supported",
        ),
    ],
)
def test_agent_platform_output_schema_invalid_unsupported_keywords_return_field_errors(
    client: TestClient,
    json_schema: dict[str, object],
    expected_field: str,
    expected_issue: str,
) -> None:
    response = client.post(
        "/api/output-schemas",
        json={
            "key": "invalid_schema",
            "name": "Invalid Schema",
            "jsonSchema": json_schema,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert any(
        detail["field"] == expected_field and expected_issue in detail["issue"]
        for detail in body["details"]
    )


def test_agent_platform_skill_crud_routes_resolve_server_declared_tool_metadata(
    client: TestClient,
) -> None:
    created = create_skill(
        client,
        payload={
            "key": "market_research",
            "name": "Market Research",
            "description": "Server-declared research toolset.",
            "toolDefinitions": [
                {"tool": "ledger.market_data.quote_lookup"},
                {"tool": "ledger.reports.lookup"},
            ],
        },
    )

    assert created["status"] == "draft"
    assert created["version"] == 1
    created_tool_definitions = cast(list[dict[str, object]], created["toolDefinitions"])
    assert [item["tool"] for item in created_tool_definitions] == [
        "ledger.market_data.quote_lookup",
        "ledger.reports.lookup",
    ]
    assert created_tool_definitions[0]["displayName"] == "Market Data Quote Lookup"

    update_response = client.patch(
        f"/api/skills/{created['id']}",
        json={
            "name": "Market Research v2",
            "toolDefinitions": [
                {"tool": "ledger.market_data.history_lookup"},
                {"tool": "ledger.reports.lookup"},
            ],
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["name"] == "Market Research v2"
    assert [item["tool"] for item in updated["toolDefinitions"]] == [
        "ledger.market_data.history_lookup",
        "ledger.reports.lookup",
    ]

    original_detail = client.get(f"/api/skills/{created['id']}")
    assert original_detail.status_code == 200, original_detail.json()
    assert original_detail.json()["status"] == "archived"
    assert original_detail.json()["version"] == 1

    get_response = client.get(f"/api/skills/{updated['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json() == updated

    list_response = client.get("/api/skills", params={"status": "draft"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [updated]

    activated = activate_skill(client, str(updated["id"]))
    assert activated["status"] == "published"

    archive_response = client.delete(f"/api/skills/{updated['id']}")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "archived"


def test_agent_platform_mcp_crud_routes_and_connection_test(
    client: TestClient,
    app: FastAPI,
) -> None:
    tester = _FakeMcpConnectionTester(message="mcp boundary ok")
    app.dependency_overrides[get_mcp_connection_tester] = lambda: tester

    created = create_mcp_server(
        client,
        payload=mcp_http_sse_payload(
            key="market_data",
            name="Market Data MCP",
            description="Reads trusted market data through HTTP/SSE.",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer secret-token"},
        ),
    )

    assert created["status"] == "draft"
    assert created["version"] == 1
    assert created["key"] == "market_data"
    assert created["name"] == "Market Data MCP"
    assert created["description"] == "Reads trusted market data through HTTP/SSE."
    assert created["enabled"] is True
    assert created["transport"] == "http-sse"
    assert created["url"] == "https://example.com/mcp"
    assert created["headers"] == {"Authorization": "Bearer secret-token"}

    update_response = client.patch(
        f"/api/mcp-servers/{created['id']}",
        json={
            "name": "Market Data MCP",
            "description": "Updated market data MCP.",
            "enabled": True,
            "transport": "http-sse",
            "url": "https://example.com/mcp/v2",
            "headers": {"Authorization": "Bearer secret-token"},
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["key"] == "market_data"
    assert updated["name"] == "Market Data MCP"
    assert updated["description"] == "Updated market data MCP."
    assert updated["enabled"] is True
    assert updated["transport"] == "http-sse"
    assert updated["url"] == "https://example.com/mcp/v2"
    assert updated["headers"] == {"Authorization": "Bearer secret-token"}

    original_detail = client.get(f"/api/mcp-servers/{created['id']}")
    assert original_detail.status_code == 200, original_detail.json()
    assert original_detail.json()["status"] == "archived"
    assert original_detail.json()["version"] == 1

    get_response = client.get(f"/api/mcp-servers/{updated['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json() == updated

    list_response = client.get("/api/mcp-servers", params={"transport": "http-sse"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [
        {
            "id": updated["id"],
            "key": "market_data",
            "version": 2,
            "status": "draft",
            "name": "Market Data MCP",
            "description": "Updated market data MCP.",
            "transport": "http-sse",
            "enabled": True,
        }
    ]

    activated = activate_mcp_server(client, str(updated["id"]))
    assert activated["status"] == "published"

    connection_test_response = client.post(f"/api/mcp-servers/{updated['id']}/connection-test")
    assert connection_test_response.status_code == 200, connection_test_response.json()
    connection_test = connection_test_response.json()
    assert connection_test["ok"] is True
    assert connection_test["message"] == "mcp boundary ok"
    assert connection_test["boundary"] == {
        "transport": "http-sse",
        "command": None,
        "url": "https://example.com/mcp/v2",
        "headerNames": ["Authorization"],
        "envKeys": [],
        "enabled": True,
    }
    assert tester.boundaries[-1].headers == {"Authorization": "Bearer secret-token"}

    archive_response = client.delete(f"/api/mcp-servers/{updated['id']}")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "archived"


def test_agent_platform_mcp_patch_rejects_key_changes(
    client: TestClient,
) -> None:
    created = create_mcp_server(
        client,
        payload={
            "key": "market_data",
            "name": "Market Data MCP",
            "enabled": True,
            "transport": "http-sse",
            "url": "https://example.com/mcp",
            "headers": {},
        },
    )

    response = client.patch(
        f"/api/mcp-servers/{created['id']}",
        json={
            "key": "renamed_market_data",
            "name": "Market Data MCP",
            "enabled": True,
            "transport": "http-sse",
            "url": "https://example.com/mcp/v2",
            "headers": {},
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    details = response.json()["details"]
    assert any("key" in detail["field"] for detail in details)
    assert any(
        "command" in detail["issue"].lower() or "extra inputs" in detail["issue"].lower()
        for detail in details
    )


def test_agent_platform_mcp_hyphenated_stdio_key_is_accepted_and_reusable(
    client: TestClient,
) -> None:
    created = create_mcp_server(
        client,
        payload=mcp_stdio_payload(
            key="sequential-thinking",
            name="Sequential Thinking",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        ),
    )
    assert created["key"] == "sequential-thinking"
    assert created["name"] == "Sequential Thinking"
    assert created["description"] == ""
    assert created["enabled"] is True
    assert created["transport"] == "stdio"
    assert created["command"] == "npx"
    assert created["args"] == ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    assert created["env"] == {}

    activated_server = activate_mcp_server(client, cast(int, created["id"]))
    seeded = _seed_agent_platform_agent_dependencies(client)
    agent = create_agent(
        client,
        payload={
            "key": "hyphenated_mcp_agent",
            "name": "Hyphenated MCP Agent",
            "description": "Uses a hyphenated MCP server key.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Summarize the market state.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
                "additionalProperties": False,
            },
            "outputSchemaKey": seeded["outputSchema"]["key"],
            "skills": [{"skillKey": seeded["skill"]["key"]}],
            "mcpServers": [{"mcpServerKey": activated_server["key"]}],
            "budgetUsd": "0.50000000",
            "streaming": False,
        },
    )
    assert cast(list[dict[str, object]], agent["mcpServers"])[0]["key"] == "sequential-thinking"


def test_agent_platform_mcp_invalid_transport_and_auth_return_field_errors(
    client: TestClient,
) -> None:
    invalid_transport = client.post(
        "/api/mcp-servers",
        json={
            "key": "broken_stdio",
            "name": "Broken Stdio",
            "transport": "stdio",
            "url": "https://example.com/mcp",
        },
    )
    assert invalid_transport.status_code == 422, invalid_transport.json()
    assert invalid_transport.json()["code"] == "validation_error"
    invalid_transport_details = invalid_transport.json()["details"]
    assert any("command" in detail["issue"].lower() for detail in invalid_transport_details)

    invalid_headers = client.post(
        "/api/mcp-servers",
        json={
            "key": "broken_headers",
            "name": "Broken Headers",
            "transport": "http-sse",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": ""},
        },
    )
    assert invalid_headers.status_code == 422, invalid_headers.json()
    assert invalid_headers.json()["code"] == "validation_error"
    assert any("headers" in detail["issue"].lower() for detail in invalid_headers.json()["details"])


def _seed_agent_platform_agent_dependencies(client: TestClient) -> dict[str, dict[str, object]]:
    created_output_schema = create_output_schema(
        client,
        payload={
            "key": "decision_schema",
            "name": "Decision Schema",
            "jsonSchema": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    )
    output_schema = activate_output_schema(client, cast(int, created_output_schema["id"]))

    created_skill = create_skill(
        client,
        payload={
            "key": "market_research",
            "name": "Market Research",
            "toolDefinitions": [{"tool": "ledger.market_data.quote_lookup"}],
        },
    )
    skill = activate_skill(client, cast(int, created_skill["id"]))

    created_mcp_server = create_mcp_server(
        client,
        payload=mcp_http_sse_payload(
            key="market_data",
            name="Market Data MCP",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer secret-token"},
        ),
    )
    mcp_server = activate_mcp_server(client, cast(int, created_mcp_server["id"]))
    return {
        "outputSchema": output_schema,
        "skill": skill,
        "mcpServer": mcp_server,
    }


def test_agent_platform_agent_create_pins_explicit_versions_and_returns_resolved_dependencies(
    client: TestClient,
) -> None:
    dependencies = _seed_agent_platform_agent_dependencies(client)

    created = create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
            "temperature": 0.2,
            "maxToolRounds": 2,
            "budgetUsd": "1.25000000",
            "streaming": True,
        },
    )

    assert created["version"] == 1
    assert created["status"] == "published"
    assert cast(dict[str, object], created["inputSchema"])["additionalProperties"] is False
    assert (
        cast(dict[str, object], created["outputSchema"])["id"] == dependencies["outputSchema"]["id"]
    )
    assert cast(dict[str, object], created["outputSchema"])["version"] == 1
    assert cast(list[dict[str, object]], created["skills"])[0]["id"] == dependencies["skill"]["id"]
    assert cast(list[dict[str, object]], created["skills"])[0]["version"] == 1
    assert (
        cast(list[dict[str, object]], created["mcpServers"])[0]["id"]
        == dependencies["mcpServer"]["id"]
    )
    assert cast(list[dict[str, object]], created["mcpServers"])[0]["boundary"] == {
        "transport": "http-sse",
        "command": None,
        "url": "https://example.com/mcp",
        "headerNames": ["Authorization"],
        "envKeys": [],
        "enabled": True,
    }

    get_response = client.get(f"/api/agents/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["version"] == 1

    list_response = client.get("/api/agents", params={"status": "published"})
    assert list_response.status_code == 200, list_response.json()
    assert [item["id"] for item in list_response.json()["items"]] == [created["id"]]


def test_agent_platform_agent_update_version_creates_new_immutable_row(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    created = create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    output_schema_v2 = create_output_schema(
        client,
        payload={
            "key": "decision_schema",
            "name": "Decision Schema v2",
            "jsonSchema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["summary", "confidence"],
            },
        },
    )
    skill_v2 = create_skill(
        client,
        payload={
            "key": "market_research",
            "name": "Market Research v2",
            "toolDefinitions": [{"tool": "ledger.market_data.history_lookup"}],
        },
    )
    mcp_server_v2 = create_mcp_server(
        client,
        payload=mcp_stdio_payload(
            key="market_data",
            name="Market Data MCP v2",
            command="python",
            args=["-m", "ledger_market_data"],
        ),
    )

    update_response = client.post(
        f"/api/agents/{created['id']}",
        json={
            "name": "Research Agent v2",
            "description": "Uses explicit pinned dependency versions.",
            "model": "openai:gpt-5.4",
            "systemPrompt": "Use the pinned dependencies and return the richer schema.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker", "horizonDays"],
            },
            "outputSchemaKey": "decision_schema",
            "outputSchemaVersion": 2,
            "skills": [{"skillKey": "market_research", "skillVersion": 2}],
            "mcpServers": [{"mcpServerKey": "market_data", "mcpServerVersion": 2}],
            "temperature": 0.4,
            "maxToolRounds": 3,
            "budgetUsd": "2.50000000",
            "streaming": False,
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()

    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["status"] == "published"
    assert updated["name"] == "Research Agent v2"
    assert cast(dict[str, object], updated["outputSchema"])["id"] == output_schema_v2["id"]
    assert cast(dict[str, object], updated["outputSchema"])["version"] == 2
    assert cast(list[dict[str, object]], updated["skills"])[0]["id"] == skill_v2["id"]
    assert cast(list[dict[str, object]], updated["skills"])[0]["version"] == 2
    assert cast(list[dict[str, object]], updated["mcpServers"])[0]["id"] == mcp_server_v2["id"]
    assert cast(list[dict[str, object]], updated["mcpServers"])[0]["transport"] == "stdio"

    previous_version = client.get(f"/api/agents/{updated['id']}", params={"version": 1})
    assert previous_version.status_code == 200, previous_version.json()
    previous = previous_version.json()
    assert previous["id"] == created["id"]
    assert previous["version"] == 1
    assert previous["status"] == "deprecated"
    assert cast(dict[str, object], previous["outputSchema"])["version"] == 1
    assert cast(list[dict[str, object]], previous["skills"])[0]["version"] == 1
    assert cast(list[dict[str, object]], previous["mcpServers"])[0]["version"] == 1


def test_agent_platform_agent_archive_keeps_pinned_history_resolvable(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    created = create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )
    updated = client.post(
        f"/api/agents/{created['id']}",
        json={
            "name": "Research Agent v2",
            "description": "Version 2 for archive coverage.",
            "model": "openai:gpt-5.4",
            "systemPrompt": "Use version 2 for archive coverage.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )
    assert updated.status_code == 200, updated.json()
    updated_body = updated.json()

    archive_response = client.delete(f"/api/agents/{updated_body['id']}")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "archived"

    current_response = client.get(f"/api/agents/{updated_body['id']}")
    assert current_response.status_code == 200, current_response.json()
    assert current_response.json()["status"] == "archived"
    assert current_response.json()["version"] == 2

    historical_response = client.get(f"/api/agents/{updated_body['id']}", params={"version": 1})
    assert historical_response.status_code == 200, historical_response.json()
    assert historical_response.json()["id"] == created["id"]
    assert historical_response.json()["version"] == 1
    assert historical_response.json()["status"] == "deprecated"

    archived_list = client.get("/api/agents", params={"status": "archived"})
    assert archived_list.status_code == 200, archived_list.json()
    assert [item["id"] for item in archived_list.json()["items"]] == [updated_body["id"]]


def test_agent_platform_agent_invalid_input_schema_returns_field_errors(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)

    response = client.post(
        "/api/agents",
        json={
            "key": "invalid_agent",
            "name": "Invalid Agent",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "This save should fail.",
            "inputSchema": {
                "allOf": [{"type": "object"}, {"type": "string"}],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert any(
        detail["field"] == "inputSchema.allOf" and "allOf is not supported" in detail["issue"]
        for detail in response.json()["details"]
    )


def test_agent_platform_agent_missing_output_schema_returns_field_errors(
    client: TestClient,
) -> None:
    create_skill(
        client,
        payload={
            "key": "market_research",
            "name": "Market Research",
            "toolDefinitions": [{"tool": "ledger.market_data.quote_lookup"}],
        },
    )
    create_mcp_server(
        client,
        payload=mcp_http_sse_payload(
            key="market_data",
            name="Market Data MCP",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer secret-token"},
        ),
    )

    response = client.post(
        "/api/agents",
        json={
            "key": "broken_agent",
            "name": "Broken Agent",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "This save should fail.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "missing_schema",
            "skills": [{"skillKey": "market_research", "skillVersion": 1}],
            "mcpServers": [{"mcpServerKey": "market_data", "mcpServerVersion": 1}],
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"] == [
        {"field": "outputSchemaKey", "issue": "Output schema 'missing_schema' was not found"}
    ]


def test_agent_platform_workflow_create_pins_explicit_versions_and_returns_resolved_structure(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
            "budgetUsd": "1.25000000",
        },
    )

    created = create_workflow(
        client,
        payload={
            "key": "market_review",
            "name": "Market Review",
            "description": "Runs research before producing the final slot output.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {
                                "ticker": {"from": "input", "path": "ticker"},
                            },
                            "optional": False,
                        }
                    ],
                }
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )

    created_steps = cast(list[dict[str, object]], created["steps"])
    step_agents = cast(list[dict[str, object]], created_steps[0]["agents"])
    step_agent = step_agents[0]
    output_spec = cast(dict[str, object], created["outputSpec"])

    assert created["version"] == 1
    assert created["status"] == "published"
    assert cast(dict[str, object], created["inputSchema"])["additionalProperties"] is False
    assert step_agent["agentVersion"] == 1
    assert step_agent["outputSchemaVersion"] == 1
    assert step_agent["budgetUsd"] == "1.25000000"
    assert step_agent["wiring"] == {"ticker": {"from": "input", "path": "ticker"}}
    assert output_spec["kind"] == "slot"
    assert output_spec["stepIndex"] == 1
    assert output_spec["slot"] == "analysis"
    assert output_spec["agentVersion"] == 1
    assert output_spec["outputSchemaVersion"] == 1
    assert created["aggregateBudgetUsd"] == "1.25000000"

    get_response = client.get(f"/api/workflows/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["version"] == 1

    list_response = client.get("/api/workflows", params={"status": "published"})
    assert list_response.status_code == 200, list_response.json()
    assert [item["id"] for item in list_response.json()["items"]] == [created["id"]]


def test_agent_platform_workflow_update_version_pins_current_agent_versions_immutably(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    created_agent = create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
            "budgetUsd": "1.25000000",
        },
    )
    created_workflow = create_workflow(
        client,
        payload={
            "key": "market_review",
            "name": "Market Review",
            "description": "Version one workflow.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {
                                "ticker": {"from": "input", "path": "ticker"},
                            },
                        }
                    ],
                }
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )

    create_output_schema(
        client,
        payload={
            "key": "decision_schema",
            "name": "Decision Schema v2",
            "jsonSchema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["summary", "confidence"],
            },
        },
    )
    update_agent_response = client.post(
        f"/api/agents/{created_agent['id']}",
        json={
            "name": "Research Agent v2",
            "description": "Publishes a richer schema.",
            "model": "openai:gpt-5.4",
            "systemPrompt": "Use the richer output schema.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker", "horizonDays"],
            },
            "outputSchemaKey": "decision_schema",
            "outputSchemaVersion": 2,
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
            "budgetUsd": "2.50000000",
        },
    )
    assert update_agent_response.status_code == 200, update_agent_response.json()

    update_workflow_response = client.post(
        f"/api/workflows/{created_workflow['id']}",
        json={
            "name": "Market Review v2",
            "description": "Pins the currently published agent version.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "horizonDays": {"type": "integer"},
                },
                "required": ["ticker", "horizonDays"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {
                                "ticker": {"from": "input", "path": "ticker"},
                                "horizonDays": {"from": "input", "path": "horizonDays"},
                            },
                        }
                    ],
                }
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )
    assert update_workflow_response.status_code == 200, update_workflow_response.json()
    updated = update_workflow_response.json()

    updated_steps = cast(list[dict[str, object]], updated["steps"])
    updated_step_agents = cast(list[dict[str, object]], updated_steps[0]["agents"])
    updated_step_agent = updated_step_agents[0]
    assert updated["id"] != created_workflow["id"]
    assert updated["version"] == 2
    assert updated["status"] == "published"
    assert updated_step_agent["agentVersion"] == 2
    assert updated_step_agent["outputSchemaVersion"] == 2
    assert updated["aggregateBudgetUsd"] == "2.50000000"

    previous_version = client.get(f"/api/workflows/{updated['id']}", params={"version": 1})
    assert previous_version.status_code == 200, previous_version.json()
    previous = previous_version.json()
    previous_steps = cast(list[dict[str, object]], previous["steps"])
    previous_step_agents = cast(list[dict[str, object]], previous_steps[0]["agents"])
    previous_step_agent = previous_step_agents[0]
    assert previous["id"] == created_workflow["id"]
    assert previous["version"] == 1
    assert previous["status"] == "deprecated"
    assert previous_step_agent["agentVersion"] == 1
    assert previous_step_agent["outputSchemaVersion"] == 1


def test_agent_platform_workflow_wiring_rejects_duplicate_slot_names(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    response = client.post(
        "/api/workflows",
        json={
            "key": "duplicate_slots_workflow",
            "name": "Duplicate Slots Workflow",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        },
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        },
                    ],
                }
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["details"] == [
        {
            "field": "steps[0].agents[1].slot",
            "issue": "Duplicate slot name within the same step",
        }
    ]


def test_agent_platform_workflow_wiring_rejects_unresolved_slots(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    response = client.post(
        "/api/workflows",
        json={
            "key": "missing_slot_workflow",
            "name": "Missing Slot Workflow",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        }
                    ],
                },
                {
                    "index": 2,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "review",
                            "wiring": {
                                "ticker": {
                                    "from": "step",
                                    "stepIndex": 1,
                                    "slot": "missing_slot",
                                }
                            },
                        }
                    ],
                },
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["details"] == [
        {
            "field": "steps[1].agents[0].wiring.ticker",
            "issue": "Slot 'missing_slot' was not found on step 1",
        }
    ]


def test_agent_platform_workflow_wiring_rejects_forward_step_references(
    client: TestClient,
) -> None:
    _seed_agent_platform_agent_dependencies(client)
    create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    response = client.post(
        "/api/workflows",
        json={
            "key": "forward_reference_workflow",
            "name": "Forward Reference Workflow",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {
                                "ticker": {
                                    "from": "step",
                                    "stepIndex": 2,
                                    "slot": "review",
                                }
                            },
                        }
                    ],
                },
                {
                    "index": 2,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "review",
                            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        }
                    ],
                },
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "review"},
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["details"] == [
        {
            "field": "steps[0].agents[0].wiring.ticker",
            "issue": "Slot references must point to an earlier step",
        }
    ]


def test_agent_platform_workflow_wiring_rejects_type_mismatches(
    client: TestClient,
) -> None:
    dependencies = _seed_agent_platform_agent_dependencies(client)
    create_agent(
        client,
        payload={
            "key": "research_agent",
            "name": "Research Agent",
            "description": "Analyzes a ticker.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Analyze the requested ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": "decision_schema",
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )
    create_agent(
        client,
        payload={
            "key": "score_agent",
            "name": "Score Agent",
            "description": "Requires an integer score.",
            "model": "openai:gpt-5.4-mini",
            "systemPrompt": "Use the integer score.",
            "inputSchema": {
                "type": "object",
                "properties": {"score": {"type": "integer"}},
                "required": ["score"],
            },
            "outputSchemaKey": cast(str, dependencies["outputSchema"]["key"]),
            "skills": [{"skillKey": "market_research"}],
            "mcpServers": [{"mcpServerKey": "market_data"}],
        },
    )

    response = client.post(
        "/api/workflows",
        json={
            "key": "type_mismatch_workflow",
            "name": "Type Mismatch Workflow",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "steps": [
                {
                    "index": 1,
                    "agents": [
                        {
                            "agentKey": "research_agent",
                            "slot": "analysis",
                            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        }
                    ],
                },
                {
                    "index": 2,
                    "agents": [
                        {
                            "agentKey": "score_agent",
                            "slot": "scored",
                            "wiring": {
                                "score": {
                                    "from": "step",
                                    "stepIndex": 1,
                                    "slot": "analysis",
                                    "path": "summary",
                                }
                            },
                        }
                    ],
                },
            ],
            "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["details"] == [
        {
            "field": "steps[1].agents[0].wiring.score",
            "issue": "Wired source type is not compatible with the target field schema",
        }
    ]


def test_agent_platform_stock_analysis_success_runs_stub_workflow_without_live_services(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RunService, "_invoke_agent", make_stock_analysis_stub_invoke())
    _seed_stock_analysis_platform(client)

    created_workflow = create_workflow(client, payload=stock_analysis_workflow_payload())
    created_steps = cast(list[dict[str, object]], created_workflow["steps"])
    created_step_agents = cast(list[dict[str, object]], created_steps[0]["agents"])
    output_spec = cast(dict[str, object], created_workflow["outputSpec"])

    assert [agent["agentKey"] for agent in created_step_agents] == list(
        STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
    )
    assert output_spec["kind"] == "agent"
    assert output_spec["agentKey"] == "decision_synthesizer"
    assert created_workflow["aggregateBudgetUsd"] == "0.50000000"

    trigger = client.post(
        f"/api/workflows/{created_workflow['id']}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, cast(int, trigger.json()["id"]))
    expected_step_outputs = {
        key: build_stock_analysis_note(agent_key=key, ticker="NVDA", horizon_days=30)
        for key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
    }

    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    assert detail["finalOutput"] == build_trading_decision(expected_step_outputs)
    assert [entry["slot"] for entry in detail["perStepOutputs"]["1"]] == list(
        STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
    )
    assert detail["perStepOutputs"]["2"][0]["agentKey"] == "decision_synthesizer"
    assert detail["perStepOutputs"]["2"][0]["resolvedInput"] == expected_step_outputs
    assert detail["perStepOutputs"]["2"][0]["status"] == "succeeded"


def test_portfolio_isolation_and_summary_counts(client: TestClient) -> None:
    first = create_portfolio(client, name="Core")
    second = create_portfolio(client, name="Sandbox")

    create_balance(client, str(first["id"]), label="Core Cash", amount="25000.00")
    create_position(client, str(second["id"]), symbol="MSFT", quantity="5", average_cost="400.00")

    first_balances = client.get(f"/api/v1/portfolios/{first['id']}/balances")
    second_balances = client.get(f"/api/v1/portfolios/{second['id']}/balances")
    first_positions = client.get(f"/api/v1/portfolios/{first['id']}/positions")
    second_positions = client.get(f"/api/v1/portfolios/{second['id']}/positions")

    assert first_balances.status_code == 200
    assert second_balances.status_code == 200
    assert first_positions.status_code == 200
    assert second_positions.status_code == 200

    assert len(first_balances.json()) == 1
    assert second_balances.json() == []
    assert first_positions.json() == []
    assert len(second_positions.json()) == 1

    portfolios = client.get("/api/v1/portfolios")
    assert portfolios.status_code == 200
    portfolio_map = {item["id"]: item for item in portfolios.json()}
    assert portfolio_map[first["id"]]["slug"] == "core"
    assert portfolio_map[second["id"]]["slug"] == "sandbox"
    assert portfolio_map[first["id"]]["balanceCount"] == 1
    assert portfolio_map[first["id"]]["positionCount"] == 0
    assert portfolio_map[second["id"]]["balanceCount"] == 0
    assert portfolio_map[second["id"]]["positionCount"] == 1


def test_portfolio_slug_validation_uniqueness_and_immutability(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement_account")
    assert portfolio["slug"] == "retirement_account"

    duplicate_response = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Retirement Copy",
            "slug": "retirement_account",
            "description": "Duplicate slug",
            "baseCurrency": "USD",
        },
    )
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["code"] == "duplicate_portfolio_slug"

    invalid_response = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Broken",
            "slug": "123-bad",
            "description": "Invalid slug",
            "baseCurrency": "USD",
        },
    )
    assert invalid_response.status_code == 422
    assert invalid_response.json()["code"] == "validation_error"
    assert invalid_response.json()["details"][0]["field"] == "slug"

    immutable_response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}",
        json={"slug": "new_slug"},
    )
    assert immutable_response.status_code == 422
    assert immutable_response.json()["code"] == "validation_error"
    assert immutable_response.json()["details"][0]["field"] == "slug"


def test_balance_crud(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    balance = create_balance(client, portfolio_id, label="Reserve", amount="1500.00")
    balance_id = str(balance["id"])

    list_response = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert list_response.status_code == 200
    assert list_response.json()[0]["label"] == "Reserve"

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/balances/{balance_id}",
        json={"label": "Trading Cash", "amount": "1750.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Trading Cash"
    assert Decimal(update_response.json()["amount"]) == Decimal("1750.00")

    delete_response = client.delete(f"/api/v1/portfolios/{portfolio_id}/balances/{balance_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_position_crud(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    position = create_position(client, portfolio_id)
    position_id = str(position["id"])

    list_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert list_response.status_code == 200
    assert list_response.json()[0]["symbol"] == "AAPL"

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}",
        json={"quantity": "12", "averageCost": "184.10", "name": "Apple Inc."},
    )
    assert update_response.status_code == 200
    assert Decimal(update_response.json()["quantity"]) == Decimal("12")
    assert Decimal(update_response.json()["averageCost"]) == Decimal("184.10")
    assert update_response.json()["name"] == "Apple Inc."

    delete_response = client.delete(f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_template_crud_and_compile_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement")
    create_portfolio(client, name="Income", slug="income")
    create_balance(client, str(portfolio["id"]), label="Cash", amount="1500.00")
    create_balance(
        client,
        str(portfolio["id"]),
        label="Taxes",
        amount="250.00",
        operation_type="WITHDRAWAL",
    )
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )
    create_position(
        client, str(portfolio["id"]), symbol="MSFT", quantity="5", average_cost="400.00"
    )

    template = create_template(
        client,
        name="Retirement Summary",
        content=(
            "# Summary\n\n"
            "Slug: {{portfolios.retirement.slug}}\n"
            "Balance: {{portfolios.retirement.balance}}\n"
            "Balance amount: {{portfolios.retirement.balance.amount}}\n"
            "Positions:\n{{portfolios.retirement.positions}}\n\n"
            "Apple name: {{portfolios.retirement.positions.AAPL.name}}\n\n"
            "All portfolios:\n{{portfolios}}"
        ),
    )

    list_response = client.get("/api/v1/templates")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [template["id"]]

    get_response = client.get(f"/api/v1/templates/{template['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Retirement Summary"

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert "Slug: retirement" in compiled
    assert "Balance: 1250.0000 USD" in compiled
    assert "Balance amount: 1250.0000" in compiled
    assert "- AAPL (AAPL Holdings): 10.00000000 shares @ 185.50000000 USD" in compiled
    assert "- MSFT (MSFT Holdings): 5.00000000 shares @ 400.00000000 USD" in compiled
    assert "Apple name: AAPL Holdings" in compiled
    assert "## Income" in compiled
    assert "## Retirement" in compiled

    update_response = client.patch(
        f"/api/v1/templates/{template['id']}",
        json={"name": "Weekly Summary", "content": "# Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Weekly Summary"
    assert update_response.json()["content"] == "# Updated"

    delete_response = client.delete(f"/api/v1/templates/{template['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/templates/{template['id']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_template_compile_accepts_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Reusable", slug="reusable")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )
    create_position(
        client, str(portfolio["id"]), symbol="TSLA", quantity="6", average_cost="210.00"
    )

    aapl_report = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Saved Analysis",
            "content": "AAPL prior view",
            "metadata": {
                "tags": ["aapl_loop"],
                "analysis": {"ticker": "AAPL"},
            },
        },
    )
    assert aapl_report.status_code == 201

    tsla_report = client.post(
        "/api/v1/reports",
        json={
            "name": "TSLA Saved Analysis",
            "content": "TSLA prior view",
            "metadata": {
                "tags": ["tsla_loop"],
                "analysis": {"ticker": "TSLA"},
            },
        },
    )
    assert tsla_report.status_code == 201

    template = create_template(
        client,
        name="Reusable Loop Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
            "Quantity: {{portfolios.by_slug(inputs.portfolio_slug).positions."
            "by_symbol(inputs.ticker).quantity}}\n"
            "Tagged prior: {{reports.by_tag(inputs.analysis_tag).latest.name}}\n"
            "Latest ticker analysis: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    inline_aapl = client.post(
        "/api/v1/templates/compile",
        json={
            "content": template["content"],
            "inputs": {
                "portfolio_slug": "reusable",
                "ticker": "AAPL",
                "analysis_tag": "aapl_loop",
            },
        },
    )
    assert inline_aapl.status_code == 200
    assert inline_aapl.json()["compiled"] == (
        "Ticker: AAPL\n"
        "Portfolio: Reusable\n"
        "Quantity: 10.00000000\n"
        "Tagged prior: AAPL Saved Analysis\n"
        "Latest ticker analysis: AAPL prior view"
    )

    stored_tsla = client.post(
        f"/api/v1/templates/{template['id']}/compile",
        json={
            "inputs": {
                "portfolio_slug": "reusable",
                "ticker": "TSLA",
                "analysis_tag": "tsla_loop",
            }
        },
    )
    assert stored_tsla.status_code == 200
    assert stored_tsla.json()["compiled"] == (
        "Ticker: TSLA\n"
        "Portfolio: Reusable\n"
        "Quantity: 6.00000000\n"
        "Tagged prior: TSLA Saved Analysis\n"
        "Latest ticker analysis: TSLA prior view"
    )


def test_template_compile_surfaces_missing_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Missing Inputs", slug="missing_inputs")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="4", average_cost="150.00"
    )

    response = client.post(
        "/api/v1/templates/compile",
        json={
            "content": (
                "Ticker: {{inputs.ticker}}\n"
                "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
                "Latest: {{reports.latest(inputs.ticker).name}}"
            ),
            "inputs": {"portfolio_slug": "missing_inputs"},
        },
    )

    assert response.status_code == 200
    assert response.json()["compiled"] == (
        "Ticker: [Missing input: ticker]\n"
        "Portfolio: Missing Inputs\n"
        "Latest: [Missing input: ticker]"
    )


def test_template_metric_placeholders_with_quotes(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    portfolio_id = str(portfolio["id"])
    create_balance(client, portfolio_id, label="Cash", amount="1500.00")
    create_balance(
        client, portfolio_id, label="Taxes", amount="250.00", operation_type="WITHDRAWAL"
    )
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")
    create_position(client, portfolio_id, symbol="MSFT", quantity="5", average_cost="400.00")

    template = create_template(
        client,
        name="Metrics Report",
        content=(
            "Total: {{portfolios.growth.total_value}}\n"
            "PnL: {{portfolios.growth.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.growth.positions.AAPL.market_value}}\n"
            "AAPL PnL: {{portfolios.growth.positions.AAPL.unrealized_pnl}}\n"
            "AAPL Pct: {{portfolios.growth.positions.AAPL.unrealized_pnl_percent}}\n"
            "MSFT MV: {{portfolios.growth.positions.MSFT.market_value}}\n"
            "Slug: {{portfolios.growth.slug}}\n"
            "Balance: {{portfolios.growth.balance.amount}}"
        ),
    )

    provider = StableQuoteProvider()
    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled == (
        "Total: 4118.6000000000\n"
        "PnL: -986.4000000000000000\n"
        "AAPL MV: 1912.4000000000\n"
        "AAPL PnL: 57.4000000000000000\n"
        "AAPL Pct: 0.03094339622641509433962264151\n"
        "MSFT MV: 956.2000000000\n"
        "Slug: growth\n"
        "Balance: 1250.0000"
    )


def test_template_metric_placeholders_batch_quote_fetches_once_per_compile(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client, name="Cached", slug="cached")
    portfolio_id = str(portfolio["id"])
    create_balance(client, portfolio_id, label="Cash", amount="1500.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")
    create_position(client, portfolio_id, symbol="MSFT", quantity="5", average_cost="400.00")

    template = create_template(
        client,
        name="Cached Metrics",
        content=(
            "Total: {{portfolios.cached.total_value}}\n"
            "PnL: {{portfolios.cached.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.cached.positions.AAPL.market_value}}\n"
            "AAPL PnL: {{portfolios.cached.positions.AAPL.unrealized_pnl}}\n"
            "MSFT MV: {{portfolios.cached.positions.MSFT.market_value}}"
        ),
    )

    provider = CountingQuoteProvider()
    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    assert provider.quote_calls == 2


def test_template_metric_placeholders_with_broken_provider(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Broken", slug="broken")
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")

    template = create_template(
        client,
        name="Broken Metrics",
        content=(
            "Total: {{portfolios.broken.total_value}}\n"
            "PnL: {{portfolios.broken.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.broken.positions.AAPL.market_value}}\n"
            "Name: {{portfolios.broken.name}}"
        ),
    )

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: BrokenQuoteProvider()

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Total: \n" in compiled
    assert "PnL: \n" in compiled
    assert "AAPL MV: \n" in compiled
    assert "Name: Broken" in compiled


def test_template_metric_zero_cost_basis_percent(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Zero", slug="zero")
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="0")

    template = create_template(
        client,
        name="Zero Cost",
        content="Pct: {{portfolios.zero.positions.AAPL.unrealized_pnl_percent}}",
    )

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: StableQuoteProvider()

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert compiled == "Pct: "


def test_nullable_patch_fields_can_be_cleared(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    clear_description = client.patch(
        f"/api/v1/portfolios/{portfolio_id}",
        json={"description": None},
    )
    assert clear_description.status_code == 200
    assert clear_description.json()["description"] is None

    position = create_position(
        client, portfolio_id, symbol="NVDA", quantity="3", average_cost="700.00"
    )
    clear_position_name = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position['id']}",
        json={"name": None},
    )
    assert clear_position_name.status_code == 200
    assert clear_position_name.json()["name"] is None


def test_csv_preview_and_commit_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    valid_csv = (
        "symbol,quantity,average_cost,name\n"
        "AAPL,10,185.50,Apple Inc.\n"
        "MSFT,5,400.00,Microsoft Corp.\n"
    )
    preview_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/preview",
        files={"file": ("positions.csv", valid_csv, "text/csv")},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["mode"] == "upsert"
    assert len(preview_payload["acceptedRows"]) == 2
    assert preview_payload["errors"] == []

    commit_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", valid_csv, "text/csv")},
    )
    assert commit_response.status_code == 200
    commit_payload = commit_response.json()
    assert commit_payload["inserted"] == 2
    assert commit_payload["updated"] == 0
    assert commit_payload["unchanged"] == 0

    updated_csv = (
        "symbol,quantity,average_cost,name\n"
        "AAPL,12,184.10,Apple Inc.\n"
        "MSFT,5,400.00,Microsoft Corp.\n"
    )
    second_commit = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", updated_csv, "text/csv")},
    )
    assert second_commit.status_code == 200
    second_commit_payload = second_commit.json()
    assert second_commit_payload["inserted"] == 0
    assert second_commit_payload["updated"] == 1
    assert second_commit_payload["unchanged"] == 1

    invalid_csv = "symbol,quantity,average_cost\nAAPL,10,185.50\nAAPL,8,184.00\n"
    preview_invalid = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/preview",
        files={"file": ("positions.csv", invalid_csv, "text/csv")},
    )
    assert preview_invalid.status_code == 200
    assert preview_invalid.json()["errors"][0]["issue"] == "Duplicate symbol in file"

    commit_invalid = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", invalid_csv, "text/csv")},
    )
    assert commit_invalid.status_code == 422
    error_payload = commit_invalid.json()
    assert error_payload["code"] == "validation_error"
    assert error_payload["details"][0]["field"] == "symbol"


def test_trading_operations_buy_and_sell_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")

    buy_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "2",
            "price": "100.00",
            "commission": "5.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert buy_response.status_code == 201
    buy_payload = buy_response.json()
    assert Decimal(buy_payload["updatedBalance"]["amount"]) == Decimal("795.00")
    assert Decimal(buy_payload["updatedPosition"]["quantity"]) == Decimal("2")
    assert Decimal(buy_payload["updatedPosition"]["averageCost"]) == Decimal("102.5")

    sell_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": "1",
            "price": "120.00",
            "commission": "5.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert sell_response.status_code == 201
    sell_payload = sell_response.json()
    assert Decimal(sell_payload["updatedBalance"]["amount"]) == Decimal("910.00")
    assert Decimal(sell_payload["updatedPosition"]["quantity"]) == Decimal("1")
    assert Decimal(sell_payload["updatedPosition"]["averageCost"]) == Decimal("102.5")

    operations_response = client.get(f"/api/v1/portfolios/{portfolio_id}/trading-operations")
    assert operations_response.status_code == 200
    assert len(operations_response.json()) == 2


def test_trading_operation_rejections(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="50.00")

    insufficient_buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "60.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert insufficient_buy.status_code == 400
    assert insufficient_buy.json()["code"] == "insufficient_balance"

    create_position(client, portfolio_id, symbol="AAPL", quantity="1", average_cost="10.00")
    oversell = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": "2",
            "price": "12.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert oversell.status_code == 400
    assert oversell.json()["code"] == "oversell_rejected"


def test_trading_operations_respect_withdrawals_and_deposit_balances(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    deposit_balance = create_balance(client, portfolio_id, label="Broker Cash", amount="1000.00")
    withdrawal_balance = create_balance(
        client,
        portfolio_id,
        label="Cash Out",
        amount="200.00",
        operation_type="WITHDRAWAL",
    )

    insufficient_after_withdrawal = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": deposit_balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "9",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert insufficient_after_withdrawal.status_code == 400
    assert insufficient_after_withdrawal.json()["code"] == "insufficient_balance"

    invalid_withdrawal_balance = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": withdrawal_balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert invalid_withdrawal_balance.status_code == 400
    assert invalid_withdrawal_balance.json()["code"] == "invalid_operation_balance"


def test_trading_operations_dividend_and_split_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    dividend_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "12.50",
            "commission": "0.50",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )
    assert dividend_response.status_code == 201
    dividend_payload = dividend_response.json()
    assert Decimal(dividend_payload["updatedBalance"]["amount"]) == Decimal("1012.00")
    assert Decimal(dividend_payload["updatedPosition"]["quantity"]) == Decimal("2")
    assert Decimal(dividend_payload["operation"]["dividendAmount"]) == Decimal("12.50")

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "4",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )
    assert split_response.status_code == 201
    split_payload = split_response.json()
    assert split_payload["updatedBalance"] is None
    assert split_payload["operation"]["balanceId"] is None
    assert split_payload["operation"]["balanceLabel"] == "Not Applicable"
    assert Decimal(split_payload["updatedPosition"]["quantity"]) == Decimal("8")
    assert Decimal(split_payload["updatedPosition"]["averageCost"]) == Decimal("25")
    assert Decimal(split_payload["operation"]["splitRatio"]) == Decimal("4")


def test_dividend_rejects_when_commission_would_make_balance_negative(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="0.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "1.00",
            "commission": "2.00",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "insufficient_balance"


def test_dividend_requires_existing_position(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="100.00")

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "1.00",
            "commission": "0.00",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "no_position_for_dividend"

    balances_response = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert balances_response.status_code == 200
    assert Decimal(balances_response.json()[0]["amount"]) == Decimal("100.00")

    operations_response = client.get(f"/api/v1/portfolios/{portfolio_id}/trading-operations")
    assert operations_response.status_code == 200
    assert operations_response.json() == []


def test_split_requires_existing_position(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "2",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )
    assert split_response.status_code == 400
    assert split_response.json()["code"] == "no_position_for_split"


def test_split_succeeds_without_balance(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "2",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )

    assert split_response.status_code == 201
    split_payload = split_response.json()
    assert split_payload["updatedBalance"] is None
    assert split_payload["operation"]["balanceId"] is None
    assert Decimal(split_payload["updatedPosition"]["quantity"]) == Decimal("4")


def test_trade_linked_balance_cannot_change_operation_type(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")

    trade_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert trade_response.status_code == 201

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/balances/{balance['id']}",
        json={"operationType": "WITHDRAWAL"},
    )

    assert update_response.status_code == 400
    assert update_response.json()["code"] == "balance_operation_type_locked"


class BrokenQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        raise QuoteProviderError(f"Unavailable for {symbol}")

    def fetch_quote(self, symbol: str) -> object:
        raise QuoteProviderError(f"Unavailable for {symbol}")


def _build_provider_quote(
    *,
    symbol: str,
    price: Decimal,
    previous_close: Decimal | None,
    currency: str,
    provider: str,
    as_of: datetime | None,
) -> ProviderQuote:
    quote = cast(ProviderQuote, object.__new__(ProviderQuote))
    quote.symbol = symbol
    quote.price = price
    quote.previous_close = previous_close
    quote.currency = currency
    quote.provider = provider
    quote.as_of = as_of
    quote.name = None
    return quote


def _build_provider_history_point(*, at: datetime, close: Decimal) -> ProviderHistoryPoint:
    point = cast(ProviderHistoryPoint, object.__new__(ProviderHistoryPoint))
    point.at = at
    point.close = close
    return point


def _build_provider_history_series(
    *,
    symbol: str,
    currency: str | None,
    provider: str,
    points: list[ProviderHistoryPoint],
) -> ProviderHistorySeries:
    series = cast(ProviderHistorySeries, object.__new__(ProviderHistorySeries))
    series.symbol = symbol
    series.currency = currency
    series.provider = provider
    series.points = points
    return series


class StableQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        if symbol.upper() == "AAPL":
            return "Apple Inc."
        return None

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        return _build_provider_quote(
            symbol=normalized_symbol,
            price=Decimal("191.24"),
            previous_close=Decimal("189.10"),
            currency="USD",
            provider="stub_feed",
            as_of=datetime(2026, 3, 10, 13, 55, tzinfo=UTC_TZ),
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        if interval != "1d" or range_value != "3mo":
            raise QuoteProviderError("Unexpected history request")

        normalized_symbol = symbol.upper()
        base_price = Decimal("100.00") if normalized_symbol == "AAPL" else Decimal("90.00")
        return _build_provider_history_series(
            symbol=normalized_symbol,
            currency="USD",
            provider="stub_feed",
            points=[
                _build_provider_history_point(
                    at=datetime(2026, 1, 5, 14, 30, tzinfo=UTC_TZ), close=base_price
                ),
                _build_provider_history_point(
                    at=datetime(2026, 2, 5, 14, 30, tzinfo=UTC_TZ),
                    close=base_price + Decimal("8.50"),
                ),
                _build_provider_history_point(
                    at=datetime(2026, 3, 5, 14, 30, tzinfo=UTC_TZ),
                    close=base_price + Decimal("12.00"),
                ),
            ],
        )


class CountingQuoteProvider(StableQuoteProvider):
    def __init__(self) -> None:
        self.quote_calls = 0

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        self.quote_calls += 1
        return super().fetch_quote(symbol)


class CountingSymbolLookupProvider:
    def __init__(self) -> None:
        self.symbol_name_calls = 0

    def fetch_symbol_name(self, symbol: str) -> str | None:
        self.symbol_name_calls += 1
        if symbol.upper() == "AAPL":
            return "Apple Inc."
        return None

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise QuoteProviderError(f"Quote lookup unavailable for {symbol}")

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        raise QuoteProviderError(f"History lookup unavailable for {symbol}")


class UnexpectedSymbolLookupProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        raise AssertionError(f"Symbol lookup should not run for {symbol}")

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise QuoteProviderError(f"Quote lookup unavailable for {symbol}")

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        raise QuoteProviderError(f"History lookup unavailable for {symbol}")


def test_position_symbol_lookup_returns_provider_name_and_uses_cache(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    provider = CountingSymbolLookupProvider()

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    first_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=aapl")
    second_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=AAPL")

    application.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert first_response.json() == {"symbol": "AAPL", "name": "Apple Inc."}
    assert second_response.status_code == 200
    assert second_response.json() == {"symbol": "AAPL", "name": "Apple Inc."}
    assert provider.symbol_name_calls == 1

    with session_factory() as session:
        cached = session.query(SymbolNameCache).filter_by(symbol="AAPL").one_or_none()

    assert cached is not None
    assert cached.name == "Apple Inc."


def test_position_symbol_lookup_returns_null_name_for_unresolved_symbol(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=unknown")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"symbol": "UNKNOWN", "name": None}


def test_create_position_backfills_name_from_symbol_lookup_when_missing(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "quantity": "10",
            "averageCost": "185.50",
        },
    )
    application.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"
    assert response.json()["name"] == "Apple Inc."


def test_create_position_uses_manual_name_without_provider_lookup(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = UnexpectedSymbolLookupProvider
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "name": "Manual Apple Name",
            "quantity": "10",
            "averageCost": "185.50",
        },
    )
    application.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"
    assert response.json()["name"] == "Manual Apple Name"


def test_market_data_falls_back_to_cached_quote(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    as_of = datetime(2026, 3, 10, 13, 55, tzinfo=UTC_TZ)

    with session_factory() as session:
        session.add(
            MarketQuote(
                symbol="AAPL",
                provider="yahoo_finance",
                price="191.24",
                previous_close="189.10",
                currency="USD",
                as_of=as_of,
                fetched_at=as_of,
                is_stale=False,
            )
        )
        session.commit()

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = BrokenQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["symbol"] == "AAPL"
    assert Decimal(payload["quotes"][0]["price"]) == Decimal("191.24")
    assert Decimal(payload["quotes"][0]["previousClose"]) == Decimal("189.10")
    assert payload["warnings"] == ["Using cached quote for AAPL"]


def test_market_data_recomputes_cached_quote_staleness_on_fallback(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    as_of = datetime.now(UTC_TZ) - timedelta(minutes=30)

    with session_factory() as session:
        cached_quote = MarketQuote(
            symbol="AAPL",
            provider="yahoo_finance",
            price="191.24",
            previous_close="189.10",
            currency="USD",
            as_of=as_of,
            fetched_at=as_of,
            is_stale=False,
        )
        session.add(cached_quote)
        session.commit()
        cached_quote_id = cached_quote.id

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = BrokenQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["isStale"] is True
    assert payload["warnings"] == ["Using cached quote for AAPL"]

    with session_factory() as session:
        refreshed_quote = session.get(MarketQuote, cached_quote_id)
        assert refreshed_quote is not None
        assert refreshed_quote.is_stale is True


def test_market_data_returns_previous_close_when_provider_supplies_it(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["provider"] == "stub_feed"
    assert Decimal(payload["quotes"][0]["previousClose"]) == Decimal("189.10")


def test_market_data_history_returns_multiple_series(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(
        f"/api/v1/portfolios/{portfolio_id}/market-data/history?symbols=AAPL,%5EGSPC&range=3mo"
    )
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == "3mo"
    assert payload["interval"] == "1d"
    assert payload["warnings"] == []
    assert [series["symbol"] for series in payload["series"]] == ["AAPL", "^GSPC"]
    assert payload["series"][0]["points"][0]["at"] == "2026-01-05T14:30:00Z"
    assert Decimal(payload["series"][1]["points"][2]["close"]) == Decimal("102.00")


def test_validate_supported_database_engine_rejects_non_postgres() -> None:
    unsupported_engine = UnsupportedEngine("mysql")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        validate_supported_database_engine(unsupported_engine)


def test_init_db_rejects_legacy_uuid_backed_schema(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE portfolios (id VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE balances (id VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE trading_operations (
                    portfolio_id VARCHAR(32) NOT NULL,
                    balance_id VARCHAR(32),
                    balance_label VARCHAR(60) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(4) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    commission NUMERIC(20, 4) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    CONSTRAINT ck_trading_operations_side CHECK (side IN ('BUY', 'SELL'))
                )
                """
            )

        with pytest.raises(RuntimeError, match="Legacy UUID-backed database detected"):
            init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert table_names == {"balances", "portfolios", "trading_operations"}
    finally:
        engine.dispose()


def test_init_db_upgrades_legacy_balance_schema_and_drops_obsolete_tables(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE balances (
                    id INTEGER PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    label VARCHAR(60) NOT NULL,
                    amount NUMERIC(20, 4) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO balances (
                    id, portfolio_id, label, amount, currency, created_at, updated_at
                )
                VALUES (1, 1, 'Cash', 1000.00, 'USD', NOW(), NOW())
                """
            )

            for table_name in (
                "llm_configs",
                "prompt_templates",
                "user_snippets",
                "portfolio_stock_analysis_settings",
                "stock_analysis_conversations",
                "stock_analysis_runs",
                "stock_analysis_requests",
                "stock_analysis_responses",
                "stock_analysis_versions",
            ):
                connection.exec_driver_sql(f'CREATE TABLE "{table_name}" (id INTEGER PRIMARY KEY)')

        init_db(database_url)

        inspector = inspect(engine)
        balance_columns = {column["name"]: column for column in inspector.get_columns("balances")}
        assert "operation_type" in balance_columns
        assert balance_columns["operation_type"]["nullable"] is False

        with engine.connect() as connection:
            operation_type = connection.exec_driver_sql(
                "SELECT operation_type FROM balances WHERE id = 1"
            ).scalar_one()

        assert operation_type == "DEPOSIT"

        table_names = set(inspector.get_table_names())
        assert {
            "llm_configs",
            "prompt_templates",
            "user_snippets",
            "portfolio_stock_analysis_settings",
            "stock_analysis_conversations",
            "stock_analysis_runs",
            "stock_analysis_requests",
            "stock_analysis_responses",
            "stock_analysis_versions",
        }.isdisjoint(table_names)
    finally:
        engine.dispose()


def test_init_db_backfills_legacy_portfolio_slugs_with_valid_unique_values(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    base_currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO portfolios (
                    id, name, description, base_currency, created_at, updated_at
                )
                VALUES
                    (1, 'Growth Income', 'Legacy', 'USD', NOW(), NOW()),
                    (2, 'Growth-Income', 'Legacy', 'USD', NOW(), NOW()),
                    (3, '123 Allocation', 'Legacy', 'USD', NOW(), NOW()),
                    (4, '!!!', 'Legacy', 'USD', NOW(), NOW())
                """
            )

        init_db(database_url)

        portfolio_columns = {
            column["name"]: column for column in inspect(engine).get_columns("portfolios")
        }
        assert "slug" in portfolio_columns
        assert portfolio_columns["slug"]["nullable"] is False

        with engine.connect() as connection:
            slugs = (
                connection.exec_driver_sql("SELECT slug FROM portfolios ORDER BY id")
                .scalars()
                .all()
            )

        assert slugs == [
            "growth_income",
            "growth_income_2",
            "portfolio_123_allocation",
            "portfolio",
        ]
        assert len(set(slugs)) == len(slugs)
    finally:
        engine.dispose()


def test_init_db_adds_market_quote_name_column_for_legacy_schema(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE market_quotes (
                    id INTEGER PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    previous_close NUMERIC(20, 8),
                    currency VARCHAR(3) NOT NULL,
                    as_of TIMESTAMP WITH TIME ZONE,
                    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    is_stale BOOLEAN NOT NULL
                )
                """
            )

        init_db(database_url)

        market_quote_columns = {
            column["name"]: column for column in inspect(engine).get_columns("market_quotes")
        }
        assert "name" in market_quote_columns
        assert market_quote_columns["name"]["nullable"] is True
    finally:
        engine.dispose()


def test_init_db_creates_symbol_name_cache_as_unlogged_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            relpersistence = connection.exec_driver_sql(
                "SELECT relpersistence FROM pg_class WHERE relname = 'symbol_name_cache'"
            ).scalar_one()

        assert relpersistence == "u"
    finally:
        engine.dispose()


def test_report_compile_crud_and_download(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement")
    create_balance(client, str(portfolio["id"]), label="Cash", amount="1500.00")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    template = create_template(
        client,
        name="Monthly Report",
        content=(
            "# Report\n\n"
            "Slug: {{portfolios.retirement.slug}}\n"
            "Positions:\n{{portfolios.retirement.positions}}"
        ),
    )

    compile_response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert compile_response.status_code == 201
    report = compile_response.json()
    assert report["name"].startswith("monthly_report_")
    assert report["slug"].startswith("monthly_report_")
    assert report["source"] == "compiled"
    assert "metadata" in report
    assert "Slug: retirement" in report["content"]
    assert "AAPL" in report["content"]
    assert "createdAt" in report
    assert "updatedAt" in report

    list_response = client.get("/api/v1/reports")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == report["id"]

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == report["name"]
    assert get_response.json()["content"] == report["content"]

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Edited Report\n\nManual edit."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Edited Report\n\nManual edit."
    assert update_response.json()["name"] == report["name"]

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert "text/markdown" in download_response.headers["content-type"]
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Edited Report\n\nManual edit."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_report_compile_nonexistent_template(client: TestClient) -> None:
    response = client.post("/api/v1/reports/compile/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_report_name_generation_and_uniqueness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_now = datetime(2026, 3, 18, 10, 56, 51, tzinfo=UTC_TZ)
    monkeypatch.setattr("app.services.report_service.utcnow", lambda: fixed_now)

    template = create_template(
        client,
        name="Q1 Summary",
        content="# Q1",
    )

    first = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert first.status_code == 201
    first_name = first.json()["name"]
    first_slug = first.json()["slug"]
    assert first_name.startswith("q1_summary_")
    assert first_slug == first_name

    second = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert second.status_code == 201
    second_name = second.json()["name"]
    second_slug = second.json()["slug"]
    assert second_name != first_name
    assert second_name.startswith("q1_summary_")
    assert second_name.endswith("_2")
    assert second_slug == second_name


def test_report_name_normalization(client: TestClient) -> None:
    template = create_template(
        client,
        name="My Portfolio — March",
        content="# March",
    )

    response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert response.status_code == 201
    name = response.json()["name"]
    assert name.startswith("my_portfolio_march_")
    assert "—" not in name
    assert " " not in name


def test_report_update_name_immutability(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Updated", "name": "new_name"},
    )
    assert response.status_code == 422


def test_report_update_validation(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    empty_payload = client.patch(f"/api/v1/reports/{report['slug']}", json={})
    assert empty_payload.status_code == 422

    whitespace_content = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "   "},
    )
    assert whitespace_content.status_code == 422


def test_report_404s(client: TestClient) -> None:
    assert client.get("/api/v1/reports/99999").status_code == 404
    assert client.patch("/api/v1/reports/99999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/v1/reports/99999").status_code == 404
    assert client.get("/api/v1/reports/99999/download").status_code == 404


def test_report_name_timestamp_format(client: TestClient) -> None:
    import re

    template = create_template(client, name="Timestamp Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    name = report["name"]

    pattern = r"^timestamp_test_\d{8}_\d{6}$"
    assert re.match(pattern, name), f"Name '{name}' does not match expected format"


def test_report_name_max_length_truncation(client: TestClient) -> None:
    long_name = "A" * 100
    template = create_template(client, name=long_name, content="# Long")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    assert len(report["name"]) <= 200


def test_report_upload_crud_and_download(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Quarterly Update.md",
                b"# Uploaded Report\n\nBody text.",
                "text/markdown",
            )
        },
        data={
            "slug": "quarterly_update",
            "author": "Analyst",
            "description": "Uploaded from disk",
            "tags": "quarterly, finance",
        },
    )
    assert upload_response.status_code == 201
    report = upload_response.json()
    assert report["name"] == "Quarterly Update"
    assert report["slug"] == "quarterly_update"
    assert report["source"] == "uploaded"
    assert report["metadata"] == {
        "author": "Analyst",
        "description": "Uploaded from disk",
        "tags": ["quarterly", "finance"],
    }

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == "# Uploaded Report\n\nBody text."

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Uploaded Report\n\nBody text."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_code"),
    [
        ("notes.txt", b"# Not markdown", "text/plain", "invalid_file_type"),
        ("broken.md", b"\xff\xfe\x00", "application/octet-stream", "invalid_file_encoding"),
    ],
)
def test_report_upload_validation(
    client: TestClient,
    filename: str,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    response = client.post(
        "/api/v1/reports/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json()["code"] == expected_code


def test_report_compile_accepts_extensible_metadata(client: TestClient) -> None:
    template = create_template(client, name="Weekly Review", content="# Weekly")

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "author": " Analyst ",
                "tags": [" weekly_review ", "reflection"],
                "analysis": {
                    "ticker": "aapl",
                    "portfolioSlug": "core_us",
                    "customKey": "custom-value",
                },
                "customBlock": {"foo": "bar"},
            }
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["source"] == "compiled"
    assert report["metadata"]["author"] == "Analyst"
    assert report["metadata"]["tags"] == ["weekly_review", "reflection"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["portfolioSlug"] == "core_us"
    assert report["metadata"]["analysis"]["customKey"] == "custom-value"
    assert report["metadata"]["customBlock"] == {"foo": "bar"}


def test_report_compile_accepts_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Runtime Compile", slug="runtime_compile")
    create_position(
        client, str(portfolio["id"]), symbol="MSFT", quantity="7", average_cost="398.00"
    )

    client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Prior Analysis",
            "content": "MSFT prior report body",
            "metadata": {
                "tags": ["msft_loop"],
                "analysis": {"ticker": "MSFT"},
            },
        },
    )

    template = create_template(
        client,
        name="Runtime Report Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
            "Quantity: {{portfolios.by_slug(inputs.portfolio_slug).positions."
            "by_symbol(inputs.ticker).quantity}}\n"
            "Prior: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "inputs": {
                "ticker": "MSFT",
                "portfolio_slug": "runtime_compile",
            },
            "metadata": {
                "tags": ["runtime_compile"],
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["content"] == (
        "Ticker: MSFT\n"
        "Portfolio: Runtime Compile\n"
        "Quantity: 7.00000000\n"
        "Prior: MSFT prior report body"
    )
    assert report["metadata"]["tags"] == ["runtime_compile"]


def test_report_create_external_json(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Weekly Reflection",
            "content": "# AAPL\n\nReview body.",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "aapl",
                    "reviewType": "weekly_review",
                },
                "customFlag": True,
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["name"] == "AAPL Weekly Reflection"
    assert report["slug"] == "aapl_weekly_reflection"
    assert report["source"] == "external"
    assert report["metadata"]["tags"] == ["weekly_review"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["reviewType"] == "weekly_review"
    assert report["metadata"]["customFlag"] is True

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["source"] == "external"


def test_report_create_external_slug_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/reports",
        json={
            "name": "External One",
            "slug": "external_one",
            "content": "# One",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/reports",
        json={
            "name": "External Two",
            "slug": "external_one",
            "content": "# Two",
        },
    )
    assert second.status_code == 409
    assert second.json()["code"] == "slug_conflict"


def test_report_list_filters_and_pagination(client: TestClient) -> None:
    template = create_template(client, name="AAPL Weekly Template", content="# Weekly")

    compiled = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review", "reflection"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Monthly Reflection",
            "content": "# AAPL Monthly",
            "metadata": {
                "tags": ["monthly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "monthly_review",
                    "portfolioSlug": "core_us",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Weekly Reflection",
            "content": "# MSFT Weekly",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "growth",
                },
            },
        },
    ).json()

    uploaded = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nArchive body.",
                "text/markdown",
            )
        },
        data={
            "slug": "uploaded_note",
            "tags": "archive",
        },
    ).json()

    all_reports = client.get("/api/v1/reports")
    assert all_reports.status_code == 200
    assert [report["id"] for report in all_reports.json()] == [
        uploaded["id"],
        external_msft["id"],
        external_aapl["id"],
        compiled["id"],
    ]

    by_ticker = client.get("/api/v1/reports", params={"ticker": "aapl"})
    assert by_ticker.status_code == 200
    assert [report["id"] for report in by_ticker.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_tag = client.get("/api/v1/reports", params={"tag": "weekly_review"})
    assert by_tag.status_code == 200
    assert [report["id"] for report in by_tag.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_review_type = client.get("/api/v1/reports", params={"reviewType": "weekly_review"})
    assert by_review_type.status_code == 200
    assert [report["id"] for report in by_review_type.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_portfolio = client.get("/api/v1/reports", params={"portfolioSlug": "core_us"})
    assert by_portfolio.status_code == 200
    assert [report["id"] for report in by_portfolio.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_source = client.get("/api/v1/reports", params={"source": "external"})
    assert by_source.status_code == 200
    assert [report["id"] for report in by_source.json()] == [
        external_msft["id"],
        external_aapl["id"],
    ]

    combined = client.get(
        "/api/v1/reports",
        params={
            "ticker": "AAPL",
            "reviewType": "weekly_review",
            "portfolioSlug": "core_us",
        },
    )
    assert combined.status_code == 200
    assert [report["id"] for report in combined.json()] == [compiled["id"]]

    paginated = client.get(
        "/api/v1/reports",
        params={"source": "external", "limit": 1, "offset": 1},
    )
    assert paginated.status_code == 200
    assert [report["id"] for report in paginated.json()] == [external_aapl["id"]]


def test_report_placeholder_all_paths(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    source_template = create_template(
        client,
        name="Source",
        content="Name: {{portfolios.growth.name}}",
    )
    report_response = client.post(f"/api/v1/reports/compile/{source_template['id']}")
    assert report_response.status_code == 201
    report = report_response.json()
    report_name = report["name"]

    meta_template = create_template(
        client,
        name="Report Meta Test",
        content=(
            "All: {{reports}}\n"
            f"Single: {{{{reports.{report_name}}}}}\n"
            f"Content: {{{{reports.{report_name}.content}}}}\n"
            f"NameField: {{{{reports.{report_name}.name}}}}\n"
            f"Created: {{{{reports.{report_name}.created_at}}}}\n"
            "Unknown: {{reports.nonexistent_report}}\n"
            f"BadField: {{{{reports.{report_name}.unknown_field}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{meta_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled.startswith("All: - **")
    assert f"**{report_name}**" in compiled

    single_line = [line for line in compiled.split("\n") if line.startswith("Single: ")][0]
    assert single_line.startswith(f"Single: **{report_name}**")
    assert "(" in single_line and "Z)" in single_line

    assert "Content: Name: Growth" in compiled

    assert f"NameField: {report_name}" in compiled

    created_line = [line for line in compiled.split("\n") if line.startswith("Created: ")][0]
    created_value = created_line.replace("Created: ", "")
    assert created_value.endswith("Z")
    assert "T" in created_value

    assert "[Unknown report: nonexistent_report]" in compiled
    assert "[Unknown report field: unknown_field]" in compiled


def test_report_placeholder_recompilation(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Recomp", slug="recomp")
    create_position(
        client, str(portfolio["id"]), symbol="TSLA", quantity="5", average_cost="200.00"
    )

    source_template = create_template(
        client,
        name="Recomp Source",
        content="Original: {{portfolios.recomp.name}}",
    )
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={
            "content": (
                "Name: {{portfolios.recomp.name}}\nPositions: {{portfolios.recomp.positions}}"
            )
        },
    )

    embed_template = create_template(
        client,
        name="Embed Test",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Name: Recomp" in compiled
    assert "TSLA" in compiled


def test_report_placeholder_cycle_detection_self_reference(
    client: TestClient,
) -> None:
    source_template = create_template(client, name="Self Ref", content="# Self")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": f"{{{{reports.{report_name}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Self Ref Embed",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report_name}]" in compiled


def test_report_placeholder_cycle_detection_indirect(
    client: TestClient,
) -> None:
    tmpl_a = create_template(client, name="Cycle A", content="# A")
    tmpl_b = create_template(client, name="Cycle B", content="# B")
    report_a = client.post(f"/api/v1/reports/compile/{tmpl_a['id']}").json()
    report_b = client.post(f"/api/v1/reports/compile/{tmpl_b['id']}").json()
    name_a = report_a["name"]
    name_b = report_b["name"]

    client.patch(
        f"/api/v1/reports/{report_a['slug']}",
        json={"content": f"A includes B: {{{{reports.{name_b}.content}}}}"},
    )
    client.patch(
        f"/api/v1/reports/{report_b['slug']}",
        json={"content": f"B includes A: {{{{reports.{name_a}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Indirect Cycle",
        content=f"{{{{reports.{name_a}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert (
        f"[Circular report reference: {name_a}]" in compiled
        or f"[Circular report reference: {name_b}]" in compiled
    )


def test_placeholder_tree_includes_reports(client: TestClient) -> None:
    source_template = create_template(client, name="Tree Test", content="# Tree")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()

    tree_response = client.get("/api/v1/templates/placeholders")
    assert tree_response.status_code == 200
    tree = tree_response.json()

    assert "reports" in tree
    report_names = [r["name"] for r in tree["reports"]]
    assert report["name"] in report_names
    assert "createdAt" in tree["reports"][0]


def test_report_placeholder_dynamic_selectors(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    source_template = create_template(client, name="Latest Report", content="Compiled AAPL")
    compiled_aapl = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Dynamic Latest",
            "content": "Dynamic AAPL: {{portfolios.growth.name}}",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Dynamic Latest",
            "content": "MSFT body",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "growth",
                },
            },
        },
    ).json()

    selector_template = create_template(
        client,
        name="Dynamic Selector Test",
        content=(
            "LatestMeta: {{reports.latest}}\n"
            "LatestName: {{reports.latest.name}}\n"
            'TickerLatestName: {{reports.latest("AAPL").name}}\n'
            'TickerLatestContent: {{reports.latest("AAPL").content}}\n'
            "IndexZeroName: {{reports[0].name}}\n"
            'TagLatestName: {{reports.by_tag("weekly_review").latest.name}}\n'
            'TagLatestContent: {{reports.by_tag("weekly_review").latest.content}}\n'
            'NoMatchInline: before{{reports.latest("NVDA").name}}after\n'
            "NoMatchIndex: before{{reports[99].content}}after\n"
            'InvalidSelector: {{reports.by_tag("weekly_review")}}\n'
            f"ExactNameCompatibility: {{{{reports.{compiled_aapl['name']}.name}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    latest_meta_line = [line for line in compiled.split("\n") if line.startswith("LatestMeta: ")][0]
    assert latest_meta_line.startswith(f"LatestMeta: **{external_msft['name']}**")
    assert f"LatestName: {external_msft['name']}" in compiled
    assert f"TickerLatestName: {external_aapl['name']}" in compiled
    assert "TickerLatestContent: Dynamic AAPL: Growth" in compiled
    assert f"IndexZeroName: {external_msft['name']}" in compiled
    assert f"TagLatestName: {external_msft['name']}" in compiled
    assert "TagLatestContent: MSFT body" in compiled
    assert "NoMatchInline: beforeafter" in compiled
    assert "NoMatchIndex: beforeafter" in compiled
    assert 'InvalidSelector: [Invalid report selector: reports.by_tag("weekly_review")]' in compiled
    assert f"ExactNameCompatibility: {compiled_aapl['name']}" in compiled


def test_report_placeholder_dynamic_selector_cycle_detection(client: TestClient) -> None:
    source_template = create_template(client, name="Cycle Selector", content="# Start")
    report = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": '{{reports.latest("AAPL").content}}'},
    )

    embed_template = create_template(
        client,
        name="Dynamic Cycle Embed",
        content='{{reports.latest("AAPL").content}}',
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report['name']}]" in compiled


def test_report_filters_and_dynamic_selectors_ignore_reports_without_analysis_metadata(
    client: TestClient,
) -> None:
    uploaded = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nLegacy body.",
                "text/markdown",
            )
        },
        data={"slug": "uploaded_note"},
    ).json()

    external = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Metadata Report",
            "content": "AAPL body",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                }
            },
        },
    ).json()

    filtered = client.get("/api/v1/reports", params={"ticker": "AAPL"})
    assert filtered.status_code == 200
    assert [report["id"] for report in filtered.json()] == [external["id"]]

    selector_template = create_template(
        client,
        name="Missing Analysis Selector",
        content=(
            'TickerLatest: {{reports.latest("AAPL").name}}\n'
            'NoTickerMatch: before{{reports.latest("MSFT").content}}after'
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert f"TickerLatest: {external['name']}" in compiled
    assert f"TickerLatest: {uploaded['name']}" not in compiled
    assert "NoTickerMatch: beforeafter" in compiled


def test_init_db_upgrades_legacy_report_schema(database_url: str) -> None:
    """Verify that upgrade_legacy_schema adds slug, source, and metadata to a
    pre-existing reports table that only has the original (name, content) columns."""
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE reports (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO reports (name, content)
                VALUES ('legacy_report_20260101_120000', '# Legacy')
                """
            )

        init_db(database_url)

        inspector = inspect(engine)
        report_columns = {column["name"]: column for column in inspector.get_columns("reports")}

        assert "slug" in report_columns
        assert report_columns["slug"]["nullable"] is False

        assert "source" in report_columns
        assert report_columns["source"]["nullable"] is False

        assert "metadata" in report_columns

        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT slug, source, metadata FROM reports"
                " WHERE name = 'legacy_report_20260101_120000'"
            ).one()

        assert row[0] == "legacy_report_20260101_120000"  # slug backfilled from name
        assert row[1] == "compiled"  # source defaults to 'compiled'
        assert row[2] == {}  # metadata defaults to empty object
    finally:
        engine.dispose()
