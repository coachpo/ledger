from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
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
from app.services.extension_service import ExtensionService
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from app.services.workflow_package_preflight import WorkflowPackagePreflightService
from tests.test_workflow_package_manifest_http_node import http_node_package_source

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
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
    "signaldeck.prediction_markets.lookup",
    "signaldeck.sec_filings.lookup",
    "signaldeck.market_sentiment.lookup",
)


def _package_source() -> str:
    return _FIXTURE.read_text()


def _tool_required_package_source() -> str:
    return _TOOL_REQUIRED_FIXTURE.read_text()


def _digital_oracle_researcher_demo_source() -> str:
    return _DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE.read_text()


def _expected_digital_oracle_disabled_tool_errors() -> list[dict[str, object]]:
    return [
        {
            "field": f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]",
            "issue": (
                f"Server-declared tool {tool_key!r} is disabled because extension "
                f"{FINANCE_WORKSPACE_EXTENSION_KEY!r} is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": f"tool.{tool_key}",
        }
        for index, tool_key in enumerate(sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
    ]


def _digital_oracle_phase1_package_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: digital_oracle_phase1_fixture
  name: Digital Oracle Phase 1 Fixture
  description: Deterministic package fixture for finance-owned phase-1 tools.
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
      description: Grants finance-owned phase-1 research tools.
      toolKeys:
        - signaldeck.prediction_markets.lookup
        - signaldeck.sec_filings.lookup
        - signaldeck.market_sentiment.lookup
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
      systemPrompt: Use the granted finance tools and return JSON.
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


def _mixed_capability_package_source() -> str:
    return """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: mixed_capability_fixture
  name: Mixed Capability Fixture
  description: Multi-agent fixture for scoped compatibility requirements.
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
        - signaldeck.memory.lookup
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


def _delete_existing_tradingagents_package(client: TestClient) -> None:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, object]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] != "tradingagents_advisory_research":
            continue
        deleted = client.delete(f"/api/workflow-packages/{package['id']}")
        assert deleted.status_code == 204, deleted.text
        break


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
                status="active",
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


def _seed_compatibility_fixture_connection(
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
                key="compat_fixture_tools_disabled",
                status="active",
                protocol_profile="openai_chat_completions",
                name="Compatibility Fixture: Tools Disabled",
                description="Probe fixture with tool calls disabled.",
                base_url="https://compat-fixture-tools-disabled.example.test",
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


def test_preflight_accepts_fixture_report_lookup_and_core_memory_tool_keys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_package_source())
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

    assert errors == []
    assert cast(list[str], profiles_by_key["memory_write_tools"]["toolKeys"]) == [
        "signaldeck.memory.lookup",
        "signaldeck.memory.write",
    ]
    assert cast(list[dict[str, Any]], compiled_plan["mcpServers"]) == []
    assert "fanout" not in _package_source()
    assert "kind: sequence" in _package_source()


def test_preflight_accepts_finance_server_declared_digital_oracle_toolKeys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_digital_oracle_phase1_package_source())
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}
    extension_dependencies = cast(list[dict[str, Any]], compiled["extensionDependencies"])

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

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
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surfaces": sorted(
                [
                    "hook.workflowPackageStart",
                    "provider.fallbackQuote",
                    "provider.quote",
                    "provider.socialSentiment",
                    *[f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                    *[f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                ]
            ),
            "fields": [
                "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[0]",
                "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
                "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[2]",
            ],
        }
    ]


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
        tool_errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

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
    created = client.post("/api/workflow-packages", json={"manifestSource": manifest_source})
    assert created.status_code == 201, created.json()
    preflight = client.post(
        f"/api/workflow-packages/{created.json()['id']}/preflight",
        params={"workflowKey": "research"},
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
    assert runtime_agent.key == "digital_oracle_researcher"
    assert runtime_agent.system_prompt.startswith(
        "Digital Oracle methodology is package-local for this agent."
    )
    assert runtime_agent.capability_profiles[0].tool_keys == tuple(
        sorted(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)
    )
    assert "Package-ready draft" not in manifest_source
    assert "spec.skills" not in manifest_source
    assert "secrets:" not in manifest_source


def test_preflight_rejects_duplicate_tool_keys_and_accepts_core_memory_tool_keys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    for profile in profiles:
        if profile["key"] == "memory_write_tools":
            profile["toolKeys"] = [
                "signaldeck.memory.write",
                "signaldeck.memory.write",
                "signaldeck.memory.lookup",
            ]

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

    assert errors == [
        {
            "field": "spec.capabilityProfiles.memory_write_tools.toolKeys[1]",
            "issue": "Duplicate tool key 'signaldeck.memory.write' is not allowed",
        }
    ]


def test_preflight_missing_digital_oracle_toolKeys_diagnostic_preserves_field_only_shape(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_digital_oracle_phase1_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles[0]["toolKeys"] = [
        "signaldeck.market_sentiment.lookup",
        "signaldeck.digital_oracle.missing",
        "signaldeck.sec_filings.lookup",
    ]

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

    assert errors == [
        {
            "field": "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
            "issue": "Unknown server-declared tool 'signaldeck.digital_oracle.missing'",
        }
    ]
    assert "code" not in errors[0]
    assert "surface" not in errors[0]


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
    _seed_compatibility_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
    )

    preflight = client.post("/api/workflow-packages/9101/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.capabilityProfiles.tool_required.toolKeys",
        "code": "model_capability_required_missing",
        "agentKey": "analyst",
        "modelConnectionKey": "compat_fixture_tools_disabled",
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
    _seed_compatibility_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.UNKNOWN,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNKNOWN,
        json_object_status=ModelConnectionCapabilityStatus.UNKNOWN,
    )

    preflight = client.post("/api/workflow-packages/9101/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    assert cast(list[dict[str, object]], body["warnings"]) == [
        {
            "field": "spec.capabilityProfiles.tool_required.toolKeys",
            "code": "model_capability_probe_inconclusive",
            "agentKey": "analyst",
            "modelConnectionKey": "compat_fixture_tools_disabled",
            "requirement": "nativeToolCalls",
            "issue": (
                "This workflow requires native tool calls, but support has not been " "proven yet."
            ),
            "severity": "warning",
        },
        {
            "field": "spec.outputSchemas.report.jsonSchema",
            "code": "model_capability_probe_inconclusive",
            "agentKey": "analyst",
            "modelConnectionKey": "compat_fixture_tools_disabled",
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
    _seed_compatibility_fixture_connection(
        session_factory,
        native_tool_calls_status=ModelConnectionCapabilityStatus.SUPPORTED,
        strict_json_schema_status=ModelConnectionCapabilityStatus.UNSUPPORTED,
        json_object_status=ModelConnectionCapabilityStatus.SUPPORTED,
    )

    preflight = client.post("/api/workflow-packages/9101/preflight")

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
            "modelConnectionKey": "compat_fixture_tools_disabled",
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
        params={"workflowKey": "main"},
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
    assert "unused_bad_model" not in result.model_bindings
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


def test_save_allows_missing_model_connection_and_preflight_blocks(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _delete_existing_tradingagents_package(client)
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 201, response.json()
    package_id = int(response.json()["id"])
    with session_factory() as session:
        assert session.query(WorkflowPackage).count() == 1

    preflight = client.post(f"/api/workflow-packages/{package_id}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    expected_count = _package_source().count("modelConnection: tradingagents_primary_model")
    missing_model_errors = [
        error
        for error in errors
        if error["issue"] == "Model connection 'tradingagents_primary_model' was not found"
    ]
    assert [error["field"] for error in missing_model_errors] == [
        f"spec.agents[{index}].modelConnection" for index in range(expected_count)
    ]


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
    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")
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

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

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


def test_preflight_blocks_secretless_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key=None)
    created = _create_package(client)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    assert preflight.json()["ready"] is False
    errors = preflight.json()["blockingErrors"]
    assert errors
    assert errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "API key is not configured",
    }


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

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

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

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

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

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

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
        errors = WorkflowPackagePreflightService(session)._http_errors(
            package,
            compiled_plan,
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


def test_preflight_blocks_digital_oracle_toolKeys_when_finance_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _digital_oracle_phase1_package_source()},
    )
    assert response.status_code == 201, response.json()
    _disable_finance_extension(session_factory)

    preflight = client.post(
        f"/api/workflow-packages/{response.json()['id']}/preflight?workflowKey=research"
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    assert body["blockingErrors"] == _expected_digital_oracle_disabled_tool_errors()


def test_save_allows_disabled_extension_dependency_and_preflight_blocks(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    _disable_finance_extension(session_factory)
    _delete_existing_tradingagents_package(client)

    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 201, response.json()
    preflight = client.post(f"/api/workflow-packages/{response.json()['id']}/preflight")
    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and error.get("surface") == "tool.signaldeck.market_data.quote_lookup"
        for error in errors
    )


def test_preflight_blocks_tradingagents_advisory_research_when_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    _disable_finance_extension(session_factory)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and error.get("surface") == "tool.signaldeck.market_data.quote_lookup"
        for error in errors
    )
