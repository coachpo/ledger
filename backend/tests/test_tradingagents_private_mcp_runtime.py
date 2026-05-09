# pyright: reportExplicitAny=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import McpClientBoundary
from app.core.config import reset_settings_cache
from app.models.model_connection import ModelConnection
from app.services.run_service import RunService
from tests.test_workflow_package_runtime_api import _drain_run_queue, _wait_for_run

_FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)

_LAUNCH_PARAMETERS = {
    "ticker": "AAPL",
    "asOfDate": "2026-05-08",
    "portfolioId": "tradingagents_demo",
    "horizonDays": 30,
    "benchmarkSymbol": "SPY",
    "initialInvestmentDebateState": {},
    "initialRiskDebateState": {},
}
_MCP_FUNCTION_NAME = "mcp_exa_web_search_exa"
_MCP_QUERY = "AAPL latest company news"


class _TradingAgentsOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    requested_mcp = False

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self) -> _TradingAgentsOpenAIClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.requested_mcp = False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        if _has_tool(kwargs, _MCP_FUNCTION_NAME) and not type(self).requested_mcp:
            type(self).requested_mcp = True
            return {
                "id": "resp_exa_request",
                "output": [
                    {
                        "type": "function_call",
                        "name": _MCP_FUNCTION_NAME,
                        "arguments": json.dumps({"query": _MCP_QUERY}),
                        "call_id": "call_exa_search",
                    }
                ],
                "usage": {"total_tokens": 2},
            }
        return _json_response(_output_for_request_schema(kwargs))


class _RecordingMcpToolClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def call_tool(
        self,
        *,
        boundary: McpClientBoundary,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        self.calls.append(
            {
                "boundary": boundary,
                "tool_name": tool_name,
                "arguments": arguments,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"content": "Exa smoke search result for AAPL."}


def _fixture_source() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def _seed_tradingagents_model(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                name="TradingAgents Primary Model",
                description="TradingAgents smoke model binding.",
                base_url="https://runtime-v1.example.com/v1",
                model_id="gpt-package-v1",
                api_style="responses",
                timeout_seconds=31,
                secret_payload={"apiKey": "sk-tradingagents-runtime"},
            )
        )
        session.commit()


def _create_tradingagents_package(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/workflow-packages", json={"manifestSource": _fixture_source()})
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _has_tool(kwargs: dict[str, Any], tool_name: str) -> bool:
    return any(tool.get("name") == tool_name for tool in kwargs.get("tools") or [])


def _json_response(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "resp_structured_output",
        "output_text": json.dumps(output),
        "usage": {"total_tokens": 1},
    }


def _output_for_request_schema(kwargs: dict[str, Any]) -> dict[str, Any]:
    text = cast(dict[str, Any], kwargs["text"])
    text_format = cast(dict[str, Any], text["format"])
    schema = cast(dict[str, Any], text_format["schema"])
    properties = cast(dict[str, Any], schema.get("properties") or {})
    required = cast(list[str], schema.get("required") or list(properties))
    return {name: _value_for_schema(name, properties.get(name)) for name in required}


def _value_for_schema(name: str, schema: object) -> Any:
    if name == "nextState":
        return {}
    schema_map = schema if isinstance(schema, dict) else {}
    schema_type = schema_map.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), "string")
    if schema_type == "object":
        return {}
    if schema_type == "array":
        return [f"smoke {name}"]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    return f"smoke {name}"


def _allow_http_sse_url(url: str, *, resolved_hosts: object = None) -> str:
    del resolved_hosts
    return url


def _disable_queue_worker(self: RunService) -> None:
    del self


def test_tradingagents_package_smoke_calls_private_exa_mcp(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
) -> None:
    _TradingAgentsOpenAIClient.reset()
    mcp_client = _RecordingMcpToolClient()
    monkeypatch.setenv("MCP_RUNTIME_ENABLED", "true")
    reset_settings_cache()
    request.addfinalizer(reset_settings_cache)
    monkeypatch.setattr("app.services.run_service.OpenAI", _TradingAgentsOpenAIClient)
    monkeypatch.setattr("app.agents.mcp.runtime.DefaultMcpToolClient", lambda: mcp_client)
    monkeypatch.setattr("app.agents.mcp.boundaries.validate_http_sse_url", _allow_http_sse_url)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", _disable_queue_worker)

    _seed_tradingagents_model(session_factory)
    created = _create_tradingagents_package(client)
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "advisory_research", "parameters": _LAUNCH_PARAMETERS},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded", detail
    assert detail["finalOutput"]["posture"] == "smoke posture"
    assert _TradingAgentsOpenAIClient.requested_mcp is True
    assert len(mcp_client.calls) == 1
    call = mcp_client.calls[0]
    boundary = cast(McpClientBoundary, call["boundary"])
    assert boundary.key == "exa"
    assert boundary.url == "https://mcp.exa.ai/mcp?tools=web_search_exa"
    assert call["tool_name"] == "web_search_exa"
    assert call["arguments"] == {"query": _MCP_QUERY}
