from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.model_connection import ModelConnection
from app.models.workflow_package import WorkflowPackage
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionCapabilityStatus,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
)
from app.schemas.schedule import FireReason, MisfirePolicy, OverlapPolicy
from app.services.extension_service import ExtensionService
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from app.services.workflow_package_preflight import (
    WorkflowPackageDiagnosticFact,
    WorkflowPackageDiagnosticLevel,
    WorkflowPackageDiagnosticProjectionContext,
    WorkflowPackagePreflightService,
)
from app.services.workflow_package_schedule_inputs import SCHEDULE_TEMPLATE_MISSING_VALUE
from app.services.workflow_package_schedule_service import (
    DueWorkflowPackageSchedule,
    ScheduleFireMetadata,
    WorkflowPackageScheduleService,
)
from tests.test_workflow_package_manifest_http_node import http_node_package_source

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_TRADINGAGENTS_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "tradingagents_advisory_research.yaml"
)
_TOOL_REQUIRED_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tool-required-fixture.yaml"
)
_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)
_DIGITAL_ORACLE_PHASE1_TOOL_KEYS = (
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.crypto_derivatives.lookup",
    "signaldeck.digital_oracle.cftc_positioning.lookup",
    "signaldeck.digital_oracle.options.lookup",
)
_FINANCE_MARKET_CONTEXT_TOOL_KEYS = (
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
)


def _canonicalize_live_tool_keys(source: str) -> str:
    return source


def _package_source() -> str:
    return _canonicalize_live_tool_keys(_FIXTURE.read_text())


def _tradingagents_demo_source() -> str:
    return _canonicalize_live_tool_keys(_TRADINGAGENTS_DEMO_FIXTURE.read_text())


def _tool_required_package_source() -> str:
    return _canonicalize_live_tool_keys(_TOOL_REQUIRED_FIXTURE.read_text())


def _digital_oracle_researcher_demo_source() -> str:
    return _canonicalize_live_tool_keys(_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE.read_text())


def _expected_digital_oracle_disabled_tool_errors() -> list[dict[str, object]]:
    return [
        {
            "field": f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]",
            "issue": (
                f"Server-declared tool {tool_key!r} is disabled because extension "
                f"{DIGITAL_ORACLE_EXTENSION_KEY!r} is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
            "surface": f"tool.{tool_key}",
        }
        for index, tool_key in enumerate(sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
    ]


def _expected_finance_market_context_disabled_tool_errors() -> list[dict[str, object]]:
    return [
        {
            "field": f"spec.capabilityProfiles.finance_market_context_tools.toolKeys[{index}]",
            "issue": (
                f"Server-declared tool {tool_key!r} is disabled because extension "
                f"{FINANCE_WORKSPACE_EXTENSION_KEY!r} is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": f"tool.{tool_key}",
        }
        for index, tool_key in enumerate(sorted(_FINANCE_MARKET_CONTEXT_TOOL_KEYS))
    ]


def _digital_oracle_phase1_package_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: digital_oracle_phase1_fixture
  name: Digital Oracle Phase 1 Fixture
  description: Deterministic package fixture for Digital Oracle phase-1 tools.
spec:
  inputs:
    type: object
    required: [researchQuestion]
    properties:
      researchQuestion:
        type: string
  capabilityProfiles:
    - key: digital_oracle_phase1_tools
      name: Digital Oracle Phase 1 Tools
      description: Grants Digital Oracle-owned phase-1 research tools.
      toolKeys:
        - signaldeck.digital_oracle.cftc_positioning.lookup
        - signaldeck.digital_oracle.crypto_derivatives.lookup
        - signaldeck.digital_oracle.macro_rates.lookup
        - signaldeck.digital_oracle.market_sentiment.lookup
        - signaldeck.digital_oracle.options.lookup
        - signaldeck.digital_oracle.prediction_markets.lookup
        - signaldeck.digital_oracle.sec_filings.lookup
  outputSchemas:
    - key: digital_oracle_report
      name: Digital Oracle Report
      jsonSchema:
        type: object
        required: [summary]
        properties:
          summary:
            type: string
  agents:
    - key: digital_oracle_researcher
      name: Digital Oracle Researcher
      modelConnection: tradingagents_primary_model
      systemPrompt: Use the granted Digital Oracle tools and return JSON.
      inputSchema:
        type: object
        required: [researchQuestion]
        properties:
          researchQuestion:
            type: string
      outputSchema: digital_oracle_report
      capabilityProfiles: [digital_oracle_phase1_tools]
  workflows:
    - key: research
      name: Research
      inputSchema:
        type: object
        required: [researchQuestion]
        properties:
          researchQuestion:
            type: string
      flow:
        kind: step
        id: research_step
        slot: report
        uses: digital_oracle_researcher
        with:
          researchQuestion: ${{ inputs.researchQuestion }}
      output:
        from: ${{ nodes.research_step.outputs.report }}
"""


def _digital_oracle_phase1_parameters() -> dict[str, object]:
    return {"researchQuestion": "What changed in NVDA filings?"}


def _digital_oracle_demo_parameters() -> dict[str, object]:
    return {
        "researchQuestion": "What changed in NVDA filings?",
        "outputLanguage": "English",
    }


def _tool_required_parameters() -> dict[str, object]:
    return {"topic": "market structure"}


def _mixed_extension_research_package_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: mixed_extension_research_fixture
  name: Mixed Extension Research Fixture
  description: Package-level composition of Finance market context and Digital Oracle tools.
spec:
  inputs:
    type: object
    required: [researchQuestion]
    properties:
      researchQuestion:
        type: string
  capabilityProfiles:
    - key: finance_market_context_tools
      name: Finance Market Context Tools
      description: Grants Finance-owned market-context tools for package-level research.
      toolKeys:
        - signaldeck.finance.market_data.history_lookup
        - signaldeck.finance.market_data.ohlcv_lookup
    - key: digital_oracle_phase1_tools
      name: Digital Oracle Phase 1 Tools
      description: Grants Digital Oracle-owned phase-1 research tools.
      toolKeys:
        - signaldeck.digital_oracle.cftc_positioning.lookup
        - signaldeck.digital_oracle.crypto_derivatives.lookup
        - signaldeck.digital_oracle.macro_rates.lookup
        - signaldeck.digital_oracle.market_sentiment.lookup
        - signaldeck.digital_oracle.options.lookup
        - signaldeck.digital_oracle.prediction_markets.lookup
        - signaldeck.digital_oracle.sec_filings.lookup
  outputSchemas:
    - key: digital_oracle_report
      name: Digital Oracle Report
      jsonSchema:
        type: object
        required: [summary]
        properties:
          summary:
            type: string
  agents:
    - key: mixed_extension_researcher
      name: Mixed Extension Researcher
      modelConnection: mixed_extension_primary_model
      systemPrompt: Use package-level Finance market context and Digital Oracle tools; return JSON.
      inputSchema:
        type: object
        required: [researchQuestion]
        properties:
          researchQuestion:
            type: string
      outputSchema: digital_oracle_report
      capabilityProfiles: [finance_market_context_tools, digital_oracle_phase1_tools]
  workflows:
    - key: research
      name: Research
      inputSchema:
        type: object
        required: [researchQuestion]
        properties:
          researchQuestion:
            type: string
      flow:
        kind: step
        id: research_step
        slot: report
        uses: mixed_extension_researcher
        with:
          researchQuestion: ${{ inputs.researchQuestion }}
      output:
        from: ${{ nodes.research_step.outputs.report }}
"""


def _project_blocking_diagnostics(
    facts: list[WorkflowPackageDiagnosticFact],
) -> list[dict[str, Any]]:
    blocking_errors, warnings = WorkflowPackagePreflightService._project_diagnostic_facts(
        facts,
        context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
    )
    assert warnings == []
    return blocking_errors


def _mixed_capability_package_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: mixed_capability_fixture
  name: Mixed Capability Fixture
  description: Multi-agent fixture for scoped capability requirements.
spec:
  inputs:
    type: object
    required: [topic]
    properties:
      topic:
        type: string
  capabilityProfiles:
    - key: tool_required
      name: Tool Required
      toolKeys:
        - signaldeck.finance.market_data.quote_lookup
  outputSchemas:
    - key: report
      name: Report
      jsonSchema:
        type: object
        required: [summary]
        properties:
          summary:
            type: string
  mcpServers: []
  agents:
    - key: tool_analyst
      name: Tool Analyst
      modelConnection: tool_capable_model
      systemPrompt: Use tools and return JSON.
      inputSchema:
        type: object
        required: [topic]
        properties:
          topic:
            type: string
      outputSchema: report
      capabilityProfiles: [tool_required]
      mcpServers: []
    - key: summary_writer
      name: Summary Writer
      modelConnection: no_tool_model
      systemPrompt: Return JSON without tools.
      inputSchema:
        type: object
        required: [topic]
        properties:
          topic:
            type: string
      outputSchema: report
      capabilityProfiles: []
      mcpServers: []
    - key: unused_critic
      name: Unused Critic
      modelConnection: unused_bad_model
      systemPrompt: This agent is not in the selected workflow.
      inputSchema:
        type: object
        required: [topic]
        properties:
          topic:
            type: string
      outputSchema: report
      capabilityProfiles: []
      mcpServers: []
  workflows:
    - key: main
      name: Main
      inputSchema:
        type: object
        required: [topic]
        properties:
          topic:
            type: string
      flow:
        kind: sequence
        id: main_sequence
        nodes:
          - kind: step
            id: analyze
            slot: analysis
            uses: tool_analyst
            with:
              topic: ${{ inputs.topic }}
          - kind: step
            id: summarize
            slot: summary
            uses: summary_writer
            with:
              topic: ${{ inputs.topic }}
      output:
        from: ${{ nodes.summarize.outputs.summary }}
    - key: fanout
      name: Fanout
      inputSchema:
        type: object
        required: [topic]
        properties:
          topic:
            type: string
      flow:
        kind: fanout
        id: fanout_tools
        branches:
          - id: tool
            node:
              kind: step
              id: tool_branch
              slot: tool_report
              uses: tool_analyst
              with:
                topic: ${{ inputs.topic }}
          - id: plain
            node:
              kind: step
              id: plain_branch
              slot: plain_report
              uses: summary_writer
              with:
                topic: ${{ inputs.topic }}
      output:
        from: ${{ nodes.fanout_tools.outputs.tool_report }}
"""


def _delete_existing_package(client: TestClient, key: str) -> None:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, object]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] != key:
            continue
        deleted = client.delete(f"/api/workflow-packages/{package['id']}")
        assert deleted.status_code == 204, deleted.text
        break


def _bind_package_secret(client: TestClient, package_id: int, key: str) -> None:
    response = client.put(
        f"/api/workflow-packages/{package_id}/secret-bindings/{key}",
        json={"value": f"{key}-test-value"},
    )
    assert response.status_code == 200, response.json()


def _delete_existing_tradingagents_package(client: TestClient) -> None:
    _delete_existing_package(client, "tradingagents_advisory_research")


def _create_package(client: TestClient) -> dict[str, Any]:
    _delete_existing_tradingagents_package(client)
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "test-api-key",
    key: str = "tradingagents_primary_model",
    name: str = "TradingAgents Primary Model",
    description: str = "Preflight model binding.",
    base_url: str = "https://provider-preflight.example.test/v1",
    model_id: str = "gpt-5.5-mini",
    protocol_profile: str = "openai_responses",
    capabilities: ModelConnectionCapabilities | None = None,
    output_strategy_policy: str = "prefer_strict_schema",
    parallel_tool_calls_policy: str = "serialize",
    reasoning_policy: str = "allow",
    streaming_policy: str = "allow",
    probe_cache_ttl_seconds: int = 900,
    timeout_seconds: int = 60,
    last_test_ok: bool | None = None,
    last_test_message: str | None = None,
) -> None:
    if capabilities is None:
        capabilities = default_model_connection_capabilities(protocol_profile)
    with session_factory() as session:
        session.add(
            ModelConnection(
                key=key,
                protocol_profile=protocol_profile,
                name=name,
                description=description,
                base_url=base_url,
                model_id=model_id,
                capabilities=dump_model_connection_capabilities(capabilities),
                output_strategy_policy=output_strategy_policy,
                parallel_tool_calls_policy=parallel_tool_calls_policy,
                reasoning_policy=reasoning_policy,
                streaming_policy=streaming_policy,
                probe_cache_ttl_seconds=probe_cache_ttl_seconds,
                timeout_seconds=timeout_seconds,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=(
                    utcnow() if last_test_ok is not None or last_test_message is not None else None
                ),
                last_test_ok=last_test_ok,
                last_test_message=last_test_message,
            )
        )
        session.commit()


def _capabilities_with_statuses(
    *,
    native_tool_calls_status: ModelConnectionCapabilityStatus = (
        ModelConnectionCapabilityStatus.SUPPORTED
    ),
    strict_json_schema_status: ModelConnectionCapabilityStatus = (
        ModelConnectionCapabilityStatus.SUPPORTED
    ),
    json_object_status: ModelConnectionCapabilityStatus = (
        ModelConnectionCapabilityStatus.SUPPORTED
    ),
    parallel_tool_calls_status: ModelConnectionCapabilityStatus = (
        ModelConnectionCapabilityStatus.SUPPORTED
    ),
    streaming_status: ModelConnectionCapabilityStatus = ModelConnectionCapabilityStatus.UNKNOWN,
    reasoning_hints_status: ModelConnectionCapabilityStatus = (
        ModelConnectionCapabilityStatus.UNKNOWN
    ),
) -> ModelConnectionCapabilities:
    capabilities = default_model_connection_capabilities("openai_chat_completions")
    capabilities.native_tool_calls.status = native_tool_calls_status
    capabilities.strict_json_schema_output.status = strict_json_schema_status
    capabilities.json_object_output.status = json_object_status
    capabilities.parallel_tool_calls.status = parallel_tool_calls_status
    capabilities.streaming.status = streaming_status
    capabilities.reasoning_hints.status = reasoning_hints_status
    return capabilities


def _seed_tool_required_package(session_factory: sessionmaker[Session]) -> None:
    compiled = compile_workflow_package_manifest(_tool_required_package_source())
    package_definition = cast(dict[str, Any], compiled["packageDefinition"])
    metadata = cast(dict[str, Any], package_definition["metadata"])
    with session_factory() as session:
        session.add(
            WorkflowPackage(
                id=9101,
                key=str(metadata["key"]),
                name=str(metadata["name"]),
                description=str(metadata.get("description") or ""),
                manifest_source=_tool_required_package_source(),
                manifest_hash=str(compiled["manifestHash"]),
                package_definition=package_definition,
                compiled_plan=cast(dict[str, Any], compiled["compiledPlan"]),
                compiled_hash=str(compiled["compiledHash"]),
                extension_dependencies=cast(
                    list[dict[str, Any]], compiled.get("extensionDependencies") or []
                ),
            )
        )
        session.commit()


def _seed_runtime_profile_fixture_connection(
    session_factory: sessionmaker[Session],
    *,
    native_tool_calls_status: ModelConnectionCapabilityStatus,
    strict_json_schema_status: ModelConnectionCapabilityStatus,
    json_object_status: ModelConnectionCapabilityStatus = ModelConnectionCapabilityStatus.UNKNOWN,
    api_key: str | None = "test-api-key",
    last_test_ok: bool | None = None,
    last_test_message: str | None = None,
) -> None:
    capabilities = default_model_connection_capabilities("openai_chat_completions")
    capabilities.native_tool_calls.status = native_tool_calls_status
    capabilities.strict_json_schema_output.status = strict_json_schema_status
    capabilities.json_object_output.status = json_object_status
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="runtime_profile_tools_disabled",
                protocol_profile="openai_chat_completions",
                name="Provider Profile Fixture: Tools Disabled",
                description="Probe fixture with tool calls disabled.",
                base_url="https://runtime-profile-tools-disabled.example.test",
                model_id="fake-tools-disabled",
                capabilities=dump_model_connection_capabilities(capabilities),
                output_strategy_policy="prefer_strict_schema",
                parallel_tool_calls_policy="serialize",
                reasoning_policy="allow",
                streaming_policy="allow",
                probe_cache_ttl_seconds=900,
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=(
                    utcnow() if last_test_ok is not None or last_test_message is not None else None
                ),
                last_test_ok=last_test_ok,
                last_test_message=last_test_message,
            )
        )
        session.commit()


def _diagnostic_wire_identity(diagnostic: dict[str, object]) -> tuple[str, str]:
    return (
        str(diagnostic.get("field") or diagnostic.get("path") or ""),
        str(diagnostic.get("issue") or diagnostic.get("message") or ""),
    )


def test_diagnostic_fact_identity_ignores_issue_text_and_preserves_first_occurrence() -> None:
    blocking_levels = {
        WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
            WorkflowPackageDiagnosticLevel.BLOCKING
        )
    }
    first_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        field="spec.agents[0].modelConnection",
        issue="Model connection 'missing_model' was not found",
        subject="missing_model",
        levels=blocking_levels,
    )
    duplicate_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        field="spec.agents[0].modelConnection",
        issue="Copy changed but identity should stay stable",
        subject="missing_model",
        levels=blocking_levels,
    )
    path_fact = WorkflowPackageDiagnosticFact(
        kind="execution_plan_invalid",
        code="execution_plan_invalid",
        path="spec.workflows.advisory_research.graph.steps[0]",
        issue="cycle",
        subject="advisory_research",
        levels=blocking_levels,
    )

    assert first_fact.identity == duplicate_fact.identity

    blocking_errors, warnings = WorkflowPackagePreflightService._project_diagnostic_facts(
        [first_fact, duplicate_fact, path_fact],
        context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
    )

    assert blocking_errors == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
        },
        {
            "path": "spec.workflows.advisory_research.graph.steps[0]",
            "issue": "cycle",
        },
    ]
    assert warnings == []


def test_diagnostic_fact_projection_contexts_preserve_public_diagnostics() -> None:
    missing_model_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        field="spec.agents[0].modelConnection",
        issue="Model connection 'missing_model' was not found",
        subject="missing_model",
        metadata={"agentKey": "analyst"},
        levels={
            WorkflowPackageDiagnosticProjectionContext.VALIDATION: (
                WorkflowPackageDiagnosticLevel.WARNING
            ),
            WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
        },
    )
    api_key_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_api_key_missing",
        code="model_connection_api_key_missing",
        field="spec.agents[0].modelConnection",
        issue="API key is not configured",
        subject="missing_model",
        levels={
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            )
        },
    )
    schema_fact = WorkflowPackageDiagnosticFact(
        kind="schema_invalid",
        code="schema_invalid",
        field="spec.outputSchemas[0].jsonSchema",
        issue="Schema must be an object",
        levels={
            WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
        },
    )

    assert WorkflowPackagePreflightService._project_validation_warning_facts(
        [missing_model_fact, api_key_fact, schema_fact]
    ) == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
            "agentKey": "analyst",
        }
    ]

    launch_blocking_errors, launch_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            [missing_model_fact, api_key_fact, schema_fact],
            context=WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA,
        )
    )
    assert launch_blocking_errors == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
            "agentKey": "analyst",
        },
        {
            "field": "spec.outputSchemas[0].jsonSchema",
            "issue": "Schema must be an object",
        },
    ]
    assert launch_warnings == []

    strict_blocking_errors, strict_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            [missing_model_fact, api_key_fact, schema_fact],
            context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
        )
    )
    assert strict_blocking_errors == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
            "agentKey": "analyst",
        },
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "API key is not configured",
        },
        {
            "field": "spec.outputSchemas[0].jsonSchema",
            "issue": "Schema must be an object",
        },
    ]
    assert strict_warnings == []


def test_readiness_diagnostic_fact_adapter_deduplicates_missing_model_warning() -> None:
    readiness_facts = [
        *WorkflowPackagePreflightService._readiness_diagnostic_facts(
            [
                {
                    "field": "spec.agents[0].modelConnection",
                    "issue": "Model connection 'missing_model' was not found",
                }
            ],
            level=WorkflowPackageDiagnosticLevel.BLOCKING,
        ),
        *WorkflowPackagePreflightService._readiness_diagnostic_facts(
            [
                {
                    "field": "spec.agents[0].modelConnection",
                    "issue": "Model connection 'missing_model' was not found",
                    "severity": "warning",
                }
            ],
            level=WorkflowPackageDiagnosticLevel.WARNING,
        ),
    ]

    launch_blocking_errors, launch_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            readiness_facts,
            context=WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA,
        )
    )

    assert launch_blocking_errors == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
        }
    ]
    assert launch_warnings == []


def test_validation_projection_hides_blocker_only_facts_but_strict_readiness_preserves_payloads() -> (  # noqa: E501
    None
):
    blocker_only_facts = [
        WorkflowPackageDiagnosticFact(
            kind="schema_invalid",
            code="schema_invalid",
            field="spec.outputSchemas[0].jsonSchema",
            issue="Schema must be an object",
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
        WorkflowPackageDiagnosticFact(
            kind="tool_invalid",
            code="extension_disabled",
            field="spec.capabilityProfiles.quote_tools.toolKeys[0]",
            issue=(
                "Server-declared tool 'signaldeck.finance.market_data.quote_lookup' is "
                "disabled because "
                "extension 'signaldeck.finance' is disabled"
            ),
            subject="tool.signaldeck.finance.market_data.quote_lookup",
            metadata={
                "code": "extension_disabled",
                "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
                "surface": "tool.signaldeck.finance.market_data.quote_lookup",
            },
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
        WorkflowPackageDiagnosticFact(
            kind="http_secret_missing",
            code="http_secret_missing",
            field="spec.workflows.notify.graph.steps[0].operations[0].request",
            issue="HTTP secret binding 'body_token' is not configured",
            subject="body_token",
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
        WorkflowPackageDiagnosticFact(
            kind="execution_plan_invalid",
            code="execution_plan_invalid",
            field="spec.workflows.advisory_research.graph.steps[0].agents[0].with.ticker",
            issue="cycle",
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
    ]

    assert (
        WorkflowPackagePreflightService._project_validation_warning_facts(blocker_only_facts) == []
    )

    strict_blocking_errors, strict_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            blocker_only_facts,
            context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
        )
    )

    assert strict_blocking_errors == [
        {
            "field": "spec.outputSchemas[0].jsonSchema",
            "issue": "Schema must be an object",
        },
        {
            "field": "spec.capabilityProfiles.quote_tools.toolKeys[0]",
            "issue": (
                "Server-declared tool 'signaldeck.finance.market_data.quote_lookup' is "
                "disabled because "
                "extension 'signaldeck.finance' is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": "tool.signaldeck.finance.market_data.quote_lookup",
        },
        {
            "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
            "issue": "HTTP secret binding 'body_token' is not configured",
        },
        {
            "field": "spec.workflows.advisory_research.graph.steps[0].agents[0].with.ticker",
            "issue": "cycle",
        },
    ]
    assert strict_warnings == []


def test_preflight_accepts_digital_oracle_server_declared_toolKeys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_digital_oracle_phase1_package_source())
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}
    extension_dependencies = cast(list[dict[str, Any]], compiled["extensionDependencies"])

    with session_factory() as session:
        errors = _project_blocking_diagnostics(
            WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)
        )

    requirements = PackageExecutionPlanBuilder.derive_package_requirements(compiled_plan)
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None

    assert errors == []
    assert profiles_by_key["digital_oracle_phase1_tools"]["toolKeys"] == sorted(
        _DIGITAL_ORACLE_PHASE1_TOOL_KEYS
    )
    assert requirements.native_tool_sources == (
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys",
    )
    assert runtime_agent.capability_profiles[0].tool_keys == tuple(
        sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)
    )
    assert extension_dependencies == [
        {
            "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
            "surfaces": sorted(
                [
                    *[f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                    *[f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                ]
            ),
            "fields": [
                f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]"
                for index in range(len(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
            ],
        }
    ]


def test_preflight_accepts_mixed_extension_research_package_with_finance_market_context(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _mixed_extension_research_package_source()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}
    extension_dependencies = cast(list[dict[str, Any]], compiled["extensionDependencies"])

    with session_factory() as session:
        tool_errors = _project_blocking_diagnostics(
            WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)
        )

    requirements = PackageExecutionPlanBuilder.derive_package_requirements(compiled_plan)
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None

    _seed_model_connection(
        session_factory,
        key="mixed_extension_primary_model",
        name="Mixed Extension Primary Model",
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    response = client.post("/api/workflow-packages", json={"manifestSource": manifest_source})
    assert response.status_code == 201, response.json()
    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": _digital_oracle_phase1_parameters()},
    )

    assert tool_errors == []
    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert preflight_body["ready"] is True
    assert preflight_body["blockingErrors"] == []
    assert preflight_body["warnings"] == []
    assert profiles_by_key["finance_market_context_tools"]["toolKeys"] == sorted(
        _FINANCE_MARKET_CONTEXT_TOOL_KEYS
    )
    assert profiles_by_key["digital_oracle_phase1_tools"]["toolKeys"] == sorted(
        _DIGITAL_ORACLE_PHASE1_TOOL_KEYS
    )
    assert set(requirements.native_tool_sources) == {
        "spec.capabilityProfiles.finance_market_context_tools.toolKeys",
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys",
    }
    agent_profiles_by_key = {profile.key: profile for profile in runtime_agent.capability_profiles}
    assert agent_profiles_by_key["finance_market_context_tools"].tool_keys == tuple(
        sorted(_FINANCE_MARKET_CONTEXT_TOOL_KEYS)
    )
    assert agent_profiles_by_key["digital_oracle_phase1_tools"].tool_keys == tuple(
        sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)
    )
    dependencies_by_extension = {
        str(dependency["extensionKey"]): dependency for dependency in extension_dependencies
    }
    assert dependencies_by_extension[DIGITAL_ORACLE_EXTENSION_KEY] == {
        "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
        "surfaces": sorted(
            [
                *[f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                *[f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
            ]
        ),
        "fields": [
            f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]"
            for index in range(len(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
        ],
    }
    finance_dependency = dependencies_by_extension[FINANCE_WORKSPACE_EXTENSION_KEY]
    assert finance_dependency["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert set(cast(list[str], finance_dependency["fields"])) == {
        "spec.capabilityProfiles.finance_market_context_tools.toolKeys[0]",
        "spec.capabilityProfiles.finance_market_context_tools.toolKeys[1]",
    }
    assert {
        *[f"runtime.tool.{tool_key}" for tool_key in _FINANCE_MARKET_CONTEXT_TOOL_KEYS],
        *[f"tool.{tool_key}" for tool_key in _FINANCE_MARKET_CONTEXT_TOOL_KEYS],
    } <= set(cast(list[str], finance_dependency["surfaces"]))


def test_digital_oracle_researcher_demo_validates_compiles_and_preflights(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _digital_oracle_researcher_demo_source()
    parsed = parse_workflow_package_manifest(manifest_source)
    assert parsed.diagnostics == []
    assert parsed.manifest is not None
    validation = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": manifest_source},
    )
    assert validation.status_code == 200, validation.json()
    assert validation.json()["diagnostics"] == []

    compiled = compile_workflow_package_manifest(manifest_source)
    package_definition = cast(dict[str, Any], compiled["packageDefinition"])
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    with session_factory() as session:
        tool_errors = _project_blocking_diagnostics(
            WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)
        )

    requirements = PackageExecutionPlanBuilder.derive_package_requirements(compiled_plan)
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None

    _seed_model_connection(
        session_factory,
        key="digital_oracle_primary_model",
        name="Digital Oracle Primary Model",
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    _delete_existing_package(client, "digital_oracle_researcher")
    created = client.post("/api/workflow-packages", json={"manifestSource": manifest_source})
    assert created.status_code == 201, created.json()
    _bind_package_secret(client, int(created.json()["id"]), "fred_api_key")
    preflight = client.post(
        f"/api/workflow-packages/{created.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": _digital_oracle_demo_parameters()},
    )

    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert preflight_body["ready"] is True
    assert preflight_body["blockingErrors"] == []
    assert preflight_body["warnings"] == []
    package_metadata = cast(dict[str, object], package_definition["metadata"])
    assert package_metadata["key"] == "digital_oracle_researcher"
    assert tool_errors == []
    assert profiles_by_key["digital_oracle_phase1_tools"]["toolKeys"] == sorted(
        _DIGITAL_ORACLE_PHASE1_TOOL_KEYS
    )
    assert requirements.native_tool_sources == (
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys",
    )
    assert runtime_agent.key == "digital_oracle_signal_researcher"
    assert runtime_agent.system_prompt.startswith(
        "Digital Oracle methodology is package-local for this agent."
    )
    agent_profiles_by_key = {profile.key: profile for profile in runtime_agent.capability_profiles}
    assert agent_profiles_by_key["digital_oracle_phase1_tools"].tool_keys == tuple(
        sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)
    )
    assert set(agent_profiles_by_key) == {"digital_oracle_phase1_tools"}


def test_preflight_missing_digital_oracle_toolKeys_diagnostic_preserves_field_only_shape(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_digital_oracle_phase1_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles[0]["toolKeys"] = [
        "signaldeck.digital_oracle.market_sentiment.lookup",
        "signaldeck.digital_oracle.missing",
        "signaldeck.digital_oracle.sec_filings.lookup",
    ]

    with session_factory() as session:
        errors = _project_blocking_diagnostics(
            WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)
        )

    assert errors == [
        {
            "field": "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
            "issue": "Unknown server-declared tool 'signaldeck.digital_oracle.missing'",
        }
    ]


def test_package_execution_plan_builder_derives_tool_and_output_requirements() -> None:
    compiled = compile_workflow_package_manifest(_tool_required_package_source())
    requirements = PackageExecutionPlanBuilder.derive_package_requirements(
        cast(dict[str, Any], compiled["compiledPlan"])
    )

    assert requirements.requires_native_tool_calls is True
    assert requirements.requires_structured_output is True
    assert requirements.native_tool_sources == ("spec.capabilityProfiles.tool_required.toolKeys",)
    assert requirements.structured_output_sources == ("spec.outputSchemas.report.jsonSchema",)


def test_preflight_blocks_tool_required_fixture_with_unsupported_native_tool_calls(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tool_required_package(session_factory)
    _seed_runtime_profile_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
    )

    preflight = client.post(
        "/api/workflow-packages/9101/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.capabilityProfiles.tool_required.toolKeys",
        "code": "model_capability_required_missing",
        "agentKey": "analyst",
        "modelConnectionKey": "runtime_profile_tools_disabled",
        "requirement": "nativeToolCalls",
        "issue": (
            "This workflow requires native tool calls, but the selected model connection "
            "does not support them."
        ),
    } in errors
    warnings = cast(list[dict[str, object]], body["warnings"])
    assert any(
        warning["field"] == "spec.outputSchemas.report.jsonSchema"
        and warning.get("code") == "model_capability_probe_inconclusive"
        and "JSON object output has not been proven yet" in str(warning["issue"])
        for warning in warnings
    )


def test_preflight_warns_when_required_model_capabilities_are_unproven(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tool_required_package(session_factory)
    _seed_runtime_profile_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.UNKNOWN,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNKNOWN,
        json_object_status=ModelConnectionCapabilityStatus.UNKNOWN,
    )

    preflight = client.post(
        "/api/workflow-packages/9101/preflight",
        json={"workflowKey": None, "parameters": _tool_required_parameters()},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    assert cast(list[dict[str, object]], body["warnings"]) == [
        {
            "field": "spec.capabilityProfiles.tool_required.toolKeys",
            "code": "model_capability_probe_inconclusive",
            "agentKey": "analyst",
            "modelConnectionKey": "runtime_profile_tools_disabled",
            "requirement": "nativeToolCalls",
            "issue": (
                "This workflow requires native tool calls, but support has not been proven yet."
            ),
            "severity": "warning",
        },
        {
            "field": "spec.outputSchemas.report.jsonSchema",
            "code": "model_capability_probe_inconclusive",
            "agentKey": "analyst",
            "modelConnectionKey": "runtime_profile_tools_disabled",
            "requirement": "structuredOutput",
            "issue": (
                "This workflow requires structured JSON output, but strict "
                "JSON-schema output has not been proven yet."
            ),
            "severity": "warning",
        },
    ]


def test_preflight_warns_when_structured_output_falls_back_to_json_object_validation(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tool_required_package(session_factory)
    _seed_runtime_profile_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.SUPPORTED,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        json_object_status=ModelConnectionCapabilityStatus.SUPPORTED,
    )

    preflight = client.post(
        "/api/workflow-packages/9101/preflight",
        json={"workflowKey": None, "parameters": _tool_required_parameters()},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    warnings = cast(list[dict[str, object]], body["warnings"])
    assert warnings == [
        {
            "field": "spec.outputSchemas.report.jsonSchema",
            "code": "model_capability_required_missing",
            "agentKey": "analyst",
            "modelConnectionKey": "runtime_profile_tools_disabled",
            "requirement": "structuredOutput",
            "issue": (
                "This workflow requires structured JSON output, but strict JSON-schema output "
                "is unavailable so JSON object validation will be used."
            ),
            "severity": "warning",
        }
    ]


def test_preflight_multi_agent_per_agent_structured_output_scope_keeps_unrelated_agents_ready(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        key="tool_capable_model",
        capabilities=_capabilities_with_statuses(),
    )
    _seed_model_connection(
        session_factory,
        key="no_tool_model",
        capabilities=_capabilities_with_statuses(
            native_tool_calls_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        ),
    )
    _seed_model_connection(
        session_factory,
        key="unused_bad_model",
        capabilities=_capabilities_with_statuses(
            native_tool_calls_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
            strict_json_schema_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
            json_object_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        ),
    )
    created = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _mixed_capability_package_source()},
    )
    assert created.status_code == 201, created.json()

    preflight = client.post(
        f"/api/workflow-packages/{created.json()['id']}/preflight",
        json={"workflowKey": "main", "parameters": _tool_required_parameters()},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    assert body["warnings"] == []
    with session_factory() as session:
        package = WorkflowPackageRepository(session).get(int(created.json()["id"]))
        assert package is not None
        result = WorkflowPackagePreflightService(session).evaluate_readiness(
            package,
            workflow_key="main",
            require_api_key=True,
        )
    assert set(result.model_bindings) == {"no_tool_model", "tool_capable_model"}
    assert result.package_requirements.requires_native_tool_calls is True
    assert (
        result.agent_requirement_scopes["summary_writer"].requirements.requires_native_tool_calls
        is False
    )


def test_preflight_parallel_streaming_reasoning_requirements_are_per_agent_scoped() -> None:
    compiled = compile_workflow_package_manifest(_mixed_capability_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    agents = cast(list[dict[str, Any]], compiled_plan["agents"])
    agents_by_key = {str(agent["key"]): agent for agent in agents}
    agents_by_key["tool_analyst"]["requiresStreaming"] = True
    agents_by_key["summary_writer"]["requiresReasoningHints"] = True

    fanout_requirements = PackageExecutionPlanBuilder.derive_workflow_agent_requirements(
        compiled_plan,
        "fanout",
    )
    main_requirements = PackageExecutionPlanBuilder.derive_workflow_agent_requirements(
        compiled_plan,
        "main",
    )

    assert fanout_requirements["tool_analyst"].requirements.requires_parallel_tool_calls is True
    assert fanout_requirements["summary_writer"].requirements.requires_parallel_tool_calls is False
    assert main_requirements["tool_analyst"].requirements.requires_streaming is True
    assert main_requirements["summary_writer"].requirements.requires_streaming is False
    assert main_requirements["summary_writer"].requirements.requires_reasoning_hints is True
    assert main_requirements["tool_analyst"].requirements.requires_reasoning_hints is False


def test_validate_manifest_warns_about_missing_model_connection_without_persisting(
    client: TestClient,
) -> None:
    validation = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": _package_source()},
    )

    assert validation.status_code == 200, validation.json()
    body = cast(dict[str, object], validation.json())
    assert body["diagnostics"] == []
    warnings = cast(list[dict[str, object]], body["warnings"])
    expected_count = _package_source().count("modelConnection: tradingagents_primary_model")
    missing_model_warnings = [
        warning
        for warning in warnings
        if warning["issue"] == "Model connection 'tradingagents_primary_model' was not found"
    ]
    assert [warning["field"] for warning in missing_model_warnings] == [
        f"spec.agents[{index}].modelConnection" for index in range(expected_count)
    ]
    assert all(warning["severity"] == "warning" for warning in missing_model_warnings)


def test_save_allows_missing_model_connection_and_preflight_blocks(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _delete_existing_tradingagents_package(client)
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 201, response.json()
    response_body = cast(dict[str, object], response.json())
    package_id = cast(int, response_body["id"])
    with session_factory() as session:
        assert session.get(WorkflowPackage, package_id) is not None

    expected_count = _package_source().count("modelConnection: tradingagents_primary_model")
    expected_fields = [f"spec.agents[{index}].modelConnection" for index in range(expected_count)]
    expected_issue = "Model connection 'tradingagents_primary_model' was not found"
    expected_identities = {(field, expected_issue) for field in expected_fields}
    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": "advisory_research", "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = cast(dict[str, object], preflight.json())
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    preflight_warnings = cast(list[dict[str, object]], body["warnings"])
    missing_model_errors = [error for error in errors if error["issue"] == expected_issue]
    assert [error["field"] for error in missing_model_errors] == expected_fields
    assert {
        _diagnostic_wire_identity(error) for error in missing_model_errors
    } == expected_identities
    preflight_error_identities = {_diagnostic_wire_identity(error) for error in errors}
    preflight_warning_identities = {
        _diagnostic_wire_identity(warning) for warning in preflight_warnings
    }
    assert preflight_warning_identities.isdisjoint(expected_identities)
    assert preflight_warning_identities.isdisjoint(preflight_error_identities)
    assert preflight_warnings == []

    launch = client.get(
        f"/api/workflow-packages/{package_id}/launch",
        params={"workflowKey": "advisory_research"},
    )

    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert launch_body["ready"] is False
    launch_errors = cast(list[dict[str, object]], launch_body["blockingErrors"])
    launch_warnings = cast(list[dict[str, object]], launch_body["warnings"])
    launch_missing_model_errors = [
        error for error in launch_errors if error["issue"] == expected_issue
    ]
    assert [error["field"] for error in launch_missing_model_errors] == expected_fields
    assert {
        _diagnostic_wire_identity(error) for error in launch_missing_model_errors
    } == expected_identities
    launch_error_identities = {_diagnostic_wire_identity(error) for error in launch_errors}
    launch_warning_identities = {_diagnostic_wire_identity(warning) for warning in launch_warnings}
    assert launch_warning_identities.isdisjoint(expected_identities)
    assert launch_warning_identities.isdisjoint(launch_error_identities)
    assert launch_warnings == []


def test_update_allows_unresolved_model_connection_and_preflight_blocks(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    missing_source = _package_source().replace(
        "modelConnection: tradingagents_primary_model",
        "modelConnection: tradingagents_future_model",
    )

    response = client.patch(
        f"/api/workflow-packages/{created['id']}",
        json={"manifestSource": missing_source},
    )

    assert response.status_code == 200, response.json()
    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )
    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    expected_count = missing_source.count("modelConnection: tradingagents_future_model")
    missing_model_errors = [
        error
        for error in errors
        if error["issue"] == "Model connection 'tradingagents_future_model' was not found"
    ]
    assert len(missing_model_errors) == expected_count


def test_preflight_reports_binding_schema_tool_and_graph_failures(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    with session_factory() as session:
        repository = WorkflowPackageRepository(session)
        package = repository.get(int(created["id"]))
        assert package is not None
        compiled_plan = deepcopy(cast(dict[str, Any], package.compiled_plan))
        package_definition = deepcopy(cast(dict[str, Any], package.package_definition))
        profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
        for profile in profiles:
            if profile["key"] == "market_research_tools":
                profile["toolKeys"] = ["signaldeck.unknown.tool"]
        cast(list[dict[str, Any]], compiled_plan["outputSchemas"])[0]["jsonSchema"] = {
            "type": "object",
            "properties": {
                "broken": {"type": "object", "patternProperties": {".*": {"type": "string"}}}
            },
        }
        cast(list[dict[str, Any]], compiled_plan["mcpServers"]).append(
            {
                "key": "research_context",
                "name": "Research Context",
                "transport": "http-sse",
                "url": "https://mcp.example.test/sse?tools=web_search_exa",
                "headers": {"Authorization": "Bearer inline-token"},
                "query": {"exaApiKey": "inline-key"},
                "toolKeys": ["web_search_exa"],
            }
        )
        workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
        cast(list[dict[str, Any]], workflow["steps"])[0]["agents"][0]["wiring"] = {
            "ticker": {"from": "step", "stepIndex": 1, "slot": "market_report"}
        }
        package.compiled_plan = compiled_plan
        package.package_definition = package_definition
        session.commit()

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.capabilityProfiles.market_research_tools.toolKeys[0]",
        "issue": "Unknown server-declared tool 'signaldeck.unknown.tool'",
    } in errors
    assert any(
        error["field"] == "spec.outputSchemas[0].jsonSchema.properties.broken.patternProperties"
        and error["issue"] == "patternProperties is not supported"
        for error in errors
    )
    assert not any(
        str(error["field"]).startswith("spec.mcpServers.research_context") for error in errors
    )
    assert {
        "field": "spec.workflows.advisory_research.graph.steps[0].agents[0].with.ticker",
        "issue": "cycle",
    } in errors


def test_missing_api_key_is_relaxed_for_launch_metadata_but_blocks_strict_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key=None)
    created = _create_package(client)

    launch = client.get(
        f"/api/workflow-packages/{created['id']}/launch",
        params={"workflowKey": "advisory_research"},
    )

    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert launch_body["ready"] is True
    assert launch_body["blockingErrors"] == []
    launch_warnings = cast(list[dict[str, object]], launch_body["warnings"])
    assert not any(warning["issue"] == "API key is not configured" for warning in launch_warnings)

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": "advisory_research", "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert preflight_body["ready"] is False
    assert preflight_body["warnings"] == []
    errors = cast(list[dict[str, object]], preflight_body["blockingErrors"])
    api_key_errors = [error for error in errors if error["issue"] == "API key is not configured"]
    assert api_key_errors == errors
    assert api_key_errors
    assert api_key_errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "API key is not configured",
    }

    launch_create = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": {
                "ticker": "AAPL",
                "asOfDate": "2026-01-02",
                "horizonDays": 30,
                "benchmarkSymbol": "SPY",
            },
        },
    )

    assert launch_create.status_code == 422, launch_create.json()
    launch_create_body = cast(dict[str, object], launch_create.json())
    assert launch_create_body["code"] == "validation_error"
    assert launch_create_body["details"] == errors


def test_preflight_blocks_failed_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        last_test_ok=False,
        last_test_message="Connection test failed.",
    )
    created = _create_package(client)

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    assert preflight.json()["ready"] is False
    errors = preflight.json()["blockingErrors"]
    assert errors
    assert errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Connection test failed.",
    }


def _create_http_package(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def test_preflight_blocks_missing_secret_binding_for_http_node(
    client: TestClient,
) -> None:
    created = _create_http_package(client)

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'body_token' is not configured",
    } in errors
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in errors


def test_preflight_accepts_configured_secret_bindings_for_http_node(
    client: TestClient,
) -> None:
    created = _create_http_package(client)
    for key in ("body_token", "slack_webhook_token"):
        response = client.put(
            f"/api/workflow-packages/{created['id']}/secret-bindings/{key}",
            json={"value": f"{key}-secret"},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "packageId": created["id"],
            "key": key,
            "hasValue": True,
            "createdAt": response.json()["createdAt"],
            "updatedAt": response.json()["updatedAt"],
        }

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []


def test_preflight_reports_unsupported_http_method_and_malformed_step_ref(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(http_node_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
    operation = cast(list[dict[str, Any]], workflow["steps"])[0]["operations"][0]
    operation["method"] = "PATCH"
    cast(dict[str, Any], operation["request"])["body"] = {"from": "step", "stepIndex": 1}
    package = WorkflowPackage(
        id=987,
        key="http_node_package",
        name="HTTP Node Package",
        description="",
        manifest_source=http_node_package_source(),
        manifest_hash="a" * 64,
        package_definition=cast(dict[str, Any], compiled["packageDefinition"]),
        compiled_plan=compiled_plan,
        compiled_hash="b" * 64,
    )

    with session_factory() as session:
        errors = _project_blocking_diagnostics(
            WorkflowPackagePreflightService(session)._http_errors(
                package,
                compiled_plan,
            )
        )

    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].method",
        "issue": "Unsupported HTTP method 'PATCH'; allowed methods: GET, POST",
    } in errors
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request.body",
        "issue": "HTTP node step reference is malformed",
    } in errors


def _disable_finance_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )


def _disable_digital_oracle_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            DIGITAL_ORACLE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )


def test_preflight_allows_digital_oracle_toolKeys_when_finance_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _digital_oracle_phase1_package_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_finance_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": _digital_oracle_phase1_parameters()},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    assert body["warnings"] == []


def test_tradingagents_demo_uses_only_finance_owned_tool_keys() -> None:
    compiled = compile_workflow_package_manifest(_tradingagents_demo_source())
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    all_tool_keys = {
        tool_key for profile in profiles for tool_key in cast(list[str], profile["toolKeys"])
    }
    assert all_tool_keys
    assert all(tool_key.startswith("signaldeck.finance.") for tool_key in all_tool_keys)
    assert "prediction_market_tools" not in profiles_by_key
    assert "signaldeck.digital_oracle.prediction_markets.lookup" not in all_tool_keys
    assert "signaldeck.finance.prediction_markets.lookup" not in all_tool_keys


def test_preflight_tradingagents_demo_stays_ready_when_digital_oracle_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    _delete_existing_tradingagents_package(client)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _tradingagents_demo_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_digital_oracle_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={
            "workflowKey": "advisory_research",
            "parameters": {
                "ticker": "NVDA",
                "asOfDate": "2026-01-02",
                "horizonDays": 30,
                "benchmarkSymbol": "SPY",
            },
        },
    )

    assert preflight.status_code == 200, preflight.json()
    body = cast(dict[str, object], preflight.json())
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert body["ready"] is True
    assert errors == []
    assert body["warnings"] == []
    assert not any(error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY for error in errors)


def test_preflight_blocks_only_finance_market_context_toolKeys_when_finance_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        key="mixed_extension_primary_model",
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _mixed_extension_research_package_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_finance_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = cast(dict[str, object], preflight.json())
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert body["ready"] is False
    assert errors == _expected_finance_market_context_disabled_tool_errors()
    assert not any(error.get("extensionKey") == DIGITAL_ORACLE_EXTENSION_KEY for error in errors)


def test_preflight_blocks_digital_oracle_toolKeys_when_digital_oracle_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _digital_oracle_phase1_package_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_digital_oracle_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    assert body["blockingErrors"] == _expected_digital_oracle_disabled_tool_errors()


def test_preflight_blocks_only_digital_oracle_toolKeys_when_digital_oracle_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        key="mixed_extension_primary_model",
        protocol_profile="openai_chat_completions",
        capabilities=_capabilities_with_statuses(),
        last_test_ok=True,
    )
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _mixed_extension_research_package_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_digital_oracle_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": "research", "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = cast(dict[str, object], preflight.json())
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert body["ready"] is False
    assert errors == _expected_digital_oracle_disabled_tool_errors()
    assert not any(error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY for error in errors)


def test_save_allows_disabled_extension_dependency_and_preflight_blocks(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    _disable_finance_extension(session_factory)
    _delete_existing_tradingagents_package(client)

    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 201, response.json()
    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )
    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and error.get("surface") == "tool.signaldeck.finance.market_data.quote_lookup"
        for error in errors
    )


def test_preflight_blocks_tradingagents_advisory_research_when_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    _disable_finance_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and error.get("surface") == "tool.signaldeck.finance.market_data.quote_lookup"
        for error in errors
    )


def test_schedule_run_now_surfaces_digital_oracle_extension_disabled_preflight_failure(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _digital_oracle_phase1_package_source()},
    )
    assert response.status_code == 201, response.json()
    package_id = int(response.json()["id"])
    schedule = client.post(
        "/api/schedules",
        json={
            "packageId": package_id,
            "workflowKey": "research",
            "name": "Disabled extension scheduled research",
            "status": "enabled",
            "timezone": "UTC",
            "recurrence": {"type": "daily", "atLocalTime": "09:00"},
            "overlapPolicy": "skip",
            "misfirePolicy": "catchUpOne",
            "misfireGraceSeconds": 86400,
            "inputTemplate": {"researchQuestion": "{{vars.researchQuestion}}"},
            "templateVars": {"researchQuestion": "What changed in NVDA filings?"},
        },
    )
    assert schedule.status_code == 201, schedule.json()
    schedule_id = int(schedule.json()["id"])
    _disable_digital_oracle_extension(session_factory)

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={
            "idempotencyKey": "disabled-extension-retry",
            "scheduledFor": "2026-06-01T13:00:00Z",
        },
    )

    assert run_now.status_code == 422, run_now.json()
    body = run_now.json()
    assert body["code"] == "validation_error"
    details = cast(list[dict[str, object]], body["details"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == DIGITAL_ORACLE_EXTENSION_KEY
        and str(error.get("surface", "")).startswith("tool.signaldeck.")
        for error in details
    )
    with session_factory() as session:
        history = WorkflowPackageScheduleService(session).list_fire_history(schedule_id)
        assert history.total_count == 1
        failed_fire = history.items[0]
        assert failed_fire.status == "failed"
        assert failed_fire.run_id is None
        assert failed_fire.error_code == "validation_error"
        assert failed_fire.error_message == "Workflow package launch validation failed"


def _schedule_render_validation_package(session: Session) -> WorkflowPackage:
    package = WorkflowPackage(
        key="schedule_render_validation_package",
        name="Schedule Render Validation Package",
        description="Package used for scheduled input render validation.",
        manifest_source="apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n",
        manifest_hash="c" * 64,
        package_definition={
            "metadata": {
                "key": "schedule_render_validation_package",
                "name": "Schedule Render Validation Package",
            }
        },
        compiled_hash="d" * 64,
        extension_dependencies=[],
        compiled_plan={
            "workflows": [
                {
                    "key": "daily_research",
                    "inputSchema": {
                        "type": "object",
                        "required": ["asOfDate", "lookbackDays", "title"],
                        "properties": {
                            "asOfDate": {"type": "string"},
                            "lookbackDays": {"type": "integer"},
                            "title": {"type": "string"},
                        },
                    },
                }
            ]
        },
    )
    session.add(package)
    session.commit()
    session.refresh(package)
    return package


def _schedule_render_validation_due_schedule(
    package: WorkflowPackage,
    *,
    input_template: dict[str, Any],
    template_vars: dict[str, Any],
) -> DueWorkflowPackageSchedule:
    scheduled_for = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    return DueWorkflowPackageSchedule(
        id=44,
        package_id=package.id,
        package_key=package.key,
        workflow_key="daily_research",
        name="Daily research",
        timezone="America/New_York",
        recurrence={"type": "daily", "atLocalTime": "09:00"},
        next_fire_at=scheduled_for,
        overlap_policy=OverlapPolicy.SKIP,
        misfire_policy=MisfirePolicy.CATCH_UP_ONE,
        misfire_grace_seconds=86400,
        input_template=input_template,
        template_vars=template_vars,
        ends_at=None,
    )


def _schedule_render_validation_fire() -> ScheduleFireMetadata:
    scheduled_for = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    return ScheduleFireMetadata(
        schedule_id=44,
        fire_key="daily-research-2026-06-01T13:00:00Z",
        reason=FireReason.SCHEDULED,
        scheduled_for=scheduled_for,
        scheduled_local_date="2026-06-01",
        scheduled_local_time="09:00",
        scheduled_local_datetime="2026-06-01T09:00:00",
    )


def test_schedule_render_validation_preview_returns_ready_rendered_parameters(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _schedule_render_validation_package(session)
        due_schedule = _schedule_render_validation_due_schedule(
            package,
            input_template={
                "asOfDate": "{{fire.scheduledLocalDate}}",
                "lookbackDays": "{{vars.lookbackDays}}",
                "title": "Daily brief for {{fire.scheduledLocalDate}}",
            },
            template_vars={"lookbackDays": 5},
        )
        preview = WorkflowPackageScheduleService(session).preview_due_schedule_input_render(
            due_schedule,
            _schedule_render_validation_fire(),
        )

    assert preview.ready is True
    assert preview.validation_errors == []
    assert preview.rendered_parameters == {
        "asOfDate": "2026-06-01",
        "lookbackDays": 5,
        "title": "Daily brief for 2026-06-01",
    }
    assert preview.parameters_for_launch() == preview.rendered_parameters


def test_schedule_render_validation_blocks_schema_invalid_rendered_parameters(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _schedule_render_validation_package(session)
        due_schedule = _schedule_render_validation_due_schedule(
            package,
            input_template={
                "asOfDate": "{{fire.scheduledLocalDate}}",
                "lookbackDays": "lookback {{vars.lookbackDays}}",
                "title": "Daily brief for {{fire.scheduledLocalDate}}",
            },
            template_vars={"lookbackDays": 5},
        )
        preview = WorkflowPackageScheduleService(session).preview_due_schedule_input_render(
            due_schedule,
            _schedule_render_validation_fire(),
        )

    assert preview.ready is False
    assert preview.rendered_parameters["lookbackDays"] == "lookback 5"
    assert preview.validation_errors[0]["code"] == "run_invalid_input"
    assert preview.validation_errors[0]["field"] == "lookbackDays"


def test_schedule_render_validation_or_raise_blocks_missing_placeholder(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _schedule_render_validation_package(session)
        due_schedule = _schedule_render_validation_due_schedule(
            package,
            input_template={
                "asOfDate": "{{fire.scheduledLocalDate}}",
                "lookbackDays": "{{vars.lookbackDays}}",
                "title": "{{vars.missingTitle}}",
            },
            template_vars={"lookbackDays": 5},
        )
        service = WorkflowPackageScheduleService(session)
        with pytest.raises(ApiError) as exc_info:
            service.render_due_schedule_input_or_raise(
                due_schedule,
                _schedule_render_validation_fire(),
            )

    exc = exc_info.value
    assert exc.code == SCHEDULE_TEMPLATE_MISSING_VALUE
    assert exc.details == [
        {
            "field": "inputTemplate.title",
            "issue": "Missing scheduled input placeholder value for 'vars.missingTitle'",
            "code": SCHEDULE_TEMPLATE_MISSING_VALUE,
            "expression": "vars.missingTitle",
        }
    ]
