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

from app.agents import get_default_skill_registry
from app.core.config import reset_settings_cache
from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.models.run import Run
from app.models.skill import Skill
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowRead
from app.services.mcp_server_service import McpServerService
from app.services.run_service import RunService
from app.services.skill_service import SkillService
from app.services.workflow_service import WorkflowService
from tests.agent_platform_stock_analysis import (
    STOCK_ANALYSIS_MCP_SERVER_KEY,
    STOCK_ANALYSIS_REFERENCE_TOOL_KEYS,
    STOCK_ANALYSIS_SKILL_KEY,
    STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
    TRADING_DECISION_SCHEMA_KEY,
    stock_analysis_note_schema,
    stock_analysis_synthesizer_input_schema,
    stock_analysis_workflow_input_schema,
    stock_analysis_workflow_payload,
    trading_decision_schema,
)

_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_TRACE_SPAN_ID_PATTERN = re.compile(r"[0-9a-f]{16}")


def _assert_logfire_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_ID_PATTERN.fullmatch(value) is not None


def _assert_logfire_span_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_SPAN_ID_PATTERN.fullmatch(value) is not None


def _build_skill(*, key: str, version: int, status: str, tools: list[str]) -> Skill:
    return Skill(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Skill toolset",
        tool_definitions=[{"tool": tool} for tool in tools],
    )


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
    skill: Skill,
    mcp_server: McpServer,
    model_connection: ModelConnection | None = None,
    input_schema: dict[str, Any] | None = None,
    budget_usd: Decimal = Decimal("1.25000000"),
) -> Agent:
    return Agent(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Agent configuration",
        model_connection_id=None if model_connection is None else model_connection.id,
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
        skills=[{"skillId": skill.id, "skillKey": skill.key, "skillVersion": skill.version}],
        mcp_servers=[
            {
                "mcpServerId": mcp_server.id,
                "mcpServerKey": mcp_server.key,
                "mcpServerVersion": mcp_server.version,
            }
        ],
        budget_usd=budget_usd,
    )


def _seed_stock_analysis_workflow(
    session: Session,
    *,
    optional_agents: set[str] | None = None,
    budget_overrides: dict[str, Decimal] | None = None,
) -> WorkflowRead:
    optional_keys = optional_agents or set()
    budgets = budget_overrides or {}
    note_schema = _build_output_schema(
        key="stock_analysis_note",
        version=1,
        status="published",
    )
    note_schema.json_schema = stock_analysis_note_schema()
    decision_schema = _build_output_schema(
        key=TRADING_DECISION_SCHEMA_KEY,
        version=1,
        status="published",
    )
    decision_schema.json_schema = trading_decision_schema()
    skill = _build_skill(
        key=STOCK_ANALYSIS_SKILL_KEY,
        version=1,
        status="published",
        tools=list(STOCK_ANALYSIS_REFERENCE_TOOL_KEYS),
    )
    mcp_server = _build_mcp_server(
        key=STOCK_ANALYSIS_MCP_SERVER_KEY,
        version=1,
        status="published",
        transport="stdio",
    )
    mcp_server.config = {
        "name": f"{STOCK_ANALYSIS_MCP_SERVER_KEY}-1",
        "description": "MCP server",
        "enabled": True,
        "transport": "stdio",
        "command": "python3",
        "args": ["-m", "app.agents.mcp.stock_analysis_reference_server"],
        "env": {},
    }
    connection = _build_model_connection(name="Stock Analysis Connection")
    session.add_all([note_schema, decision_schema, skill, mcp_server, connection])
    session.flush()

    created_agents = [
        _build_agent_platform_agent(
            key=agent_key,
            version=1,
            status="published",
            output_schema=note_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema=stock_analysis_workflow_input_schema(),
            budget_usd=budgets.get(agent_key, Decimal("0.05000000")),
        )
        for agent_key in STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS
    ]
    created_agents.append(
        _build_agent_platform_agent(
            key=STOCK_ANALYSIS_SYNTHESIZER_KEY,
            version=1,
            status="published",
            output_schema=decision_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
            input_schema=stock_analysis_synthesizer_input_schema(optional_agents=optional_keys),
            budget_usd=budgets.get(STOCK_ANALYSIS_SYNTHESIZER_KEY, Decimal("0.10000000")),
        )
    )
    session.add_all(created_agents)
    session.commit()
    return WorkflowService(session).create_workflow(
        WorkflowCreate.model_validate(
            stock_analysis_workflow_payload(optional_agents=optional_keys)
        )
    )


def _seed_stock_analysis_reference_context(session: Session) -> None:
    portfolio = Portfolio(
        name="Stock Analysis Reference",
        slug="stock_analysis_reference",
        description="Reference portfolio for stock-analysis runtime coverage.",
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
            name="nvda_reference_report",
            slug="nvda_reference_report",
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


def test_agent_platform_skill_registry_resolves_versioned_rows_to_server_declared_toolsets(
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

        service = SkillService(session, skill_registry=get_default_skill_registry())
        published = service.resolve_toolset_version("market_research", None)
        draft = service.resolve_toolset_version("market_research", 2)

        assert published.skill_version == 1
        assert [tool.key for tool in published.tools] == [
            "ledger.market_data.quote_lookup",
            "ledger.reports.lookup",
        ]
        assert published.tools[0].module == "app.agents.skills.server_declared"
        assert draft.skill_version == 2
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
    assert created["baseUrl"] == "https://api.openai.com/v1"
    assert created["hasApiKey"] is True
    assert created["apiKeyLast4"] == "1234"
    assert "apiKey" not in created and "secretPayload" not in created
    assert "sk-test-secret-1234" not in json.dumps(created)

    listed = client.get("/api/model-connections")
    assert listed.status_code == 200, listed.json()
    listed_item = listed.json()["items"][0]
    assert listed_item["id"] == connection_id
    assert listed_item["hasApiKey"] is True
    assert listed_item["apiKeyLast4"] == "1234"
    assert "apiKey" not in listed_item and "sk-test-secret-1234" not in json.dumps(listed_item)

    detail = client.get(f"/api/model-connections/{connection_id}")
    assert detail.status_code == 200, detail.json()
    assert detail.json()["id"] == connection_id

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
            "key": "archived_save_agent",
            "name": "Archived Save Agent",
            "description": "Should fail",
            "modelConnectionId": archived_connection.id,
            "systemPrompt": "Analyze the ticker and return a typed result.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
            "outputSchemaKey": output_schema.key,
            "outputSchemaVersion": output_schema.version,
            "skills": [{"skillKey": skill.key, "skillVersion": skill.version}],
            "mcpServers": [
                {
                    "mcpServerKey": mcp_server.key,
                    "mcpServerVersion": mcp_server.version,
                }
            ],
            "budgetUsd": "1.25000000",
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json() == {
        "code": "validation_error",
        "message": "Agent validation failed",
        "details": [
            {
                "field": "modelConnectionId",
                "issue": "Archived model connections cannot be selected",
            }
        ],
    }


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


def test_agent_platform_stock_analysis_real_skills_executes_reference_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setenv("QUOTE_PROVIDER_BACKEND", "deterministic")
    reset_settings_cache()

    with session_factory() as session:
        _seed_stock_analysis_reference_context(session)
        workflow = _seed_stock_analysis_workflow(session)

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_one_entries = {entry["slot"]: entry for entry in detail["perStepOutputs"]["1"]}

    assert detail["status"] == "succeeded"
    _assert_logfire_trace_id(detail["traceId"])
    for entry in detail["perStepOutputs"]["1"]:
        _assert_logfire_span_id(entry["traceSpanId"])
    _assert_logfire_span_id(detail["perStepOutputs"]["2"][0]["traceSpanId"])
    assert detail["finalOutput"]["action"] == "buy"
    assert "stub" not in detail["finalOutput"]["rationale"]
    assert "stock_analysis_reference" in detail["finalOutput"]["rationale"]
    assert "nvda_reference_report" in detail["finalOutput"]["rationale"]
    assert detail["totalCostUsd"] == "0.11000000"
    assert step_one_entries["financials_analyst"]["output"]["summary"].startswith(
        "Ledger has 1 persisted report(s)"
    )
    assert "NVDA trades at" in step_one_entries["market_analyst"]["output"]["summary"]
    assert "stock_analysis_reference" in step_one_entries["position_reader"]["output"]["summary"]
    assert detail["perStepOutputs"]["2"][0]["agentKey"] == STOCK_ANALYSIS_SYNTHESIZER_KEY


def test_agent_platform_stock_analysis_missing_dependency_reports_mcp_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setenv("QUOTE_PROVIDER_BACKEND", "deterministic")
    reset_settings_cache()

    with session_factory() as session:
        _seed_stock_analysis_reference_context(session)
        workflow = _seed_stock_analysis_workflow(session)
        broken_server = session.query(McpServer).filter_by(key=STOCK_ANALYSIS_MCP_SERVER_KEY).one()
        broken_server.config = {
            "name": broken_server.name,
            "description": broken_server.description,
            "enabled": broken_server.enabled,
            "transport": "stdio",
            "command": "definitely_missing_stock_analysis_mcp_binary",
            "args": ["--missing"],
            "env": {},
        }
        session.commit()

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_one_entries = {entry["slot"]: entry for entry in detail["perStepOutputs"]["1"]}

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert "could not access MCP server" in str(detail["error"])
    assert step_one_entries["financials_analyst"]["status"] == "failed"
    assert (
        step_one_entries["financials_analyst"]["error"]["code"]
        == "agent_execution_missing_dependency"
    )
    assert "2" not in detail["perStepOutputs"]


def test_agent_platform_stock_analysis_budget_failure_is_reported_deterministically(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setenv("QUOTE_PROVIDER_BACKEND", "deterministic")
    reset_settings_cache()

    with session_factory() as session:
        _seed_stock_analysis_reference_context(session)
        workflow = _seed_stock_analysis_workflow(
            session,
            budget_overrides={"price_analyst": Decimal("0.01000000")},
        )

    trigger = client.post(
        f"/api/workflows/{workflow.id}/runs",
        json={"ticker": "NVDA", "horizon_days": 30},
    )
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run(client, trigger.json()["id"])
    step_one_entries = {entry["slot"]: entry for entry in detail["perStepOutputs"]["1"]}

    assert detail["status"] == "failed"
    assert detail["finalOutput"] is None
    assert detail["error"] == "Agent 'price_analyst' exceeded its budget of 0.01000000 USD"
    assert step_one_entries["price_analyst"]["status"] == "failed"
    assert step_one_entries["price_analyst"]["output"] is None
    assert step_one_entries["price_analyst"]["error"]["code"] == "agent_budget_exceeded"
    assert step_one_entries["financials_analyst"]["status"] == "succeeded"
    assert "2" not in detail["perStepOutputs"]


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
