from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from decimal import Decimal
from typing import Any

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp import DefaultMcpConnectionTester
from app.core.config import reset_settings_cache
from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.run import Run
from app.models.workflow import Workflow
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.schemas.workflow import WorkflowCreate, WorkflowRead
from app.services.capability_service import (
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_LOOKUP_ACCESS_DENIED_CODE,
    REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
    CapabilityService,
)
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
from app.services.position_service import PositionService
from app.services.report_service import ReportService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService

_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_TRACE_SPAN_ID_PATTERN = re.compile(r"[0-9a-f]{16}")


def _assert_logfire_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_ID_PATTERN.fullmatch(value) is not None


def _assert_logfire_span_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_SPAN_ID_PATTERN.fullmatch(value) is not None


REFERENCE_STEP_ONE_AGENT_KEYS = (
    "financials_analyst",
    "news_analyst",
    "market_analyst",
    "industry_analyst",
    "economy_analyst",
    "price_analyst",
    "position_reader",
    "history_reader",
)
REFERENCE_SYNTHESIZER_KEY = "decision_synthesizer"
REFERENCE_CAPABILITY_KEY = "reference_runtime_tools"
REFERENCE_MCP_SERVER_KEY = "reference_runtime_data"
REFERENCE_DECISION_SCHEMA_KEY = "reference_trading_decision"


def _reference_workflow_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "horizon_days": {"type": "integer"},
        },
        "required": ["ticker", "horizon_days"],
        "additionalProperties": False,
    }


def _reference_note_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "signal": {"type": "string"},
        },
        "required": ["summary", "signal"],
        "additionalProperties": False,
    }


def _reference_trading_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
            "price_targets": {"type": "array", "items": {"type": "number"}},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action", "confidence", "rationale", "price_targets", "risks"],
        "additionalProperties": False,
    }


def _reference_synthesizer_input_schema(
    *,
    optional_agents: set[str] | None = None,
) -> dict[str, Any]:
    optional_keys = optional_agents or set()
    return {
        "type": "object",
        "properties": {key: _reference_note_schema() for key in REFERENCE_STEP_ONE_AGENT_KEYS},
        "required": [key for key in REFERENCE_STEP_ONE_AGENT_KEYS if key not in optional_keys],
        "additionalProperties": False,
    }


def _reference_workflow_payload(*, optional_agents: set[str] | None = None) -> dict[str, Any]:
    optional_keys = optional_agents or set()
    return {
        "key": "report_lookup_reference",
        "name": "Report Lookup Reference",
        "description": "Reference workflow runtime coverage.",
        "inputSchema": _reference_workflow_input_schema(),
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": key,
                        "slot": key,
                        "wiring": {
                            "ticker": {"from": "input", "path": "ticker"},
                            "horizon_days": {"from": "input", "path": "horizon_days"},
                        },
                        "optional": key in optional_keys,
                    }
                    for key in REFERENCE_STEP_ONE_AGENT_KEYS
                ],
            },
            {
                "index": 2,
                "agents": [
                    {
                        "agentKey": REFERENCE_SYNTHESIZER_KEY,
                        "slot": "decision",
                        "wiring": {
                            key: {"from": "step", "stepIndex": 1, "slot": key}
                            for key in REFERENCE_STEP_ONE_AGENT_KEYS
                        },
                    }
                ],
            },
        ],
        "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "decision"},
    }


def _build_skill(*, key: str, version: int, status: str, tools: list[str]) -> Capability:
    return Capability(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Capability toolset",
        tool_grants=[{"tool": tool} for tool in tools],
    )


def _reference_workflow_skill_tools(*, grant_report_lookup: bool) -> list[str]:
    tools = [
        "ledger.market_data.quote_lookup",
        "ledger.market_data.history_lookup",
    ]
    if grant_report_lookup:
        tools.append("ledger.reports.lookup")
    return tools


def _build_mcp_server(
    *,
    key: str,
    version: int,
    status: str,
    transport: str,
    enabled: bool = True,
) -> McpServer:
    config: dict[str, object]
    if transport == "stdio":
        config = {
            "name": f"{key}-{version}",
            "description": "MCP server",
            "enabled": enabled,
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "ledger_market_data"],
            "env": {},
        }
    else:
        config = {
            "name": f"{key}-{version}",
            "description": "MCP server",
            "enabled": enabled,
            "transport": "http-sse",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer secret-token"},
        }

    return McpServer(
        key=key,
        version=version,
        status=status,
        config=config,
    )


def _build_output_schema(*, key: str, version: int, status: str) -> OutputSchema:
    return OutputSchema(
        key=key,
        version=version,
        status=status,
        kind="standalone",
        name=f"{key}-{version}",
        description="Structured output schema",
        json_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        registry_refs=[],
    )


def _build_model_connection(
    *,
    name: str,
    key: str | None = None,
    status: str = "active",
    api_key: str | None = "sk-test-secret-1234",
    base_url: str = "https://api.openai.com/v1",
    model_id: str = "gpt-5.4-mini",
    reasoning_effort: str = "medium",
    timeout_seconds: int = 60,
    organization: str | None = None,
    project: str | None = None,
) -> ModelConnection:
    payload = {} if api_key is None else {"apiKey": api_key}
    return ModelConnection(
        key=key or name.strip().lower().replace(" ", "_"),
        status=status,
        name=name,
        description=f"{name} description",
        base_url=base_url,
        organization=organization,
        project=project,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        secret_payload=payload,
        has_api_key=api_key is not None,
        api_key_last4=None if api_key is None else api_key[-4:],
    )


def _build_agent_platform_agent(
    *,
    key: str,
    version: int,
    status: str,
    output_schema: OutputSchema,
    skill: Capability,
    mcp_server: McpServer,
    model_connection: ModelConnection | None = None,
    input_schema: dict[str, Any] | None = None,
    budget_usd: Decimal = Decimal("1.25000000"),
) -> Agent:
    if model_connection is None:
        model_connection_snapshot = {}
    else:
        model_connection_snapshot = build_model_connection_runtime_snapshot(model_connection)
    return Agent(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Agent configuration",
        model_connection_id=None if model_connection is None else model_connection.id,
        model_connection_snapshot=model_connection_snapshot,
        model=("openai:gpt-5.4-mini" if model_connection is None else model_connection.model_id),
        system_prompt="Analyze the ticker and return a typed result.",
        input_schema=input_schema
        or {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        output_schema_id=output_schema.id,
        output_schema_version=output_schema.version,
        capabilities=[
            {
                "capabilityId": skill.id,
                "capabilityKey": skill.key,
                "capabilityVersion": skill.version,
            }
        ],
        mcp_servers=[
            {
                "mcpServerId": mcp_server.id,
                "mcpServerKey": mcp_server.key,
                "mcpServerVersion": mcp_server.version,
            }
        ],
        budget_usd=budget_usd,
    )


def _seed_reference_workflow(
    session: Session,
    *,
    optional_agents: set[str] | None = None,
    budget_overrides: dict[str, Decimal] | None = None,
    grant_report_lookup: bool = True,
    resource_version: int = 1,
    workflow_key: str = "report_lookup_reference",
    workflow_name: str = "Report Lookup Reference",
    note_schema_key: str = "reference_analysis_note",
    decision_schema_key: str = REFERENCE_DECISION_SCHEMA_KEY,
    skill_key: str = REFERENCE_CAPABILITY_KEY,
    mcp_server_key: str = REFERENCE_MCP_SERVER_KEY,
    connection_name: str = "Reference Runtime Connection",
) -> WorkflowRead:
    optional_keys = optional_agents or set()
    budgets = budget_overrides or {}
    note_schema = _build_output_schema(
        key=note_schema_key,
        version=resource_version,
        status="published",
    )
    note_schema.json_schema = _reference_note_schema()
    decision_schema = _build_output_schema(
        key=decision_schema_key,
        version=resource_version,
        status="published",
    )
    decision_schema.json_schema = _reference_trading_decision_schema()
    skill = _build_skill(
        key=skill_key,
        version=resource_version,
        status="published",
        tools=_reference_workflow_skill_tools(grant_report_lookup=grant_report_lookup),
    )
    mcp_server = _build_mcp_server(
        key=mcp_server_key,
        version=resource_version,
        status="published",
        transport="stdio",
    )
    mcp_server.config = {
        "name": f"{mcp_server_key}-{resource_version}",
        "description": "MCP server",
        "enabled": True,
        "transport": "stdio",
        "command": "python3",
        "args": ["-V"],
        "env": {},
    }
    connection = _build_model_connection(name=f"{connection_name} v{resource_version}")
    session.add_all([note_schema, decision_schema, skill, mcp_server, connection])
    session.flush()

    created_agents = [
        _build_agent_platform_agent(
            key=agent_key,
            version=resource_version,
            status="published",
            output_schema=note_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema=_reference_workflow_input_schema(),
            budget_usd=budgets.get(agent_key, Decimal("0.05000000")),
        )
        for agent_key in REFERENCE_STEP_ONE_AGENT_KEYS
    ]
    created_agents.append(
        _build_agent_platform_agent(
            key=REFERENCE_SYNTHESIZER_KEY,
            version=resource_version,
            status="published",
            output_schema=decision_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema=_reference_synthesizer_input_schema(optional_agents=optional_keys),
            budget_usd=budgets.get(REFERENCE_SYNTHESIZER_KEY, Decimal("0.10000000")),
        )
    )
    session.add_all(created_agents)
    session.commit()
    workflow_payload = _reference_workflow_payload(optional_agents=optional_keys)
    workflow_payload["key"] = workflow_key
    workflow_payload["name"] = workflow_name
    return WorkflowService(session).create_workflow(WorkflowCreate.model_validate(workflow_payload))


def _seed_backend_report_lookup_workflow(
    session: Session,
    *,
    grant_report_lookup: bool,
    workflow_key: str = "backend_report_lookup_runtime",
    skill_key: str = "backend_report_lookup_runtime_skill",
    agent_key: str = "report_lookup_reader",
) -> WorkflowRead:
    note_schema = _build_output_schema(
        key=f"{workflow_key}_note",
        version=1,
        status="published",
    )
    note_schema.json_schema = _reference_note_schema()
    skill = _build_skill(
        key=skill_key,
        version=1,
        status="published",
        tools=(
            ["ledger.reports.lookup"]
            if grant_report_lookup
            else ["ledger.market_data.quote_lookup"]
        ),
    )
    mcp_server = _build_mcp_server(
        key=f"{workflow_key}_server",
        version=1,
        status="published",
        transport="stdio",
    )
    mcp_server.config = {
        "name": f"{workflow_key}_server-1",
        "description": "MCP server",
        "enabled": True,
        "transport": "stdio",
        "command": "python3",
        "args": ["-V"],
        "env": {},
    }
    connection = _build_model_connection(name=f"{workflow_key} connection")
    session.add_all([note_schema, skill, mcp_server, connection])
    session.flush()
    agent = _build_agent_platform_agent(
        key=agent_key,
        version=1,
        status="published",
        output_schema=note_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
        input_schema=_reference_workflow_input_schema(),
        budget_usd=Decimal("0.05000000"),
    )
    session.add(agent)
    session.commit()
    return WorkflowService(session).create_workflow(
        WorkflowCreate.model_validate(
            {
                "key": workflow_key,
                "name": "Backend Report Lookup Runtime",
                "inputSchema": _reference_workflow_input_schema(),
                "steps": [
                    {
                        "index": 1,
                        "agents": [
                            {
                                "agentKey": agent_key,
                                "slot": "analysis",
                                "wiring": {
                                    "ticker": {"from": "input", "path": "ticker"},
                                    "horizon_days": {
                                        "from": "input",
                                        "path": "horizon_days",
                                    },
                                },
                            }
                        ],
                    }
                ],
                "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
            }
        )
    )


def _seed_backend_position_lookup_workflow(
    session: Session,
    *,
    grant_position_lookup: bool,
    grant_report_lookup: bool = False,
    workflow_key: str = "backend_position_lookup_runtime",
    skill_key: str = "backend_position_lookup_runtime_skill",
    agent_key: str = "position_lookup_reader",
) -> WorkflowRead:
    note_schema = _build_output_schema(
        key=f"{workflow_key}_note",
        version=1,
        status="published",
    )
    note_schema.json_schema = _reference_note_schema()
    tools: list[str] = []
    if grant_report_lookup:
        tools.append("ledger.reports.lookup")
    if grant_position_lookup:
        tools.append("ledger.positions.lookup")
    if not tools:
        tools.append("ledger.market_data.quote_lookup")
    skill = _build_skill(
        key=skill_key,
        version=1,
        status="published",
        tools=tools,
    )
    mcp_server = _build_mcp_server(
        key=f"{workflow_key}_server",
        version=1,
        status="published",
        transport="stdio",
    )
    mcp_server.config = {
        "name": f"{workflow_key}_server-1",
        "description": "MCP server",
        "enabled": True,
        "transport": "stdio",
        "command": "python3",
        "args": ["-V"],
        "env": {},
    }
    connection = _build_model_connection(name=f"{workflow_key} connection")
    session.add_all([note_schema, skill, mcp_server, connection])
    session.flush()
    agent = _build_agent_platform_agent(
        key=agent_key,
        version=1,
        status="published",
        output_schema=note_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
        input_schema=_reference_workflow_input_schema(),
        budget_usd=Decimal("0.05000000"),
    )
    session.add(agent)
    session.commit()
    return WorkflowService(session).create_workflow(
        WorkflowCreate.model_validate(
            {
                "key": workflow_key,
                "name": "Backend Position Lookup Runtime",
                "inputSchema": _reference_workflow_input_schema(),
                "steps": [
                    {
                        "index": 1,
                        "agents": [
                            {
                                "agentKey": agent_key,
                                "slot": "analysis",
                                "wiring": {
                                    "ticker": {"from": "input", "path": "ticker"},
                                    "horizon_days": {
                                        "from": "input",
                                        "path": "horizon_days",
                                    },
                                },
                            }
                        ],
                    }
                ],
                "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
            }
        )
    )


def _seed_position_lookup_reference_context(session: Session) -> None:
    portfolio = Portfolio(
        name="Position Lookup Reference",
        slug="position_lookup_reference",
        description="Reference portfolio for position-lookup runtime coverage.",
        base_currency="USD",
    )
    session.add(portfolio)
    session.flush()
    session.add_all(
        [
            Position(
                portfolio_id=portfolio.id,
                symbol="NVDA",
                name="NVIDIA Corporation",
                quantity=Decimal("12.00000000"),
                average_cost=Decimal("101.50000000"),
                currency="USD",
                last_source="manual",
            ),
            Position(
                portfolio_id=portfolio.id,
                symbol="MSFT",
                name="Microsoft Corporation",
                quantity=Decimal("5.00000000"),
                average_cost=Decimal("220.00000000"),
                currency="USD",
                last_source="manual",
            ),
        ]
    )
    session.commit()


def _seed_report_lookup_reference_context(session: Session) -> None:
    portfolio = Portfolio(
        name="Report Lookup Reference",
        slug="report_lookup_reference",
        description="Reference portfolio for report-lookup runtime coverage.",
        base_currency="USD",
    )
    session.add(portfolio)
    session.flush()
    session.add(
        Position(
            portfolio_id=portfolio.id,
            symbol="NVDA",
            name="NVIDIA Corporation",
            quantity=Decimal("12.00000000"),
            average_cost=Decimal("101.50000000"),
            currency="USD",
            last_source="manual",
        )
    )
    session.add(
        Report(
            name="nvda_lookup_reference",
            slug="nvda_lookup_reference",
            source="external",
            content="# NVDA reference\n\nRevenue acceleration remains intact.",
            metadata_={
                "tags": ["news", "earnings"],
                "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
            },
        )
    )
    session.commit()


class _FakeMcpConnectionTester:
    def __init__(self, *, ok: bool = True, message: str = "connection ok") -> None:
        self.ok = ok
        self.message = message
        self.boundaries = []

    def test(self, boundary):
        self.boundaries.append(boundary)
        from app.agents.mcp import McpConnectionTestResult

        return McpConnectionTestResult(ok=self.ok, message=self.message)


def _model_connection_payload(
    *,
    key: str = "primary_openai",
    name: str = "Primary OpenAI",
    description: str = "Primary model connection.",
    base_url: str = "https://api.openai.com",
    organization: str | None = None,
    project: str | None = None,
    model_id: str = "gpt-5.4-mini",
    reasoning_effort: str = "medium",
    timeout_seconds: int = 60,
    api_key: str | None = "sk-test-secret-1234",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "key": key,
        "name": name,
        "description": description,
        "baseUrl": base_url,
        "modelId": model_id,
        "reasoningEffort": reasoning_effort,
        "timeoutSeconds": timeout_seconds,
    }
    if organization is not None:
        payload["organization"] = organization
    if project is not None:
        payload["project"] = project
    if api_key is not None:
        payload["apiKey"] = api_key
    return payload


class _FakeOpenAIResponse:
    def __init__(self, request_id: str | None = "req_model_connection_test") -> None:
        self._request_id = request_id


class _RecordingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    request_id: str | None = "req_model_connection_test"

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _FakeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        return _FakeOpenAIResponse(type(self).request_id)

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.request_id = "req_model_connection_test"


class _FailingOpenAIClient(_RecordingOpenAIClient):
    failure_message = "Provider rejected sk-test-secret-1234"

    def create(self, **kwargs: Any) -> _FakeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        raise Exception(type(self).failure_message)

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.failure_message = "Provider rejected sk-test-secret-1234"


class _RuntimeOpenAIUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


class _RuntimeOpenAIResponse:
    def __init__(self, *, output_text: str, total_tokens: int) -> None:
        self.output_text = output_text
        self.usage = _RuntimeOpenAIUsage(total_tokens)


class _RuntimeRecordingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    output_text = '{"summary": "saved connection output"}'
    total_tokens = 17

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        return _RuntimeOpenAIResponse(
            output_text=type(self).output_text,
            total_tokens=type(self).total_tokens,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.output_text = '{"summary": "saved connection output"}'
        cls.total_tokens = 17


class _RuntimeFailingOpenAIClient(_RuntimeRecordingOpenAIClient):
    exception_factory = staticmethod(lambda: Exception("provider failure"))

    def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        raise type(self).exception_factory()

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.exception_factory = staticmethod(lambda: Exception("provider failure"))


class _RuntimeToolCallResponse:
    def __init__(
        self,
        *,
        response_id: str,
        output: list[dict[str, Any]] | None = None,
        output_text: str | None = None,
        total_tokens: int,
    ) -> None:
        self.id = response_id
        self.output = list(output or [])
        self.output_text = output_text
        self.usage = _RuntimeOpenAIUsage(total_tokens)


def _assert_openai_strict_tool_schemas(tools: list[dict[str, Any]]) -> None:
    for tool in tools:
        if tool.get("strict") is not True:
            continue
        assert tool.get("type") == "function"
        parameters = tool.get("parameters")
        assert isinstance(parameters, dict)
        properties = parameters.get("properties")
        assert isinstance(properties, dict)
        assert parameters.get("required") == list(properties)
        assert parameters.get("additionalProperties") is False

        if tool.get("name") == "ledger_reports_lookup":
            assert properties["ticker"]["type"] == ["string", "null"]
            assert properties["tag"]["type"] == ["string", "null"]
            assert properties["reviewType"]["type"] == ["string", "null"]
            assert properties["portfolioSlug"]["type"] == ["string", "null"]
            assert properties["source"]["type"] == ["string", "null"]
            assert properties["source"]["enum"] == ["compiled", "uploaded", "external", None]
            assert properties["limit"]["type"] == ["integer", "null"]
            assert properties["offset"]["type"] == ["integer", "null"]
        elif tool.get("name") == "ledger_positions_lookup":
            assert properties["portfolioSlug"]["type"] == "string"
            assert properties["symbol"]["type"] == ["string", "null"]
            assert properties["limit"]["type"] == ["integer", "null"]
            assert properties["offset"]["type"] == ["integer", "null"]


class _RuntimeToolCallingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    expect_report_lookup_tool = True
    tool_arguments_json = '{"ticker":"NVDA","limit":1}'
    final_output_text = '{"summary":"tool loop output","signal":"bullish"}'
    captured_lookup_arguments: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeToolCallResponse:
        type(self).create_calls.append(kwargs)
        call_number = len(type(self).create_calls)
        if call_number == 1:
            tools = kwargs.get("tools")
            if type(self).expect_report_lookup_tool:
                assert isinstance(tools, list)
                _assert_openai_strict_tool_schemas(tools)
                assert tools[0]["name"] == "ledger_reports_lookup"
            else:
                assert "tools" not in kwargs
            return _RuntimeToolCallResponse(
                response_id="resp_report_lookup_1",
                output=[
                    {
                        "type": "function_call",
                        "name": "ledger_reports_lookup",
                        "arguments": type(self).tool_arguments_json,
                        "call_id": "call_report_lookup_1",
                    }
                ],
                total_tokens=11,
            )
        assert kwargs["previous_response_id"] == "resp_report_lookup_1"
        output_items = kwargs["input"]
        assert output_items[0]["type"] == "function_call_output"
        assert output_items[0]["call_id"] == "call_report_lookup_1"
        return _RuntimeToolCallResponse(
            response_id="resp_report_lookup_2",
            output_text=type(self).final_output_text,
            total_tokens=13,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.expect_report_lookup_tool = True
        cls.tool_arguments_json = '{"ticker":"NVDA","limit":1}'
        cls.final_output_text = '{"summary":"tool loop output","signal":"bullish"}'


class _RuntimePositionToolCallingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    expected_tool_names: list[str] | None = ["ledger_positions_lookup"]
    tool_call_name: str | None = "ledger_positions_lookup"
    tool_arguments_json = (
        '{"portfolioSlug":"position_lookup_reference","symbol":"NVDA","limit":1,"offset":0}'
    )
    final_output_text = '{"summary":"position tool loop output","signal":"bullish"}'

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeToolCallResponse:
        type(self).create_calls.append(kwargs)
        call_number = len(type(self).create_calls)
        if call_number == 1:
            expected_tool_names = type(self).expected_tool_names
            if expected_tool_names is None:
                assert "tools" not in kwargs
            else:
                tools = kwargs.get("tools")
                assert isinstance(tools, list)
                _assert_openai_strict_tool_schemas(tools)
                assert [tool["name"] for tool in tools] == expected_tool_names
            tool_call_name = type(self).tool_call_name
            if tool_call_name is None:
                return _RuntimeToolCallResponse(
                    response_id="resp_position_lookup_final",
                    output_text=type(self).final_output_text,
                    total_tokens=11,
                )
            return _RuntimeToolCallResponse(
                response_id="resp_position_lookup_1",
                output=[
                    {
                        "type": "function_call",
                        "name": tool_call_name,
                        "arguments": type(self).tool_arguments_json,
                        "call_id": "call_position_lookup_1",
                    }
                ],
                total_tokens=11,
            )
        assert kwargs["previous_response_id"] == "resp_position_lookup_1"
        output_items = kwargs["input"]
        assert output_items[0]["type"] == "function_call_output"
        assert output_items[0]["call_id"] == "call_position_lookup_1"
        return _RuntimeToolCallResponse(
            response_id="resp_position_lookup_2",
            output_text=type(self).final_output_text,
            total_tokens=13,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.expected_tool_names = ["ledger_positions_lookup"]
        cls.tool_call_name = "ledger_positions_lookup"
        cls.tool_arguments_json = (
            '{"portfolioSlug":"position_lookup_reference","symbol":"NVDA","limit":1,"offset":0}'
        )
        cls.final_output_text = '{"summary":"position tool loop output","signal":"bullish"}'


def _build_api_status_error(*, message: str, status_code: int = 400) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(
        message,
        response=response,
        body={"error": {"message": message}},
    )


def _build_api_connection_error(
    *,
    message: str = "Connection error.",
) -> openai.APIConnectionError:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return openai.APIConnectionError(message=message, request=request)


def test_agent_platform_capability_service_resolves_versioned_rows_to_server_declared_toolsets(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            _build_skill(
                key="market_research",
                version=1,
                status="published",
                tools=["ledger.market_data.quote_lookup", "ledger.reports.lookup"],
            )
        )
        session.add(
            _build_skill(
                key="market_research",
                version=2,
                status="draft",
                tools=["ledger.market_data.history_lookup", "ledger.reports.lookup"],
            )
        )
        session.commit()

        service = CapabilityService(session, tool_catalog=get_default_tool_catalog())
        published = service.resolve_toolset_version("market_research", None)
        draft = service.resolve_toolset_version("market_research", 2)

        assert published.capability_version == 1
        assert [tool.key for tool in published.tools] == [
            "ledger.market_data.quote_lookup",
            "ledger.reports.lookup",
        ]
        assert published.tools[0].module == "app.agents.tool_catalog.server_declared"
        assert draft.capability_version == 2
        assert [tool.key for tool in draft.tools] == [
            "ledger.market_data.history_lookup",
            "ledger.reports.lookup",
        ]


def test_agent_platform_mcp_connection_test_builds_deterministic_boundaries(
    session_factory: sessionmaker[Session],
) -> None:
    tester = _FakeMcpConnectionTester(message="boundary ok")
    with session_factory() as session:
        published = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        draft = _build_mcp_server(
            key="market_data",
            version=2,
            status="draft",
            transport="stdio",
            enabled=False,
        )
        session.add_all([published, draft])
        session.commit()
        session.refresh(published)
        session.refresh(draft)

        service = McpServerService(session, connection_tester=tester)
        published_boundary = service.build_client_boundary_version(
            "market_data",
            None,
            require_enabled=True,
        )
        draft_boundary = service.build_client_boundary_version("market_data", 2)
        tested = service.test_connection(published.id)

        assert published_boundary.transport == "http-sse"
        assert published_boundary.url == "https://example.com/mcp"
        assert published_boundary.headers == {"Authorization": "Bearer secret-token"}
        assert draft_boundary.transport == "stdio"
        assert draft_boundary.command == ("python", "-m", "ledger_market_data")
        assert draft_boundary.enabled is False
        assert tested.ok is True
        assert tested.message == "boundary ok"
        assert tested.boundary.header_names == ["Authorization"]
        assert tester.boundaries[-1].key == "market_data"
        assert tester.boundaries[-1].version == 1


def test_agent_platform_mcp_boundary_validation_uses_flat_field_names(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        server = McpServer(
            key="market_data",
            version=1,
            status="published",
            config={
                "name": "market_data-1",
                "description": "MCP server",
                "enabled": True,
                "transport": "unknown",
            },
        )
        session.add(server)
        session.commit()
        session.refresh(server)

        service = McpServerService(session, connection_tester=_FakeMcpConnectionTester())

        with pytest.raises(ApiError) as exc_info:
            service.build_client_boundary_version("market_data", None)

    assert exc_info.value.details == [
        {"field": "transport", "issue": "Server transport must be either 'stdio' or 'http-sse'"},
    ]


def test_agent_platform_model_connections_api_crud_redacts_secrets_and_persists_tests(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _RecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.model_connection_service.OpenAI", _RecordingOpenAIClient)

    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            organization="org-test",
            project="proj-test",
            reasoning_effort="high",
            timeout_seconds=75,
        ),
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()
    connection_id = created["id"]
    assert created["key"] == "primary_openai"
    assert created["baseUrl"] == "https://api.openai.com/v1"
    assert created["hasApiKey"] is True
    assert created["apiKeyLast4"] == "1234"
    assert "apiKey" not in created and "secretPayload" not in created
    assert "sk-test-secret-1234" not in json.dumps(created)

    listed = client.get("/api/model-connections")
    assert listed.status_code == 200, listed.json()
    listed_item = listed.json()["items"][0]
    assert listed_item["id"] == connection_id
    assert listed_item["key"] == "primary_openai"
    assert listed_item["hasApiKey"] is True
    assert listed_item["apiKeyLast4"] == "1234"
    assert "apiKey" not in listed_item and "sk-test-secret-1234" not in json.dumps(listed_item)

    detail = client.get(f"/api/model-connections/{connection_id}")
    assert detail.status_code == 200, detail.json()
    assert detail.json()["id"] == connection_id
    assert detail.json()["key"] == "primary_openai"

    preserved = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"description": "Updated description.", "timeoutSeconds": 90},
    )
    assert preserved.status_code == 200, preserved.json()
    assert preserved.json()["apiKeyLast4"] == "1234"

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.secret_payload == {"apiKey": "sk-test-secret-1234"}
        assert row.timeout_seconds == 90

    replacement = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"apiKey": "sk-test-secret-9999", "reasoningEffort": "low"},
    )
    assert replacement.status_code == 200, replacement.json()
    assert replacement.json()["apiKeyLast4"] == "9999"

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.secret_payload == {"apiKey": "sk-test-secret-9999"}
        assert row.reasoning_effort == "low"

    connection_test = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert connection_test.status_code == 200, connection_test.json()
    body = connection_test.json()
    assert body["ok"] is True
    assert "Connection test succeeded" in body["message"]
    assert _RecordingOpenAIClient.init_calls[-1]["api_key"] == "sk-test-secret-9999"
    assert _RecordingOpenAIClient.init_calls[-1]["base_url"] == "https://api.openai.com/v1"
    assert _RecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "low"}

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None and row.last_tested_at is not None
        assert row.last_test_ok is True
        assert row.last_test_message == body["message"]

    archived = client.delete(f"/api/model-connections/{connection_id}")
    assert archived.status_code == 200, archived.json()
    assert archived.json()["status"] == "archived"
    assert client.get("/api/model-connections", params={"status": "active"}).json() == {"items": []}
    archived_items = client.get(
        "/api/model-connections",
        params={"status": "archived"},
    ).json()["items"]
    assert archived_items[0]["id"] == connection_id
    assert archived_items[0]["key"] == "primary_openai"


def test_agent_platform_model_connections_require_unique_immutable_keys(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    missing_key_payload = _model_connection_payload()
    missing_key_payload.pop("key")
    missing_key = client.post("/api/model-connections", json=missing_key_payload)
    assert missing_key.status_code == 422, missing_key.json()
    assert missing_key.json()["code"] == "validation_error"

    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_payload(key="Primary_OpenAI", name="Primary OpenAI"),
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()
    connection_id = created["id"]
    assert created["key"] == "primary_openai"

    duplicate = client.post(
        "/api/model-connections",
        json=_model_connection_payload(key="primary_openai", name="Secondary OpenAI"),
    )
    assert duplicate.status_code == 409, duplicate.json()
    assert duplicate.json()["code"] == "model_connection_duplicate_key"

    key_change = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"key": "secondary_openai"},
    )
    assert key_change.status_code == 422, key_change.json()
    assert key_change.json()["code"] == "validation_error"

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.key == "primary_openai"


def test_agent_platform_model_connections_patch_rejects_empty_api_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post("/api/model-connections", json=_model_connection_payload())
    assert create_response.status_code == 201, create_response.json()
    connection_id = create_response.json()["id"]

    rejected = client.patch(f"/api/model-connections/{connection_id}", json={"apiKey": ""})
    assert rejected.status_code == 422, rejected.json()
    body = rejected.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert any("apiKey" in detail["field"] for detail in body["details"])
    assert any("API key cannot be empty" in detail["issue"] for detail in body["details"])

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.secret_payload == {"apiKey": "sk-test-secret-1234"}
        assert row.api_key_last4 == "1234"


def test_agent_platform_model_connections_connection_test_failure_redacts_secret(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FailingOpenAIClient.reset()
    _FailingOpenAIClient.failure_message = "Provider rejected sk-test-secret-1234 during auth"
    monkeypatch.setattr("app.services.model_connection_service.OpenAI", _FailingOpenAIClient)

    create_response = client.post("/api/model-connections", json=_model_connection_payload())
    assert create_response.status_code == 201, create_response.json()
    connection_id = create_response.json()["id"]

    failed = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert failed.status_code == 200, failed.json()
    body = failed.json()
    assert body["ok"] is False
    assert "[REDACTED]" in body["message"]
    assert "sk-test-secret-1234" not in body["message"]

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None and row.last_tested_at is not None
        assert row.last_test_ok is False
        assert row.last_test_message == body["message"]
        assert row.secret_payload == {"apiKey": "sk-test-secret-1234"}
        assert "sk-test-secret-1234" not in (row.last_test_message or "")


def test_agent_platform_agent_run_route_uses_requested_agent_version_from_archived_anchor(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        return {
            "output": {"summary": f"{agent.key}:{resolved_input['ticker']}"},
            "tokens": 7,
            "costUsd": "0.01000000",
            "durationMs": 4,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema_v1 = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        output_schema_v2 = _build_output_schema(
            key="decision_schema",
            version=2,
            status="draft",
        )
        skill_v1 = _build_skill(
            key="market_research",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server_v1 = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        archived_connection = _build_model_connection(
            name="Archived historical connection",
            status="archived",
            api_key="sk-archived-9876",
        )
        session.add_all(
            [
                output_schema_v1,
                output_schema_v2,
                skill_v1,
                mcp_server_v1,
                archived_connection,
            ]
        )
        session.flush()

        agent_v1 = _build_agent_platform_agent(
            key="research_agent",
            version=1,
            status="deprecated",
            output_schema=output_schema_v1,
            skill=skill_v1,
            mcp_server=mcp_server_v1,
            model_connection=archived_connection,
        )
        agent_v2 = _build_agent_platform_agent(
            key="research_agent",
            version=2,
            status="archived",
            output_schema=output_schema_v2,
            skill=skill_v1,
            mcp_server=mcp_server_v1,
            model_connection=archived_connection,
        )
        session.add_all([agent_v1, agent_v2])
        session.commit()
        archived_agent_id = agent_v2.id
        historical_agent_id = agent_v1.id

    response = client.post(
        f"/api/agents/{archived_agent_id}/runs",
        params={"version": 1},
        json={"ticker": "MSFT"},
    )

    assert response.status_code == 201, response.json()
    created = response.json()
    assert created == {
        "id": created["id"],
        "targetKind": "agent",
        "targetId": historical_agent_id,
        "targetKey": "research_agent",
        "targetVersion": 1,
        "status": "running",
        "traceId": None,
        "createdAt": created["createdAt"],
    }

    detail = _wait_for_agent_platform_run(client, created["id"])

    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    assert detail["targetKind"] == "agent"
    assert detail["targetId"] == historical_agent_id
    assert detail["targetKey"] == "research_agent"
    assert detail["targetVersion"] == 1
    assert detail["input"] == {"ticker": "MSFT"}
    assert detail["finalOutput"] == {"summary": "research_agent:MSFT"}
    assert detail["perStepOutputs"] == {
        "1": [
            {
                "slot": "final_output",
                "agentId": historical_agent_id,
                "agentKey": "research_agent",
                "agentVersion": 1,
                "outputSchemaId": detail["perStepOutputs"]["1"][0]["outputSchemaId"],
                "outputSchemaVersion": 1,
                "resolvedInput": {"ticker": "MSFT"},
                "output": {"summary": "research_agent:MSFT"},
                "error": None,
                "status": "succeeded",
                "tokens": 7,
                "costUsd": "0.01000000",
                "durationMs": 4,
                "traceSpanId": detail["perStepOutputs"]["1"][0]["traceSpanId"],
            }
        ]
    }
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][0]["traceSpanId"])

    listed = client.get(
        "/api/runs",
        params={"targetKind": "agent", "targetId": historical_agent_id, "status": "succeeded"},
    )
    assert listed.status_code == 200, listed.json()
    assert listed.json() == {
        "items": [
            {
                "id": created["id"],
                "targetKind": "agent",
                "targetId": historical_agent_id,
                "targetKey": "research_agent",
                "targetVersion": 1,
                "status": "succeeded",
                "totalTokens": 7,
                "totalCostUsd": "0.01000000",
                "traceId": detail["traceId"],
                "startedAt": listed.json()["items"][0]["startedAt"],
                "finishedAt": listed.json()["items"][0]["finishedAt"],
            }
        ]
    }


def test_agent_platform_agent_create_rejects_archived_model_connection_selection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        output_schema = _build_output_schema(
            key="archived_agent_schema",
            version=1,
            status="published",
        )
        skill = _build_skill(
            key="archived_agent_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="archived_agent_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        archived_connection = _build_model_connection(
            name="Archived Save Target",
            status="archived",
            api_key="sk-archived-save-1234",
        )
        session.add_all([output_schema, skill, mcp_server, archived_connection])
        session.commit()

    response = client.post(
        "/api/agents",
        json={
            "manifestSource": f"""apiVersion: ledger.agent/v1
kind: Agent
metadata:
  key: archived_save_agent
  name: Archived Save Agent
  description: Should fail
spec:
  modelConnection: {archived_connection.key}
  systemPrompt: |
    Analyze the ticker and return a typed result.
  inputSchema:
    type: object
    properties:
      ticker:
        type: string
    required:
      - ticker
  outputSchema: {output_schema.key}@{output_schema.version}
  capabilities:
    - {skill.key}@{skill.version}
  mcpServers:
    - {mcp_server.key}@{mcp_server.version}
  budgetUsd: "1.25000000"
""",
        },
    )

    assert response.status_code == 422, response.json()
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Agent manifest validation failed"
    assert body["details"][0]["field"] == "manifestSource"
    assert body["details"][0]["path"] == "spec.modelConnection"
    assert "Active model connection" in body["details"][0]["issue"]


def test_agent_platform_run_uses_saved_model_connection_instead_of_env_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "db-backed runtime output"}'
    _RuntimeRecordingOpenAIClient.total_tokens = 29
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setenv("RUNTIME_AGENT_API_KEY", "sk-env-wrong-0000")
    monkeypatch.setenv("RUNTIME_AGENT_BASE_URL", "https://env.example.invalid/v1")
    monkeypatch.setenv("RUNTIME_AGENT_MODEL", "env-model-should-not-run")
    reset_settings_cache()

    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="db_runtime_agent",
            workflow_key="db_runtime_workflow",
            connection=_build_model_connection(
                name="Saved Runtime Connection",
                api_key="sk-db-right-7777",
                base_url="https://saved.example.com/v1",
                model_id="gpt-db-right",
                reasoning_effort="high",
                timeout_seconds=37,
                organization="org-db",
                project="proj-db",
            ),
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "TSLA"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "db-backed runtime output"}
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-db-right-7777",
        "base_url": "https://saved.example.com/v1",
        "timeout": 37.0,
        "organization": "org-db",
        "project": "proj-db",
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-db-right"
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "high"}
    assert "TSLA" in _RuntimeRecordingOpenAIClient.create_calls[-1]["input"]


def test_agent_platform_run_uses_agent_version_model_connection_snapshot_after_connection_update(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "snapshot runtime output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    with session_factory() as session:
        connection = _build_model_connection(
            name="Snapshot Runtime Connection",
            api_key="sk-original-secret-1111",
            base_url="https://snapshot-v1.example.com/v1",
            model_id="gpt-snapshot-v1",
            reasoning_effort="high",
            timeout_seconds=31,
            organization="org-v1",
            project="proj-v1",
        )
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="snapshot_runtime_agent",
            workflow_key="snapshot_runtime_workflow",
            connection=connection,
        )
        connection.base_url = "https://snapshot-v2.example.com/v1"
        connection.model_id = "gpt-snapshot-v2"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.organization = "org-v2"
        connection.project = "proj-v2"
        connection.secret_payload = {"apiKey": "sk-rotated-secret-2222"}
        connection.has_api_key = True
        connection.api_key_last4 = "2222"
        session.commit()

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "MSFT"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "snapshot runtime output"}
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-rotated-secret-2222",
        "base_url": "https://snapshot-v1.example.com/v1",
        "timeout": 31.0,
        "organization": "org-v1",
        "project": "proj-v1",
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-snapshot-v1"
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "high"}


@pytest.mark.parametrize(
    ("client_class", "exception_factory", "expected_code", "expected_message"),
    [
        (
            _RuntimeFailingOpenAIClient,
            lambda: _build_api_status_error(
                message="Model gpt-bad-model rejected sk-db-fail-4444",
                status_code=404,
            ),
            "agent_provider_status_error",
            "Model gpt-bad-model rejected [REDACTED]",
        ),
        (
            _RuntimeFailingOpenAIClient,
            lambda: _build_api_connection_error(
                message="dial tcp 127.0.0.1:9999: connect refused",
            ),
            "agent_provider_connection_error",
            "OpenAI request could not reach the API.",
        ),
    ],
)
def test_agent_platform_run_surfaces_saved_connection_provider_failures(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    client_class,
    exception_factory,
    expected_code: str,
    expected_message: str,
) -> None:
    client_class.reset()
    client_class.exception_factory = staticmethod(exception_factory)
    monkeypatch.setattr("app.services.run_service.OpenAI", client_class)

    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key=f"{expected_code}_agent",
            workflow_key=f"{expected_code}_workflow",
            connection=_build_model_connection(
                name=f"{expected_code} connection",
                api_key="sk-db-fail-4444",
                base_url="https://saved-failure.example.com/v1",
                model_id="gpt-db-fail",
            ),
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AAPL"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert detail["error"] == expected_message
    step_error = detail["perStepOutputs"]["1"][0]["error"]
    assert step_error["code"] == expected_code
    assert step_error["message"] == expected_message
    assert "sk-db-fail-4444" not in json.dumps(detail)


def test_agent_platform_run_fails_when_saved_model_connection_has_no_api_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="missing_key_agent",
            workflow_key="missing_key_workflow",
            connection=_build_model_connection(
                name="Missing API key connection",
                api_key=None,
            ),
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "NFLX"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert "missing an API key" in detail["error"]
    step_error = detail["perStepOutputs"]["1"][0]["error"]
    assert step_error["code"] == "agent_model_connection_api_key_missing"
    assert "missing an API key" in step_error["message"]


def test_agent_platform_run_rejects_invalid_input_without_persisting_run(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="invalid_input_agent",
            workflow_key="invalid_input_workflow",
            connection=_build_model_connection(name="Invalid Input Connection"),
        )

    response = client.post(f"/api/workflows/{workflow.id}/runs", json={})

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "run_invalid_input"
    assert response.json()["message"] == "Run input failed workflow input schema validation"
    assert response.json()["details"] == [{"field": "ticker", "issue": "Field required"}]

    with session_factory() as session:
        assert session.query(Run).all() == []

    listed = client.get(
        "/api/runs",
        params={"targetKind": "workflow", "targetId": workflow.id},
    )
    assert listed.status_code == 200, listed.json()
    assert listed.json() == {"items": []}


def test_agent_platform_agent_run_rejects_invalid_input_without_persisting_run(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _workflow, agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="invalid_input_agent_direct",
            workflow_key="invalid_input_workflow_direct",
            connection=_build_model_connection(name="Invalid Direct Agent Input Connection"),
        )

    response = client.post(f"/api/agents/{agent.id}/runs", json={})

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "run_invalid_input"
    assert response.json()["message"] == "Run input failed agent input schema validation"
    assert response.json()["details"] == [{"field": "ticker", "issue": "Field required"}]

    with session_factory() as session:
        assert session.query(Run).all() == []

    listed = client.get(
        "/api/runs",
        params={"targetKind": "agent", "targetId": agent.id},
    )
    assert listed.status_code == 200, listed.json()
    assert listed.json() == {"items": []}


def test_agent_platform_workflow_validation_rejects_optional_slots_for_required_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        output_schema = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        skill = _build_skill(
            key="market_research",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Workflow Validation Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()

        optional_source_agent = _build_agent_platform_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        required_consumer_agent = _build_agent_platform_agent(
            key="consumer_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema={
                "type": "object",
                "properties": {
                    "analysis": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    }
                },
                "required": ["analysis"],
            },
        )
        session.add_all([optional_source_agent, required_consumer_agent])
        session.commit()

        service = WorkflowService(session)
        with pytest.raises(ApiError) as excinfo:
            service.create_workflow(
                WorkflowCreate.model_validate(
                    {
                        "key": "market_review",
                        "name": "Market Review",
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
                                        "optional": True,
                                    }
                                ],
                            },
                            {
                                "index": 2,
                                "agents": [
                                    {
                                        "agentKey": "consumer_agent",
                                        "slot": "decision",
                                        "wiring": {
                                            "analysis": {
                                                "from": "step",
                                                "stepIndex": 1,
                                                "slot": "analysis",
                                            }
                                        },
                                    }
                                ],
                            },
                        ],
                        "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "decision"},
                    }
                )
            )

        assert excinfo.value.details == [
            {
                "field": "steps[1].agents[0].wiring.analysis",
                "issue": "Optional slots can only wire into optional target fields",
            }
        ]


def test_agent_platform_workflow_validation_allows_optional_slots_for_optional_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        output_schema = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        skill = _build_skill(
            key="market_research",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Workflow Validation Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()

        optional_source_agent = _build_agent_platform_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        optional_consumer_agent = _build_agent_platform_agent(
            key="consumer_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema={
                "type": "object",
                "properties": {
                    "analysis": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    }
                },
            },
        )
        session.add_all([optional_source_agent, optional_consumer_agent])
        session.commit()

        created = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "market_review",
                    "name": "Market Review",
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
                                    "optional": True,
                                }
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "consumer_agent",
                                    "slot": "decision",
                                    "wiring": {
                                        "analysis": {
                                            "from": "step",
                                            "stepIndex": 1,
                                            "slot": "analysis",
                                        }
                                    },
                                }
                            ],
                        },
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "decision"},
                }
            )
        )

        assert created.version == 1
        assert created.aggregate_budget_usd == Decimal("2.50000000")
        assert created.steps[0].agents[0].optional is True
        assert created.steps[1].agents[0].wiring["analysis"].source == "step"
        assert created.output_spec.agent_version == 1
        assert created.output_spec.output_schema_version == 1


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


def _create_single_agent_runtime_workflow(
    session: Session,
    *,
    agent_key: str,
    workflow_key: str,
    connection: ModelConnection,
) -> tuple[WorkflowRead, Agent]:
    output_schema = _build_output_schema(key=f"{agent_key}_schema", version=1, status="published")
    skill = _build_skill(
        key=f"{agent_key}_skill",
        version=1,
        status="published",
        tools=["ledger.market_data.quote_lookup"],
    )
    mcp_server = _build_mcp_server(
        key=f"{agent_key}_server",
        version=1,
        status="published",
        transport="http-sse",
    )
    session.add_all([output_schema, skill, mcp_server, connection])
    session.flush()
    agent = _build_agent_platform_agent(
        key=agent_key,
        version=1,
        status="published",
        output_schema=output_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
    )
    session.add(agent)
    session.commit()
    workflow = WorkflowService(session).create_workflow(
        WorkflowCreate.model_validate(
            {
                "key": workflow_key,
                "name": workflow_key.replace("_", " ").title(),
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
                                "agentKey": agent_key,
                                "slot": "analysis",
                                "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                            }
                        ],
                    }
                ],
                "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
            }
        )
    )
    return workflow, agent


def test_agent_platform_run_http_routes_cover_trigger_detail_and_list_flow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        return {
            "output": {"summary": f"{agent.key}:{resolved_input['ticker']}"},
            "tokens": 13,
            "costUsd": "0.01500000",
            "durationMs": 6,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="http_schema", version=1, status="published")
        skill = _build_skill(
            key="http_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="http_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="HTTP Run Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()

        http_agent = _build_agent_platform_agent(
            key="http_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        session.add(http_agent)
        session.commit()

        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "http_workflow",
                    "name": "HTTP Workflow",
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
                                    "agentKey": "http_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        }
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
                }
            )
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AVGO"})
    assert trigger.status_code == 201, trigger.json()
    created = trigger.json()
    assert created == {
        "id": created["id"],
        "targetKind": "workflow",
        "targetId": workflow.id,
        "targetKey": workflow.key,
        "targetVersion": workflow.version,
        "status": "running",
        "traceId": None,
        "createdAt": created["createdAt"],
    }

    detail = _wait_for_agent_platform_run(client, created["id"])
    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    assert detail["targetKind"] == "workflow"
    assert detail["targetId"] == workflow.id
    assert detail["targetKey"] == workflow.key
    assert detail["targetVersion"] == workflow.version
    assert detail["input"] == {"ticker": "AVGO"}
    assert detail["finalOutput"] == {"summary": "http_agent:AVGO"}
    assert detail["perStepOutputs"] == {
        "1": [
            {
                "slot": "analysis",
                "agentId": detail["perStepOutputs"]["1"][0]["agentId"],
                "agentKey": "http_agent",
                "agentVersion": 1,
                "outputSchemaId": detail["perStepOutputs"]["1"][0]["outputSchemaId"],
                "outputSchemaVersion": 1,
                "resolvedInput": {"ticker": "AVGO"},
                "output": {"summary": "http_agent:AVGO"},
                "error": None,
                "status": "succeeded",
                "tokens": 13,
                "costUsd": "0.01500000",
                "durationMs": 6,
                "traceSpanId": detail["perStepOutputs"]["1"][0]["traceSpanId"],
            }
        ]
    }
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][0]["traceSpanId"])

    listed = client.get(
        "/api/runs",
        params={"targetKind": "workflow", "targetId": workflow.id, "status": "succeeded"},
    )
    assert listed.status_code == 200, listed.json()
    assert listed.json() == {
        "items": [
            {
                "id": created["id"],
                "targetKind": "workflow",
                "targetId": workflow.id,
                "targetKey": workflow.key,
                "targetVersion": workflow.version,
                "status": "succeeded",
                "totalTokens": 13,
                "totalCostUsd": "0.01500000",
                "traceId": detail["traceId"],
                "startedAt": listed.json()["items"][0]["startedAt"],
                "finishedAt": listed.json()["items"][0]["finishedAt"],
            }
        ]
    }


def test_agent_platform_run_trigger_persists_running_row_and_finishes_in_background(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    step_one_gate = threading.Event()
    step_one_slots: list[str] = []

    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        if step_index == 1:
            step_one_slots.append(slot)
            if len(step_one_slots) == 2:
                step_one_gate.set()
            ready = await asyncio.to_thread(step_one_gate.wait, 0.25)
            if not ready:
                raise TimeoutError("step fan-out did not start in parallel")
            await asyncio.sleep(0.05)
            return {
                "output": {"summary": f"{slot}:{resolved_input['ticker']}"},
                "tokens": 11,
                "costUsd": "0.01000000",
                "durationMs": 25,
                "traceSpanId": None,
            }
        return {
            "output": {
                "summary": (
                    f"{resolved_input['analysisA']['summary']}|"
                    f"{resolved_input['analysisB']['summary']}"
                )
            },
            "tokens": 7,
            "costUsd": "0.01000000",
            "durationMs": 10,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="decision_schema", version=1, status="published")
        skill = _build_skill(
            key="market_research",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Workflow Validation Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()

        analyst_a = _build_agent_platform_agent(
            key="analyst_a",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        analyst_b = _build_agent_platform_agent(
            key="analyst_b",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        decision_agent = _build_agent_platform_agent(
            key="decision_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema={
                "type": "object",
                "properties": {
                    "analysisA": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    },
                    "analysisB": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    },
                },
                "required": ["analysisA", "analysisB"],
            },
        )
        session.add_all([analyst_a, analyst_b, decision_agent])
        session.commit()

        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "stock_review",
                    "name": "Stock Review",
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
                                    "agentKey": "analyst_a",
                                    "slot": "alpha",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                },
                                {
                                    "agentKey": "analyst_b",
                                    "slot": "beta",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                },
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "decision_agent",
                                    "slot": "decision",
                                    "wiring": {
                                        "analysisA": {
                                            "from": "step",
                                            "stepIndex": 1,
                                            "slot": "alpha",
                                        },
                                        "analysisB": {
                                            "from": "step",
                                            "stepIndex": 1,
                                            "slot": "beta",
                                        },
                                    },
                                }
                            ],
                        },
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "decision"},
                }
            )
        )

    response = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "NVDA"})
    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["status"] == "running"
    run_id = created["id"]

    immediate = client.get(f"/api/runs/{run_id}")
    assert immediate.status_code == 200, immediate.json()
    assert immediate.json()["status"] == "running"

    detail = _wait_for_agent_platform_run(client, run_id)
    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][0]["traceSpanId"])
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][1]["traceSpanId"])
    _assert_logfire_span_id(detail["perStepOutputs"]["2"][0]["traceSpanId"])
    assert detail["finalOutput"] == {"summary": "alpha:NVDA|beta:NVDA"}
    assert set(step_one_slots) == {"alpha", "beta"}
    assert [item["slot"] for item in detail["perStepOutputs"]["1"]] == ["alpha", "beta"]
    assert detail["perStepOutputs"]["1"][0]["resolvedInput"] == {"ticker": "NVDA"}
    assert detail["perStepOutputs"]["1"][0]["status"] == "succeeded"
    assert detail["perStepOutputs"]["2"][0]["resolvedInput"] == {
        "analysisA": {"summary": "alpha:NVDA"},
        "analysisB": {"summary": "beta:NVDA"},
    }


def test_agent_platform_run_detail_lists_persisted_monitor_fields_after_completion(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        return {
            "output": {"summary": f"{agent.key}:{resolved_input['ticker']}"},
            "tokens": 21,
            "costUsd": "0.02000000",
            "durationMs": 8,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="detail_schema", version=1, status="published")
        skill = _build_skill(
            key="detail_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="detail_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Detail Run Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        detail_agent = _build_agent_platform_agent(
            key="detail_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            budget_usd=Decimal("0.50000000"),
        )
        session.add(detail_agent)
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "detail_workflow",
                    "name": "Detail Workflow",
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
                                    "agentKey": "detail_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        }
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
                }
            )
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "MSFT"})
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run(client, run_id)

    list_response = client.get(
        "/api/runs",
        params={"targetKind": "workflow", "targetId": workflow.id, "status": "succeeded"},
    )
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [
        {
            "id": run_id,
            "targetKind": "workflow",
            "targetId": workflow.id,
            "targetKey": workflow.key,
            "targetVersion": workflow.version,
            "status": "succeeded",
            "totalTokens": 21,
            "totalCostUsd": "0.02000000",
            "traceId": detail["traceId"],
            "startedAt": list_response.json()["items"][0]["startedAt"],
            "finishedAt": list_response.json()["items"][0]["finishedAt"],
        }
    ]

    _assert_logfire_trace_id(detail["traceId"])
    assert detail["targetKind"] == "workflow"
    assert detail["targetId"] == workflow.id
    assert detail["targetKey"] == workflow.key
    assert detail["targetVersion"] == workflow.version
    assert detail["input"] == {"ticker": "MSFT"}
    assert detail["totalTokens"] == 21
    assert detail["totalCostUsd"] == "0.02000000"
    assert detail["perStepOutputs"] == {
        "1": [
            {
                "slot": "analysis",
                "agentId": detail["perStepOutputs"]["1"][0]["agentId"],
                "agentKey": "detail_agent",
                "agentVersion": 1,
                "outputSchemaId": detail["perStepOutputs"]["1"][0]["outputSchemaId"],
                "outputSchemaVersion": 1,
                "resolvedInput": {"ticker": "MSFT"},
                "output": {"summary": "detail_agent:MSFT"},
                "error": None,
                "status": "succeeded",
                "tokens": 21,
                "costUsd": "0.02000000",
                "durationMs": 8,
                "traceSpanId": detail["perStepOutputs"]["1"][0]["traceSpanId"],
            }
        ]
    }
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][0]["traceSpanId"])


def test_agent_platform_report_lookup_run_requires_capability_grant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeToolCallingOpenAIClient.reset()
    _RuntimeToolCallingOpenAIClient.expect_report_lookup_tool = False
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeToolCallingOpenAIClient)

    with session_factory() as session:
        session.add(
            Report(
                name="nvda_backend_lookup_denied",
                slug="nvda_backend_lookup_denied",
                source="external",
                content="# NVDA backend lookup denied\n\nRevenue acceleration remains intact.",
                metadata_={
                    "tags": ["earnings"],
                    "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
                },
            )
        )
        session.commit()
        workflow = _seed_backend_report_lookup_workflow(
            session,
            grant_report_lookup=False,
            workflow_key="backend_report_lookup_without_grant",
            skill_key="backend_report_lookup_without_grant_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == REPORT_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["agentKey"] == "report_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["error"] == {
        "code": REPORT_LOOKUP_ACCESS_DENIED_CODE,
        "message": REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
        "details": [],
    }
    assert "tools" not in _RuntimeToolCallingOpenAIClient.create_calls[0]


def test_agent_platform_report_lookup_run_uses_backend_owned_report_boundary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeToolCallingOpenAIClient.reset()
    _RuntimeToolCallingOpenAIClient.tool_arguments_json = (
        '{"ticker":"NVDA","tag":null,"reviewType":null,'
        '"portfolioSlug":null,"source":null,"limit":null,"offset":null}'
    )
    _RuntimeToolCallingOpenAIClient.final_output_text = (
        '{"summary":"backend report lookup used nvda_backend_lookup","signal":"bullish"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeToolCallingOpenAIClient)
    retired_mcp_calls: list[str] = []
    captured_lookup_calls: list[dict[str, Any]] = []

    def fail_if_retired_mcp_tested(
        self: DefaultMcpConnectionTester,
        boundary: Any,
    ) -> object:
        del self
        retired_mcp_calls.append(str(boundary.key))
        raise AssertionError("retired report-lookup MCP path should not be invoked")

    original_lookup_reports = ReportService.lookup_reports

    def fake_lookup_reports(
        self: ReportService,
        *,
        capability_references: list[dict[str, Any]],
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        portfolio_slug: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        captured_lookup_calls.append(
            {
                "capability_references": capability_references,
                "ticker": ticker,
                "tag": tag,
                "review_type": review_type,
                "portfolio_slug": portfolio_slug,
                "source": source,
                "limit": limit,
                "offset": offset,
            }
        )
        return original_lookup_reports(
            self,
            capability_references=capability_references,
            ticker=ticker,
            tag=tag,
            review_type=review_type,
            portfolio_slug=portfolio_slug,
            source=source,
            limit=limit,
            offset=offset,
        )

    monkeypatch.setattr(DefaultMcpConnectionTester, "test", fail_if_retired_mcp_tested)
    monkeypatch.setattr(ReportService, "lookup_reports", fake_lookup_reports)

    with session_factory() as session:
        session.add(
            Report(
                name="nvda_backend_lookup",
                slug="nvda_backend_lookup",
                source="external",
                content="# NVDA backend lookup\n\nRevenue acceleration remains intact.",
                metadata_={
                    "tags": ["earnings"],
                    "analysis": {"ticker": "NVDA", "reviewType": "fundamental"},
                },
            )
        )
        session.commit()
        workflow = _seed_backend_report_lookup_workflow(
            session,
            grant_report_lookup=True,
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "backend report lookup used nvda_backend_lookup",
        "signal": "bullish",
    }
    assert step_entry["agentKey"] == "report_lookup_reader"
    assert step_entry["status"] == "succeeded"
    assert step_entry["output"] == detail["finalOutput"]
    assert retired_mcp_calls == []
    assert len(captured_lookup_calls) == 1
    assert captured_lookup_calls[0]["ticker"] == "NVDA"
    assert captured_lookup_calls[0]["tag"] is None
    assert captured_lookup_calls[0]["review_type"] is None
    assert captured_lookup_calls[0]["portfolio_slug"] is None
    assert captured_lookup_calls[0]["source"] is None
    assert captured_lookup_calls[0]["limit"] == 50
    assert captured_lookup_calls[0]["offset"] == 0
    assert isinstance(captured_lookup_calls[0]["capability_references"], list)
    assert (
        _RuntimeToolCallingOpenAIClient.create_calls[0]["tools"][0]["name"]
        == "ledger_reports_lookup"
    )
    assert (
        "nvda_backend_lookup"
        in _RuntimeToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )


def test_agent_platform_position_lookup_run_requires_capability_grant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = ["ledger_reports_lookup"]
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = (
        '{"portfolioSlug":"position_lookup_reference","symbol":"NVDA"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)

    with session_factory() as session:
        workflow = _seed_backend_position_lookup_workflow(
            session,
            grant_position_lookup=False,
            grant_report_lookup=True,
            workflow_key="backend_position_lookup_without_grant",
            skill_key="backend_position_lookup_without_grant_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["agentKey"] == "position_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["error"] == {
        "code": POSITION_LOOKUP_ACCESS_DENIED_CODE,
        "message": POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
        "details": [],
    }
    first_tool_names = [
        tool["name"] for tool in _RuntimePositionToolCallingOpenAIClient.create_calls[0]["tools"]
    ]
    assert first_tool_names == ["ledger_reports_lookup"]
    assert "ledger_positions_lookup" not in first_tool_names


def test_agent_platform_position_lookup_run_uses_backend_owned_position_boundary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = (
        '{"portfolioSlug":"position_lookup_reference","symbol":" nvda ","limit":1,"offset":0}'
    )
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"backend position lookup used NVDA","signal":"bullish"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)
    retired_mcp_calls: list[str] = []
    captured_lookup_calls: list[dict[str, Any]] = []

    def fail_if_retired_mcp_tested(
        self: DefaultMcpConnectionTester,
        boundary: Any,
    ) -> object:
        del self
        retired_mcp_calls.append(str(boundary.key))
        raise AssertionError("retired position-lookup MCP path should not be invoked")

    original_lookup_positions = PositionService.lookup_positions

    def fake_lookup_positions(
        self: PositionService,
        *,
        capability_references: list[dict[str, object]],
        portfolio_slug: str,
        symbol: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PositionRead]:
        captured_lookup_calls.append(
            {
                "capability_references": capability_references,
                "portfolio_slug": portfolio_slug,
                "symbol": symbol,
                "limit": limit,
                "offset": offset,
                "quote_provider": self.quote_provider,
            }
        )
        return original_lookup_positions(
            self,
            capability_references=capability_references,
            portfolio_slug=portfolio_slug,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )

    monkeypatch.setattr(DefaultMcpConnectionTester, "test", fail_if_retired_mcp_tested)
    monkeypatch.setattr(PositionService, "lookup_positions", fake_lookup_positions)

    with session_factory() as session:
        _seed_position_lookup_reference_context(session)
        workflow = _seed_backend_position_lookup_workflow(
            session,
            grant_position_lookup=True,
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "backend position lookup used NVDA",
        "signal": "bullish",
    }
    assert step_entry["agentKey"] == "position_lookup_reader"
    assert step_entry["status"] == "succeeded"
    assert step_entry["output"] == detail["finalOutput"]
    assert retired_mcp_calls == []
    assert len(captured_lookup_calls) == 1
    assert captured_lookup_calls[0]["portfolio_slug"] == "position_lookup_reference"
    assert captured_lookup_calls[0]["symbol"] == "NVDA"
    assert captured_lookup_calls[0]["limit"] == 1
    assert captured_lookup_calls[0]["offset"] == 0
    assert captured_lookup_calls[0]["quote_provider"] is None
    assert isinstance(captured_lookup_calls[0]["capability_references"], list)
    assert captured_lookup_calls[0]["capability_references"][0]["capabilityKey"] == (
        "backend_position_lookup_runtime_skill"
    )
    assert (
        _RuntimePositionToolCallingOpenAIClient.create_calls[0]["tools"][0]["name"]
        == "ledger_positions_lookup"
    )
    tool_output = json.loads(
        _RuntimePositionToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    assert tool_output["count"] == 1
    assert tool_output["portfolioSlug"] == "position_lookup_reference"
    assert len(tool_output["positions"]) == 1
    position_payload = tool_output["positions"][0]
    assert set(position_payload) == {
        "id",
        "portfolioId",
        "symbol",
        "name",
        "quantity",
        "averageCost",
        "currency",
        "createdAt",
        "updatedAt",
    }
    assert position_payload["symbol"] == "NVDA"
    assert position_payload["name"] == "NVIDIA Corporation"
    assert position_payload["quantity"] == "12.00000000"
    assert position_payload["averageCost"] == "101.50000000"
    assert position_payload["currency"] == "USD"
    assert not {
        "marketPrice",
        "marketValue",
        "unrealizedGainLoss",
        "unrealizedGainLossPercent",
    } & set(position_payload)


def test_agent_platform_position_lookup_tool_order_is_deterministic_when_report_and_position_grants_exist(  # noqa: E501
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = [
        "ledger_reports_lookup",
        "ledger_positions_lookup",
    ]
    _RuntimePositionToolCallingOpenAIClient.tool_call_name = None
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"both tools exposed deterministically","signal":"neutral"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)

    with session_factory() as session:
        workflow = _seed_backend_position_lookup_workflow(
            session,
            grant_position_lookup=True,
            grant_report_lookup=True,
            workflow_key="backend_position_lookup_order",
            skill_key="backend_position_lookup_order_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "both tools exposed deterministically",
        "signal": "neutral",
    }
    assert [
        tool["name"] for tool in _RuntimePositionToolCallingOpenAIClient.create_calls[0]["tools"]
    ] == ["ledger_reports_lookup", "ledger_positions_lookup"]


@pytest.mark.parametrize(
    ("case_name", "arguments_json", "expected_message"),
    [
        (
            "unsupported_field",
            '{"portfolioSlug":"position_lookup_reference","unsupported":true}',
            "ledger_positions_lookup arguments contained unsupported fields: unsupported",
        ),
        (
            "non_string_portfolio_slug",
            '{"portfolioSlug":123}',
            "ledger_positions_lookup portfolioSlug must be a string.",
        ),
        (
            "non_integer_limit",
            '{"portfolioSlug":"position_lookup_reference","limit":"1"}',
            "ledger_positions_lookup limit must be an integer.",
        ),
        (
            "limit_too_high",
            '{"portfolioSlug":"position_lookup_reference","limit":201}',
            "ledger_positions_lookup limit must be at most 200.",
        ),
        (
            "negative_offset",
            '{"portfolioSlug":"position_lookup_reference","offset":-1}',
            "ledger_positions_lookup offset must be at least 0.",
        ),
    ],
    ids=[
        "unsupported-field",
        "non-string-portfolio-slug",
        "non-integer-limit",
        "limit-too-high",
        "negative-offset",
    ],
)
def test_agent_platform_position_lookup_run_rejects_invalid_tool_arguments(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    case_name: str,
    arguments_json: str,
    expected_message: str,
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = arguments_json
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)

    def fail_lookup_positions(self: PositionService, **kwargs: Any) -> list[PositionRead]:
        del self, kwargs
        raise AssertionError("invalid ledger_positions_lookup arguments should not hit service")

    monkeypatch.setattr(PositionService, "lookup_positions", fail_lookup_positions)

    with session_factory() as session:
        workflow = _seed_backend_position_lookup_workflow(
            session,
            grant_position_lookup=True,
            workflow_key=f"backend_position_lookup_invalid_{case_name}",
            skill_key=f"backend_position_lookup_invalid_{case_name}_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == expected_message
    assert step_entry["agentKey"] == "position_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["error"] == {
        "code": "agent_tool_call_invalid",
        "message": expected_message,
        "details": [],
    }
    assert len(_RuntimePositionToolCallingOpenAIClient.create_calls) == 1


def test_agent_platform_position_lookup_run_returns_empty_payload_for_unknown_slug(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = (
        '{"portfolioSlug":"unknown_portfolio","symbol":"NVDA","limit":10,"offset":0}'
    )
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"unknown slug returned empty positions","signal":"neutral"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)

    with session_factory() as session:
        workflow = _seed_backend_position_lookup_workflow(
            session,
            grant_position_lookup=True,
            workflow_key="backend_position_lookup_unknown_slug",
            skill_key="backend_position_lookup_unknown_slug_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "unknown slug returned empty positions",
        "signal": "neutral",
    }
    tool_output = json.loads(
        _RuntimePositionToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    assert tool_output == {
        "count": 0,
        "portfolioSlug": "unknown_portfolio",
        "positions": [],
    }


def test_agent_platform_budget_enforcement_fails_run_when_agent_budget_is_exceeded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        return {
            "output": {"summary": "too expensive"},
            "tokens": 12,
            "costUsd": "0.09000000",
            "durationMs": 12,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="budget_schema", version=1, status="published")
        skill = _build_skill(
            key="budget_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="budget_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Budget Run Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        budget_agent = _build_agent_platform_agent(
            key="budget_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            budget_usd=Decimal("0.05000000"),
        )
        session.add(budget_agent)
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "budget_workflow",
                    "name": "Budget Workflow",
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
                                    "agentKey": "budget_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        }
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "analysis"},
                }
            )
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "TSLA"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert "exceeded its budget" in str(detail["error"])
    assert detail["finalOutput"] is None
    assert detail["totalCostUsd"] == "0.09000000"
    assert detail["perStepOutputs"]["1"][0]["status"] == "failed"
    assert detail["perStepOutputs"]["1"][0]["output"] is None
    assert detail["perStepOutputs"]["1"][0]["error"]["code"] == "agent_budget_exceeded"


def test_agent_platform_budget_enforcement_fails_run_when_aggregate_budget_is_exceeded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        return {
            "output": {"summary": slot},
            "tokens": 5,
            "costUsd": "0.10000000",
            "durationMs": 5,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="aggregate_schema", version=1, status="published")
        skill = _build_skill(
            key="aggregate_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="aggregate_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Aggregate Run Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        first_agent = _build_agent_platform_agent(
            key="aggregate_agent_a",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            budget_usd=Decimal("1.00000000"),
        )
        second_agent = _build_agent_platform_agent(
            key="aggregate_agent_b",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            budget_usd=Decimal("1.00000000"),
        )
        session.add_all([first_agent, second_agent])
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "aggregate_budget_workflow",
                    "name": "Aggregate Budget Workflow",
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
                                    "agentKey": "aggregate_agent_a",
                                    "slot": "alpha",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                },
                                {
                                    "agentKey": "aggregate_agent_b",
                                    "slot": "beta",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                },
                            ],
                        }
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 1, "slot": "alpha"},
                }
            )
        )
        workflow_row = session.get(Workflow, workflow.id)
        assert workflow_row is not None
        workflow_row.aggregate_budget_usd = Decimal("0.15000000")
        session.commit()

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AMD"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert "aggregate budget" in str(detail["error"])
    assert detail["perStepOutputs"]["1"][0]["status"] == "succeeded"
    assert detail["perStepOutputs"]["1"][1]["status"] == "failed"
    assert detail["perStepOutputs"]["1"][1]["error"]["code"] == "run_budget_exceeded"


def test_agent_platform_optional_agent_failure_keeps_optional_downstream_running(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def fake_invoke(
        self: RunService,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model,
        trace_id: str | None,
        step_index: int,
        slot: str,
    ) -> dict[str, Any]:
        if slot == "analysis":
            raise RuntimeError("analysis tool failed")
        assert resolved_input == {}
        return {
            "output": {"summary": "fallback decision"},
            "tokens": 4,
            "costUsd": "0.01000000",
            "durationMs": 6,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="optional_schema", version=1, status="published")
        skill = _build_skill(
            key="optional_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="optional_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="Optional Run Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        optional_agent = _build_agent_platform_agent(
            key="optional_source_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        consumer_agent = _build_agent_platform_agent(
            key="optional_consumer_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema={
                "type": "object",
                "properties": {
                    "analysis": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                        "required": ["summary"],
                    }
                },
            },
        )
        session.add_all([optional_agent, consumer_agent])
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "optional_workflow",
                    "name": "Optional Workflow",
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
                                    "agentKey": "optional_source_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                    "optional": True,
                                }
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "optional_consumer_agent",
                                    "slot": "decision",
                                    "wiring": {
                                        "analysis": {
                                            "from": "step",
                                            "stepIndex": 1,
                                            "slot": "analysis",
                                        }
                                    },
                                }
                            ],
                        },
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 2, "slot": "decision"},
                }
            )
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "NFLX"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    assert detail["finalOutput"] == {"summary": "fallback decision"}
    assert detail["perStepOutputs"]["1"][0]["status"] == "failed"
    assert detail["perStepOutputs"]["1"][0]["output"] is None
    assert detail["perStepOutputs"]["1"][0]["error"]["code"] == "agent_execution_failed"
    assert detail["perStepOutputs"]["2"][0]["resolvedInput"] == {}
    assert detail["perStepOutputs"]["2"][0]["status"] == "succeeded"
