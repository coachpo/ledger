from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp import DefaultMcpConnectionTester
from app.api.dependencies import get_quote_provider
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
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.schemas.workflow import WorkflowCreate, WorkflowCreateRequest, WorkflowRead, WorkflowUpdate
from app.services.agent_service import AgentService
from app.services.capability_service import (
    MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
    POSITION_LOOKUP_ACCESS_DENIED_CODE,
    POSITION_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_LOOKUP_ACCESS_DENIED_CODE,
    REPORT_LOOKUP_ACCESS_DENIED_MESSAGE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE,
    REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    REPORT_MEMORY_WRITE_TOOL_KEY,
    CapabilityService,
)
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_snapshot import (
    ModelConnectionRuntimeSnapshot,
    build_model_connection_runtime_snapshot,
    parse_model_connection_runtime_snapshot,
    snapshot_to_json,
)
from app.services.position_service import PositionService
from app.services.quote_provider import (
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)
from app.services.report_service import ReportService
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_manifest_examples import (
    TRADINGAGENTS_AGENT_MANIFEST_SOURCES,
    TRADINGAGENTS_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
)
from app.services.workflow_service import WorkflowService
from tests.test_agent_manifest_compiler import _seed_tradingagents_manifest_refs

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
    reasoning_effort: str | None = "medium",
    timeout_seconds: int = 60,
    organization: str | None = None,
    project: str | None = None,
    api_style: str = "responses",
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
        api_style=api_style,
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
    api_style: str = "responses",
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
    connection = _build_model_connection(
        name=f"{workflow_key} connection",
        api_style=api_style,
    )
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


def _seed_backend_reports_write_workflow(
    session: Session,
    *,
    grant_reports_write: bool,
    workflow_key: str = "backend_reports_write_runtime",
    skill_key: str = "backend_reports_write_runtime_skill",
    agent_key: str = "report_memory_writer",
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
            [REPORT_MEMORY_WRITE_TOOL_KEY] if grant_reports_write else ["ledger.reports.lookup"]
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
                "name": "Backend Reports Write Runtime",
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


def _seed_backend_market_data_lookup_workflow(
    session: Session,
    *,
    tool_key: str,
    workflow_key: str,
    skill_key: str,
    agent_key: str,
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
        tools=[tool_key],
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
                "name": "Backend Market Data Lookup Runtime",
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


class _RuntimeMarketDataQuoteProvider:
    def __init__(self, *, failing_symbols: set[str] | None = None) -> None:
        self.failing_symbols: set[str] = failing_symbols or set()
        self.quote_calls: list[str] = []
        self.history_calls: list[tuple[str, str, str]] = []
        self.ohlcv_calls: list[tuple[str, datetime, datetime, str]] = []

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol.upper()} Incorporated"

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        self.quote_calls.append(normalized_symbol)
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"Quote unavailable for {normalized_symbol}")
        price = Decimal("120.25000000")
        return ProviderQuote(
            symbol=normalized_symbol,
            name=f"{normalized_symbol} Incorporated",
            price=price,
            previous_close=Decimal("119.75000000"),
            currency="USD",
            provider="api_fake_provider",
            as_of=datetime_from_api_fake(),
        )

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        normalized_symbol = symbol.upper()
        self.history_calls.append((normalized_symbol, range_value, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"History unavailable for {normalized_symbol}")
        return ProviderHistorySeries(
            symbol=normalized_symbol,
            currency="USD",
            provider="api_fake_provider",
            points=[
                ProviderHistoryPoint(
                    at=datetime_from_api_fake(day=1),
                    close=Decimal("118.75"),
                ),
                ProviderHistoryPoint(
                    at=datetime_from_api_fake(day=2, hour=0),
                    close=Decimal("119.75"),
                ),
                ProviderHistoryPoint(at=datetime_from_api_fake(), close=Decimal("120.25")),
            ],
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        normalized_symbol = symbol.upper()
        self.ohlcv_calls.append((normalized_symbol, start_date, end_date, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"OHLCV unavailable for {normalized_symbol}")
        return ProviderOhlcvSeries(
            symbol=normalized_symbol,
            currency="USD",
            provider="api_fake_provider",
            rows=[
                ProviderOhlcvRow(
                    at=start_date,
                    open=Decimal("118.00"),
                    high=Decimal("121.00"),
                    low=Decimal("117.00"),
                    close=Decimal("119.75"),
                    volume=1000,
                    adjusted_close=Decimal("119.50"),
                ),
                ProviderOhlcvRow(
                    at=end_date,
                    open=Decimal("119.75"),
                    high=Decimal("121.50"),
                    low=Decimal("119.00"),
                    close=Decimal("120.25"),
                    volume=1200,
                ),
            ],
        )


def datetime_from_api_fake(*, day: int = 2, hour: int = 3) -> datetime:
    return datetime(2026, 1, day, hour, 4, 5, tzinfo=UTC)


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
    reasoning_effort: object = "medium",
    timeout_seconds: int = 60,
    api_key: str | None = "sk-test-secret-1234",
    api_style: str | None = None,
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
    if api_style is not None:
        payload["apiStyle"] = api_style
    return payload


def _assert_reasoning_effort_validation_error(
    response: httpx.Response,
    expected_issue: str,
) -> None:
    assert response.status_code == 422, response.json()
    body = response.json()
    assert body["code"] == "validation_error"
    assert any("reasoningEffort" in detail["field"] for detail in body["details"])
    assert any(expected_issue in detail["issue"] for detail in body["details"])


def test_model_connection_snapshot_reasoning_effort_null_default_and_custom_contract() -> None:
    base_snapshot: dict[str, object] = {
        "base_url": "https://api.openai.com/v1",
        "model_id": "gpt-5.4-mini",
        "organization": None,
        "project": None,
        "api_style": "responses",
        "timeout_seconds": 60,
    }

    legacy_snapshot = parse_model_connection_runtime_snapshot(base_snapshot)
    assert legacy_snapshot.reasoning_effort == "medium"
    assert snapshot_to_json(legacy_snapshot)["reasoning_effort"] == "medium"

    def parse_with_reasoning_effort(value: object) -> ModelConnectionRuntimeSnapshot:
        snapshot = dict(base_snapshot)
        snapshot["reasoning_effort"] = value
        return parse_model_connection_runtime_snapshot(snapshot)

    null_snapshot = parse_with_reasoning_effort(None)
    assert null_snapshot.reasoning_effort is None
    assert snapshot_to_json(null_snapshot)["reasoning_effort"] is None

    custom_snapshot = parse_with_reasoning_effort(" XHigh ")
    assert custom_snapshot.reasoning_effort == "XHigh"
    assert snapshot_to_json(custom_snapshot)["reasoning_effort"] == "XHigh"

    max_length_snapshot = parse_with_reasoning_effort("r" * 128)
    assert max_length_snapshot.reasoning_effort == "r" * 128

    for invalid_reasoning_effort in ("", "   ", 3, True, {"effort": "medium"}):
        with pytest.raises(ValueError):
            _ = parse_with_reasoning_effort(invalid_reasoning_effort)
    with pytest.raises(ValueError):
        _ = parse_with_reasoning_effort("r" * 129)


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


class _ApiStyleRecordingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    responses_create_calls: list[dict[str, Any]] = []
    chat_create_calls: list[dict[str, Any]] = []
    fail_responses = False
    fail_chat = False

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = SimpleNamespace(create=self.create_response)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create_chat_completion))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create_response(self, **kwargs: Any) -> _FakeOpenAIResponse:
        type(self).responses_create_calls.append(kwargs)
        if type(self).fail_responses:
            raise Exception("Responses provider rejected sk-api-style-1234")
        return _FakeOpenAIResponse("req_responses_connection_test")

    def create_chat_completion(self, **kwargs: Any) -> _FakeOpenAIResponse:
        type(self).chat_create_calls.append(kwargs)
        if type(self).fail_chat:
            raise Exception("Chat provider rejected sk-api-style-1234")
        return _FakeOpenAIResponse("req_chat_connection_test")

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.responses_create_calls = []
        cls.chat_create_calls = []
        cls.fail_responses = False
        cls.fail_chat = False


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


class _UnexpectedRuntimeResponsesNamespace:
    def create(self, **kwargs: Any) -> object:
        del kwargs
        raise AssertionError("Responses API must not be called for chat_completions")


class _RuntimeChatCompletionsOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    chat_create_calls: list[dict[str, Any]] = []
    output_text = '{"summary": "chat runtime output"}'
    total_tokens = 19
    tool_call_name: str | None = None
    tool_arguments_json = '{"ticker":"NVDA","limit":1}'
    final_output_text = '{"summary":"chat tool loop output","signal":"bullish"}'

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = _UnexpectedRuntimeResponsesNamespace()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create_chat_completion))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create_chat_completion(self, **kwargs: Any) -> object:
        type(self).chat_create_calls.append(kwargs)
        call_number = len(type(self).chat_create_calls)
        if call_number == 1 and type(self).tool_call_name is not None:
            tools = kwargs.get("tools")
            assert isinstance(tools, list)
            assert tools[0]["type"] == "function"
            assert tools[0]["function"]["name"] == type(self).tool_call_name
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="chat_call_report_lookup_1",
                                    function=SimpleNamespace(
                                        name=type(self).tool_call_name,
                                        arguments=type(self).tool_arguments_json,
                                    ),
                                )
                            ],
                        )
                    )
                ],
                usage=_RuntimeOpenAIUsage(7),
            )
        if call_number > 1:
            messages = kwargs["messages"]
            assert messages[-1]["role"] == "tool"
            assert messages[-1]["tool_call_id"] == "chat_call_report_lookup_1"
            assert messages[-2]["role"] == "assistant"
            assert messages[-2]["tool_calls"][0]["id"] == "chat_call_report_lookup_1"
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            type(self).final_output_text
                            if call_number > 1
                            else type(self).output_text
                        ),
                        tool_calls=None,
                    )
                )
            ],
            usage=_RuntimeOpenAIUsage(type(self).total_tokens),
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.chat_create_calls = []
        cls.output_text = '{"summary": "chat runtime output"}'
        cls.total_tokens = 19
        cls.tool_call_name = None
        cls.tool_arguments_json = '{"ticker":"NVDA","limit":1}'
        cls.final_output_text = '{"summary":"chat tool loop output","signal":"bullish"}'


class _RuntimeFailingChatCompletionsOpenAIClient(_RuntimeChatCompletionsOpenAIClient):
    exception_factory = staticmethod(lambda: Exception("chat provider failure"))

    def create_chat_completion(self, **kwargs: Any) -> object:
        type(self).chat_create_calls.append(kwargs)
        raise type(self).exception_factory()

    @classmethod
    def reset(cls) -> None:
        super().reset()
        cls.exception_factory = staticmethod(lambda: Exception("chat provider failure"))


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
            assert properties["source"]["enum"] == [
                "compiled",
                "uploaded",
                "external",
                "agent",
                None,
            ]
            assert properties["limit"]["type"] == ["integer", "null"]
            assert properties["offset"]["type"] == ["integer", "null"]
        elif tool.get("name") == "ledger_positions_lookup":
            assert properties["portfolioSlug"]["type"] == "string"
            assert properties["symbol"]["type"] == ["string", "null"]
            assert properties["limit"]["type"] == ["integer", "null"]
            assert properties["offset"]["type"] == ["integer", "null"]
        elif tool.get("name") == "ledger_market_data_quote_lookup":
            assert properties["symbols"]["type"] == "array"
            assert properties["symbols"]["maxItems"] == 10
            assert properties["baseCurrency"]["type"] == ["string", "null"]
        elif tool.get("name") == "ledger_market_data_history_lookup":
            assert properties["symbols"]["type"] == "array"
            assert properties["symbols"]["maxItems"] == 5
            assert properties["range"]["enum"] == ["1mo", "3mo", "ytd", "1y", "max", None]
            assert properties["pointLimit"]["maximum"] == 250
        elif tool.get("name") == "ledger_reports_write":
            analysis_schema = properties["analysis"]
            assert analysis_schema["type"] == "object"
            analysis_properties = analysis_schema["properties"]
            assert set(analysis_properties) == {
                "ticker",
                "portfolioSlug",
                "horizonDays",
                "confidence",
                "decisionSummary",
                "decision",
            }
            assert "runId" not in analysis_properties
            assert "resolvedStatus" not in analysis_properties


class _RuntimeToolCallingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    expected_tool_names: list[str] | None = ["ledger_reports_lookup"]
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
            expected_tool_names = type(self).expected_tool_names
            if expected_tool_names is None:
                assert "tools" not in kwargs
            else:
                tools = kwargs.get("tools")
                assert isinstance(tools, list)
                _assert_openai_strict_tool_schemas(tools)
                assert [tool["name"] for tool in tools] == expected_tool_names
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
        cls.expected_tool_names = ["ledger_reports_lookup"]
        cls.tool_arguments_json = '{"ticker":"NVDA","limit":1}'
        cls.final_output_text = '{"summary":"tool loop output","signal":"bullish"}'


class _RuntimeReportsWriteToolCallingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    expected_tool_names: list[str] | None = ["ledger_reports_write"]
    tool_call_name: str = "ledger_reports_write"
    tool_arguments_json = json.dumps(
        {
            "analysis": {
                "ticker": " nvda ",
                "portfolioSlug": " core_us ",
                "horizonDays": 30,
                "confidence": " high ",
                "decisionSummary": " Durable earnings setup. ",
                "decision": {
                    "action": "buy",
                    "rationale": "Accelerating demand supports upside.",
                    "riskSummary": "Position sizing should respect valuation risk.",
                    "executionPlan": "Scale in over two sessions.",
                },
            }
        }
    )
    final_output_text = '{"summary":"report memory written","signal":"bullish"}'

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
            return _RuntimeToolCallResponse(
                response_id="resp_reports_write_1",
                output=[
                    {
                        "type": "function_call",
                        "name": type(self).tool_call_name,
                        "arguments": type(self).tool_arguments_json,
                        "call_id": "call_reports_write_1",
                    }
                ],
                total_tokens=11,
            )
        assert kwargs["previous_response_id"] == "resp_reports_write_1"
        output_items = kwargs["input"]
        assert output_items[0]["type"] == "function_call_output"
        assert output_items[0]["call_id"] == "call_reports_write_1"
        return _RuntimeToolCallResponse(
            response_id="resp_reports_write_2",
            output_text=type(self).final_output_text,
            total_tokens=13,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.expected_tool_names = ["ledger_reports_write"]
        cls.tool_call_name = "ledger_reports_write"
        cls.tool_arguments_json = json.dumps(
            {
                "analysis": {
                    "ticker": " nvda ",
                    "portfolioSlug": " core_us ",
                    "horizonDays": 30,
                    "confidence": " high ",
                    "decisionSummary": " Durable earnings setup. ",
                    "decision": {
                        "action": "buy",
                        "rationale": "Accelerating demand supports upside.",
                        "riskSummary": "Position sizing should respect valuation risk.",
                        "executionPlan": "Scale in over two sessions.",
                    },
                }
            }
        )
        cls.final_output_text = '{"summary":"report memory written","signal":"bullish"}'


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
        body={
            "error": {"message": message},
        },
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
    assert listed_item["apiStyle"] == "responses"
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
        assert row.api_style == "responses"
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

    style_update = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"apiStyle": "chat_completions"},
    )
    assert style_update.status_code == 200, style_update.json()
    assert style_update.json()["apiStyle"] == "chat_completions"

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.api_style == "chat_completions"
        assert row.last_tested_at is None
        assert row.last_test_ok is None
        assert row.last_test_message is None

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


def test_agent_platform_model_connections_reasoning_effort_nullable_and_custom_contract(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    def stored_reasoning(connection_id: int) -> str | None:
        with session_factory() as session:
            row = session.get(ModelConnection, connection_id)
            assert row is not None
            return row.reasoning_effort

    omitted_payload = _model_connection_payload(
        key="default_reasoning",
        name="Default Reasoning",
    )
    omitted_payload.pop("reasoningEffort")
    default_create = client.post("/api/model-connections", json=omitted_payload)
    assert default_create.status_code == 201, default_create.json()
    default_created = default_create.json()
    assert default_created["reasoningEffort"] == "medium"
    assert stored_reasoning(default_created["id"]) == "medium"

    null_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="null_reasoning",
            name="Null Reasoning",
            reasoning_effort=None,
        ),
    )
    assert null_create.status_code == 201, null_create.json()
    null_created = null_create.json()
    null_connection_id = null_created["id"]
    assert null_created["reasoningEffort"] is None
    assert stored_reasoning(null_connection_id) is None

    null_preserved = client.patch(
        f"/api/model-connections/{null_connection_id}",
        json={"description": "Still null."},
    )
    assert null_preserved.status_code == 200, null_preserved.json()
    assert null_preserved.json()["reasoningEffort"] is None
    assert stored_reasoning(null_connection_id) is None

    none_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="literal_none_reasoning",
            name="Literal None Reasoning",
            reasoning_effort=" none ",
        ),
    )
    assert none_create.status_code == 201, none_create.json()
    none_created = none_create.json()
    assert none_created["reasoningEffort"] == "none"
    assert stored_reasoning(none_created["id"]) == "none"

    custom_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="custom_reasoning",
            name="Custom Reasoning",
            reasoning_effort="xhigh",
        ),
    )
    assert custom_create.status_code == 201, custom_create.json()
    custom_created = custom_create.json()
    custom_connection_id = custom_created["id"]
    assert custom_created["reasoningEffort"] == "xhigh"
    assert stored_reasoning(custom_connection_id) == "xhigh"

    custom_preserved = client.patch(
        f"/api/model-connections/{custom_connection_id}",
        json={"description": "Preserve custom."},
    )
    assert custom_preserved.status_code == 200, custom_preserved.json()
    assert custom_preserved.json()["reasoningEffort"] == "xhigh"
    assert stored_reasoning(custom_connection_id) == "xhigh"

    case_preserved = client.patch(
        f"/api/model-connections/{custom_connection_id}",
        json={"reasoningEffort": " XHigh "},
    )
    assert case_preserved.status_code == 200, case_preserved.json()
    assert case_preserved.json()["reasoningEffort"] == "XHigh"
    assert stored_reasoning(custom_connection_id) == "XHigh"

    max_length_reasoning = "r" * 128
    max_length_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="max_reasoning",
            name="Max Reasoning",
            reasoning_effort=max_length_reasoning,
        ),
    )
    assert max_length_create.status_code == 201, max_length_create.json()
    assert max_length_create.json()["reasoningEffort"] == max_length_reasoning
    assert stored_reasoning(max_length_create.json()["id"]) == max_length_reasoning

    cleared = client.patch(
        f"/api/model-connections/{custom_connection_id}",
        json={"reasoningEffort": None},
    )
    assert cleared.status_code == 200, cleared.json()
    assert cleared.json()["reasoningEffort"] is None
    assert stored_reasoning(custom_connection_id) is None


@pytest.mark.parametrize(
    ("suffix", "reasoning_effort", "expected_issue"),
    [
        ("empty", "", "Reasoning effort is required"),
        ("whitespace", "   ", "Reasoning effort is required"),
        ("object", {"effort": "medium"}, "Reasoning effort must be a string"),
        ("array", ["medium"], "Reasoning effort must be a string"),
        ("number", 3, "Reasoning effort must be a string"),
        ("boolean", True, "Reasoning effort must be a string"),
    ],
)
def test_agent_platform_model_connections_reject_invalid_reasoning_effort_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
    suffix: str,
    reasoning_effort: object,
    expected_issue: str,
) -> None:
    rejected_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key=f"invalid_reasoning_{suffix}",
            name=f"Invalid Reasoning {suffix.title()}",
            reasoning_effort=reasoning_effort,
        ),
    )
    _assert_reasoning_effort_validation_error(rejected_create, expected_issue)

    valid_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key=f"valid_reasoning_{suffix}",
            name=f"Valid Reasoning {suffix.title()}",
        ),
    )
    assert valid_create.status_code == 201, valid_create.json()
    connection_id = valid_create.json()["id"]

    rejected_update = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"reasoningEffort": reasoning_effort},
    )
    _assert_reasoning_effort_validation_error(rejected_update, expected_issue)

    with session_factory() as session:
        row = session.get(ModelConnection, connection_id)
        assert row is not None
        assert row.reasoning_effort == "medium"


def test_agent_platform_model_connections_create_and_test_selected_api_style(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ApiStyleRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_service.OpenAI",
        _ApiStyleRecordingOpenAIClient,
    )

    responses_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="responses_connection",
            name="Responses Connection",
            api_key="sk-api-style-1234",
        ),
    )
    assert responses_create.status_code == 201, responses_create.json()
    responses_connection_id = responses_create.json()["id"]
    assert responses_create.json()["apiStyle"] == "responses"

    chat_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="chat_connection",
            name="Chat Connection",
            api_key="sk-api-style-1234",
            api_style="chat_completions",
        ),
    )
    assert chat_create.status_code == 201, chat_create.json()
    chat_connection_id = chat_create.json()["id"]
    assert chat_create.json()["apiStyle"] == "chat_completions"

    responses_test = client.post(
        f"/api/model-connections/{responses_connection_id}/connection-test"
    )
    assert responses_test.status_code == 200, responses_test.json()
    assert responses_test.json()["ok"] is True
    assert len(_ApiStyleRecordingOpenAIClient.responses_create_calls) == 1
    assert _ApiStyleRecordingOpenAIClient.responses_create_calls[0]["model"] == "gpt-5.4-mini"
    assert _ApiStyleRecordingOpenAIClient.responses_create_calls[0]["reasoning"] == {
        "effort": "medium"
    }
    assert _ApiStyleRecordingOpenAIClient.chat_create_calls == []

    chat_test = client.post(f"/api/model-connections/{chat_connection_id}/connection-test")
    assert chat_test.status_code == 200, chat_test.json()
    assert chat_test.json()["ok"] is True
    assert len(_ApiStyleRecordingOpenAIClient.responses_create_calls) == 1
    assert len(_ApiStyleRecordingOpenAIClient.chat_create_calls) == 1
    assert _ApiStyleRecordingOpenAIClient.chat_create_calls[0] == {
        "model": "gpt-5.4-mini",
        "messages": [
            {"role": "system", "content": "Reply with the single word OK."},
            {"role": "user", "content": "Connection test."},
        ],
    }

    with session_factory() as session:
        responses_row = session.get(ModelConnection, responses_connection_id)
        chat_row = session.get(ModelConnection, chat_connection_id)
        assert responses_row is not None and responses_row.api_style == "responses"
        assert chat_row is not None and chat_row.api_style == "chat_completions"


@pytest.mark.parametrize(
    ("suffix", "reasoning_effort", "expected_reasoning"),
    [
        ("null", None, None),
        ("minimal", "minimal", {"effort": "minimal"}),
        ("none", "none", {"effort": "none"}),
        ("xhigh", "xhigh", {"effort": "xhigh"}),
    ],
)
def test_model_connections_responses_test_reasoning_omission_and_custom_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    reasoning_effort: str | None,
    expected_reasoning: dict[str, str] | None,
) -> None:
    _ApiStyleRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_service.OpenAI",
        _ApiStyleRecordingOpenAIClient,
    )
    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key=f"responses_connection_test_{suffix}",
            name=f"Responses Connection Test {suffix.title()}",
            api_key="sk-api-style-1234",
            reasoning_effort=reasoning_effort,
        ),
    )
    assert create_response.status_code == 201, create_response.json()

    connection_test = client.post(
        f"/api/model-connections/{create_response.json()['id']}/connection-test"
    )
    assert connection_test.status_code == 200, connection_test.json()
    assert connection_test.json()["ok"] is True
    request = _ApiStyleRecordingOpenAIClient.responses_create_calls[-1]
    if expected_reasoning is None:
        assert "reasoning" not in request
    else:
        assert request["reasoning"] == expected_reasoning
    assert _ApiStyleRecordingOpenAIClient.chat_create_calls == []


def test_agent_platform_model_connections_selected_api_style_failure_does_not_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ApiStyleRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_service.OpenAI",
        _ApiStyleRecordingOpenAIClient,
    )

    responses_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="responses_failure_connection",
            name="Responses Failure Connection",
            api_key="sk-api-style-1234",
        ),
    )
    assert responses_create.status_code == 201, responses_create.json()
    chat_create = client.post(
        "/api/model-connections",
        json=_model_connection_payload(
            key="chat_failure_connection",
            name="Chat Failure Connection",
            api_key="sk-api-style-1234",
            api_style="chat_completions",
        ),
    )
    assert chat_create.status_code == 201, chat_create.json()

    _ApiStyleRecordingOpenAIClient.fail_responses = True
    responses_failure = client.post(
        f"/api/model-connections/{responses_create.json()['id']}/connection-test"
    )
    assert responses_failure.status_code == 200, responses_failure.json()
    assert responses_failure.json()["ok"] is False
    assert len(_ApiStyleRecordingOpenAIClient.responses_create_calls) == 1
    assert _ApiStyleRecordingOpenAIClient.chat_create_calls == []

    _ApiStyleRecordingOpenAIClient.reset()
    _ApiStyleRecordingOpenAIClient.fail_chat = True
    chat_failure = client.post(f"/api/model-connections/{chat_create.json()['id']}/connection-test")
    assert chat_failure.status_code == 200, chat_failure.json()
    assert chat_failure.json()["ok"] is False
    assert _ApiStyleRecordingOpenAIClient.responses_create_calls == []
    assert len(_ApiStyleRecordingOpenAIClient.chat_create_calls) == 1


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
        "status": "queued",
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
    assert "perStepOutputs" not in detail
    assert [step["index"] for step in detail["steps"]] == [1]
    step = detail["steps"][0]
    invocation = step["invocations"][0]
    assert step["status"] == "succeeded"
    assert step["origin"] == "planned"
    assert invocation["slot"] == "final_output"
    assert invocation["agentId"] == historical_agent_id
    assert invocation["agentKey"] == "research_agent"
    assert invocation["agentVersion"] == 1
    assert invocation["outputSchemaVersion"] == 1
    assert invocation["inputMode"] == "passthrough"
    assert invocation["wiring"] == {}
    assert invocation["resolvedInput"] == {"ticker": "MSFT"}
    assert invocation["resolvedInputOrigin"] == "passthrough"
    assert invocation["output"] == {"summary": "research_agent:MSFT"}
    assert invocation["outputOrigin"] == "executed"
    assert invocation["sourceInvocationId"] is None
    assert invocation["errorCode"] is None
    assert invocation["errorMessage"] is None
    assert invocation["errorDetails"] == []
    assert invocation["status"] == "succeeded"
    assert invocation["tokens"] == 7
    assert invocation["durationMs"] == 4
    _assert_logfire_span_id(invocation["traceSpanId"])

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
                "traceId": detail["traceId"],
                "queuedAt": listed.json()["items"][0]["queuedAt"],
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
        assert _agent.model_connection_snapshot["api_style"] == "responses"
        connection.project = "proj-v2"
        connection.secret_payload = {"apiKey": "sk-rotated-secret-2222"}
        connection.has_api_key = True
        connection.api_key_last4 = "2222"
        session.commit()

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "MSFT"},
        },
    )
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
    ("suffix", "reasoning_effort", "expected_reasoning"),
    [
        ("null", None, None),
        ("minimal", "minimal", {"effort": "minimal"}),
        ("none", "none", {"effort": "none"}),
        ("xhigh", "xhigh", {"effort": "xhigh"}),
    ],
)
def test_agent_platform_run_responses_reasoning_effort_omission_and_custom_snapshot_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    suffix: str,
    reasoning_effort: str | None,
    expected_reasoning: dict[str, str] | None,
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "reasoning runtime output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    with session_factory() as session:
        workflow, agent = _create_single_agent_runtime_workflow(
            session,
            agent_key=f"responses_reasoning_{suffix}_agent",
            workflow_key=f"responses_reasoning_{suffix}_workflow",
            connection=_build_model_connection(
                name=f"Responses Reasoning {suffix.title()} Connection",
                api_key="sk-reasoning-runtime-1234",
                reasoning_effort=reasoning_effort,
            ),
        )
        assert agent.model_connection_snapshot["reasoning_effort"] == reasoning_effort
        workflow_row = session.get(Workflow, workflow.id)
        assert workflow_row is not None
        workflow_storage = json.dumps(
            {"steps": workflow_row.steps, "outputSpec": workflow_row.output_spec},
            sort_keys=True,
        )
        assert "reasoningEffort" not in workflow_storage
        assert "reasoning_effort" not in workflow_storage
        assert "modelConnectionSnapshot" not in workflow_storage
        assert "model_connection_snapshot" not in workflow_storage

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "MSFT"}},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "reasoning runtime output"}
    request = _RuntimeRecordingOpenAIClient.create_calls[-1]
    if expected_reasoning is None:
        assert "reasoning" not in request
    else:
        assert request["reasoning"] == expected_reasoning


def test_agent_platform_run_chat_completions_snapshot_parses_message_content_json(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeChatCompletionsOpenAIClient.reset()
    _RuntimeChatCompletionsOpenAIClient.output_text = '{"summary": "chat snapshot output"}'
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeChatCompletionsOpenAIClient,
    )

    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="chat_snapshot_agent",
            workflow_key="chat_snapshot_workflow",
            connection=_build_model_connection(
                name="Chat Snapshot Connection",
                api_key="sk-chat-runtime-1111",
                base_url="https://chat-runtime.example.com/v1",
                model_id="gpt-chat-runtime",
                api_style="chat_completions",
            ),
        )
        assert _agent.model_connection_snapshot["api_style"] == "chat_completions"

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "MSFT"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat snapshot output"}
    assert _RuntimeChatCompletionsOpenAIClient.init_calls[-1] == {
        "api_key": "sk-chat-runtime-1111",
        "base_url": "https://chat-runtime.example.com/v1",
        "timeout": 60.0,
    }
    chat_request = _RuntimeChatCompletionsOpenAIClient.chat_create_calls[-1]
    assert chat_request["model"] == "gpt-chat-runtime"
    assert [message["role"] for message in chat_request["messages"]] == ["system", "user"]
    assert chat_request["response_format"]["type"] == "json_schema"
    assert "previous_response_id" not in chat_request
    assert "input" not in chat_request
    assert "reasoning" not in chat_request


@pytest.mark.parametrize(
    ("suffix", "reasoning_effort"),
    [("null", None), ("custom", "xhigh")],
)
def test_agent_platform_run_chat_completions_never_sends_reasoning_for_null_or_custom(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    suffix: str,
    reasoning_effort: str | None,
) -> None:
    _RuntimeChatCompletionsOpenAIClient.reset()
    _RuntimeChatCompletionsOpenAIClient.output_text = '{"summary": "chat reasoning output"}'
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeChatCompletionsOpenAIClient,
    )

    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key=f"chat_reasoning_{suffix}_agent",
            workflow_key=f"chat_reasoning_{suffix}_workflow",
            connection=_build_model_connection(
                name=f"Chat Reasoning {suffix.title()} Connection",
                api_key="sk-chat-reasoning-1111",
                api_style="chat_completions",
                reasoning_effort=reasoning_effort,
            ),
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "MSFT"}},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat reasoning output"}
    chat_request = _RuntimeChatCompletionsOpenAIClient.chat_create_calls[-1]
    assert [message["role"] for message in chat_request["messages"]] == ["system", "user"]
    assert chat_request["response_format"]["type"] == "json_schema"
    assert "reasoning" not in chat_request
    assert "input" not in chat_request


def test_agent_platform_run_chat_completions_tool_call_round_appends_tool_messages(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeChatCompletionsOpenAIClient.reset()
    _RuntimeChatCompletionsOpenAIClient.tool_call_name = "ledger_reports_lookup"
    _RuntimeChatCompletionsOpenAIClient.tool_arguments_json = (
        '{"ticker":"NVDA","tag":null,"reviewType":null,'
        '"portfolioSlug":null,"source":null,"limit":1,"offset":null}'
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeChatCompletionsOpenAIClient,
    )

    with session_factory() as session:
        session.add(
            Report(
                name="nvda_chat_lookup",
                slug="nvda_chat_lookup",
                source="external",
                content="# NVDA chat lookup\n\nRevenue acceleration remains intact.",
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
            workflow_key="chat_report_lookup_runtime",
            skill_key="chat_report_lookup_runtime_skill",
            api_style="chat_completions",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "chat tool loop output",
        "signal": "bullish",
    }
    assert len(_RuntimeChatCompletionsOpenAIClient.chat_create_calls) == 2
    followup_messages = _RuntimeChatCompletionsOpenAIClient.chat_create_calls[1]["messages"]
    assert followup_messages[-2]["role"] == "assistant"
    assert followup_messages[-1]["role"] == "tool"
    assert followup_messages[-1]["tool_call_id"] == "chat_call_report_lookup_1"
    tool_payload = json.loads(followup_messages[-1]["content"])
    assert tool_payload["count"] == 1
    assert tool_payload["reports"][0]["slug"] == "nvda_chat_lookup"


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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "AAPL"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert detail["error"] == expected_message
    step_error = detail["steps"][0]["invocations"][0]
    assert step_error["errorCode"] == expected_code
    assert step_error["errorMessage"] == expected_message
    assert "sk-db-fail-4444" not in json.dumps(detail)


def test_agent_platform_run_chat_completions_provider_failure_does_not_use_responses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeFailingChatCompletionsOpenAIClient.reset()
    _RuntimeFailingChatCompletionsOpenAIClient.exception_factory = staticmethod(
        lambda: _build_api_status_error(
            message="Chat model rejected sk-chat-fail-4444",
            status_code=404,
        )
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeFailingChatCompletionsOpenAIClient,
    )

    with session_factory() as session:
        workflow, _agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="chat_provider_failure_agent",
            workflow_key="chat_provider_failure_workflow",
            connection=_build_model_connection(
                name="Chat provider failure connection",
                api_key="sk-chat-fail-4444",
                api_style="chat_completions",
            ),
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "AAPL"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert detail["error"] == "Chat model rejected [REDACTED]"
    assert len(_RuntimeFailingChatCompletionsOpenAIClient.chat_create_calls) == 1
    assert "sk-chat-fail-4444" not in json.dumps(detail)


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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NFLX"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert "missing an API key" in detail["error"]
    step_error = detail["steps"][0]["invocations"][0]
    assert step_error["errorCode"] == "agent_model_connection_api_key_missing"
    assert "missing an API key" in step_error["errorMessage"]


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

    response = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {},
        },
    )

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


def test_agent_platform_run_input_metadata_does_not_change_validation_semantics(
    session_factory: sessionmaker[Session],
) -> None:
    plain_schema = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "horizonDays": {"type": "integer"},
            "priceTargets": {"type": "array", "items": {"type": "number"}},
        },
        "required": ["ticker"],
        "additionalProperties": False,
    }
    metadata_schema = {
        "type": "object",
        "title": "Run input",
        "description": "Values supplied when starting a run.",
        "properties": {
            "ticker": {
                "type": "string",
                "title": "Ticker symbol",
                "description": "Public market ticker to research.",
            },
            "horizonDays": {
                "type": "integer",
                "title": "Horizon days",
                "description": "Optional number of days to assess.",
            },
            "priceTargets": {
                "type": "array",
                "title": "Price targets",
                "description": "Optional candidate price targets.",
                "items": {
                    "type": "number",
                    "title": "Price target",
                    "description": "Candidate target price.",
                },
            },
        },
        "required": ["ticker"],
        "additionalProperties": False,
    }
    input_payload = {"ticker": "NVDA", "priceTargets": [125.5, 130]}

    with session_factory() as session:
        service = RunService(session)
        assert service._validate_run_input(
            input_schema=plain_schema,
            input_payload=input_payload,
            candidate_key="plain_runtime_input",
            resource_name="workflow",
        ) == service._validate_run_input(
            input_schema=metadata_schema,
            input_payload=input_payload,
            candidate_key="metadata_runtime_input",
            resource_name="workflow",
        )

        errors: list[ApiError] = []
        for schema in (plain_schema, metadata_schema):
            with pytest.raises(ApiError) as excinfo:
                service._validate_run_input(
                    input_schema=schema,
                    input_payload={"horizonDays": 30},
                    candidate_key="invalid_runtime_input",
                    resource_name="workflow",
                )
            errors.append(excinfo.value)

    assert [(error.code, error.message, error.details) for error in errors] == [
        (
            "run_invalid_input",
            "Run input failed workflow input schema validation",
            [{"field": "ticker", "issue": "Field required"}],
        ),
        (
            "run_invalid_input",
            "Run input failed workflow input schema validation",
            [{"field": "ticker", "issue": "Field required"}],
        ),
    ]


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
        if body["status"] not in {"queued", "running"}:
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


def test_agent_platform_workflow_launch_read_lists_versions_and_removes_old_run_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    with session_factory() as session:
        created = _seed_reference_workflow(
            session,
            workflow_key="launch_api_workflow",
            workflow_name="Launch API Workflow",
        )
        updated = WorkflowService(session).update_workflow(
            created.id,
            WorkflowUpdate.model_validate(
                {
                    "name": "Launch API Workflow Updated",
                    "description": "Updated launch schema.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "horizon_days": {"type": "integer"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["ticker", "horizon_days", "confidence"],
                        "additionalProperties": False,
                    },
                    "steps": _reference_workflow_payload()["steps"],
                    "outputSpec": _reference_workflow_payload()["outputSpec"],
                }
            ),
        )

    old_route = client.post(
        f"/api/workflows/{updated.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
    )
    assert old_route.status_code == 404
    with session_factory() as session:
        assert session.query(Run).all() == []

    launch = client.get(f"/api/workflows/{updated.id}/launch", params={"version": 1})
    assert launch.status_code == 200, launch.json()
    assert launch.json() == {
        "workflowId": created.id,
        "key": created.key,
        "version": 1,
        "name": created.name,
        "description": created.description,
        "inputSchema": created.input_schema,
    }

    versions = client.get(f"/api/workflows/{updated.id}/versions")
    assert versions.status_code == 200, versions.json()
    assert [item["version"] for item in versions.json()["items"]] == [2, 1]
    assert versions.json()["items"][0]["inputSchema"] == updated.input_schema
    assert versions.json()["items"][1]["inputSchema"] == created.input_schema

    invalid_raw = client.post(
        f"/api/workflows/{updated.id}/launches",
        json={"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
    )
    assert invalid_raw.status_code == 422, invalid_raw.json()
    assert invalid_raw.json()["code"] == "validation_error"
    with session_factory() as session:
        assert session.query(Run).all() == []

    invalid_parameters = client.post(
        f"/api/workflows/{updated.id}/launches",
        json={
            "version": 2,
            "parameters": {"ticker": "NVDA", "horizon_days": 5},
        },
    )
    assert invalid_parameters.status_code == 400, invalid_parameters.json()
    assert invalid_parameters.json()["code"] == "run_invalid_input"
    with session_factory() as session:
        assert session.query(Run).all() == []

    first = client.post(
        f"/api/workflows/{updated.id}/launches",
        json={
            "version": 2,
            "parameters": {"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
        },
    )
    second = client.post(
        f"/api/workflows/{updated.id}/launches",
        json={
            "version": 2,
            "parameters": {"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
        },
    )
    assert first.status_code == 201, first.json()
    assert second.status_code == 201, second.json()
    assert first.json() == {
        "id": first.json()["id"],
        "status": "queued",
        "workflowId": updated.id,
        "workflowKey": updated.key,
        "workflowVersion": 2,
        "createdAt": first.json()["createdAt"],
    }
    assert second.json()["id"] != first.json()["id"]
    with session_factory() as session:
        stored_runs = session.query(Run).order_by(Run.id).all()
        assert [run.id for run in stored_runs] == [first.json()["id"], second.json()["id"]]
        assert [run.input for run in stored_runs] == [
            {"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
            {"ticker": "NVDA", "horizon_days": 5, "confidence": 0.7},
        ]


def test_agent_platform_workflow_run_creation_persists_planned_steps_and_invocations(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    with session_factory() as session:
        workflow = _seed_reference_workflow(
            session,
            workflow_key="planned_creation_workflow",
            workflow_name="Planned Creation Workflow",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 5},
        },
    )
    assert trigger.status_code == 201, trigger.json()

    detail = client.get(f"/api/runs/{trigger.json()['id']}")
    assert detail.status_code == 200, detail.json()
    body = detail.json()

    assert body["status"] == "queued"
    assert body["queuedAt"] is not None
    assert body["startedAt"] is None
    assert body["finishedAt"] is None
    assert body["resumeStepIndex"] == 1
    assert body["totalTokens"] == 0
    assert body["inheritedTokens"] == 0
    assert body["executedTokens"] == 0
    assert [step["index"] for step in body["steps"]] == [1, 2]
    assert [step["status"] for step in body["steps"]] == ["pending", "pending"]
    assert [step["origin"] for step in body["steps"]] == ["planned", "planned"]

    step_one_invocations = body["steps"][0]["invocations"]
    step_two_invocations = body["steps"][1]["invocations"]
    assert [item["position"] for item in step_one_invocations] == list(range(8))
    assert [item["slot"] for item in step_one_invocations] == list(REFERENCE_STEP_ONE_AGENT_KEYS)
    assert len(step_two_invocations) == 1
    assert step_two_invocations[0]["slot"] == "decision"
    assert step_one_invocations[0]["status"] == "pending"
    assert step_one_invocations[0]["inputMode"] == "wired"
    assert step_one_invocations[0]["resolvedInput"] == {}
    assert step_one_invocations[0]["resolvedInputOrigin"] == "derived"
    assert step_one_invocations[0]["wiring"] == {
        "ticker": {"from": "input", "path": "ticker"},
        "horizon_days": {"from": "input", "path": "horizon_days"},
    }
    assert step_two_invocations[0]["wiring"]["financials_analyst"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "financials_analyst",
    }
    assert body["steps"][0]["graphMetadata"] is None
    assert step_one_invocations[0]["graphMetadata"] is None


def _v2_graph_runtime_manifest_source() -> str:
    return """apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: v2_graph_runtime_workflow
  name: V2 Graph Runtime Workflow
  description: Runtime graph metadata coverage.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
  additionalProperties: false
flow:
  kind: sequence
  id: root_sequence
  nodes:
    - kind: fanout
      id: analyst_fanout
      branches:
        - id: market
          node:
            kind: step
            id: market_analysis
            slot: market
            uses: v2_market_agent@1
            with:
              ticker: ${{ inputs.ticker }}
        - id: news
          node:
            kind: step
            id: news_analysis
            slot: news
            uses: v2_news_agent@1
            with:
              ticker: ${{ inputs.ticker }}
    - kind: loop
      id: review_loop
      maxIterations: 2
      sequence:
        kind: sequence
        id: review_sequence
        nodes:
          - kind: step
            id: risk_review
            slot: risk
            uses: v2_risk_agent@1
            with:
              ticker: ${{ inputs.ticker }}
    - kind: step
      id: decision
      slot: final
      uses: v2_decision_agent@1
      with:
        marketReport: ${{ nodes.analyst_fanout.outputs.market }}
        newsReport: ${{ nodes.analyst_fanout.outputs.news }}
        riskReport: ${{ nodes.review_loop.outputs.risk }}
output:
  from: ${{ nodes.root_sequence.outputs.final }}
"""


def test_agent_platform_v2_workflow_run_detail_exposes_graph_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    execution_starts: list[tuple[int, str]] = []

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
        del self, output_model, trace_id
        execution_starts.append((step_index, slot))
        await asyncio.sleep(0.01 if step_index == 1 else 0)
        if agent.key == "v2_decision_agent":
            summary = "|".join(
                [
                    resolved_input["marketReport"]["summary"],
                    resolved_input["newsReport"]["summary"],
                    resolved_input["riskReport"]["summary"],
                ]
            )
            output = {"summary": summary}
        else:
            output = {"summary": f"{slot}:{resolved_input['ticker']}"}
        return {"output": output, "tokens": 5, "durationMs": 1}

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_output_schema(key="v2_graph_schema", version=1, status="published")
        skill = _build_skill(
            key="v2_graph_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="v2_graph_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="V2 Graph Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        note_input_schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        decision_input_schema = {
            "type": "object",
            "properties": {
                "marketReport": note_input_schema,
                "newsReport": note_input_schema,
                "riskReport": note_input_schema,
            },
            "required": ["marketReport", "newsReport", "riskReport"],
            "additionalProperties": False,
        }
        for key, input_schema in [
            ("v2_market_agent", None),
            ("v2_news_agent", None),
            ("v2_risk_agent", None),
            ("v2_decision_agent", decision_input_schema),
        ]:
            session.add(
                _build_agent_platform_agent(
                    key=key,
                    version=1,
                    status="published",
                    output_schema=output_schema,
                    skill=skill,
                    mcp_server=mcp_server,
                    model_connection=connection,
                    input_schema=input_schema,
                )
            )
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreateRequest.model_validate(
                {"manifestSource": _v2_graph_runtime_manifest_source()}
            )
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "market:NVDA|news:NVDA|risk:NVDA"}
    assert [step["index"] for step in detail["steps"]] == [1, 2, 3, 4]
    assert [[item["slot"] for item in step["invocations"]] for step in detail["steps"]] == [
        ["market", "news"],
        ["risk"],
        ["risk"],
        ["final"],
    ]
    assert execution_starts[:2] == [(1, "market"), (1, "news")]
    assert execution_starts[2:] == [(2, "risk"), (3, "risk"), (4, "final")]

    fanout_step = detail["steps"][0]
    assert fanout_step["graphMetadata"] == {
        "nodeKind": "fanout",
        "fanoutId": "analyst_fanout",
        "sourceRefs": {
            "branches": [
                {"nodeId": "market_analysis", "branchId": "market", "slot": "market"},
                {"nodeId": "news_analysis", "branchId": "news", "slot": "news"},
            ]
        },
    }
    market_metadata = fanout_step["invocations"][0]["graphMetadata"]
    assert market_metadata["nodeId"] == "market_analysis"
    assert market_metadata["nodeKind"] == "step"
    assert market_metadata["fanoutId"] == "analyst_fanout"
    assert market_metadata["branchId"] == "market"
    assert market_metadata["sourceRefs"] == {"ticker": {"source": "inputs", "path": "ticker"}}
    assert detail["steps"][1]["invocations"][0]["graphMetadata"]["loopIteration"] == 1
    assert detail["steps"][2]["invocations"][0]["graphMetadata"]["loopIteration"] == 2
    assert detail["steps"][3]["invocations"][0]["graphMetadata"]["sourceRefs"] == {
        "marketReport": {
            "source": "nodes",
            "nodeId": "analyst_fanout",
            "slot": "market",
            "stepIndex": 1,
            "compiledSlot": "market",
            "sourceNodeId": "market_analysis",
            "sourceSlot": "market",
        },
        "newsReport": {
            "source": "nodes",
            "nodeId": "analyst_fanout",
            "slot": "news",
            "stepIndex": 1,
            "compiledSlot": "news",
            "sourceNodeId": "news_analysis",
            "sourceSlot": "news",
        },
        "riskReport": {
            "source": "nodes",
            "nodeId": "review_loop",
            "slot": "risk",
            "stepIndex": 3,
            "compiledSlot": "risk",
            "sourceNodeId": "risk_review",
            "sourceSlot": "risk",
        },
    }


def _v2_loop_state_carry_manifest_source() -> str:
    return """apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: v2_loop_state_carry_runtime
  name: V2 Loop State Carry Runtime
inputSchema:
  type: object
  properties:
    initial_state:
      type: object
      properties:
        history:
          type: array
          items:
            type: string
      required:
        - history
      additionalProperties: false
  required:
    - initial_state
  additionalProperties: false
flow:
  kind: loop
  id: state_loop
  maxIterations: 2
  state:
    state: ${{ inputs.initial_state }}
  sequence:
    kind: sequence
    id: state_sequence
    nodes:
      - kind: step
        id: state_update
        slot: state
        uses: v2_state_agent@1
        with:
          priorState: ${{ inputs.initial_state }}
output:
  from: ${{ nodes.state_loop.outputs.state }}
"""


def test_agent_platform_v2_loop_state_carries_between_iterations(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    observed_inputs: list[dict[str, Any]] = []

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
        del self, agent, output_model, trace_id, slot
        observed_inputs.append(dict(resolved_input))
        prior_state = cast(dict[str, Any], resolved_input["priorState"])
        return {"output": {"history": [*prior_state["history"], f"iteration_{step_index}"]}}

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    state_schema = {
        "type": "object",
        "properties": {"history": {"type": "array", "items": {"type": "string"}}},
        "required": ["history"],
        "additionalProperties": False,
    }
    agent_input_schema = {
        "type": "object",
        "properties": {"priorState": state_schema},
        "required": ["priorState"],
        "additionalProperties": False,
    }
    with session_factory() as session:
        output_schema = _build_output_schema(
            key="v2_loop_state_schema",
            version=1,
            status="published",
        )
        output_schema.json_schema = state_schema
        skill = _build_skill(
            key="v2_loop_state_skill",
            version=1,
            status="published",
            tools=["ledger.market_data.quote_lookup"],
        )
        mcp_server = _build_mcp_server(
            key="v2_loop_state_server",
            version=1,
            status="published",
            transport="http-sse",
        )
        connection = _build_model_connection(name="V2 Loop State Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        session.add(
            _build_agent_platform_agent(
                key="v2_state_agent",
                version=1,
                status="published",
                output_schema=output_schema,
                skill=skill,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=agent_input_schema,
            )
        )
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreateRequest.model_validate(
                {"manifestSource": _v2_loop_state_carry_manifest_source()}
            )
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"initial_state": {"history": ["seed"]}},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"history": ["seed", "iteration_1", "iteration_2"]}
    assert observed_inputs == [
        {"priorState": {"history": ["seed"]}},
        {"priorState": {"history": ["seed", "iteration_1"]}},
    ]
    assert detail["steps"][0]["invocations"][0]["wiring"]["priorState"] == {
        "from": "input",
        "path": "initial_state",
    }
    assert detail["steps"][1]["invocations"][0]["wiring"]["priorState"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "state",
    }


def _v2_post_run_memory_manifest_source(
    *,
    workflow_key: str,
    post_run_memory: str = "",
) -> str:
    return f"""apiVersion: ledger.workflow/v2
kind: Workflow
metadata:
  key: {workflow_key}
  name: V2 Post Run Memory Workflow
  description: Post-run memory coverage.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
    portfolio_slug:
      type: string
    horizon_days:
      type: integer
  required:
    - ticker
  additionalProperties: false
flow:
  kind: step
  id: decision
  slot: decision
  uses: {workflow_key}_agent@1
  with:
    ticker: ${{{{ inputs.ticker }}}}
    portfolio_slug: ${{{{ inputs.portfolio_slug }}}}
    horizon_days: ${{{{ inputs.horizon_days }}}}
output:
  from: ${{{{ nodes.decision.outputs.decision.summary }}}}
{post_run_memory}"""


def _v2_post_run_memory_block(*, enabled: bool = True) -> str:
    enabled_text = "true" if enabled else "false"
    return f"""postRunMemory:
  enabled: {enabled_text}
  source:
    ticker: ${{{{ inputs.ticker }}}}
    action: ${{{{ nodes.decision.outputs.decision.action }}}}
    rationale: ${{{{ nodes.decision.outputs.decision.rationale }}}}
    riskSummary: ${{{{ nodes.decision.outputs.decision.riskSummary }}}}
    executionPlan: ${{{{ nodes.decision.outputs.decision.executionPlan }}}}
    portfolioSlug: ${{{{ inputs.portfolio_slug }}}}
    horizonDays: ${{{{ inputs.horizon_days }}}}
    confidence: ${{{{ nodes.decision.outputs.decision.confidence }}}}
    decisionSummary: ${{{{ nodes.decision.outputs.decision.summary }}}}
  benchmarkSymbol: ${{{{ inputs.ticker }}}}
"""


def _create_v2_post_run_memory_workflow(
    session: Session,
    *,
    workflow_key: str,
    post_run_memory: str = "",
) -> WorkflowRead:
    output_schema = _build_output_schema(
        key=f"{workflow_key}_schema",
        version=1,
        status="published",
    )
    output_schema.json_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "action": {"type": "string", "enum": ["buy", "hold", "sell"]},
            "rationale": {"type": "string"},
            "riskSummary": {"type": "string"},
            "executionPlan": {"type": "string"},
            "confidence": {"type": "string"},
        },
        "required": ["summary", "action", "rationale", "riskSummary", "executionPlan"],
        "additionalProperties": False,
    }
    skill = _build_skill(
        key=f"{workflow_key}_skill",
        version=1,
        status="published",
        tools=[REPORT_MEMORY_WRITE_TOOL_KEY],
    )
    mcp_server = _build_mcp_server(
        key=f"{workflow_key}_server",
        version=1,
        status="published",
        transport="http-sse",
    )
    connection = _build_model_connection(name=f"{workflow_key} Connection")
    session.add_all([output_schema, skill, mcp_server, connection])
    session.flush()
    agent = _build_agent_platform_agent(
        key=f"{workflow_key}_agent",
        version=1,
        status="published",
        output_schema=output_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
        input_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "portfolio_slug": {"type": "string"},
                "horizon_days": {"type": "integer"},
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
    )
    session.add(agent)
    session.commit()
    return WorkflowService(session).create_workflow(
        WorkflowCreateRequest.model_validate(
            {
                "manifestSource": _v2_post_run_memory_manifest_source(
                    workflow_key=workflow_key,
                    post_run_memory=post_run_memory,
                )
            }
        )
    )


async def _post_run_memory_fake_invoke(
    self: RunService,
    *,
    agent: Agent,
    resolved_input: dict[str, Any],
    output_model,
    trace_id: str | None,
    step_index: int,
    slot: str,
) -> dict[str, Any]:
    del self, agent, output_model, trace_id, step_index, slot
    ticker = resolved_input["ticker"]
    return {
        "output": {
            "summary": f"Buy {ticker} after risk review.",
            "action": "buy",
            "rationale": "Demand and margin trends support upside.",
            "riskSummary": "Valuation risk requires staged sizing.",
            "executionPlan": "Scale in over two sessions.",
            "confidence": "high",
        },
        "tokens": 5,
        "durationMs": 1,
    }


def test_agent_platform_v2_post_run_memory_omitted_or_disabled_writes_no_artifact(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_invoke_agent", _post_run_memory_fake_invoke)

    with session_factory() as session:
        omitted = _create_v2_post_run_memory_workflow(
            session,
            workflow_key="v2_post_memory_omitted",
        )
        disabled = _create_v2_post_run_memory_workflow(
            session,
            workflow_key="v2_post_memory_disabled",
            post_run_memory=_v2_post_run_memory_block(enabled=False),
        )

    for workflow in (omitted, disabled):
        trigger = client.post(
            f"/api/workflows/{workflow.id}/launches",
            json={
                "version": workflow.version,
                "parameters": {"ticker": "NVDA", "portfolio_slug": "core_us", "horizon_days": 30},
            },
        )
        assert trigger.status_code == 201, trigger.json()
        detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
        assert detail["status"] == "succeeded"
        assert detail["memoryArtifacts"] == []

    with session_factory() as session:
        assert session.query(Report).count() == 0


def test_agent_platform_v2_post_run_memory_success_creates_one_linked_artifact(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_invoke_agent", _post_run_memory_fake_invoke)

    with session_factory() as session:
        workflow = _create_v2_post_run_memory_workflow(
            session,
            workflow_key="v2_post_memory_success",
            post_run_memory=_v2_post_run_memory_block(),
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "nvda", "portfolio_slug": "core_us", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == "Buy nvda after risk review."
    assert len(detail["memoryArtifacts"]) == 1
    artifact = detail["memoryArtifacts"][0]
    assert set(artifact) == {
        "reportId",
        "slug",
        "name",
        "status",
        "createdAt",
        "sourceGraphMetadata",
    }
    assert artifact["status"] == "pending"
    assert artifact["sourceGraphMetadata"] == {
        "nodeId": "decision",
        "slot": "decision",
        "traceId": detail["traceId"],
        "workflowKey": workflow.key,
        "workflowVersion": workflow.version,
    }

    with session_factory() as session:
        report = session.get(Report, int(artifact["reportId"]))
        assert report is not None
        analysis = report.metadata_["analysis"]
        created_by = report.metadata_["createdBy"]
        serialized_metadata = json.dumps(report.metadata_, sort_keys=True)
        RunService(session, session_factory)._create_post_run_memory_artifact(run_id)
        reports = list(session.query(Report).all())

    assert len(reports) == 1
    assert artifact["slug"] == report.slug
    assert artifact["name"] == report.name
    assert report.source == "agent"
    assert created_by == {
        "type": "agent",
        "runId": run_id,
        "agentKey": f"{workflow.key}_agent",
        "agentVersion": 1,
        "agentName": f"{workflow.key}_agent-1",
        "workflowKey": workflow.key,
        "workflowVersion": workflow.version,
        "stepId": "decision",
        "slot": "decision",
        "traceId": detail["traceId"],
    }
    assert analysis["reviewType"] == "agent_memory"
    assert analysis["versionGroup"] == "agent_memory/v1"
    assert analysis["ticker"] == "NVDA"
    assert analysis["portfolioSlug"] == "core_us"
    assert analysis["horizonDays"] == 30
    assert analysis["confidence"] == "high"
    assert analysis["decisionSummary"] == "Buy nvda after risk review."
    assert analysis["benchmarkSymbol"] == "NVDA"
    assert analysis["decision"] == {
        "action": "buy",
        "rationale": "Demand and margin trends support upside.",
        "riskSummary": "Valuation risk requires staged sizing.",
        "executionPlan": "Scale in over two sessions.",
    }
    assert analysis["runId"] == run_id
    assert analysis["agentKey"] == f"{workflow.key}_agent"
    assert analysis["agentVersion"] == 1
    assert analysis["workflowKey"] == workflow.key
    assert analysis["workflowVersion"] == workflow.version
    assert analysis["stepId"] == "decision"
    assert analysis["slot"] == "decision"
    assert analysis["traceId"] == detail["traceId"]
    assert "sk-" not in serialized_metadata
    assert "apiKey" not in serialized_metadata
    assert "secret" not in serialized_metadata.lower()


def _seed_tradingagents_v2_runtime_workflow(session: Session) -> WorkflowRead:
    _seed_tradingagents_manifest_refs(session)
    agent_service = AgentService(session, get_default_tool_catalog(), DefaultMcpConnectionTester())
    for source in TRADINGAGENTS_AGENT_MANIFEST_SOURCES.values():
        _ = agent_service.create_agent_from_manifest(source)
    return WorkflowService(session).create_workflow(
        WorkflowCreateRequest.model_validate(
            {"manifestSource": TRADINGAGENTS_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE}
        )
    )


async def _tradingagents_v2_fake_invoke(
    self: RunService,
    *,
    agent: Agent,
    resolved_input: dict[str, Any],
    output_model,
    trace_id: str | None,
    step_index: int,
    slot: str,
) -> dict[str, Any]:
    del self, output_model, trace_id, step_index
    ticker = str(resolved_input.get("ticker") or "NVDA")
    if slot.endswith("report"):
        output = {"summary": f"{slot}:{ticker}"}
    elif agent.key in {"bull_researcher", "bear_researcher"}:
        output = {
            "nextState": {
                "analystReports": {
                    "marketReport": "Market report complete.",
                    "socialSentimentReport": "Social report complete.",
                    "newsReport": "News report complete.",
                    "fundamentalsReport": "Fundamentals report complete.",
                },
                "bullCase": "Demand growth supports upside.",
                "bearCase": "Valuation remains the main risk.",
                "debateHistory": [f"{agent.key}:{slot}"],
            }
        }
    elif agent.key == "research_manager":
        output = {
            "recommendation": "buy",
            "thesis": "Evidence supports a staged long research view.",
            "debateSummary": "Bull and bear cases were debated twice.",
        }
    elif agent.key == "trader":
        output = {
            "action": "buy",
            "rationale": "Research supports staged accumulation.",
            "sizingNotes": "Keep this research-only and size conservatively.",
        }
    elif agent.key.endswith("risk_analyst"):
        output = {
            "nextState": {
                "researchPlan": {
                    "recommendation": "buy",
                    "thesis": "Demand growth supports upside.",
                    "debateSummary": "Risk loop reviewed the proposal.",
                },
                "traderProposal": {
                    "action": "buy",
                    "rationale": "Staged accumulation balances evidence and risk.",
                    "sizingNotes": "Use conservative sizing.",
                },
                "aggressiveCase": "Add on confirmed strength.",
                "neutralCase": "Scale gradually.",
                "conservativeCase": "Hold if volatility widens.",
                "debateHistory": [f"risk:{slot}"],
            }
        }
    else:
        output = {
            "action": "buy",
            "rationale": "Analyst fanout and bounded debates support a staged buy.",
            "riskSummary": "Main risks are valuation and volatility.",
            "executionPlan": "Research-only: scale in over two review windows.",
        }
    return {"output": output, "tokens": 5, "durationMs": 1}


def test_agent_platform_tradingagents_v2_stubbed_run_completes_with_graph_and_memory(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_invoke_agent", _tradingagents_v2_fake_invoke)

    with session_factory() as session:
        workflow = _seed_tradingagents_v2_runtime_workflow(session)

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {
                "ticker": "NVDA",
                "asOfDate": "2026-05-03",
                "portfolioId": "core-us",
                "portfolioSlug": "core_us",
                "horizonDays": 30,
                "benchmarkSymbol": "SPY",
                "initialInvestmentDebateState": {},
                "initialRiskDebateState": {},
            },
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["targetKey"] == "tradingagents_v2_practical_fanout_review"
    assert detail["finalOutput"] == {
        "action": "buy",
        "rationale": "Analyst fanout and bounded debates support a staged buy.",
        "riskSummary": "Main risks are valuation and volatility.",
        "executionPlan": "Research-only: scale in over two review windows.",
    }
    assert [step["index"] for step in detail["steps"]] == list(range(1, 15))
    assert [item["slot"] for item in detail["steps"][0]["invocations"]] == [
        "market_report",
        "social_sentiment_report",
        "news_report",
        "fundamentals_report",
    ]
    assert detail["steps"][0]["graphMetadata"]["fanoutId"] == "analyst_fanout"
    assert detail["steps"][1]["invocations"][0]["graphMetadata"]["loopIteration"] == 1
    assert detail["steps"][3]["invocations"][0]["graphMetadata"]["loopIteration"] == 2
    assert detail["steps"][13]["invocations"][0]["graphMetadata"]["nodeId"] == "portfolio_manager"
    assert len(detail["memoryArtifacts"]) == 1
    artifact = detail["memoryArtifacts"][0]
    assert artifact["status"] == "pending"
    assert artifact["sourceGraphMetadata"]["nodeId"] == "portfolio_manager"
    serialized_detail = json.dumps(detail, sort_keys=True)
    assert "sk-" not in serialized_detail
    assert "apiKey" not in serialized_detail
    assert "configured-test-value" not in serialized_detail

    with session_factory() as session:
        report = session.get(Report, int(artifact["reportId"]))
        assert report is not None
        analysis = report.metadata_["analysis"]
    assert artifact["slug"] == report.slug
    assert analysis["ticker"] == "NVDA"
    assert analysis["benchmarkSymbol"] == "SPY"
    assert analysis["workflowKey"] == workflow.key
    assert analysis["decision"]["action"] == "buy"


def test_agent_platform_v2_post_run_memory_failed_run_writes_no_artifact(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    async def failing_invoke(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        raise RuntimeError("provider failed before memory")

    monkeypatch.setattr(RunService, "_invoke_agent", failing_invoke)

    with session_factory() as session:
        workflow = _create_v2_post_run_memory_workflow(
            session,
            workflow_key="v2_post_memory_failed",
            post_run_memory=_v2_post_run_memory_block(),
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "portfolio_slug": "core_us", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert detail["memoryArtifacts"] == []
    with session_factory() as session:
        assert session.query(Report).count() == 0


def test_agent_platform_agent_run_creation_persists_synthetic_passthrough_step(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    with session_factory() as session:
        _workflow, agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="planned_agent_direct",
            workflow_key="planned_agent_holder_workflow",
            connection=_build_model_connection(name="Planned Direct Agent Connection"),
        )

    trigger = client.post(f"/api/agents/{agent.id}/runs", json={"ticker": "MSFT"})
    assert trigger.status_code == 201, trigger.json()

    detail = client.get(f"/api/runs/{trigger.json()['id']}")
    assert detail.status_code == 200, detail.json()
    body = detail.json()

    assert body["targetKind"] == "agent"
    assert body["status"] == "queued"
    assert body["queuedAt"] is not None
    assert body["startedAt"] is None
    assert [step["index"] for step in body["steps"]] == [1]
    invocation = body["steps"][0]["invocations"][0]
    assert invocation["slot"] == "final_output"
    assert invocation["position"] == 0
    assert invocation["agentId"] == agent.id
    assert invocation["agentKey"] == "planned_agent_direct"
    assert invocation["inputMode"] == "passthrough"
    assert invocation["wiring"] == {}
    assert invocation["resolvedInput"] == {"ticker": "MSFT"}
    assert invocation["resolvedInputOrigin"] == "passthrough"
    assert invocation["status"] == "pending"


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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "AVGO"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    created = trigger.json()
    assert created == {
        "id": created["id"],
        "status": "queued",
        "workflowId": workflow.id,
        "workflowKey": workflow.key,
        "workflowVersion": workflow.version,
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
    assert "perStepOutputs" not in detail
    assert [step["index"] for step in detail["steps"]] == [1]
    step = detail["steps"][0]
    invocation = step["invocations"][0]
    assert step["status"] == "succeeded"
    assert step["origin"] == "planned"
    assert invocation["slot"] == "analysis"
    assert invocation["agentKey"] == "http_agent"
    assert invocation["agentVersion"] == 1
    assert invocation["outputSchemaVersion"] == 1
    assert invocation["inputMode"] == "wired"
    assert invocation["resolvedInput"] == {"ticker": "AVGO"}
    assert invocation["resolvedInputOrigin"] == "derived"
    assert invocation["output"] == {"summary": "http_agent:AVGO"}
    assert invocation["outputOrigin"] == "executed"
    assert invocation["sourceInvocationId"] is None
    assert invocation["errorCode"] is None
    assert invocation["errorMessage"] is None
    assert invocation["errorDetails"] == []
    assert invocation["status"] == "succeeded"
    assert invocation["tokens"] == 13
    assert invocation["durationMs"] == 6
    _assert_logfire_span_id(invocation["traceSpanId"])

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
                "traceId": detail["traceId"],
                "queuedAt": listed.json()["items"][0]["queuedAt"],
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

    response = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA"},
        },
    )
    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["status"] == "queued"
    run_id = created["id"]

    immediate = client.get(f"/api/runs/{run_id}")
    assert immediate.status_code == 200, immediate.json()
    assert immediate.json()["status"] in {"queued", "running"}

    detail = _wait_for_agent_platform_run(client, run_id)
    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    _assert_logfire_span_id(detail["steps"][0]["invocations"][0]["traceSpanId"])
    _assert_logfire_span_id(detail["steps"][0]["invocations"][1]["traceSpanId"])
    _assert_logfire_span_id(detail["steps"][1]["invocations"][0]["traceSpanId"])
    assert detail["finalOutput"] == {"summary": "alpha:NVDA|beta:NVDA"}
    assert set(step_one_slots) == {"alpha", "beta"}
    assert [item["slot"] for item in detail["steps"][0]["invocations"]] == ["alpha", "beta"]
    assert detail["steps"][0]["invocations"][0]["resolvedInput"] == {"ticker": "NVDA"}
    assert detail["steps"][0]["invocations"][0]["status"] == "succeeded"
    assert detail["steps"][1]["invocations"][0]["resolvedInput"] == {
        "analysisA": {"summary": "alpha:NVDA"},
        "analysisB": {"summary": "beta:NVDA"},
    }


def test_agent_platform_queue_claims_queued_run_before_execution(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    with session_factory() as session:
        workflow = _seed_reference_workflow(
            session,
            workflow_key="claim_transition_workflow",
            workflow_name="Claim Transition Workflow",
        )

    first = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 5},
        },
    )
    second = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 5},
        },
    )
    assert first.status_code == 201, first.json()
    assert second.status_code == 201, second.json()
    first_body = first.json()
    second_body = second.json()
    assert first_body["status"] == "queued"
    assert second_body["status"] == "queued"
    assert first_body["id"] != second_body["id"]

    queued_list = client.get(
        "/api/runs",
        params={"targetKind": "workflow", "targetId": workflow.id, "status": "queued"},
    )
    assert queued_list.status_code == 200, queued_list.json()
    assert [item["id"] for item in queued_list.json()["items"]] == [
        second_body["id"],
        first_body["id"],
    ]
    assert all(item["startedAt"] is None for item in queued_list.json()["items"])

    with session_factory() as session:
        claimed_id = RunQueueService(session, session_factory).claim_next_run()

    assert claimed_id == first_body["id"]
    claimed_detail = client.get(f"/api/runs/{first_body['id']}")
    pending_detail = client.get(f"/api/runs/{second_body['id']}")
    assert claimed_detail.status_code == 200, claimed_detail.json()
    assert pending_detail.status_code == 200, pending_detail.json()
    assert claimed_detail.json()["status"] == "running"
    assert claimed_detail.json()["queuedAt"] is not None
    assert claimed_detail.json()["startedAt"] is not None
    assert pending_detail.json()["status"] == "queued"
    assert pending_detail.json()["startedAt"] is None

    queued_after_claim = client.get(
        "/api/runs",
        params={"targetKind": "workflow", "targetId": workflow.id, "status": "queued"},
    )
    assert queued_after_claim.status_code == 200, queued_after_claim.json()
    assert [item["id"] for item in queued_after_claim.json()["items"]] == [second_body["id"]]


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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "MSFT"},
        },
    )
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
            "traceId": detail["traceId"],
            "queuedAt": list_response.json()["items"][0]["queuedAt"],
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
    assert detail["inheritedTokens"] == 0
    assert detail["executedTokens"] == 21
    assert "perStepOutputs" not in detail
    assert [step["index"] for step in detail["steps"]] == [1]
    step = detail["steps"][0]
    invocation = step["invocations"][0]
    assert step["status"] == "succeeded"
    assert step["origin"] == "planned"
    assert invocation["slot"] == "analysis"
    assert invocation["agentKey"] == "detail_agent"
    assert invocation["agentVersion"] == 1
    assert invocation["outputSchemaVersion"] == 1
    assert invocation["resolvedInput"] == {"ticker": "MSFT"}
    assert invocation["resolvedInputOrigin"] == "derived"
    assert invocation["output"] == {"summary": "detail_agent:MSFT"}
    assert invocation["outputOrigin"] == "executed"
    assert invocation["sourceInvocationId"] is None
    assert invocation["errorCode"] is None
    assert invocation["errorMessage"] is None
    assert invocation["errorDetails"] == []
    assert invocation["status"] == "succeeded"
    assert invocation["tokens"] == 21
    assert invocation["durationMs"] == 8
    _assert_logfire_span_id(invocation["traceSpanId"])


def test_agent_platform_report_lookup_run_requires_capability_grant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeToolCallingOpenAIClient.reset()
    _RuntimeToolCallingOpenAIClient.expected_tool_names = ["ledger_market_data_quote_lookup"]
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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == REPORT_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["agentKey"] == "report_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["errorCode"] == REPORT_LOOKUP_ACCESS_DENIED_CODE
    assert step_entry["errorMessage"] == REPORT_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["errorDetails"] == []
    first_tool_names = [
        tool["name"] for tool in _RuntimeToolCallingOpenAIClient.create_calls[0]["tools"]
    ]
    assert first_tool_names == ["ledger_market_data_quote_lookup"]
    assert "ledger_reports_lookup" not in first_tool_names


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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

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


def test_agent_platform_reports_write_run_requires_capability_grant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeReportsWriteToolCallingOpenAIClient.reset()
    _RuntimeReportsWriteToolCallingOpenAIClient.expected_tool_names = ["ledger_reports_lookup"]
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeReportsWriteToolCallingOpenAIClient,
    )

    with session_factory() as session:
        workflow = _seed_backend_reports_write_workflow(
            session,
            grant_reports_write=False,
            workflow_key="backend_reports_write_without_grant",
            skill_key="backend_reports_write_without_grant_skill",
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert step_entry["agentKey"] == "report_memory_writer"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["errorCode"] == REPORT_MEMORY_WRITE_ACCESS_DENIED_CODE
    assert step_entry["errorMessage"] == REPORT_MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert step_entry["errorDetails"] == []
    first_tool_names = [
        tool["name"]
        for tool in _RuntimeReportsWriteToolCallingOpenAIClient.create_calls[0]["tools"]
    ]
    assert first_tool_names == ["ledger_reports_lookup"]
    assert "ledger_reports_write" not in first_tool_names


def test_post_run_memory_artifacts_use_agent_source(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeReportsWriteToolCallingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeReportsWriteToolCallingOpenAIClient,
    )

    with session_factory() as session:
        workflow = _seed_backend_reports_write_workflow(
            session,
            grant_reports_write=True,
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run(client, run_id)
    step_entry = detail["steps"][0]["invocations"][0]

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "report memory written",
        "signal": "bullish",
    }
    assert step_entry["agentKey"] == "report_memory_writer"
    assert step_entry["status"] == "succeeded"
    tool_output = json.loads(
        _RuntimeReportsWriteToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    assert tool_output["toolKey"] == REPORT_MEMORY_WRITE_TOOL_KEY
    assert tool_output["action"] == "created"

    with session_factory() as session:
        report = session.get(Report, int(tool_output["reportId"]))
        assert report is not None
        assert report.source == "agent"
        report_slug = report.slug
        analysis = report.metadata_["analysis"]
        created_by = report.metadata_["createdBy"]

    assert tool_output["reportSlug"] == report_slug
    assert created_by == {
        "type": "agent",
        "runId": run_id,
        "agentKey": "report_memory_writer",
        "agentVersion": 1,
        "agentName": "report_memory_writer-1",
        "workflowKey": workflow.key,
        "workflowVersion": workflow.version,
        "stepId": "step_1",
        "slot": "analysis",
        "traceId": detail["traceId"],
    }
    assert analysis["reviewType"] == "agent_memory"
    assert analysis["versionGroup"] == "agent_memory/v1"
    assert analysis["ticker"] == "NVDA"
    assert analysis["portfolioSlug"] == "core_us"
    assert analysis["horizonDays"] == 30
    assert analysis["confidence"] == "high"
    assert analysis["decisionSummary"] == "Durable earnings setup."
    assert analysis["runId"] == run_id
    assert analysis["agentKey"] == "report_memory_writer"
    assert analysis["agentVersion"] == 1
    assert analysis["agentName"] == "report_memory_writer-1"
    assert analysis["workflowKey"] == workflow.key
    assert analysis["workflowVersion"] == workflow.version
    assert analysis["stepId"] == "step_1"
    assert analysis["slot"] == "analysis"
    assert analysis["traceId"] == detail["traceId"]
    assert analysis["resolvedStatus"] == "pending"
    assert analysis["reflections"] == []
    assert "resolvedAt" not in analysis
    assert "rawReturn" not in analysis
    assert "alpha" not in analysis


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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["agentKey"] == "position_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["errorCode"] == POSITION_LOOKUP_ACCESS_DENIED_CODE
    assert step_entry["errorMessage"] == POSITION_LOOKUP_ACCESS_DENIED_MESSAGE
    assert step_entry["errorDetails"] == []
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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_entry = detail["steps"][0]["invocations"][0]

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == expected_message
    assert step_entry["agentKey"] == "position_lookup_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["errorCode"] == "agent_tool_call_invalid"
    assert step_entry["errorMessage"] == expected_message
    assert step_entry["errorDetails"] == []
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
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NVDA", "horizon_days": 30},
        },
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


def test_agent_platform_quote_lookup_run_uses_injected_market_data_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = [
        "ledger_market_data_quote_lookup"
    ]
    _RuntimePositionToolCallingOpenAIClient.tool_call_name = "ledger_market_data_quote_lookup"
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = (
        '{"symbols":[" nvda "],"baseCurrency":null}'
    )
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"quote lookup used injected provider","signal":"bullish"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)
    quote_provider = _RuntimeMarketDataQuoteProvider()
    app = cast(Any, client.app)
    app.dependency_overrides[get_quote_provider] = lambda: quote_provider

    with session_factory() as session:
        workflow = _seed_backend_market_data_lookup_workflow(
            session,
            tool_key="ledger.market_data.quote_lookup",
            workflow_key="backend_quote_lookup_runtime",
            skill_key="backend_quote_lookup_runtime_skill",
            agent_key="quote_lookup_reader",
        )

    try:
        trigger = client.post(
            f"/api/workflows/{workflow.id}/launches",
            json={
                "version": workflow.version,
                "parameters": {"ticker": "NVDA", "horizon_days": 30},
            },
        )
        assert trigger.status_code == 201, trigger.json()
        detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    finally:
        app.dependency_overrides.pop(get_quote_provider, None)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "quote lookup used injected provider",
        "signal": "bullish",
    }
    assert quote_provider.quote_calls == ["NVDA"]
    tool_output = json.loads(
        _RuntimePositionToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    assert tool_output["toolKey"] == "ledger.market_data.quote_lookup"
    assert tool_output["quotes"][0]["previousClose"] == "119.75000000"
    assert tool_output["quotes"][0]["asOf"] == "2026-01-02T03:04:05Z"
    assert tool_output["quotes"][0]["isStale"] is True


def test_agent_platform_history_lookup_run_uses_injected_market_data_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = [
        "ledger_market_data_history_lookup"
    ]
    _RuntimePositionToolCallingOpenAIClient.tool_call_name = "ledger_market_data_history_lookup"
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = (
        '{"symbols":["NVDA"],"range":"3mo","pointLimit":2}'
    )
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"history lookup used injected provider","signal":"neutral"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)
    quote_provider = _RuntimeMarketDataQuoteProvider()
    app = cast(Any, client.app)
    app.dependency_overrides[get_quote_provider] = lambda: quote_provider

    with session_factory() as session:
        workflow = _seed_backend_market_data_lookup_workflow(
            session,
            tool_key="ledger.market_data.history_lookup",
            workflow_key="backend_history_lookup_runtime",
            skill_key="backend_history_lookup_runtime_skill",
            agent_key="history_lookup_reader",
        )

    try:
        trigger = client.post(
            f"/api/workflows/{workflow.id}/launches",
            json={
                "version": workflow.version,
                "parameters": {"ticker": "NVDA", "horizon_days": 30},
            },
        )
        assert trigger.status_code == 201, trigger.json()
        detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    finally:
        app.dependency_overrides.pop(get_quote_provider, None)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "history lookup used injected provider",
        "signal": "neutral",
    }
    assert quote_provider.history_calls == [("NVDA", "3mo", "1d")]
    tool_output = json.loads(
        _RuntimePositionToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    assert tool_output["toolKey"] == "ledger.market_data.history_lookup"
    assert tool_output["endDate"] == "2026-01-02T03:04:05Z"
    assert tool_output["series"][0]["points"] == [
        {"at": "2026-01-02T00:04:05Z", "close": "119.75"},
        {"at": "2026-01-02T03:04:05Z", "close": "120.25"},
    ]


def test_agent_platform_ohlcv_lookup_run_requires_capability_grant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = [
        "ledger_market_data_quote_lookup"
    ]
    _RuntimePositionToolCallingOpenAIClient.tool_call_name = "ledger_market_data_ohlcv_lookup"
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = json.dumps(
        {
            "symbols": ["NVDA"],
            "startDate": "2026-01-01",
            "endDate": "2026-01-03T16:00:00Z",
            "rowLimit": 2,
        }
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)
    quote_provider = _RuntimeMarketDataQuoteProvider()
    app = cast(Any, client.app)
    app.dependency_overrides[get_quote_provider] = lambda: quote_provider

    with session_factory() as session:
        workflow = _seed_backend_market_data_lookup_workflow(
            session,
            tool_key="ledger.market_data.quote_lookup",
            workflow_key="backend_ohlcv_lookup_without_grant",
            skill_key="backend_ohlcv_lookup_without_grant_skill",
            agent_key="ohlcv_lookup_denied_reader",
        )

    try:
        trigger = client.post(
            f"/api/workflows/{workflow.id}/launches",
            json={
                "version": workflow.version,
                "parameters": {"ticker": "NVDA", "horizon_days": 30},
            },
        )
        assert trigger.status_code == 201, trigger.json()
        detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    finally:
        app.dependency_overrides.pop(get_quote_provider, None)

    step_entry = detail["steps"][0]["invocations"][0]
    expected_message = "Agent is not authorized to use ledger.market_data.ohlcv_lookup."

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == expected_message
    assert step_entry["agentKey"] == "ohlcv_lookup_denied_reader"
    assert step_entry["status"] == "failed"
    assert step_entry["output"] is None
    assert step_entry["errorCode"] == "agent_execution_access_denied"
    assert step_entry["errorMessage"] == expected_message
    assert step_entry["errorDetails"] == []
    first_tool_names = [
        tool["name"] for tool in _RuntimePositionToolCallingOpenAIClient.create_calls[0]["tools"]
    ]
    assert first_tool_names == ["ledger_market_data_quote_lookup"]
    assert "ledger_market_data_ohlcv_lookup" not in first_tool_names
    assert len(_RuntimePositionToolCallingOpenAIClient.create_calls) == 1
    assert quote_provider.ohlcv_calls == []


def test_agent_platform_ohlcv_lookup_run_uses_injected_market_data_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimePositionToolCallingOpenAIClient.reset()
    _RuntimePositionToolCallingOpenAIClient.expected_tool_names = [
        "ledger_market_data_ohlcv_lookup"
    ]
    _RuntimePositionToolCallingOpenAIClient.tool_call_name = "ledger_market_data_ohlcv_lookup"
    _RuntimePositionToolCallingOpenAIClient.tool_arguments_json = json.dumps(
        {
            "symbols": [" nvda "],
            "startDate": "2026-01-01",
            "endDate": "2026-01-03T16:00:00Z",
            "rowLimit": 2,
        }
    )
    _RuntimePositionToolCallingOpenAIClient.final_output_text = (
        '{"summary":"ohlcv lookup used injected provider","signal":"bullish"}'
    )
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimePositionToolCallingOpenAIClient)
    quote_provider = _RuntimeMarketDataQuoteProvider()
    app = cast(Any, client.app)
    app.dependency_overrides[get_quote_provider] = lambda: quote_provider

    with session_factory() as session:
        workflow = _seed_backend_market_data_lookup_workflow(
            session,
            tool_key="ledger.market_data.ohlcv_lookup",
            workflow_key="backend_ohlcv_lookup_runtime",
            skill_key="backend_ohlcv_lookup_runtime_skill",
            agent_key="ohlcv_lookup_reader",
        )

    try:
        trigger = client.post(
            f"/api/workflows/{workflow.id}/launches",
            json={
                "version": workflow.version,
                "parameters": {"ticker": "NVDA", "horizon_days": 30},
            },
        )
        assert trigger.status_code == 201, trigger.json()
        detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    finally:
        app.dependency_overrides.pop(get_quote_provider, None)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "summary": "ohlcv lookup used injected provider",
        "signal": "bullish",
    }
    assert quote_provider.ohlcv_calls == [
        (
            "NVDA",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, 16, tzinfo=UTC),
            "1d",
        )
    ]
    first_tool = _RuntimePositionToolCallingOpenAIClient.create_calls[0]["tools"][0]
    assert first_tool["name"] == "ledger_market_data_ohlcv_lookup"
    assert first_tool["parameters"]["required"] == [
        "symbols",
        "startDate",
        "endDate",
        "rowLimit",
    ]
    assert first_tool["parameters"]["properties"]["rowLimit"]["maximum"] == 500

    tool_output = json.loads(
        _RuntimePositionToolCallingOpenAIClient.create_calls[1]["input"][0]["output"]
    )
    output_json = json.dumps(tool_output)
    assert "adjusted_close" not in output_json
    assert tool_output["toolKey"] == "ledger.market_data.ohlcv_lookup"
    assert tool_output["startDate"] == "2026-01-01T00:00:00Z"
    assert tool_output["endDate"] == "2026-01-03T16:00:00Z"
    assert tool_output["warnings"] == []
    assert tool_output["series"][0]["symbol"] == "NVDA"
    assert tool_output["series"][0]["provider"] == "api_fake_provider"
    assert tool_output["series"][0]["rows"] == [
        {
            "at": "2026-01-01T00:00:00Z",
            "open": "118.00",
            "high": "121.00",
            "low": "117.00",
            "close": "119.75",
            "volume": 1000,
            "adjustedClose": "119.50",
        },
        {
            "at": "2026-01-03T16:00:00Z",
            "open": "119.75",
            "high": "121.50",
            "low": "119.00",
            "close": "120.25",
            "volume": 1200,
            "adjustedClose": None,
        },
    ]


def test_agent_platform_budget_metadata_does_not_enforce_agent_runtime_cost(
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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "TSLA"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["error"] is None
    assert detail["finalOutput"] == {"summary": "too expensive"}
    assert detail["totalTokens"] == 12
    assert detail["executedTokens"] == 12
    assert detail["steps"][0]["invocations"][0]["status"] == "succeeded"
    assert detail["steps"][0]["invocations"][0]["output"] == {"summary": "too expensive"}
    assert detail["steps"][0]["invocations"][0]["errorCode"] is None
    assert detail["steps"][0]["invocations"][0]["tokens"] == 12


def test_agent_platform_budget_metadata_does_not_enforce_aggregate_runtime_cost(
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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "AMD"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["error"] is None
    assert detail["finalOutput"] == {"summary": "alpha"}
    assert detail["totalTokens"] == 10
    assert detail["executedTokens"] == 10
    assert detail["steps"][0]["invocations"][0]["status"] == "succeeded"
    assert detail["steps"][0]["invocations"][1]["status"] == "succeeded"
    assert detail["steps"][0]["invocations"][1]["errorCode"] is None
    assert [invocation["tokens"] for invocation in detail["steps"][0]["invocations"]] == [5, 5]


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

    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={
            "version": workflow.version,
            "parameters": {"ticker": "NFLX"},
        },
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    assert detail["finalOutput"] == {"summary": "fallback decision"}
    assert detail["steps"][0]["invocations"][0]["status"] == "failed"
    assert detail["steps"][0]["invocations"][0]["output"] is None
    assert detail["steps"][0]["invocations"][0]["errorCode"] == "agent_execution_failed"
    assert detail["steps"][1]["invocations"][0]["resolvedInput"] == {}
    assert detail["steps"][1]["invocations"][0]["status"] == "succeeded"


def test_tradingagents_fixed_workflow_runs_end_to_end_with_mcp_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setenv("MCP_RUNTIME_ENABLED", "false")
    reset_settings_cache()
    observed_inputs: dict[str, dict[str, Any]] = {}

    async def fake_invoke(self: RunService, **kwargs: Any) -> dict[str, Any]:
        del self
        slot = str(kwargs["slot"])
        resolved_input = cast(dict[str, Any], kwargs["resolved_input"])
        observed_inputs[slot] = resolved_input
        if slot.endswith("_report"):
            return {
                "output": {
                    "summary": f"{slot} for {resolved_input['ticker']}",
                    "signal": "neutral",
                }
            }
        if slot == "bull_round_1":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            return {"output": {"nextState": prior_state | {"history": ["bull_round_1"]}}}
        if slot == "bear_round_1":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            history = [*prior_state["history"], "bear_round_1"]
            return {"output": {"nextState": prior_state | {"history": history}}}
        if slot == "bull_round_2":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            history = [*prior_state["history"], "bull_round_2"]
            return {"output": {"nextState": prior_state | {"history": history}}}
        if slot == "bear_round_2":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            history = [*prior_state["history"], "bear_round_2"]
            return {"output": {"nextState": prior_state | {"history": history}}}
        if slot == "research_plan":
            debate_state = cast(dict[str, Any], resolved_input["debateState"])
            return {"output": {"recommendation": "hold", "history": debate_state["history"]}}
        if slot == "trader_proposal":
            research_plan = cast(dict[str, Any], resolved_input["researchPlan"])
            return {"output": {"action": "hold", "history": research_plan["history"]}}
        if slot == "aggressive":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            return {"output": {"nextState": prior_state | {"history": ["aggressive"]}}}
        if slot == "neutral":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            return {
                "output": {
                    "nextState": prior_state | {"history": [*prior_state["history"], "neutral"]}
                }
            }
        if slot == "conservative":
            prior_state = cast(dict[str, Any], resolved_input["priorState"])
            return {
                "output": {
                    "nextState": prior_state
                    | {"history": [*prior_state["history"], "conservative"]}
                }
            }
        risk_state = cast(dict[str, Any], resolved_input["riskState"])
        return {
            "output": {
                "action": "hold",
                "rationale": "Risk debate completed.",
                "history": risk_state["history"],
            }
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    state_schema = {"type": "object", "additionalProperties": True}
    transition_schema = {
        "type": "object",
        "properties": {"nextState": state_schema},
        "required": ["nextState"],
        "additionalProperties": False,
    }
    note_schema = _reference_note_schema()
    plan_schema = {
        "type": "object",
        "properties": {
            "recommendation": {"type": "string"},
            "history": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["recommendation", "history"],
        "additionalProperties": False,
    }
    proposal_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "history": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action", "history"],
        "additionalProperties": False,
    }
    decision_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "rationale": {"type": "string"},
            "history": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action", "rationale", "history"],
        "additionalProperties": False,
    }
    analyst_input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}, "horizon_days": {"type": "integer"}},
        "required": ["ticker", "horizon_days"],
        "additionalProperties": False,
    }
    prior_state_input_schema = {
        "type": "object",
        "properties": {"priorState": state_schema},
        "required": ["priorState"],
        "additionalProperties": False,
    }
    with session_factory() as session:
        note_output = _build_output_schema(key="tradingagents_note", version=1, status="published")
        note_output.json_schema = note_schema
        transition_output = _build_output_schema(
            key="tradingagents_transition", version=1, status="published"
        )
        transition_output.json_schema = transition_schema
        plan_output = _build_output_schema(key="tradingagents_plan", version=1, status="published")
        plan_output.json_schema = plan_schema
        proposal_output = _build_output_schema(
            key="tradingagents_proposal", version=1, status="published"
        )
        proposal_output.json_schema = proposal_schema
        decision_output = _build_output_schema(
            key="tradingagents_decision", version=1, status="published"
        )
        decision_output.json_schema = decision_schema
        capability = _build_skill(
            key="tradingagents_runtime_tools",
            version=1,
            status="published",
            tools=[
                MARKET_DATA_QUOTE_LOOKUP_TOOL_KEY,
                MARKET_DATA_HISTORY_LOOKUP_TOOL_KEY,
                REPORT_MEMORY_WRITE_TOOL_KEY,
            ],
        )
        mcp_server = _build_mcp_server(
            key="tradingagents_runtime_data",
            version=1,
            status="published",
            transport="stdio",
        )
        connection = _build_model_connection(name="TradingAgents Runtime Connection")
        session.add_all(
            [
                note_output,
                transition_output,
                plan_output,
                proposal_output,
                decision_output,
                capability,
                mcp_server,
                connection,
            ]
        )
        session.flush()
        analyst_agents = [
            _build_agent_platform_agent(
                key=agent_key,
                version=1,
                status="published",
                output_schema=note_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=analyst_input_schema,
            )
            for agent_key in [
                "market_analyst",
                "social_analyst",
                "news_analyst",
                "fundamentals_analyst",
            ]
        ]
        agents = [
            *analyst_agents,
            _build_agent_platform_agent(
                key="bull_researcher",
                version=1,
                status="published",
                output_schema=transition_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=prior_state_input_schema,
            ),
            _build_agent_platform_agent(
                key="bear_researcher",
                version=1,
                status="published",
                output_schema=transition_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=prior_state_input_schema,
            ),
            _build_agent_platform_agent(
                key="research_manager",
                version=1,
                status="published",
                output_schema=plan_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema={
                    "type": "object",
                    "properties": {"debateState": state_schema},
                    "required": ["debateState"],
                    "additionalProperties": False,
                },
            ),
            _build_agent_platform_agent(
                key="trader",
                version=1,
                status="published",
                output_schema=proposal_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema={
                    "type": "object",
                    "properties": {"researchPlan": plan_schema},
                    "required": ["researchPlan"],
                    "additionalProperties": False,
                },
            ),
            _build_agent_platform_agent(
                key="aggressive_risk_analyst",
                version=1,
                status="published",
                output_schema=transition_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema={
                    "type": "object",
                    "properties": {
                        "priorState": state_schema,
                        "researchPlan": plan_schema,
                        "traderProposal": proposal_schema,
                    },
                    "required": ["priorState", "researchPlan", "traderProposal"],
                    "additionalProperties": False,
                },
            ),
            _build_agent_platform_agent(
                key="neutral_risk_analyst",
                version=1,
                status="published",
                output_schema=transition_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=prior_state_input_schema,
            ),
            _build_agent_platform_agent(
                key="conservative_risk_analyst",
                version=1,
                status="published",
                output_schema=transition_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema=prior_state_input_schema,
            ),
            _build_agent_platform_agent(
                key="portfolio_manager",
                version=1,
                status="published",
                output_schema=decision_output,
                skill=capability,
                mcp_server=mcp_server,
                model_connection=connection,
                input_schema={
                    "type": "object",
                    "properties": {"riskState": state_schema},
                    "required": ["riskState"],
                    "additionalProperties": False,
                },
            ),
        ]
        session.add_all(agents)
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "tradingagents_state_carry",
                    "name": "TradingAgents State Carry",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "horizon_days": {"type": "integer"},
                            "initialInvestmentDebateState": state_schema,
                            "initialRiskDebateState": state_schema,
                        },
                        "required": [
                            "ticker",
                            "horizon_days",
                            "initialInvestmentDebateState",
                            "initialRiskDebateState",
                        ],
                        "additionalProperties": False,
                    },
                    "steps": [
                        {
                            "index": 1,
                            "agents": [
                                {
                                    "agentKey": "market_analyst",
                                    "slot": "market_report",
                                    "wiring": {
                                        "ticker": {"from": "input", "path": "ticker"},
                                        "horizon_days": {"from": "input", "path": "horizon_days"},
                                    },
                                },
                                {
                                    "agentKey": "social_analyst",
                                    "slot": "social_report",
                                    "wiring": {
                                        "ticker": {"from": "input", "path": "ticker"},
                                        "horizon_days": {"from": "input", "path": "horizon_days"},
                                    },
                                },
                                {
                                    "agentKey": "news_analyst",
                                    "slot": "news_report",
                                    "wiring": {
                                        "ticker": {"from": "input", "path": "ticker"},
                                        "horizon_days": {"from": "input", "path": "horizon_days"},
                                    },
                                },
                                {
                                    "agentKey": "fundamentals_analyst",
                                    "slot": "fundamentals_report",
                                    "wiring": {
                                        "ticker": {"from": "input", "path": "ticker"},
                                        "horizon_days": {"from": "input", "path": "horizon_days"},
                                    },
                                },
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "bull_researcher",
                                    "slot": "bull_round_1",
                                    "wiring": {
                                        "priorState": {
                                            "from": "input",
                                            "path": "initialInvestmentDebateState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 3,
                            "agents": [
                                {
                                    "agentKey": "bear_researcher",
                                    "slot": "bear_round_1",
                                    "wiring": {
                                        "priorState": {
                                            "from": "step",
                                            "stepIndex": 2,
                                            "slot": "bull_round_1",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 4,
                            "agents": [
                                {
                                    "agentKey": "bull_researcher",
                                    "slot": "bull_round_2",
                                    "wiring": {
                                        "priorState": {
                                            "from": "step",
                                            "stepIndex": 3,
                                            "slot": "bear_round_1",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 5,
                            "agents": [
                                {
                                    "agentKey": "bear_researcher",
                                    "slot": "bear_round_2",
                                    "wiring": {
                                        "priorState": {
                                            "from": "step",
                                            "stepIndex": 4,
                                            "slot": "bull_round_2",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 6,
                            "agents": [
                                {
                                    "agentKey": "research_manager",
                                    "slot": "research_plan",
                                    "wiring": {
                                        "debateState": {
                                            "from": "step",
                                            "stepIndex": 5,
                                            "slot": "bear_round_2",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 7,
                            "agents": [
                                {
                                    "agentKey": "trader",
                                    "slot": "trader_proposal",
                                    "wiring": {
                                        "researchPlan": {
                                            "from": "step",
                                            "stepIndex": 6,
                                            "slot": "research_plan",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 8,
                            "agents": [
                                {
                                    "agentKey": "aggressive_risk_analyst",
                                    "slot": "aggressive",
                                    "wiring": {
                                        "priorState": {
                                            "from": "input",
                                            "path": "initialRiskDebateState",
                                        },
                                        "researchPlan": {
                                            "from": "step",
                                            "stepIndex": 6,
                                            "slot": "research_plan",
                                        },
                                        "traderProposal": {
                                            "from": "step",
                                            "stepIndex": 7,
                                            "slot": "trader_proposal",
                                        },
                                    },
                                }
                            ],
                        },
                        {
                            "index": 9,
                            "agents": [
                                {
                                    "agentKey": "neutral_risk_analyst",
                                    "slot": "neutral",
                                    "wiring": {
                                        "priorState": {
                                            "from": "step",
                                            "stepIndex": 8,
                                            "slot": "aggressive",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 10,
                            "agents": [
                                {
                                    "agentKey": "conservative_risk_analyst",
                                    "slot": "conservative",
                                    "wiring": {
                                        "priorState": {
                                            "from": "step",
                                            "stepIndex": 9,
                                            "slot": "neutral",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                        {
                            "index": 11,
                            "agents": [
                                {
                                    "agentKey": "portfolio_manager",
                                    "slot": "decision",
                                    "wiring": {
                                        "riskState": {
                                            "from": "step",
                                            "stepIndex": 10,
                                            "slot": "conservative",
                                            "path": "nextState",
                                        }
                                    },
                                }
                            ],
                        },
                    ],
                    "outputSpec": {"kind": "slot", "stepIndex": 11, "slot": "decision"},
                }
            )
        )

    run_input = {
        "ticker": "NVDA",
        "horizon_days": 30,
        "initialInvestmentDebateState": {"history": []},
        "initialRiskDebateState": {"history": []},
    }
    trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": run_input},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {
        "action": "hold",
        "rationale": "Risk debate completed.",
        "history": ["aggressive", "neutral", "conservative"],
    }
    assert detail["steps"][1]["invocations"][0]["output"] == {
        "nextState": {"history": ["bull_round_1"]}
    }
    assert "priorState" not in detail["steps"][1]["invocations"][0]["output"]
    assert detail["steps"][7]["invocations"][0]["output"] == {
        "nextState": {"history": ["aggressive"]}
    }
    assert "priorState" not in detail["steps"][7]["invocations"][0]["output"]
    assert [entry["slot"] for entry in detail["steps"][0]["invocations"]] == [
        "market_report",
        "social_report",
        "news_report",
        "fundamentals_report",
    ]
    assert observed_inputs["market_report"] == {"ticker": "NVDA", "horizon_days": 30}
    assert observed_inputs["bull_round_1"]["priorState"] == {"history": []}
    assert observed_inputs["bear_round_1"]["priorState"] == {"history": ["bull_round_1"]}
    assert observed_inputs["bull_round_2"]["priorState"] == {
        "history": ["bull_round_1", "bear_round_1"]
    }
    assert observed_inputs["bear_round_2"]["priorState"] == {
        "history": ["bull_round_1", "bear_round_1", "bull_round_2"]
    }
    assert observed_inputs["research_plan"]["debateState"] == {
        "history": ["bull_round_1", "bear_round_1", "bull_round_2", "bear_round_2"]
    }
    assert observed_inputs["trader_proposal"]["researchPlan"] == {
        "recommendation": "hold",
        "history": ["bull_round_1", "bear_round_1", "bull_round_2", "bear_round_2"],
    }
    assert observed_inputs["aggressive"]["priorState"] == {"history": []}
    assert observed_inputs["neutral"]["priorState"] == {"history": ["aggressive"]}
    assert observed_inputs["conservative"]["priorState"] == {"history": ["aggressive", "neutral"]}
    assert observed_inputs["decision"]["riskState"] == {
        "history": ["aggressive", "neutral", "conservative"]
    }
    reset_settings_cache()


def _create_replay_runtime_workflow(
    session: Session,
    *,
    workflow_key: str,
    optional_first_agent: bool = False,
    require_decider_analysis: bool = True,
) -> WorkflowRead:
    output_schema = _build_output_schema(
        key=f"{workflow_key}_schema",
        version=1,
        status="published",
    )
    skill = _build_skill(
        key=f"{workflow_key}_skill",
        version=1,
        status="published",
        tools=["ledger.market_data.quote_lookup"],
    )
    mcp_server = _build_mcp_server(
        key=f"{workflow_key}_server",
        version=1,
        status="published",
        transport="http-sse",
    )
    connection = _build_model_connection(name=f"{workflow_key} Connection")
    session.add_all([output_schema, skill, mcp_server, connection])
    session.flush()
    analyst = _build_agent_platform_agent(
        key=f"{workflow_key}_analyst",
        version=1,
        status="published",
        output_schema=output_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
    )
    decider_input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            }
        },
    }
    if require_decider_analysis:
        decider_input_schema["required"] = ["analysis"]
    decider = _build_agent_platform_agent(
        key=f"{workflow_key}_decider",
        version=1,
        status="published",
        output_schema=output_schema,
        skill=skill,
        mcp_server=mcp_server,
        model_connection=connection,
        input_schema=decider_input_schema,
    )
    session.add_all([analyst, decider])
    session.commit()
    return WorkflowService(session).create_workflow(
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
                                "agentKey": f"{workflow_key}_analyst",
                                "slot": "analysis",
                                "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                "optional": optional_first_agent,
                            }
                        ],
                    },
                    {
                        "index": 2,
                        "agents": [
                            {
                                "agentKey": f"{workflow_key}_decider",
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


def test_agent_platform_run_rerun_draft_and_create_starts_from_first_step(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[tuple[int, str, dict[str, Any]]] = []

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
        calls.append((step_index, slot, dict(resolved_input)))
        if step_index == 1:
            return {
                "output": {"summary": f"source:{resolved_input['ticker']}"},
                "tokens": 10,
                "durationMs": 4,
                "traceSpanId": None,
            }
        return {
            "output": {"summary": f"decision:{resolved_input['analysis']['summary']}"},
            "tokens": 5,
            "durationMs": 3,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(session, workflow_key="rerun_workflow")

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "NVDA"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])
    assert source_detail["status"] == "succeeded"

    draft = client.get(f"/api/runs/{source_detail['id']}/rerun-draft")
    assert draft.status_code == 200, draft.json()
    assert draft.json() == {
        "sourceRunId": source_detail["id"],
        "targetKind": "workflow",
        "targetId": workflow.id,
        "targetKey": workflow.key,
        "targetVersion": workflow.version,
        "parameters": {"ticker": "NVDA"},
    }

    calls.clear()
    rerun = client.post(
        f"/api/runs/{source_detail['id']}/reruns",
        json={"parameters": {"ticker": "MSFT"}},
    )
    assert rerun.status_code == 201, rerun.json()
    assert rerun.json()["id"] != source_detail["id"]
    assert rerun.json()["status"] == "queued"
    rerun_detail = _wait_for_agent_platform_run(client, rerun.json()["id"])

    assert calls == [
        (1, "analysis", {"ticker": "MSFT"}),
        (2, "decision", {"analysis": {"summary": "source:MSFT"}}),
    ]
    assert rerun_detail["sourceRunId"] == source_detail["id"]
    assert rerun_detail["lineageRootRunId"] == source_detail["id"]
    assert rerun_detail["replayStepIndex"] is None
    assert rerun_detail["resumeStepIndex"] == 1
    assert rerun_detail["input"] == {"ticker": "MSFT"}
    assert rerun_detail["finalOutput"] == {"summary": "decision:source:MSFT"}
    assert rerun_detail["inheritedTokens"] == 0
    assert rerun_detail["executedTokens"] == 15
    assert [step["origin"] for step in rerun_detail["steps"]] == ["planned", "planned"]
    assert all(
        invocation["sourceInvocationId"] is None
        for step in rerun_detail["steps"]
        for invocation in step["invocations"]
    )

    source_after = client.get(f"/api/runs/{source_detail['id']}")
    assert source_after.status_code == 200, source_after.json()
    assert source_after.json()["status"] == source_detail["status"]
    assert source_after.json()["input"] == {"ticker": "NVDA"}
    assert source_after.json()["finalOutput"] == source_detail["finalOutput"]
    assert source_after.json()["sourceRunId"] == source_detail["sourceRunId"]
    assert source_after.json()["replayStepIndex"] == source_detail["replayStepIndex"]
    assert [step["origin"] for step in source_after.json()["steps"]] == [
        step["origin"] for step in source_detail["steps"]
    ]
    assert source_after.json()["steps"][0]["invocations"][0]["output"] == {"summary": "source:NVDA"}


def test_agent_platform_run_step_replay_copies_prior_context_and_replays_step(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[tuple[int, str, dict[str, Any]]] = []

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
        calls.append((step_index, slot, dict(resolved_input)))
        if step_index == 1:
            return {
                "output": {"summary": f"source:{resolved_input['ticker']}"},
                "tokens": 10,
                "durationMs": 4,
                "traceSpanId": None,
            }
        return {
            "output": {"summary": f"decision:{resolved_input['analysis']['summary']}"},
            "tokens": 5,
            "durationMs": 3,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(session, workflow_key="step_replay_workflow")

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "NVDA"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])
    assert source_detail["status"] == "succeeded"

    draft = client.get(
        f"/api/runs/{source_detail['id']}/step-replay-draft",
        params={"stepIndex": 2},
    )
    assert draft.status_code == 200, draft.json()
    assert draft.json()["replayStepIndex"] == 2
    assert draft.json()["parameters"] == {"ticker": "NVDA"}

    calls.clear()
    replay = client.post(
        f"/api/runs/{source_detail['id']}/step-replays",
        json={"replayStepIndex": 2, "parameters": {"ticker": "MSFT"}},
    )
    assert replay.status_code == 201, replay.json()
    assert replay.json()["id"] != source_detail["id"]
    replay_detail = _wait_for_agent_platform_run(client, replay.json()["id"])

    assert calls == [(2, "decision", {"analysis": {"summary": "source:NVDA"}})]
    assert replay_detail["sourceRunId"] == source_detail["id"]
    assert replay_detail["lineageRootRunId"] == source_detail["id"]
    assert replay_detail["replayStepIndex"] == 2
    assert replay_detail["resumeStepIndex"] == 2
    assert replay_detail["input"] == {"ticker": "MSFT"}
    assert replay_detail["finalOutput"] == {"summary": "decision:source:NVDA"}
    assert replay_detail["inheritedTokens"] == 10
    assert replay_detail["executedTokens"] == 5
    assert [step["origin"] for step in replay_detail["steps"]] == ["copied", "planned"]
    copied_invocation = replay_detail["steps"][0]["invocations"][0]
    assert copied_invocation["resolvedInput"] == {"ticker": "NVDA"}
    assert copied_invocation["resolvedInputOrigin"] == "copied"
    assert copied_invocation["output"] == {"summary": "source:NVDA"}
    assert copied_invocation["outputOrigin"] == "copied"
    assert copied_invocation["sourceInvocationId"] == (
        source_detail["steps"][0]["invocations"][0]["id"]
    )
    replayed_invocation = replay_detail["steps"][1]["invocations"][0]
    assert replayed_invocation["outputOrigin"] == "executed"
    assert replayed_invocation["sourceInvocationId"] is None

    source_after = client.get(f"/api/runs/{source_detail['id']}")
    assert source_after.status_code == 200, source_after.json()
    assert source_after.json()["status"] == source_detail["status"]
    assert source_after.json()["input"] == {"ticker": "NVDA"}
    assert source_after.json()["finalOutput"] == source_detail["finalOutput"]
    assert source_after.json()["sourceRunId"] == source_detail["sourceRunId"]
    assert source_after.json()["replayStepIndex"] == source_detail["replayStepIndex"]
    assert [step["origin"] for step in source_after.json()["steps"]] == [
        step["origin"] for step in source_detail["steps"]
    ]
    assert source_after.json()["steps"][0]["invocations"][0]["resolvedInput"] == {"ticker": "NVDA"}
    assert source_after.json()["steps"][0]["invocations"][0]["output"] == {"summary": "source:NVDA"}


def test_agent_platform_run_step_replay_copies_prior_optional_failed_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    calls: list[tuple[int, str, dict[str, Any]]] = []

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
        calls.append((step_index, slot, dict(resolved_input)))
        if step_index == 1:
            raise RuntimeError(f"analysis failed for {resolved_input['ticker']}")
        return {
            "output": {"summary": f"decision:{resolved_input.get('analysis', 'fallback')}"},
            "tokens": 5,
            "durationMs": 3,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(
            session,
            workflow_key="step_replay_optional_failed_workflow",
            optional_first_agent=True,
            require_decider_analysis=False,
        )

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "NVDA"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])

    assert source_detail["status"] == "succeeded"
    assert source_detail["input"] == {"ticker": "NVDA"}
    assert source_detail["finalOutput"] == {"summary": "decision:fallback"}
    source_optional_invocation = source_detail["steps"][0]["invocations"][0]
    assert source_optional_invocation["optional"] is True
    assert source_optional_invocation["status"] == "failed"
    assert source_optional_invocation["resolvedInput"] == {"ticker": "NVDA"}
    assert source_optional_invocation["output"] is None
    assert source_optional_invocation["outputOrigin"] is None
    assert source_optional_invocation["errorCode"] == "agent_execution_failed"
    assert source_optional_invocation["errorMessage"] == "analysis failed for NVDA"
    assert source_optional_invocation["persistedAt"] is not None
    assert source_detail["steps"][1]["invocations"][0]["resolvedInput"] == {}

    draft = client.get(
        f"/api/runs/{source_detail['id']}/step-replay-draft",
        params={"stepIndex": 2},
    )
    assert draft.status_code == 200, draft.json()
    assert draft.json()["replayStepIndex"] == 2

    calls.clear()
    replay = client.post(
        f"/api/runs/{source_detail['id']}/step-replays",
        json={"replayStepIndex": 2, "parameters": {"ticker": "MSFT"}},
    )
    assert replay.status_code == 201, replay.json()
    assert replay.json()["id"] != source_detail["id"]
    replay_detail = _wait_for_agent_platform_run(client, replay.json()["id"])

    assert calls == [(2, "decision", {})]
    assert replay_detail["status"] == "succeeded"
    assert replay_detail["sourceRunId"] == source_detail["id"]
    assert replay_detail["replayStepIndex"] == 2
    assert replay_detail["resumeStepIndex"] == 2
    assert replay_detail["input"] == {"ticker": "MSFT"}
    assert replay_detail["finalOutput"] == {"summary": "decision:fallback"}
    copied_optional_invocation = replay_detail["steps"][0]["invocations"][0]
    assert copied_optional_invocation["optional"] is True
    assert copied_optional_invocation["status"] == "failed"
    assert copied_optional_invocation["resolvedInput"] == {"ticker": "NVDA"}
    assert copied_optional_invocation["resolvedInputOrigin"] == "copied"
    assert copied_optional_invocation["output"] is None
    assert copied_optional_invocation["outputOrigin"] is None
    assert copied_optional_invocation["errorCode"] == source_optional_invocation["errorCode"]
    assert copied_optional_invocation["errorMessage"] == source_optional_invocation["errorMessage"]
    assert copied_optional_invocation["errorDetails"] == source_optional_invocation["errorDetails"]
    assert copied_optional_invocation["sourceInvocationId"] == source_optional_invocation["id"]
    assert copied_optional_invocation["startedAt"] == source_optional_invocation["startedAt"]
    assert copied_optional_invocation["finishedAt"] == source_optional_invocation["finishedAt"]
    assert copied_optional_invocation["persistedAt"] is not None
    assert replay_detail["steps"][1]["invocations"][0]["outputOrigin"] == "executed"

    source_after = client.get(f"/api/runs/{source_detail['id']}")
    assert source_after.status_code == 200, source_after.json()
    assert source_after.json()["status"] == source_detail["status"]
    assert source_after.json()["input"] == source_detail["input"]
    assert source_after.json()["finalOutput"] == source_detail["finalOutput"]
    assert source_after.json()["steps"] == source_detail["steps"]


def test_agent_platform_run_step_replay_rejects_required_failed_prior_context(
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
        if step_index == 1:
            output = {"summary": f"source:{resolved_input['ticker']}"}
        else:
            output = {"summary": f"decision:{resolved_input['analysis']['summary']}"}
        return {"output": output, "tokens": 3, "durationMs": 1}

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(
            session,
            workflow_key="step_replay_required_failed_context_workflow",
        )

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "AMD"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])
    assert source_detail["status"] == "succeeded"

    with session_factory() as session:
        run = session.get(Run, source_detail["id"])
        assert run is not None
        source_step = cast(list[RunStep], run.steps)[0]
        invocation = cast(list[RunAgentInvocation], source_step.invocations)[0]
        invocation.status = "failed"
        invocation.output = None
        invocation.output_origin = None
        invocation.error_code = "agent_execution_failed"
        invocation.error_message = "required source failed"
        session.commit()

    rejected = client.post(
        f"/api/runs/{source_detail['id']}/step-replays",
        json={"replayStepIndex": 2, "parameters": {"ticker": "AMD"}},
    )
    assert rejected.status_code == 400, rejected.json()
    assert rejected.json()["code"] == "run_step_replay_context_output_not_persisted"


def test_agent_platform_run_step_replay_rejects_non_persisted_source_step(
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
        if step_index == 1:
            output = {"summary": f"source:{resolved_input['ticker']}"}
        else:
            output = {"summary": f"decision:{resolved_input['analysis']['summary']}"}
        return {"output": output, "tokens": 3, "durationMs": 1}

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(
            session, workflow_key="step_replay_reject_workflow"
        )

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "AMD"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])
    with session_factory() as session:
        run = session.get(Run, source_detail["id"])
        assert run is not None
        steps = cast(list[RunStep], run.steps)
        steps[1].status = "failed"
        steps[1].persisted_at = None
        session.commit()

    rejected = client.post(
        f"/api/runs/{source_detail['id']}/step-replays",
        json={"replayStepIndex": 2, "parameters": {"ticker": "AMD"}},
    )
    assert rejected.status_code == 400, rejected.json()
    assert rejected.json()["code"] == "run_step_replay_step_not_persisted"


def test_agent_platform_run_step_replay_rejects_agent_source_run_without_creating_run(
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
            "output": {"summary": f"agent:{resolved_input['ticker']}"},
            "tokens": 8,
            "durationMs": 2,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        _workflow, agent = _create_single_agent_runtime_workflow(
            session,
            agent_key="step_replay_agent_source_agent",
            workflow_key="step_replay_agent_source_holder_workflow",
            connection=_build_model_connection(name="Step Replay Agent Source Connection"),
        )

    source_trigger = client.post(f"/api/agents/{agent.id}/runs", json={"ticker": "AAPL"})
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])
    assert source_detail["targetKind"] == "agent"

    draft = client.get(
        f"/api/runs/{source_detail['id']}/step-replay-draft",
        params={"stepIndex": 1},
    )
    assert draft.status_code == 400, draft.json()
    assert draft.json()["code"] == "run_step_replay_target_kind_unsupported"

    replay = client.post(
        f"/api/runs/{source_detail['id']}/step-replays",
        json={"replayStepIndex": 1, "parameters": {"ticker": "TSLA"}},
    )
    assert replay.status_code == 400, replay.json()
    assert replay.json()["code"] == "run_step_replay_target_kind_unsupported"

    listed = client.get("/api/runs", params={"targetKind": "agent", "targetId": agent.id})
    assert listed.status_code == 200, listed.json()
    assert [item["id"] for item in listed.json()["items"]] == [source_detail["id"]]


def test_agent_platform_legacy_fork_run_endpoints_are_unavailable_without_creating_run(
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
        if step_index == 1:
            output = {"summary": f"source:{resolved_input['ticker']}"}
        else:
            output = {"summary": f"decision:{resolved_input['analysis']['summary']}"}
        return {"output": output, "tokens": 1, "durationMs": 1}

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)
    with session_factory() as session:
        workflow = _create_replay_runtime_workflow(
            session, workflow_key="removed_endpoint_workflow"
        )

    source_trigger = client.post(
        f"/api/workflows/{workflow.id}/launches",
        json={"version": workflow.version, "parameters": {"ticker": "NVDA"}},
    )
    assert source_trigger.status_code == 201, source_trigger.json()
    source_detail = _wait_for_agent_platform_run(client, source_trigger.json()["id"])

    draft = client.get(
        f"/api/runs/{source_detail['id']}/fork-draft",
        params={"forkStepIndex": 1},
    )
    assert draft.status_code == 404
    create = client.post(
        f"/api/runs/{source_detail['id']}/forks",
        json={"forkStepIndex": 1, "input": {"ticker": "MSFT"}},
    )
    assert create.status_code == 404

    listed = client.get("/api/runs", params={"targetKind": "workflow", "targetId": workflow.id})
    assert listed.status_code == 200, listed.json()
    assert [item["id"] for item in listed.json()["items"]] == [source_detail["id"]]
