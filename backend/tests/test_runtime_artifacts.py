from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.skill import Skill
from app.schemas.workflow import WorkflowCreate
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService

_TRACE_SPAN_ID_PATTERN = re.compile(r"[0-9a-f]{16}")


def _assert_logfire_span_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_SPAN_ID_PATTERN.fullmatch(value) is not None


def _build_agent_platform_output_schema(*, key: str, version: int, status: str) -> OutputSchema:
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


def _build_agent_platform_skill(*, key: str, version: int, status: str) -> Skill:
    return Skill(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Skill toolset",
        tool_definitions=[{"tool": "ledger.market_data.quote_lookup"}],
    )


def _build_agent_platform_mcp_server(*, key: str, version: int, status: str) -> McpServer:
    return McpServer(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="MCP server",
        transport="http-sse",
        command=None,
        url="https://example.com/mcp",
        auth={"header": "Authorization", "apiKey": "Bearer secret-token"},
        enabled=True,
    )


def _build_model_connection(
    *,
    name: str,
    api_key: str | None = "sk-artifact-secret-1234",
    base_url: str = "https://api.openai.com/v1",
    model_id: str = "gpt-5.4-mini",
) -> ModelConnection:
    payload = {} if api_key is None else {"apiKey": api_key}
    return ModelConnection(
        status="active",
        name=name,
        description=f"{name} description",
        base_url=base_url,
        organization=None,
        project=None,
        model_id=model_id,
        reasoning_effort="medium",
        timeout_seconds=60,
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
    budget_usd: Decimal = Decimal("1.00000000"),
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
        temperature=0.2,
        max_tool_rounds=2,
        budget_usd=budget_usd,
        streaming=True,
    )


def _wait_for_agent_platform_run_detail(
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


class _RuntimeFailingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    failure_message = "Provider rejected sk-artifact-secret-1234 during auth"

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any):
        type(self).create_calls.append(kwargs)
        raise Exception(type(self).failure_message)

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.failure_message = "Provider rejected sk-artifact-secret-1234 during auth"


def test_agent_platform_trace_falls_back_to_null_ids_when_logfire_is_unavailable(
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
            "tokens": 9,
            "costUsd": "0.01000000",
            "durationMs": 7,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    def raise_missing_trace(*, run, workflow):
        raise RuntimeError("logfire missing")

    monkeypatch.setattr(
        RunService,
        "_start_trace_session",
        staticmethod(raise_missing_trace),
    )

    with session_factory() as session:
        output_schema = _build_agent_platform_output_schema(
            key="trace_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(key="trace_skill", version=1, status="published")
        mcp_server = _build_agent_platform_mcp_server(
            key="trace_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(name="Trace Artifact Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        trace_agent = _build_agent_platform_agent(
            key="trace_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        session.add(trace_agent)
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "trace_workflow",
                    "name": "Trace Workflow",
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
                                    "agentKey": "trace_agent",
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

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "SHOP"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run_detail(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["traceId"] is None
    assert detail["perStepOutputs"]["1"][0]["traceSpanId"] is None
    assert detail["finalOutput"] == {"summary": "trace_agent:SHOP"}


def test_agent_platform_step_persistence_retains_completed_steps_when_later_step_fails(
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
            return {
                "output": {"summary": f"analysis:{resolved_input['ticker']}"},
                "tokens": 10,
                "costUsd": "0.01000000",
                "durationMs": 10,
                "traceSpanId": None,
            }
        raise RuntimeError("decision synthesis failed")

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        output_schema = _build_agent_platform_output_schema(
            key="step_persistence_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(
            key="step_persistence_skill",
            version=1,
            status="published",
        )
        mcp_server = _build_agent_platform_mcp_server(
            key="step_persistence_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(name="Step Persistence Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        first_agent = _build_agent_platform_agent(
            key="step_agent_a",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        second_agent = _build_agent_platform_agent(
            key="step_agent_b",
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
        session.add_all([first_agent, second_agent])
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "step_persistence_workflow",
                    "name": "Step Persistence Workflow",
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
                                    "agentKey": "step_agent_a",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "step_agent_b",
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

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "INTC"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run_detail(client, trigger.json()["id"])

    assert detail["status"] == "failed"
    assert detail["traceId"] is None
    assert detail["perStepOutputs"]["1"][0]["status"] == "succeeded"
    assert detail["perStepOutputs"]["1"][0]["output"] == {"summary": "analysis:INTC"}
    _assert_logfire_span_id(detail["perStepOutputs"]["1"][0]["traceSpanId"])
    assert detail["perStepOutputs"]["2"][0]["status"] == "failed"
    assert detail["perStepOutputs"]["2"][0]["output"] is None
    _assert_logfire_span_id(detail["perStepOutputs"]["2"][0]["traceSpanId"])
    assert detail["perStepOutputs"]["2"][0]["error"]["code"] == "agent_execution_failed"


def test_agent_platform_run_persists_redacted_provider_failure_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeFailingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeFailingOpenAIClient)

    with session_factory() as session:
        output_schema = _build_agent_platform_output_schema(
            key="artifact_failure_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(
            key="artifact_failure_skill",
            version=1,
            status="published",
        )
        mcp_server = _build_agent_platform_mcp_server(
            key="artifact_failure_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(
            name="Artifact Failure Connection",
            api_key="sk-artifact-secret-1234",
        )
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        failing_agent = _build_agent_platform_agent(
            key="artifact_failure_agent",
            version=1,
            status="published",
            output_schema=output_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        session.add(failing_agent)
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "artifact_failure_workflow",
                    "name": "Artifact Failure Workflow",
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
                                    "agentKey": "artifact_failure_agent",
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

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AMD"})
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run_detail(client, run_id)

    assert detail["status"] == "failed"
    assert "[REDACTED]" in detail["error"]
    assert "sk-artifact-secret-1234" not in detail["error"]
    step_error = detail["perStepOutputs"]["1"][0]["error"]
    assert step_error["code"] == "agent_provider_error"
    assert "[REDACTED]" in step_error["message"]
    assert "sk-artifact-secret-1234" not in json.dumps(detail)

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error is not None and "[REDACTED]" in run.error
        assert "sk-artifact-secret-1234" not in run.error
        assert "sk-artifact-secret-1234" not in json.dumps(run.per_step_outputs)
