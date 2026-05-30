from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.extensions.signaldeck_finance.runtime_types import (
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
)
from app.models.agent_memory import RunMemoryEvent
from app.models.model_connection import ModelConnection
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import (
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.schemas.model_connection import (
    ModelConnectionProtocolProfile,
    default_model_connection_capabilities,
)
from app.schemas.run import RunPackageResolvedModelConnectionRead
from app.services.agent_execution_service import AgentExecutionService, RunAgentInvocationResult
from app.services.extension_service import ExtensionService
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.model_connection_snapshot import parse_model_connection_runtime_snapshot
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_http_node import (
    assert_removed_contract_tokens_absent,
    http_node_package_source,
)

_REMOVED_MODEL_CONNECTION_KIND_FIELD = f"connection{'K'}ind"

_EXPECTED_STRUCTURED_OUTPUT_WARNING = {
    "field": "spec.outputSchemas.summary_output.jsonSchema",
    "code": "model_capability_probe_inconclusive",
    "agentKey": "package_analyst",
    "modelConnectionKey": "package_runtime_model",
    "requirement": "structuredOutput",
    "issue": (
        "This workflow requires structured JSON output, but strict JSON-schema output has "
        "not been proven yet."
    ),
    "severity": "warning",
}
_EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING = {
    "ready": True,
    "blockingErrors": [],
    "warnings": [_EXPECTED_STRUCTURED_OUTPUT_WARNING],
}


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
    output_text = '{"summary": "package runtime output"}'
    total_tokens = 23

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self) -> _RuntimeRecordingOpenAIClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
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
        cls.output_text = '{"summary": "package runtime output"}'
        cls.total_tokens = 23


_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)


def _digital_oracle_researcher_demo_source() -> str:
    return _DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE.read_text()


def _seeded_tradingagents_package(client: TestClient) -> dict[str, Any]:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, Any]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] == _TRADINGAGENTS_PRESET_KEY:
            return package
    raise AssertionError("TradingAgents advisory preset was not seeded")


def _seed_tradingagents_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "test-api-key",
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                name="TradingAgents Primary Model",
                description="Preflight model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=None,
                last_test_ok=None,
                last_test_message=None,
            )
        )
        session.commit()


def _package_source(*, package_key: str = "runtime_package") -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Runtime Package
  description: Runtime package fixture.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles: []
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      outputSchema: summary_output
      capabilityProfiles: []
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


_DIGITAL_ORACLE_PHASE1_TOOL_KEYS = (
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
)


class _DigitalOracleGuidanceOutput(BaseModel):
    summary: str
    signals: list[str]
    contradictions: list[str]
    limitations: list[str]
    next_questions: list[str] = Field(alias="nextQuestions")


def _digital_oracle_guidance_package_source(
    *,
    tool_keys: tuple[str, ...] = _DIGITAL_ORACLE_PHASE1_TOOL_KEYS,
) -> str:
    tool_key_lines = "\n".join(f"        - {tool_key}" for tool_key in tool_keys)
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: digital_oracle_guidance_package
  name: Digital Oracle Guidance Package
spec:
  inputs:
    type: object
    properties:
      researchQuestion:
        type: string
      outputLanguage:
        type: string
    required: [researchQuestion, outputLanguage]
  capabilityProfiles:
    - key: digital_oracle_phase1_tools
      name: Digital Oracle Phase 1 Tools
      toolKeys:
{tool_key_lines}
  outputSchemas:
    - key: digital_oracle_report
      name: Digital Oracle Report
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
          signals:
            type: array
            items:
              type: string
          contradictions:
            type: array
            items:
              type: string
          limitations:
            type: array
            items:
              type: string
          nextQuestions:
            type: array
            items:
              type: string
        required: [summary, signals, contradictions, limitations, nextQuestions]
  agents:
    - key: digital_oracle_researcher
      name: Digital Oracle Researcher
      modelConnection: package_runtime_model
      systemPrompt: |
        Digital Oracle methodology is package-local for this agent.
        Decompose the research question before calling tools.
        Call the minimum relevant tools from granted package capability profiles.
        Compare contradictory signals and disclose warnings or coverage gaps.
        Synthesize a research-only report; never invent prices, filing facts,
        event probabilities, or sentiment readings.
      inputSchema:
        type: object
        properties:
          researchQuestion:
            type: string
          outputLanguage:
            type: string
        required: [researchQuestion, outputLanguage]
      outputSchema: digital_oracle_report
      capabilityProfiles: [digital_oracle_phase1_tools]
  workflows:
    - key: research
      name: Research
      inputSchema:
        type: object
        properties:
          researchQuestion:
            type: string
          outputLanguage:
            type: string
        required: [researchQuestion, outputLanguage]
      flow:
        kind: step
        id: digital_oracle_research
        slot: report
        uses: digital_oracle_researcher
        with:
          researchQuestion: ${{{{ inputs.researchQuestion }}}}
          outputLanguage: ${{{{ inputs.outputLanguage }}}}
      output:
        from: ${{{{ nodes.digital_oracle_research.outputs.report }}}}
"""


def _create_package(
    client: TestClient,
    *,
    package_key: str = "runtime_package",
) -> dict[str, object]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key=package_key)},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "test-api-key",
    base_url: str = "https://provider-runtime.example.test/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
) -> None:
    with session_factory() as session:
        payload = {} if api_key is None else {"apiKey": api_key}
        session.add(
            ModelConnection(
                key="package_runtime_model",
                status="active",
                name="Package Runtime Model",
                description="Package runtime model binding.",
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="high",
                api_style=api_style,
                timeout_seconds=31,
                secret_payload=payload,
            )
        )
        session.commit()


def test_digital_oracle_package_local_system_prompt_receives_runtime_tool_guidance(
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _digital_oracle_guidance_package_source()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    assert runtime_agent.key == "digital_oracle_researcher"
    assert runtime_agent.system_prompt.startswith(
        "Digital Oracle methodology is package-local for this agent."
    )
    assert [profile.key for profile in runtime_agent.capability_profiles] == [
        "digital_oracle_phase1_tools"
    ]
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }
    assert granted_tool_keys == set(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)

    with session_factory() as session:
        registry = ExtensionService(session).get_runtime_tool_registry()
        guidance = registry.get_guidance(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )

    assert "skills:" not in manifest_source
    assert "skills" not in compiled_plan
    assert "Digital Oracle methodology" not in guidance
    assert "Digital Oracle methodology is package-local for this agent." in instructions
    assert "Decompose the research question before calling tools." in instructions
    assert "Call the minimum relevant tools" in instructions
    assert "call signaldeck_prediction_markets_lookup" in instructions
    assert "call signaldeck_sec_filings_lookup" in instructions
    assert "call signaldeck_market_sentiment_lookup" in instructions
    assert instructions.index("Digital Oracle methodology") < instructions.index(
        "When you need prediction-market signals"
    )


def test_digital_oracle_researcher_demo_builds_execution_plan_with_package_local_methodology(
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _digital_oracle_researcher_demo_source()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }

    with session_factory() as session:
        registry = ExtensionService(session).get_runtime_tool_registry()
        guidance = registry.get_guidance(granted_tool_keys)
        declarations = registry.get_tool_declarations(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].agents[0].agent_key == "digital_oracle_researcher"
    assert runtime_agent.output_schema.key == "digital_oracle_report"
    assert granted_tool_keys == set(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)
    assert {declaration.tool_key for declaration in declarations} == granted_tool_keys
    assert "Package-ready draft" not in manifest_source
    assert "skills:" not in manifest_source
    assert "spec.skills" not in manifest_source
    assert "secrets:" not in manifest_source
    assert "Digital Oracle methodology is package-local for this agent." in instructions
    assert "Decompose each research question" in instructions
    assert "Call the minimum relevant granted tools" in instructions
    assert "Compare contradictory signals" in instructions
    assert "Disclose warnings" in instructions
    assert "Never invent prices" in instructions
    assert "call signaldeck_prediction_markets_lookup" in instructions
    assert "call signaldeck_sec_filings_lookup" in instructions
    assert "call signaldeck_market_sentiment_lookup" in instructions


def test_digital_oracle_guidance_omits_ungranted_phase1_tools_and_global_skill_surface(
    session_factory: sessionmaker[Session],
) -> None:
    granted_profile_tool_keys = (
        PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        SEC_FILINGS_LOOKUP_TOOL_KEY,
    )
    manifest_source = _digital_oracle_guidance_package_source(
        tool_keys=granted_profile_tool_keys,
    )
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }
    assert granted_tool_keys == set(granted_profile_tool_keys)

    with session_factory() as session:
        registry = ExtensionService(session).get_runtime_tool_registry()
        guidance = registry.get_guidance(granted_tool_keys)
        declarations = registry.get_tool_declarations(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )
    declared_tool_keys = {declaration.tool_key for declaration in declarations}

    assert declared_tool_keys == set(granted_profile_tool_keys)
    assert MARKET_SENTIMENT_LOOKUP_TOOL_KEY not in declared_tool_keys
    assert "Digital Oracle methodology" not in guidance
    assert "signaldeck_prediction_markets_lookup" in instructions
    assert "signaldeck_sec_filings_lookup" in instructions
    assert "signaldeck_market_sentiment_lookup" not in instructions
    assert "When you need broad market sentiment" not in guidance
    assert "skills:" not in manifest_source
    assert "skills" not in compiled_plan
    assert not hasattr(runtime_agent, "skills")


def test_runtime_profile_normalizes_api_style_and_rejects_snapshot_mismatch() -> None:
    legacy_profile_payload: dict[str, Any] = {
        "key": "legacy_chat_model",
        "name": "Legacy Chat Model",
        "apiStyle": "chat_completions",
        "baseUrl": "https://legacy-chat.example.test/v1",
        "modelId": "gpt-legacy-chat",
        "reasoningEffort": None,
        "timeoutSeconds": 45,
        "hasApiKey": True,
    }

    normalized_profile = RunPackageResolvedModelConnectionRead.model_validate(
        legacy_profile_payload,
    ).model_dump(mode="json", by_alias=True)

    assert normalized_profile["protocolProfile"] == (
        ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value
    )
    assert normalized_profile["apiStyle"] == "chat_completions"
    assert normalized_profile["capabilities"] == default_model_connection_capabilities(
        ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS,
    ).model_dump(mode="json", by_alias=True)
    assert normalized_profile["outputStrategyPolicy"] == "prefer_strict_schema"
    assert normalized_profile["parallelToolCallsPolicy"] == "serialize"
    assert normalized_profile["reasoningPolicy"] == "allow"
    assert normalized_profile["streamingPolicy"] == "allow"
    assert normalized_profile["probeCacheTtlSeconds"] == 900

    parsed_snapshot = parse_model_connection_runtime_snapshot(
        {
            "api_style": "chat_completions",
            "base_url": "https://legacy-chat.example.test/v1",
            "model_id": "gpt-legacy-chat",
            "reasoning_effort": None,
            "timeout_seconds": 45,
        },
    )
    assert parsed_snapshot.protocol_profile == (
        ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value
    )
    assert parsed_snapshot.api_style == "chat_completions"
    assert parsed_snapshot.output_strategy_policy == "prefer_strict_schema"
    assert parsed_snapshot.parallel_tool_calls_policy == "serialize"
    assert parsed_snapshot.reasoning_policy == "allow"
    assert parsed_snapshot.streaming_policy == "allow"
    assert parsed_snapshot.probe_cache_ttl_seconds == 900

    with pytest.raises(ValidationError, match="apiStyle does not match protocolProfile"):
        RunPackageResolvedModelConnectionRead.model_validate(
            {
                **legacy_profile_payload,
                "protocolProfile": ModelConnectionProtocolProfile.OPENAI_RESPONSES.value,
            },
        )
    with pytest.raises(ValueError, match="api_style does not match protocol_profile"):
        parse_model_connection_runtime_snapshot(
            {
                "protocol_profile": ModelConnectionProtocolProfile.OPENAI_RESPONSES.value,
                "api_style": "chat_completions",
                "base_url": "https://legacy-chat.example.test/v1",
                "model_id": "gpt-legacy-chat",
                "timeout_seconds": 45,
            },
        )


def _drain_run_queue(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        drained = RunQueueService(session, session_factory).drain_once()
        assert drained is True


def _wait_for_run(client: TestClient, run_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 3.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.json()
        body = response.json()
        last_body = cast(dict[str, Any], body)
        if body["status"] not in {"queued", "running"}:
            return last_body
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish in time: {last_body}")


def _launch_package_run(
    client: TestClient,
    package: dict[str, object],
    *,
    ticker: str = "MSFT",
) -> dict[str, Any]:
    response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": ticker},
        },
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def test_progress_for_queued_run_uses_planned_invocation_counts_in_list_and_detail(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="queued_progress_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])
    expected_progress = {
        "unit": "invocation",
        "terminalCount": 0,
        "totalCount": 1,
        "percent": 0,
    }

    detail_response = client.get(f"/api/runs/{run_id}")
    list_response = client.get(
        "/api/runs",
        params={"workflowPackageKey": "queued_progress_package"},
    )

    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    assert detail["status"] == "queued"
    assert detail["progress"] == expected_progress
    assert detail["steps"][0]["invocations"][0]["status"] == "pending"
    assert list_response.status_code == 200, list_response.json()
    items = cast(list[dict[str, Any]], list_response.json()["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


def test_queue_read_models_expose_capacity_and_serial_policy_reasons_in_list_and_detail(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="queue_reason_package")
    first_run = _launch_package_run(client, package, ticker="MSFT")
    second_run = _launch_package_run(client, package, ticker="AAPL")
    first_run_id = int(first_run["id"])
    second_run_id = int(second_run["id"])

    first_detail_response = client.get(f"/api/runs/{first_run_id}")
    second_detail_response = client.get(f"/api/runs/{second_run_id}")
    list_response = client.get(
        "/api/runs",
        params={"workflowPackageKey": "queue_reason_package"},
    )

    assert first_detail_response.status_code == 200, first_detail_response.json()
    assert second_detail_response.status_code == 200, second_detail_response.json()
    assert list_response.status_code == 200, list_response.json()
    first_detail = cast(dict[str, Any], first_detail_response.json())
    second_detail = cast(dict[str, Any], second_detail_response.json())
    items = cast(list[dict[str, Any]], list_response.json()["items"])

    assert first_detail["status"] == "queued"
    assert first_detail["queue"] == {
        "state": "waiting",
        "reason": "awaiting-worker-capacity",
        "message": "Eligible to run and waiting for an available scheduler worker.",
        "blockingRunId": None,
    }
    assert second_detail["status"] == "queued"
    assert second_detail["queue"] == {
        "state": "blocked",
        "reason": "blocked-by-package-serial-policy",
        "message": (
            f"Queued behind run #{first_run_id} from the same Workflow Package "
            "because package runs execute one at a time."
        ),
        "blockingRunId": first_run_id,
    }
    assert [item["id"] for item in items] == [second_run_id, first_run_id]
    assert items[0]["status"] == "queued"
    assert items[0]["queue"] == second_detail["queue"]
    assert items[1]["status"] == "queued"
    assert items[1]["queue"] == first_detail["queue"]


def _assert_current_readiness_create_rejected(
    client: TestClient,
    *,
    run_id: int,
    source_invocation_id: int,
    expected_detail_field: str,
) -> None:
    responses = [
        client.post(
            f"/api/runs/{run_id}/reruns",
            json={"parameters": {"ticker": "AAPL"}},
        ),
        client.post(
            f"/api/runs/{run_id}/forks",
            json={
                "sourceInvocationId": source_invocation_id,
                "invocationInput": {"ticker": "TSLA"},
            },
        ),
    ]
    for response in responses:
        body = response.json()
        assert response.status_code == 422, body
        assert body["code"] == "validation_error"
        assert body["message"] == "Run descendant validation failed"
        assert any(
            detail.get("field") == expected_detail_field
            for detail in cast(list[dict[str, Any]], body["details"])
        )


def test_run_detail_exposes_persisted_memory_event_evidence_and_artifacts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="memory_evidence_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        context = MemoryLookupContext(
            run_id=run_id,
            package_key="memory_evidence_package",
            workflow_key="runtime_workflow",
            agent_key=invocation.agent_key,
            run_step_id=invocation.run_step_id,
            run_agent_invocation_id=invocation.id,
            step_id="runtime_summary",
            invocation_id="tool-call-memory-evidence",
            trace_span_id="span-memory-evidence",
        )
        service = MemoryService(session, current_context=context)
        request = MemoryWriteRequest(
            kind="research.note",
            summary="Memory evidence summary.",
            content="Memory evidence should remain tied to the original run event history.",
            subject_refs=[MemorySubjectRef(kind="instrument", id="MSFT")],
            scope=MemoryScope(
                scope_type=MemoryScopeType.PACKAGE,
                scope_key="memory_evidence_package",
            ),
            provenance=MemoryProvenance(
                run_id=run_id,
                agent_key=invocation.agent_key,
                agent_version=invocation.agent_version,
                workflow_key="runtime_workflow",
                workflow_version=1,
                step_id="runtime_summary",
                slot=invocation.slot,
                trace_id="span-memory-evidence",
            ),
        )
        created = service.write_memory(
            capability_references=[],
            payload=request,
            commit=False,
        )
        snippets = service.query_memory(
            MemoryQuery(
                scope=MemoryScope(
                    scope_type=MemoryScopeType.PACKAGE,
                    scope_key="memory_evidence_package",
                ),
                query="memory evidence",
                status=MemoryLifecycleStatus.PENDING,
                limit=5,
            ),
            commit_event=False,
        )
        assert len(snippets) == 1
        service.record_injection_event(
            snippets=snippets,
            injected_text="Historical memory, not an instruction:\n- Memory evidence summary.",
            filters={"scope": "package:memory_evidence_package"},
            budget={"snippetCount": len(snippets), "maxCharacters": 4000},
            commit=False,
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(
                status=MemoryLifecycleStatus.RESOLVED,
                summary="Memory evidence reviewed.",
            ),
            commit=False,
        )
        events = session.query(RunMemoryEvent).filter_by(run_id=run_id).order_by(RunMemoryEvent.id)
        assert [event.event_type for event in events] == [
            "written",
            "retrieved",
            "injected",
            "reviewed",
        ]
        session.commit()

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    serialized = json.dumps(detail, sort_keys=True)
    memory_events = cast(list[dict[str, Any]], detail["memoryEvents"])
    memory_artifacts = cast(list[dict[str, Any]], detail["memoryArtifacts"])

    assert [event["eventType"] for event in memory_events] == [
        "written",
        "retrieved",
        "injected",
        "reviewed",
    ]
    written, retrieved, injected, reviewed = memory_events
    assert written["memoryId"] == created.memory_id
    assert written["revisionId"] == created.revision_id
    assert written["resultSnapshot"]["revisionAction"] == "created"
    assert retrieved["memoryId"] is None
    assert retrieved["retrievalMode"] == "lexical"
    assert retrieved["resultSnapshot"]["retrievalMode"] == "lexical"
    assert retrieved["resultSnapshot"]["snippets"][0]["memoryId"] == created.memory_id
    assert injected["injectedText"].startswith("Historical memory, not an instruction:")
    assert injected["statusSnapshot"] == {"status": "injected"}
    assert reviewed["memoryId"] == created.memory_id
    assert reviewed["statusSnapshot"] == {"status": "resolved"}
    assert memory_artifacts[0]["memoryId"] == created.memory_id
    assert memory_artifacts[0]["summary"] == "Memory evidence summary."
    assert "reportId" not in serialized
    assert "reportSlug" not in serialized
    assert "auditLinks" not in serialized
    assert "/reports/" not in serialized
    assert "download" not in serialized


def test_operation_invocation_read_shape_for_http_package_run_is_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    for key, value in {
        "slack_webhook_token": "slack-secret-value",
        "body_token": "body-secret-value",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package['id']}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    step = cast(dict[str, Any], detail["steps"][0])
    operation_invocations = cast(list[dict[str, Any]], step["operationInvocations"])
    request_metadata = cast(dict[str, Any], operation_invocations[0]["requestMetadata"])
    serialized = json.dumps(detail, sort_keys=True)

    assert step["invocations"] == []
    assert len(operation_invocations) == 1
    assert operation_invocations[0]["operationKey"] == "notify_slack"
    assert operation_invocations[0]["operationKind"] == "http"
    assert operation_invocations[0]["outputSchemaRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "webhook_response",
        "version": 1,
    }
    assert "outputSchemaId" not in operation_invocations[0]
    assert operation_invocations[0]["status"] == "pending"
    assert request_metadata["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
        "redacted": True,
    }
    assert request_metadata["body"]["token"] == {
        "from": "secret",
        "key": "body_token",
        "redacted": True,
    }
    assert "slack-secret-value" not in serialized
    assert "body-secret-value" not in serialized
    assert "secretPayload" not in serialized
    with session_factory() as session:
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() == 0
        operation = session.query(RunOperationInvocation).filter_by(run_id=run_id).one()
        assert operation.request_metadata == request_metadata


def test_secret_binding_delete_preserves_historical_detail_and_blocks_future_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    package_id = int(package["id"])
    secret_values = {
        "slack_webhook_token": "slack-delete-secret-value",
        "body_token": "body-delete-secret-value",
    }
    for key, value in secret_values.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package_id}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    with session_factory() as session:
        runs_before_delete = session.query(Run).count()

    delete_response = client.delete(
        f"/api/workflow-packages/{package_id}/secret-bindings/slack_webhook_token"
    )
    assert delete_response.status_code == 204, delete_response.text
    assert delete_response.content == b""

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    serialized_detail = json.dumps(detail, sort_keys=True)
    operation = cast(dict[str, Any], detail["steps"][0]["operationInvocations"][0])
    assert operation["requestMetadata"]["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
        "redacted": True,
    }
    assert operation["requestMetadata"]["body"]["token"] == {
        "from": "secret",
        "key": "body_token",
        "redacted": True,
    }
    assert all(value not in serialized_detail for value in secret_values.values())
    assert "secretPayload" not in serialized_detail

    preflight_response = client.post(f"/api/workflow-packages/{package_id}/preflight")
    assert preflight_response.status_code == 200, preflight_response.json()
    preflight = cast(dict[str, Any], preflight_response.json())
    assert preflight["ready"] is False
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], preflight["blockingErrors"])

    blocked_launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "AAPL"},
        },
    )
    assert blocked_launch.status_code == 422, blocked_launch.json()
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], blocked_launch.json()["details"])

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    assert rerun_draft.json()["ready"] is False
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], rerun_draft.json()["blockingErrors"])

    rerun_create = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"webhookUrl": "https://example.test/hook", "ticker": "AAPL"}},
    )
    assert rerun_create.status_code == 422, rerun_create.json()
    assert rerun_create.json()["message"] == "Run descendant validation failed"
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], rerun_create.json()["details"])

    with session_factory() as session:
        assert session.query(Run).count() == runs_before_delete
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None


def test_fork_rejects_operation_invocation_target_without_creating_run(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    for key, value in {
        "slack_webhook_token": "slack-secret-value",
        "body_token": "body-secret-value",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package['id']}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    operation = cast(
        dict[str, Any],
        detail_response.json()["steps"][0]["operationInvocations"][0],
    )
    operation_id = int(operation["id"])

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "succeeded"
        session.commit()
        runs_before = session.query(Run).count()

    draft_response = client.get(
        f"/api/runs/{run_id}/fork-draft",
        params={"sourceInvocationId": operation_id},
    )
    create_fork_response = client.post(
        f"/api/runs/{run_id}/forks",
        json={"sourceInvocationId": operation_id, "invocationInput": {}},
    )

    assert draft_response.status_code == 400, draft_response.json()
    assert draft_response.json()["code"] == "run_fork_target_unsupported"
    assert create_fork_response.status_code == 400, create_fork_response.json()
    assert create_fork_response.json()["code"] == "run_fork_target_unsupported"
    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def test_package_run_list_filters_and_detail_provenance_are_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key="sk-package-provenance-secret")
    first_package = _create_package(client, package_key="provenance_filter_package")
    second_package = _create_package(client, package_key="other_filter_package")
    first_package_id = cast(int, first_package["id"])

    first_run = _launch_package_run(client, first_package, ticker="MSFT")
    second_run = _launch_package_run(client, second_package, ticker="AAPL")

    by_package_key = client.get(
        "/api/runs",
        params={"workflowPackageKey": "provenance_filter_package"},
    )
    assert by_package_key.status_code == 200, by_package_key.json()
    assert [item["id"] for item in by_package_key.json()["items"]] == [first_run["id"]]

    by_package_id = client.get(
        "/api/runs",
        params={"workflowPackageId": first_package_id},
    )
    assert by_package_id.status_code == 200, by_package_id.json()
    assert [item["id"] for item in by_package_id.json()["items"]] == [first_run["id"]]

    by_workflow_key = client.get("/api/runs", params={"workflowKey": "runtime_workflow"})
    assert by_workflow_key.status_code == 200, by_workflow_key.json()
    assert [item["id"] for item in by_workflow_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    by_model_key = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_model_key.status_code == 200, by_model_key.json()
    assert [item["id"] for item in by_model_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    detail_response = client.get(f"/api/runs/{first_run['id']}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert_removed_contract_tokens_absent(detail, context="run detail")
    assert detail["targetKind"] == "workflowPackage"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert_removed_contract_tokens_absent(provenance, context="package provenance")
    assert provenance["workflowPackageId"] == first_package["id"]
    assert provenance["workflowPackageKey"] == "provenance_filter_package"
    assert provenance["workflowPackageStatus"] is None
    assert provenance["workflowPackageManifestHash"]
    assert provenance["workflowPackageCompiledHash"]
    assert provenance["workflowPackageManifestHash"] != provenance["workflowPackageCompiledHash"]
    assert provenance["workflowKey"] == "runtime_workflow"
    assert provenance["launchSnapshot"] == {
        "workflowKey": "runtime_workflow",
        "workflowName": "Runtime Workflow",
        "workflowDescription": "",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "parameters": {"ticker": "MSFT"},
    }
    assert provenance["localResourceRefs"] == {
        "agents": ["package_analyst"],
        "outputSchemas": ["summary_output"],
        "capabilityProfiles": [],
        "mcpServers": [],
        "workflows": ["runtime_workflow"],
    }
    assert provenance["resolvedModelConnections"] == [
        {
            "key": "package_runtime_model",
            "name": "Package Runtime Model",
            "protocolProfile": "openai_responses",
            "baseUrl": "https://provider-runtime.example.test/v1",
            "modelId": "gpt-package-v1",
            "reasoningEffort": "high",
            "capabilities": default_model_connection_capabilities("openai_responses").model_dump(
                mode="json", by_alias=True
            ),
            "outputStrategyPolicy": "prefer_strict_schema",
            "parallelToolCallsPolicy": "serialize",
            "reasoningPolicy": "allow",
            "streamingPolicy": "allow",
            "probeCacheTtlSeconds": 900,
            "apiStyle": "responses",
            "timeoutSeconds": 31,
            "hasApiKey": True,
        }
    ]
    assert provenance["preflightSummary"] == _EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING
    assert provenance["currentPackage"]["available"] is True
    assert "status" not in provenance["currentPackage"]
    assert provenance["currentPackage"]["manifestHashMatchesSnapshot"] is True
    assert provenance["currentPackage"]["compiledHashMatchesSnapshot"] is True
    serialized = json.dumps(detail, sort_keys=True)
    assert "last" + "LaunchedAt" not in serialized
    assert "sk-package-provenance-secret" not in serialized
    assert "secretPayload" not in serialized

    rerun_draft = client.get(f"/api/runs/{first_run['id']}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    rerun_provenance = cast(dict[str, Any], rerun_draft.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageKey"] == "provenance_filter_package"
    first_connection = cast(dict[str, Any], rerun_provenance["resolvedModelConnections"][0])
    assert _REMOVED_MODEL_CONNECTION_KIND_FIELD not in first_connection
    assert first_connection["protocolProfile"] == "openai_responses"
    assert first_connection["outputStrategyPolicy"] == "prefer_strict_schema"
    assert first_connection["parallelToolCallsPolicy"] == "serialize"
    assert first_connection["reasoningPolicy"] == "allow"
    assert first_connection["streamingPolicy"] == "allow"
    assert first_connection["probeCacheTtlSeconds"] == 900
    assert first_connection["capabilities"] == default_model_connection_capabilities(
        "openai_responses"
    ).model_dump(mode="json", by_alias=True)


def test_new_workflow_package_runs_store_null_snapshot_status_for_fresh_and_lineage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="null_status_snapshot_package")
    fresh_run = _launch_package_run(client, package, ticker="MSFT")
    fresh_run_id = int(fresh_run["id"])

    fresh_detail_response = client.get(f"/api/runs/{fresh_run_id}")
    assert fresh_detail_response.status_code == 200, fresh_detail_response.json()
    fresh_provenance = cast(dict[str, Any], fresh_detail_response.json()["packageProvenance"])
    assert fresh_provenance["workflowPackageStatus"] is None
    assert "status" not in fresh_provenance["currentPackage"]

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        assert source_run is not None
        source_snapshot = source_run.workflow_package_snapshot
        assert source_snapshot is not None
        assert source_snapshot.workflow_package_status is None
        source_snapshot.workflow_package_status = "active"
        session.commit()

    historical_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert historical_source_response.status_code == 200, historical_source_response.json()
    historical_source_provenance = cast(
        dict[str, Any],
        historical_source_response.json()["packageProvenance"],
    )
    assert historical_source_provenance["workflowPackageStatus"] == "active"

    rerun_response = client.post(
        f"/api/runs/{fresh_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageStatus"] is None
    assert "status" not in rerun_provenance["currentPackage"]

    stable_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert stable_source_response.status_code == 200, stable_source_response.json()
    stable_source_provenance = cast(
        dict[str, Any],
        stable_source_response.json()["packageProvenance"],
    )
    assert stable_source_provenance["workflowPackageStatus"] == "active"

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        rerun = session.get(Run, rerun_id)
        assert source_run is not None
        assert rerun is not None
        assert source_run.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot is not None
        assert source_run.workflow_package_snapshot.workflow_package_status == "active"
        assert rerun.workflow_package_snapshot.workflow_package_status is None


_recording_package_agent_calls: list[dict[str, Any]] = []


async def _recording_package_agent_invoke(
    self: AgentExecutionService,
    **kwargs: Any,
) -> RunAgentInvocationResult:
    del self
    _recording_package_agent_calls.append(dict(kwargs))
    return RunAgentInvocationResult(output={"summary": "versionless package context"}, tokens=1)


def test_workflow_package_runtime_context_does_not_emit_fake_workflow_version(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(AgentExecutionService, "invoke", _recording_package_agent_invoke)
    _recording_package_agent_calls.clear()
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="versionless_context_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert len(_recording_package_agent_calls) == 1
    assert _recording_package_agent_calls[0]["workflow_key"] == "runtime_workflow"
    assert _recording_package_agent_calls[0]["workflow_version"] is None
    assert _recording_package_agent_calls[0]["package_ownership"] is not None


def test_rerun_uses_run_snapshot_after_current_package_mutation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="mutated_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="MSFT")
    source_run_id = int(launched["id"])
    source_detail_response = client.get(f"/api/runs/{source_run_id}")
    assert source_detail_response.status_code == 200, source_detail_response.json()
    source_provenance = cast(dict[str, Any], source_detail_response.json()["packageProvenance"])
    snapshot_compiled_plan = deepcopy(source_provenance["compiledPlan"])
    snapshot_compiled_hash = str(source_provenance["workflowPackageCompiledHash"])

    with session_factory() as session:
        package_row = session.get(WorkflowPackage, package_id)
        assert package_row is not None
        package_row.manifest_hash = "c" * 64
        package_row.compiled_hash = "d" * 64
        package_row.compiled_plan = {"packageKey": "mutated_snapshot_package", "workflows": []}
        session.commit()

    rerun_response = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])

    removed_target_version_field = "target" + "Version"
    assert removed_target_version_field not in rerun_response.json()
    assert removed_target_version_field not in rerun_detail_response.json()
    by_snapshot_model = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_snapshot_model.status_code == 200, by_snapshot_model.json()
    assert [item["id"] for item in by_snapshot_model.json()["items"]] == [
        rerun_id,
        source_run_id,
    ]

    assert rerun_provenance["compiledPlan"] == snapshot_compiled_plan
    assert rerun_provenance["workflowPackageCompiledHash"] == snapshot_compiled_hash
    assert rerun_provenance["launchSnapshot"]["parameters"] == {"ticker": "AAPL"}
    assert rerun_provenance["currentPackage"]["available"] is True
    assert "status" not in rerun_provenance["currentPackage"]
    assert rerun_provenance["currentPackage"]["manifestHashMatchesSnapshot"] is False
    assert rerun_provenance["currentPackage"]["compiledHashMatchesSnapshot"] is False

    with session_factory() as session:
        rerun = session.get(Run, rerun_id)
        assert rerun is not None
        assert rerun.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot.compiled_plan == snapshot_compiled_plan
        assert rerun.workflow_package_snapshot.launch_parameters == {"ticker": "AAPL"}


def test_package_deletion_deletes_owned_runs_and_agent_memory_reports(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package deletion output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_owned_runs_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(
        dict[str, Any],
        succeeded_detail["steps"][0]["invocations"][0],
    )
    source_invocation_id = int(source_invocation["id"])
    assert source_invocation["resolvedInput"] == {"ticker": "NVDA"}

    fork_response = client.post(
        f"/api/runs/{run_id}/forks",
        json={
            "sourceInvocationId": source_invocation_id,
            "invocationInput": {"ticker": "TSLA"},
        },
    )
    assert fork_response.status_code == 201, fork_response.json()
    fork_id = int(fork_response.json()["id"])
    memory_slugs = {
        run_id: f"agent_memory_deleted_owned_run_{run_id}",
        fork_id: f"agent_memory_deleted_owned_run_{fork_id}",
    }

    with session_factory() as session:
        source_run = session.get(Run, run_id)
        fork_run = session.get(Run, fork_id)
        assert source_run is not None
        assert fork_run is not None
        assert source_run.workflow_package_id == package_id
        assert fork_run.workflow_package_id == package_id
        assert session.query(RunStep).filter_by(run_id=run_id).count() > 0
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() > 0
        fork_run.status = "running"
        for owned_run_id, slug in memory_slugs.items():
            session.add(
                Report(
                    name=f"Agent Memory Deleted Owned Run {owned_run_id}",
                    slug=slug,
                    source="agent",
                    content="# Agent memory",
                    metadata_={
                        "analysis": {"reviewType": "agent_memory", "runId": owned_run_id},
                    },
                )
            )
        session.commit()

    deleted = client.delete(f"/api/workflow-packages/{package_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{fork_id}").status_code == 404

    with session_factory() as session:
        assert session.get(WorkflowPackage, package_id) is None
        assert session.get(Run, run_id) is None
        assert session.get(Run, fork_id) is None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is None
        assert session.get(RunWorkflowPackageSnapshot, fork_id) is None
        assert session.query(RunStep).filter(RunStep.run_id.in_([run_id, fork_id])).count() == 0
        assert (
            session.query(RunAgentInvocation)
            .filter(RunAgentInvocation.run_id.in_([run_id, fork_id]))
            .count()
            == 0
        )
        assert session.query(Report).filter(Report.slug.in_(memory_slugs.values())).count() == 0


def test_deleted_model_connection_preserves_historical_detail_and_blocks_future_readiness(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "deleted connection source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_connection_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], succeeded_detail["steps"][0]["invocations"][0])
    source_invocation_id = int(source_invocation["id"])

    with session_factory() as session:
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection_id = connection.id
        runs_before = session.query(Run).count()

    deleted_connection = client.delete(f"/api/model-connections/{connection_id}")
    assert deleted_connection.status_code == 204, deleted_connection.text
    assert deleted_connection.content == b""

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert provenance["resolvedModelConnections"][0]["key"] == "package_runtime_model"
    assert provenance["currentPackage"]["available"] is True

    preflight_response = client.post(f"/api/workflow-packages/{package_id}/preflight")
    assert preflight_response.status_code == 200, preflight_response.json()
    preflight = cast(dict[str, Any], preflight_response.json())
    assert preflight["ready"] is False
    assert any(
        detail.get("field") == "spec.agents[0].modelConnection"
        for detail in cast(list[dict[str, Any]], preflight["blockingErrors"])
    )

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AAPL"}},
    )
    assert launch_response.status_code == 422, launch_response.json()
    assert launch_response.json()["message"] == "Workflow package launch validation failed"
    assert any(
        detail.get("field") == "spec.agents[0].modelConnection"
        for detail in cast(list[dict[str, Any]], launch_response.json()["details"])
    )

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    fork_draft = client.get(
        f"/api/runs/{run_id}/fork-draft",
        params={"sourceInvocationId": source_invocation_id},
    )
    for draft_response in (rerun_draft, fork_draft):
        assert draft_response.status_code == 200, draft_response.json()
        draft = cast(dict[str, Any], draft_response.json())
        assert draft["ready"] is False
        assert any(
            detail.get("field") == "spec.agents[0].modelConnection"
            for detail in cast(list[dict[str, Any]], draft["blockingErrors"])
        )
        draft_provenance = cast(dict[str, Any], draft["packageProvenance"])
        assert draft_provenance["resolvedModelConnections"][0]["key"] == "package_runtime_model"

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None
        assert session.get(WorkflowPackage, package_id) is not None
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None

    _assert_current_readiness_create_rejected(
        client,
        run_id=run_id,
        source_invocation_id=source_invocation_id,
        expected_detail_field="spec.agents[0].modelConnection",
    )

    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def test_rerun_and_fork_execute_frozen_runtime_profile_after_live_model_connection_drift(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="drifted_connection_snapshot_package")
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], succeeded_detail["steps"][0]["invocations"][0])
    source_invocation_id = int(source_invocation["id"])

    with session_factory() as session:
        source_snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert source_snapshot is not None
        source_profile = cast(dict[str, Any], source_snapshot.resolved_model_connections[0])
        assert source_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
        assert source_profile["modelId"] == "gpt-package-v1"
        assert source_profile["reasoningEffort"] == "high"
        assert source_profile["timeoutSeconds"] == 31
        source_snapshot.preflight_summary = {
            "ready": False,
            "blockingErrors": [{"field": "historical", "issue": "stale source readiness"}],
            "warnings": [],
        }
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-live-drift.example.com/v1"
        connection.model_id = "gpt-package-live-drift"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "sk-package-runtime-live"}
        session.commit()
        runs_before = session.query(Run).count()

    drifted_detail_response = client.get(f"/api/runs/{run_id}")
    assert drifted_detail_response.status_code == 200, drifted_detail_response.json()
    drifted_detail = cast(dict[str, Any], drifted_detail_response.json())
    drifted_provenance = cast(dict[str, Any], drifted_detail["packageProvenance"])
    drifted_profile = cast(dict[str, Any], drifted_provenance["resolvedModelConnections"][0])
    assert drifted_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
    assert drifted_profile["modelId"] == "gpt-package-v1"
    assert drifted_profile["reasoningEffort"] == "high"
    assert drifted_profile["timeoutSeconds"] == 31
    assert "runtime-live-drift" not in json.dumps(drifted_detail, sort_keys=True)
    assert "gpt-package-live-drift" not in json.dumps(drifted_detail, sort_keys=True)

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    fork_draft = client.get(
        f"/api/runs/{run_id}/fork-draft",
        params={"sourceInvocationId": source_invocation_id},
    )
    for draft_response in (rerun_draft, fork_draft):
        assert draft_response.status_code == 200, draft_response.json()
        draft = cast(dict[str, Any], draft_response.json())
        assert draft["ready"] is True
        assert draft["blockingErrors"] == []
        draft_provenance = cast(dict[str, Any], draft["packageProvenance"])
        assert draft_provenance["preflightSummary"]["ready"] is False
        draft_profile = cast(dict[str, Any], draft_provenance["resolvedModelConnections"][0])
        assert draft_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
        assert draft_profile["modelId"] == "gpt-package-v1"
        assert draft_profile["reasoningEffort"] == "high"
        assert draft_profile["timeoutSeconds"] == 31

    rerun_response = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    fork_response = client.post(
        f"/api/runs/{run_id}/forks",
        json={
            "sourceInvocationId": source_invocation_id,
            "invocationInput": {"ticker": "TSLA"},
        },
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    assert fork_response.status_code == 201, fork_response.json()
    old_snapshot_gate_code = "run_model_connection_" + "incompatible"
    assert old_snapshot_gate_code not in json.dumps(
        [
            rerun_draft.json(),
            fork_draft.json(),
            rerun_response.json(),
            fork_response.json(),
        ],
        sort_keys=True,
    )
    rerun_id = int(rerun_response.json()["id"])
    fork_id = int(fork_response.json()["id"])

    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift rerun output"}'
    with session_factory() as session:
        RunService(session, session_factory).execute_run(rerun_id)
    rerun_detail = _wait_for_run(client, rerun_id)
    assert rerun_detail["status"] == "succeeded"
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-package-runtime-live",
        "base_url": "https://provider-runtime.example.test/v1",
        "timeout": 31.0,
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-package-v1"
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "high"}

    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift fork output"}'
    with session_factory() as session:
        RunService(session, session_factory).execute_run(fork_id)
    fork_detail = _wait_for_run(client, fork_id)
    assert fork_detail["status"] == "succeeded"
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-package-runtime-live",
        "base_url": "https://provider-runtime.example.test/v1",
        "timeout": 31.0,
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-package-v1"
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "high"}

    with session_factory() as session:
        rerun_snapshot = session.get(RunWorkflowPackageSnapshot, rerun_id)
        fork_snapshot = session.get(RunWorkflowPackageSnapshot, fork_id)
        assert rerun_snapshot is not None
        assert fork_snapshot is not None
        assert (
            rerun_snapshot.resolved_model_connections == source_snapshot.resolved_model_connections
        )
        assert (
            fork_snapshot.resolved_model_connections == source_snapshot.resolved_model_connections
        )
        assert (
            rerun_snapshot.preflight_summary == _EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING
        )
        assert (
            fork_snapshot.preflight_summary == _EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING
        )
        assert session.query(Run).count() == runs_before + 2


def test_compat_runtime_profile_run_fixture_9201_exposes_secret_safe_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    fixture_run_id = 9201
    fixture_package_id = 9101
    fixture_target_key = "compat-runtime-profile-run"
    manifest_source = _package_source(package_key="compat_runtime_profile_package")
    compiled = compile_workflow_package_manifest(manifest_source)
    package_definition = cast(dict[str, Any], deepcopy(compiled["packageDefinition"]))
    compiled_plan = cast(dict[str, Any], deepcopy(compiled["compiledPlan"]))
    package_definition["metadata"]["key"] = fixture_target_key
    compiled_plan["packageKey"] = fixture_target_key
    workflow = cast(dict[str, Any], compiled_plan["workflows"][0])
    capabilities = default_model_connection_capabilities("openai_chat_completions").model_dump(
        mode="json", by_alias=True
    )
    capabilities["strictJsonSchemaOutput"]["status"] = "unsupported"
    resolved_model_connections = [
        {
            "key": "package_runtime_model",
            "name": "Compatibility Runtime Profile Model",
            "protocolProfile": "openai_chat_completions",
            "baseUrl": "https://compat-runtime-profile.example.test/v1",
            "modelId": "fake-compat-runtime-profile",
            "reasoningEffort": None,
            "capabilities": capabilities,
            "outputStrategyPolicy": "allow_json_object_validation",
            "parallelToolCallsPolicy": "serialize",
            "reasoningPolicy": "forbid",
            "streamingPolicy": "forbid",
            "probeCacheTtlSeconds": 120,
            "apiStyle": "chat_completions",
            "timeoutSeconds": 45,
            "hasApiKey": True,
        }
    ]

    with session_factory() as session:
        package = WorkflowPackage(
            id=fixture_package_id,
            key=fixture_target_key,
            name="Compatibility Runtime Profile Package",
            description="Deterministic run-detail fixture for runtime profile provenance.",
            manifest_source=manifest_source,
            manifest_hash=str(compiled["manifestHash"]),
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=str(compiled["compiledHash"]),
            extension_dependencies=[],
        )
        session.add(package)
        session.flush()
        run = Run(
            id=fixture_run_id,
            agent_id=None,
            target_workflow_id=None,
            target_kind="workflowPackage",
            target_id=fixture_package_id,
            target_key=fixture_target_key,
            target_version=1,
            workflow_package_id=fixture_package_id,
            workflow_package_key=fixture_target_key,
            workflow_package_workflow_key="runtime_workflow",
            extension_dependencies=[],
            input={"ticker": "MSFT"},
            status="succeeded",
            source_run_id=None,
            lineage_root_run_id=None,
            forked_from_step_index=None,
            resume_step_index=1,
            final_output={"summary": "compat fixture output"},
            total_tokens=17,
            inherited_tokens=0,
            executed_tokens=17,
            trace_id="trace-compat-runtime-profile",
            error=None,
        )
        run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=fixture_package_id,
            workflow_package_key=fixture_target_key,
            workflow_package_name="Compatibility Runtime Profile Package",
            workflow_package_description=package.description,
            workflow_package_status=None,
            workflow_key="runtime_workflow",
            workflow_name=str(workflow["name"]),
            workflow_description=str(workflow.get("description") or ""),
            manifest_hash=str(compiled["manifestHash"]),
            compiled_hash=str(compiled["compiledHash"]),
            manifest_source=manifest_source,
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            extension_dependencies=[],
            local_resource_refs={
                "agents": ["package_analyst"],
                "outputSchemas": ["summary_output"],
                "capabilityProfiles": [],
                "mcpServers": [],
                "workflows": ["runtime_workflow"],
            },
            input_schema=deepcopy(workflow["inputSchema"]),
            launch_parameters={"ticker": "MSFT"},
            resolved_model_connections=resolved_model_connections,
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(run)
        session.commit()

    detail_response = client.get(f"/api/runs/{fixture_run_id}")

    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    profile = cast(dict[str, Any], provenance["resolvedModelConnections"][0])
    serialized = json.dumps(detail, sort_keys=True)
    assert detail["id"] == fixture_run_id
    assert detail["targetKey"] == fixture_target_key
    assert provenance["workflowPackageKey"] == fixture_target_key
    assert provenance["launchSnapshot"]["parameters"] == {"ticker": "MSFT"}
    assert provenance["preflightSummary"] == {"ready": True, "blockingErrors": [], "warnings": []}
    assert provenance["currentPackage"]["available"] is True
    assert provenance["currentPackage"]["manifestHashMatchesSnapshot"] is True
    assert provenance["currentPackage"]["compiledHashMatchesSnapshot"] is True
    assert profile == resolved_model_connections[0]
    assert "secretPayload" not in serialized
    assert "sk-" not in serialized
    assert "providerPayload" not in serialized


def _create_tradingagents_package(client: TestClient) -> dict[str, Any]:
    return _seeded_tradingagents_package(client)


def _tradingagents_parameters() -> dict[str, object]:
    return {
        "ticker": "MSFT",
        "asOfDate": "2026-05-15",
        "portfolioId": "portfolio-1",
        "horizonDays": 30,
        "benchmarkSymbol": "SPY",
    }


def test_seeded_tradingagents_advisory_manifest_exports_after_startup(
    client: TestClient,
) -> None:
    package = _seeded_tradingagents_package(client)

    response = client.get(f"/api/workflow-packages/{package['id']}/manifest")

    assert response.status_code == 200, response.json()
    manifest = cast(dict[str, Any], response.json())
    assert_removed_contract_tokens_absent(manifest, context="seeded manifest hydration")
    assert manifest["packageId"] == package["id"]
    assert manifest["packageKey"] == _TRADINGAGENTS_PRESET_KEY
    assert _TRADINGAGENTS_PRESET_KEY in manifest["manifestSource"]
    assert manifest["packageDefinition"]["metadata"]["key"] == _TRADINGAGENTS_PRESET_KEY

    exported = client.get(f"/api/workflow-packages/{package['id']}/export")
    assert exported.status_code == 200, exported.text
    assert_removed_contract_tokens_absent(exported.text, context="seeded manifest export")


def _mcp_only_package_source(package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: MCP Dependency Snapshot Fixture
spec:
  inputs:
    type: object
  capabilityProfiles: []
  outputSchemas:
    - key: mcp_output
      name: MCP Output
      jsonSchema:
        type: object
  mcpServers:
    - key: exa
      name: Exa Web Search
      transport: http-sse
      url: https://mcp.exa.ai/mcp?tools=web_search_exa
      toolKeys: [web_search_exa]
  agents:
    - key: mcp_agent
      name: MCP Agent
      modelConnection: tradingagents_primary_model
      systemPrompt: Use package-private MCP search and return JSON.
      inputSchema:
        type: object
      outputSchema: mcp_output
      capabilityProfiles: []
      mcpServers: [exa]
  workflows:
    - key: mcp_flow
      name: MCP Flow
      inputSchema:
        type: object
      flow:
        kind: step
        id: mcp_step
        slot: result
        uses: mcp_agent
        with: {{}}
      output:
        from: ${{{{ nodes.mcp_step.outputs.result }}}}
"""


def _disable_finance_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )


def test_tradingagents_advisory_research_launch_persists_extension_dependencies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )

    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert dependencies
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
    assert dependencies[0]["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    surfaces = set(cast(list[str], dependencies[0]["surfaces"]))
    assert {
        "hook.workflowPackageStart",
        "provider.quote",
        "provider.socialSentiment",
        "runtime.tool.signaldeck.market_data.quote_lookup",
        "tool.signaldeck.market_data.quote_lookup",
    } <= surfaces
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        assert package_row.extension_dependencies == dependencies


def test_run_dependency_snapshot_is_copied_from_current_package(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        frozen_dependencies = deepcopy(package_row.extension_dependencies)
        compiled_plan = deepcopy(package_row.compiled_plan)
        for profile in cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"]):
            profile["toolKeys"] = []
        package_row.compiled_plan = compiled_plan
        session.commit()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json()["extensionDependencies"] == frozen_dependencies

    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        package_row.extension_dependencies = []
        session.commit()

    stable_detail_response = client.get(f"/api/runs/{run_id}")
    assert stable_detail_response.status_code == 200, stable_detail_response.json()
    assert stable_detail_response.json()["extensionDependencies"] == frozen_dependencies


def test_package_private_mcp_dependency_snapshot_blocks_disabled_extension_runtime(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _mcp_only_package_source("mcp_dependency_package")},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={"workflowKey": "mcp_flow", "parameters": {}},
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    queued_detail = client.get(f"/api/runs/{run_id}")
    assert queued_detail.status_code == 200, queued_detail.json()
    dependency = cast(list[dict[str, object]], queued_detail.json()["extensionDependencies"])[0]
    surfaces = set(cast(list[str], dependency["surfaces"]))
    assert "mcp.packagePrivate.web_search_exa" in surfaces
    assert "tool.signaldeck.market_data.quote_lookup" not in surfaces

    _disable_finance_extension(session_factory)
    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)

    failed_detail = client.get(f"/api/runs/{run_id}")
    assert failed_detail.status_code == 200, failed_detail.json()
    assert failed_detail.json()["status"] == "failed"
    assert failed_detail.json()["error"] == "Extension is disabled"


def test_tradingagents_advisory_research_launch_blocks_extension_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    _disable_finance_extension(session_factory)

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )

    assert launch_response.status_code == 422, launch_response.json()
    body = launch_response.json()
    assert body["code"] == "validation_error"
    details = cast(list[dict[str, object]], body["details"])
    assert any(
        detail.get("code") == "extension_disabled"
        and detail.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        for detail in details
    )


def test_tradingagents_advisory_research_runtime_fails_when_extension_disabled_after_launch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    _disable_finance_extension(session_factory)

    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert detail["status"] == "failed"
    assert detail["error"] == "Extension is disabled"
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
