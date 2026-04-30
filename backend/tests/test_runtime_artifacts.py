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
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowCreate
from app.services.execution_plan_builder import ExecutionPlanBuilder
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
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


def _build_agent_platform_skill(*, key: str, version: int, status: str) -> Capability:
    return Capability(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Capability toolset",
        tool_grants=[{"tool": "ledger.market_data.quote_lookup"}],
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
    key: str | None = None,
    api_key: str | None = "sk-artifact-secret-1234",
    base_url: str = "https://api.openai.com/v1",
    model_id: str = "gpt-5.4-mini",
) -> ModelConnection:
    payload = {} if api_key is None else {"apiKey": api_key}
    return ModelConnection(
        key=key or name.strip().lower().replace(" ", "_"),
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
    skill: Capability,
    mcp_server: McpServer,
    model_connection: ModelConnection | None = None,
    input_schema: dict[str, Any] | None = None,
    budget_usd: Decimal = Decimal("1.00000000"),
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


def _create_single_agent_runtime_workflow(
    session: Session,
    *,
    agent_key: str,
    workflow_key: str,
    connection: ModelConnection,
) -> tuple[Any, Agent, OutputSchema]:
    output_schema = _build_agent_platform_output_schema(
        key=f"{agent_key}_schema",
        version=1,
        status="published",
    )
    skill = _build_agent_platform_skill(
        key=f"{agent_key}_skill",
        version=1,
        status="published",
    )
    mcp_server = _build_agent_platform_mcp_server(
        key=f"{agent_key}_server",
        version=1,
        status="published",
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
    return workflow, agent, output_schema


def _create_paused_workflow_run(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    workflow_id: int,
    input_payload: dict[str, Any],
) -> int:
    monkeypatch.setattr(RunService, "_dispatch_run_in_background", lambda self, run_id: None)
    response = client.post(f"/api/workflows/{workflow_id}/runs", json=input_payload)
    assert response.status_code == 201, response.json()
    assert response.json()["status"] == "running"
    return int(response.json()["id"])


def _execute_run_synchronously(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
) -> None:
    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)


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


def test_execution_plan_builder_normalizes_standalone_agent_to_one_step_passthrough(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        output_schema = _build_agent_platform_output_schema(
            key="standalone_plan_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(
            key="standalone_plan_skill",
            version=1,
            status="published",
        )
        mcp_server = _build_agent_platform_mcp_server(
            key="standalone_plan_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(name="Standalone Plan Connection")
        session.add_all([output_schema, skill, mcp_server, connection])
        session.flush()
        agent = _build_agent_platform_agent(
            key="standalone_plan_agent",
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
                    "horizon_days": {"type": "integer"},
                },
                "required": ["ticker"],
            },
            budget_usd=Decimal("0.33000000"),
        )
        session.add(agent)
        session.commit()
        session.refresh(agent)

        plan = ExecutionPlanBuilder(session).build_target_plan("agent", agent.id)

    assert plan.target.kind == "agent"
    assert plan.target.id == agent.id
    assert plan.target.key == "standalone_plan_agent"
    assert plan.target.version == 1
    assert plan.aggregate_budget_usd == Decimal("0.33000000")
    assert plan.input_schema == {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "horizon_days": {"type": "integer"},
        },
        "required": ["ticker"],
    }
    assert len(plan.steps) == 1
    assert plan.steps[0].index == 1
    assert len(plan.steps[0].agents) == 1
    assert plan.steps[0].agents[0].slot == "final_output"
    assert plan.steps[0].agents[0].agent_key == "standalone_plan_agent"
    assert plan.steps[0].agents[0].input_mode == "passthrough"
    assert plan.steps[0].agents[0].wiring == {}
    assert plan.final_output.step_index == 1
    assert plan.final_output.slot == "final_output"
    assert plan.final_output.path is None


def test_execution_plan_builder_preserves_explicit_final_output_step(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        note_schema = _build_agent_platform_output_schema(
            key="workflow_plan_note_schema",
            version=1,
            status="published",
        )
        decision_schema = _build_agent_platform_output_schema(
            key="workflow_plan_decision_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(
            key="workflow_plan_skill",
            version=1,
            status="published",
        )
        mcp_server = _build_agent_platform_mcp_server(
            key="workflow_plan_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(name="Workflow Plan Connection")
        session.add_all([note_schema, decision_schema, skill, mcp_server, connection])
        session.flush()
        analysis_agent = _build_agent_platform_agent(
            key="workflow_plan_analysis_agent",
            version=1,
            status="published",
            output_schema=note_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        decision_agent = _build_agent_platform_agent(
            key="workflow_plan_decision_agent",
            version=1,
            status="published",
            output_schema=decision_schema,
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
        session.add_all([analysis_agent, decision_agent])
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "workflow_plan_with_slot_output",
                    "name": "Workflow Plan With Slot Output",
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
                                    "agentKey": "workflow_plan_analysis_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "workflow_plan_decision_agent",
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

        plan = ExecutionPlanBuilder(session).build_target_plan("workflow", workflow.id)

    assert plan.target.kind == "workflow"
    assert plan.target.id == workflow.id
    assert plan.target.key == "workflow_plan_with_slot_output"
    assert plan.target.version == 1
    assert len(plan.steps) == 2
    assert plan.steps[0].index == 1
    assert len(plan.steps[0].agents) == 1
    assert plan.steps[0].agents[0].slot == "analysis"
    assert plan.steps[1].index == 2
    assert len(plan.steps[1].agents) == 1
    assert plan.steps[1].agents[0].slot == "decision"
    assert plan.steps[1].agents[0].agent_key == "workflow_plan_decision_agent"
    assert plan.steps[1].agents[0].input_mode == "wired"
    assert plan.steps[1].agents[0].wiring["analysis"].source == "step"
    assert plan.steps[1].agents[0].wiring["analysis"].step_index == 1
    assert plan.steps[1].agents[0].wiring["analysis"].slot == "analysis"
    assert plan.final_output.step_index == 2
    assert plan.final_output.slot == "decision"
    assert plan.final_output.path is None


def test_agent_platform_run_persists_explicit_final_output_step(
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
        del self, output_model, trace_id, step_index
        if slot == "analysis":
            return {
                "output": {"summary": f"analysis:{resolved_input['ticker']}"},
                "tokens": 10,
                "costUsd": "0.01000000",
                "durationMs": 8,
                "traceSpanId": None,
            }
        assert slot == "decision"
        assert agent.key == "legacy_output_decision_agent"
        return {
            "output": {"summary": f"decision:{resolved_input['analysis']['summary']}"},
            "tokens": 11,
            "costUsd": "0.01100000",
            "durationMs": 9,
            "traceSpanId": None,
        }

    monkeypatch.setattr(RunService, "_invoke_agent", fake_invoke)

    with session_factory() as session:
        note_schema = _build_agent_platform_output_schema(
            key="legacy_output_note_schema",
            version=1,
            status="published",
        )
        decision_schema = _build_agent_platform_output_schema(
            key="legacy_output_decision_schema",
            version=1,
            status="published",
        )
        skill = _build_agent_platform_skill(
            key="legacy_output_skill",
            version=1,
            status="published",
        )
        mcp_server = _build_agent_platform_mcp_server(
            key="legacy_output_server",
            version=1,
            status="published",
        )
        connection = _build_model_connection(name="Legacy Output Connection")
        session.add_all([note_schema, decision_schema, skill, mcp_server, connection])
        session.flush()
        analysis_agent = _build_agent_platform_agent(
            key="legacy_output_analysis_agent",
            version=1,
            status="published",
            output_schema=note_schema,
            skill=skill,
            mcp_server=mcp_server,
            model_connection=connection,
        )
        decision_agent = _build_agent_platform_agent(
            key="legacy_output_decision_agent",
            version=1,
            status="published",
            output_schema=decision_schema,
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
        session.add_all([analysis_agent, decision_agent])
        session.commit()
        workflow = WorkflowService(session).create_workflow(
            WorkflowCreate.model_validate(
                {
                    "key": "legacy_output_workflow",
                    "name": "Legacy Output Workflow",
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
                                    "agentKey": "legacy_output_analysis_agent",
                                    "slot": "analysis",
                                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                                }
                            ],
                        },
                        {
                            "index": 2,
                            "agents": [
                                {
                                    "agentKey": "legacy_output_decision_agent",
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

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AMD"})
    assert trigger.status_code == 201, trigger.json()
    detail = _wait_for_agent_platform_run_detail(client, trigger.json()["id"])

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "decision:analysis:AMD"}
    assert detail["perStepOutputs"]["1"][0]["slot"] == "analysis"
    assert detail["perStepOutputs"]["1"][0]["output"] == {"summary": "analysis:AMD"}
    assert detail["perStepOutputs"]["2"][0]["slot"] == "decision"
    assert detail["perStepOutputs"]["2"][0]["agentKey"] == "legacy_output_decision_agent"
    assert detail["perStepOutputs"]["2"][0]["resolvedInput"] == {
        "analysis": {"summary": "analysis:AMD"}
    }
    assert detail["perStepOutputs"]["2"][0]["output"] == {"summary": "decision:analysis:AMD"}


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

    def raise_missing_trace(*, run, plan):
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


def test_agent_platform_run_persists_missing_workflow_target_failure_before_step_execution(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        workflow, _agent, _output_schema = _create_single_agent_runtime_workflow(
            session,
            agent_key="missing_target_agent",
            workflow_key="missing_target_workflow",
            connection=_build_model_connection(name="Missing Target Connection"),
        )

    run_id = _create_paused_workflow_run(
        client,
        monkeypatch,
        workflow_id=workflow.id,
        input_payload={"ticker": "AMD"},
    )

    with session_factory() as session:
        workflow_row = session.get(Workflow, workflow.id)
        assert workflow_row is not None
        session.delete(workflow_row)
        session.commit()

    _execute_run_synchronously(session_factory, run_id=run_id)
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200, detail.json()
    body = detail.json()
    expected_error = f"Workflow {workflow.key!r} version {workflow.version} is no longer available"

    assert body["status"] == "failed"
    assert body["error"] == expected_error
    assert body["finalOutput"] is None
    assert body["perStepOutputs"] == {}
    assert body["traceId"] is None

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error == expected_error
        assert run.final_output is None
        assert run.per_step_outputs == {}
        assert run.finished_at is not None


def test_agent_platform_run_persists_missing_output_schema_failure(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        workflow, agent, output_schema = _create_single_agent_runtime_workflow(
            session,
            agent_key="missing_output_schema_agent",
            workflow_key="missing_output_schema_workflow",
            connection=_build_model_connection(name="Missing Output Schema Connection"),
        )

    with session_factory() as session:
        output_schema_row = session.get(OutputSchema, output_schema.id)
        assert output_schema_row is not None
        session.delete(output_schema_row)
        session.commit()

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "AMD"})
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run_detail(client, run_id)
    expected_error = f"Agent {agent.key!r} references a missing output schema version"
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["error"] == expected_error
    assert detail["finalOutput"] is None
    assert detail["traceId"] is None
    assert step_entry["status"] == "failed"
    assert step_entry["resolvedInput"] == {}
    assert step_entry["output"] is None
    assert step_entry["traceSpanId"] is None
    assert step_entry["error"] == {
        "code": "run_output_schema_missing",
        "message": expected_error,
        "details": [],
    }

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error == expected_error
        assert run.final_output is None
        assert run.per_step_outputs["1"][0]["error"]["code"] == "run_output_schema_missing"


def test_agent_platform_run_persists_missing_model_connection_failure(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        workflow, agent, _output_schema = _create_single_agent_runtime_workflow(
            session,
            agent_key="missing_model_connection_agent",
            workflow_key="missing_model_connection_workflow",
            connection=_build_model_connection(name="Missing Model Connection"),
        )
        missing_connection_id = agent.model_connection_id

    with session_factory() as session:
        connection_row = session.get(ModelConnection, missing_connection_id)
        assert connection_row is not None
        session.delete(connection_row)
        session.commit()

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "IBM"})
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run_detail(client, run_id)
    expected_error = (
        f"Agent {agent.key!r} references missing model connection {missing_connection_id}"
    )
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["error"] == expected_error
    assert detail["finalOutput"] is None
    assert step_entry["status"] == "failed"
    assert step_entry["resolvedInput"] == {"ticker": "IBM"}
    assert step_entry["output"] is None
    assert step_entry["error"] == {
        "code": "run_agent_model_connection_missing",
        "message": expected_error,
        "details": [],
    }
    _assert_logfire_span_id(step_entry["traceSpanId"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error == expected_error
        assert run.final_output is None
        assert run.per_step_outputs["1"][0]["error"]["code"] == "run_agent_model_connection_missing"


def test_agent_platform_run_persists_missing_api_key_failure(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    connection = _build_model_connection(
        name="Persisted Missing API Key Connection",
        api_key=None,
    )
    with session_factory() as session:
        workflow, agent, _output_schema = _create_single_agent_runtime_workflow(
            session,
            agent_key="persisted_missing_api_key_agent",
            workflow_key="persisted_missing_api_key_workflow",
            connection=connection,
        )

    trigger = client.post(f"/api/workflows/{workflow.id}/runs", json={"ticker": "NFLX"})
    assert trigger.status_code == 201, trigger.json()
    run_id = trigger.json()["id"]
    detail = _wait_for_agent_platform_run_detail(client, run_id)
    expected_error = (
        f"Agent {agent.key!r} cannot run because model connection {connection.name!r} "
        "is missing an API key"
    )
    step_entry = detail["perStepOutputs"]["1"][0]

    assert detail["status"] == "failed"
    assert detail["error"] == expected_error
    assert detail["finalOutput"] is None
    assert step_entry["status"] == "failed"
    assert step_entry["resolvedInput"] == {"ticker": "NFLX"}
    assert step_entry["output"] is None
    assert step_entry["error"] == {
        "code": "agent_model_connection_api_key_missing",
        "message": expected_error,
        "details": [],
    }
    _assert_logfire_span_id(step_entry["traceSpanId"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error == expected_error
        assert run.final_output is None
        assert (
            run.per_step_outputs["1"][0]["error"]["code"]
            == "agent_model_connection_api_key_missing"
        )


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
