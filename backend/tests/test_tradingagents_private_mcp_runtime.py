# pyright: reportExplicitAny=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import NotFoundError
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
    reject_followup = False
    rejected_continuation = False

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
        cls.reject_followup = False
        cls.rejected_continuation = False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        if len(type(self).create_calls) > 2:
            raise AssertionError(
                f"Unexpected third provider call: requested_mcp={type(self).requested_mcp}, "
                f"rejected_continuation={type(self).rejected_continuation}, kwargs={kwargs!r}"
            )
        if len(type(self).create_calls) == 1:
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
        if type(self).reject_followup and not type(self).rejected_continuation:
            type(self).rejected_continuation = True
            request = httpx.Request("POST", "https://api.openai.local/v1/responses")
            response = httpx.Response(
                404,
                request=request,
                json={"error": {"message": "previous_response_id rejected by provider"}},
            )
            raise NotFoundError(
                "previous_response_id rejected by provider", response=response, body=response.json()
            )
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


def _single_agent_fixture_source(*, package_key: str) -> str:
    return f"""apiVersion: ledger.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: TradingAgents MCP Rejection Fixture
  description: Single-agent package fixture for rejected continuation coverage.
spec:
  inputs:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
      asOfDate:
        type: string
      portfolioId:
        type: string
      horizonDays:
        type: integer
      benchmarkSymbol:
        type: string
      initialInvestmentDebateState:
        type: object
        additionalProperties: true
      initialRiskDebateState:
        type: object
        additionalProperties: true
    required:
      - ticker
      - asOfDate
      - portfolioId
      - horizonDays
      - benchmarkSymbol
      - initialInvestmentDebateState
      - initialRiskDebateState
  capabilityProfiles: []
  outputSchemas:
    - key: trader_proposal
      name: Trader Proposal
      description: Advisory portfolio proposal used for rejection coverage.
      jsonSchema:
        type: object
        additionalProperties: false
        properties:
          posture:
            type: string
          rationale:
            type: string
          sizingNotes:
            type: string
        required: [posture, rationale, sizingNotes]
  mcpServers:
    - key: exa
      name: Exa Web Search
      description: Remote Exa MCP server for advisory information search.
      transport: http-sse
      url: https://mcp.exa.ai/mcp?tools=web_search_exa
      headers:
        Authorization: Bearer exa-inline-token
      query:
        exaApiKey: exa-inline-key
      toolKeys:
        - web_search_exa
  agents:
    - key: news_analyst
      name: News Analyst
      description: Produces company news context for the rejection workflow.
      modelConnection: tradingagents_primary_model
      systemPrompt: Use the Exa MCP web search tool to search current company information, then return a short JSON summary.
      inputSchema:
        type: object
        additionalProperties: true
      outputSchema: trader_proposal
      capabilityProfiles: []
      mcpServers: [exa]
      budgetUsd: "0.20"
  workflows:
    - key: news_research
      name: News Research
      inputSchema:
        type: object
        additionalProperties: false
        properties:
          ticker:
            type: string
          asOfDate:
            type: string
          portfolioId:
            type: string
          horizonDays:
            type: integer
          benchmarkSymbol:
            type: string
          initialInvestmentDebateState:
            type: object
            additionalProperties: true
          initialRiskDebateState:
            type: object
            additionalProperties: true
        required:
          - ticker
          - asOfDate
          - portfolioId
          - horizonDays
          - benchmarkSymbol
          - initialInvestmentDebateState
          - initialRiskDebateState
      flow:
        kind: step
        id: news_analysis
        slot: analysis
        uses: news_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
          asOfDate: ${{{{ inputs.asOfDate }}}}
          portfolioId: ${{{{ inputs.portfolioId }}}}
          horizonDays: ${{{{ inputs.horizonDays }}}}
          benchmarkSymbol: ${{{{ inputs.benchmarkSymbol }}}}
          initialInvestmentDebateState: ${{{{ inputs.initialInvestmentDebateState }}}}
          initialRiskDebateState: ${{{{ inputs.initialRiskDebateState }}}}
      output:
        from: ${{{{ nodes.news_analysis.outputs.analysis }}}}
"""


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


def _create_tradingagents_package(
    client: TestClient,
    *,
    manifest_source: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source or _fixture_source()},
    )
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


def _allow_http_sse_url(
    url: str,
    *,
    resolved_hosts: object = None,
    allowed_secret_query_param_names: object = None,
) -> str:
    del resolved_hosts, allowed_secret_query_param_names
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
    created = _create_tradingagents_package(
        client,
        manifest_source=_single_agent_fixture_source(package_key="tradingagents_mcp_smoke"),
    )
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "news_research", "parameters": _LAUNCH_PARAMETERS},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded", detail
    assert detail["finalOutput"]["posture"] == "smoke posture"
    assert _TradingAgentsOpenAIClient.requested_mcp is True
    assert len(_TradingAgentsOpenAIClient.create_calls) == 2
    first_call = _TradingAgentsOpenAIClient.create_calls[0]
    second_call = _TradingAgentsOpenAIClient.create_calls[1]
    assert first_call.get("previous_response_id") is None
    assert _has_tool(first_call, _MCP_FUNCTION_NAME) is True
    assert second_call.get("previous_response_id") == "resp_exa_request"
    second_input = cast(list[dict[str, Any]], second_call.get("input"))
    assert second_input == [
        {
            "type": "function_call_output",
            "call_id": "call_exa_search",
            "output": cast(str, second_input[0]["output"]),
        }
    ]
    assert json.loads(cast(str, second_input[0]["output"])) == {
        "mcpServerKey": "exa",
        "mcpServerVersion": 1,
        "originalToolName": "web_search_exa",
        "output": {"content": "Exa smoke search result for AAPL."},
        "toolKey": "exa@1:mcp_exa_web_search_exa",
    }
    assert len(mcp_client.calls) == 1
    call = mcp_client.calls[0]
    boundary = cast(McpClientBoundary, call["boundary"])
    assert boundary.key == "exa"
    assert boundary.url == "https://mcp.exa.ai/mcp?tools=web_search_exa&exaApiKey=exa-inline-key"
    assert boundary.headers == {"Authorization": "Bearer exa-inline-token"}
    assert boundary.query == {"exaApiKey": "exa-inline-key"}
    assert call["tool_name"] == "web_search_exa"
    assert call["arguments"] == {"query": _MCP_QUERY}


def test_tradingagents_package_rejected_continuation_does_not_retry_statelessly(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    session_factory: sessionmaker[Session],
) -> None:
    _TradingAgentsOpenAIClient.reset()
    _TradingAgentsOpenAIClient.reject_followup = True
    mcp_client = _RecordingMcpToolClient()
    monkeypatch.setenv("MCP_RUNTIME_ENABLED", "true")
    reset_settings_cache()
    request.addfinalizer(reset_settings_cache)
    monkeypatch.setattr("app.services.run_service.OpenAI", _TradingAgentsOpenAIClient)
    monkeypatch.setattr("app.agents.mcp.runtime.DefaultMcpToolClient", lambda: mcp_client)
    monkeypatch.setattr("app.agents.mcp.boundaries.validate_http_sse_url", _allow_http_sse_url)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", _disable_queue_worker)

    _seed_tradingagents_model(session_factory)
    created = _create_tradingagents_package(
        client,
        manifest_source=_single_agent_fixture_source(package_key="tradingagents_mcp_rejection"),
    )
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "news_research", "parameters": _LAUNCH_PARAMETERS},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed", detail
    failure_detail = (
        detail.get("error")
        or detail.get("failureCause")
        or detail.get("failureMessage")
        or detail.get("errorMessage")
        or detail.get("message")
        or detail.get("statusDetail")
    )
    assert failure_detail is not None, detail
    assert "previous_response_id rejected by provider" in str(failure_detail)
    assert len(mcp_client.calls) == 1
    call = mcp_client.calls[0]
    boundary = cast(McpClientBoundary, call["boundary"])
    assert boundary.key == "exa"
    assert boundary.url == "https://mcp.exa.ai/mcp?tools=web_search_exa&exaApiKey=exa-inline-key"
    assert boundary.headers == {"Authorization": "Bearer exa-inline-token"}
    assert boundary.query == {"exaApiKey": "exa-inline-key"}
    assert call["tool_name"] == "web_search_exa"
    assert call["arguments"] == {"query": _MCP_QUERY}

    assert len(_TradingAgentsOpenAIClient.create_calls) == 2
    first_call = _TradingAgentsOpenAIClient.create_calls[0]
    second_call = _TradingAgentsOpenAIClient.create_calls[1]
    assert first_call.get("previous_response_id") is None
    assert _has_tool(first_call, _MCP_FUNCTION_NAME) is True
    assert second_call.get("previous_response_id") is not None
    assert "function_call_output" in str(second_call.get("input") or "")
    assert all(
        "function_call_output" not in str(call.get("input") or "")
        or call.get("previous_response_id") is not None
        for call in _TradingAgentsOpenAIClient.create_calls
    )
    assert _TradingAgentsOpenAIClient.rejected_continuation is True
