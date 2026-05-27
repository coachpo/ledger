from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Lock
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_fork import RunFork
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackage, WorkflowPackageRuntimeInputEntry
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.workflow_package import WorkflowPackageLaunchCreateRequest
from app.services.extension_service import ExtensionService
from app.services.model_gateway import ModelExecutionGateway
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_package_runtime_input_registry import (
    RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
    WorkflowPackageRuntimeInputRegistryService,
)
from app.services.workflow_package_runtime_inputs import (
    RUNTIME_INPUT_PAYLOAD_MAX_BYTES,
    RUNTIME_INPUT_PAYLOAD_MAX_DEPTH,
    RUNTIME_INPUT_PAYLOAD_MAX_NODES,
    RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS,
    RuntimeInputStoredMetadata,
    build_runtime_input_current_metadata,
    evaluate_runtime_input_staleness,
    runtime_input_schema_fingerprint,
    validate_runtime_input_payload_safety,
)
from app.workers.run_scheduler import scheduler_lease_owner
from tests.test_workflow_package_manifest_http_node import assert_removed_contract_tokens_absent

_DIGITAL_ORACLE_PHASE1_TOOL_KEYS = (
    "signaldeck.prediction_markets.lookup",
    "signaldeck.sec_filings.lookup",
    "signaldeck.market_sentiment.lookup",
)


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
    output_texts: list[str] | None = None
    total_tokens = 23

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
        output_texts = type(self).output_texts
        output_text = (
            output_texts[min(len(type(self).create_calls) - 1, len(output_texts) - 1)]
            if output_texts
            else type(self).output_text
        )
        return _RuntimeOpenAIResponse(
            output_text=output_text,
            total_tokens=type(self).total_tokens,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.output_text = '{"summary": "package runtime output"}'
        cls.output_texts = None
        cls.total_tokens = 23


class _RuntimeRecordingChatCompletionsClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    final_output_text = '{"summary": "package chat runtime output"}'
    return_empty_choices = False
    malformed_tool_arguments = False
    tool_argument_sequence: list[str] | None = None
    tool_name_sequence: list[str] | None = None
    reasoning_content: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.chat = self
        self.completions = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        if type(self).return_empty_choices:
            return {
                "choices": [],
                "usage": self._usage(prompt_tokens=1, completion_tokens=0),
            }
        call_index = len(type(self).create_calls)
        tool_argument_sequence = type(self).tool_argument_sequence
        should_emit_tool_call = (
            call_index <= len(tool_argument_sequence)
            if tool_argument_sequence is not None
            else call_index == 1
        )
        if should_emit_tool_call:
            tool_name_sequence = type(self).tool_name_sequence or []
            tool_name = (
                tool_name_sequence[call_index - 1]
                if call_index <= len(tool_name_sequence)
                else "signaldeck_memory_lookup"
            )
            arguments = (
                tool_argument_sequence[call_index - 1]
                if tool_argument_sequence is not None
                else (
                    "{" if type(self).malformed_tool_arguments else self._memory_lookup_arguments()
                )
            )
            call_id = (
                "call_memory_lookup"
                if tool_argument_sequence is None and tool_name == "signaldeck_memory_lookup"
                else f"call_{call_index}"
            )
            message: dict[str, Any] = {
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": arguments},
                    }
                ],
            }
            if type(self).reasoning_content is not None:
                message["reasoning_content"] = type(self).reasoning_content
            return {
                "choices": [{"message": message}],
                "usage": self._usage(prompt_tokens=7, completion_tokens=2),
            }
        return {
            "choices": [{"message": {"content": type(self).final_output_text}}],
            "usage": self._usage(prompt_tokens=11, completion_tokens=8),
        }

    @staticmethod
    def _usage(*, prompt_tokens: int, completion_tokens: int) -> dict[str, int]:
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    @staticmethod
    def _memory_lookup_arguments() -> str:
        return json.dumps(
            {
                "query": None,
                "scope": None,
                "subjectRefs": None,
                "kind": None,
                "status": None,
                "tags": None,
                "limit": 1,
                "offset": 0,
                "maxCharacters": 1000,
            },
            sort_keys=True,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.final_output_text = '{"summary": "package chat runtime output"}'
        cls.return_empty_choices = False
        cls.malformed_tool_arguments = False
        cls.tool_argument_sequence = None
        cls.tool_name_sequence = None
        cls.reasoning_content = None


class _RuntimeMalformedResponsesToolClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        return {
            "id": "resp_tool_invalid",
            "output": [
                {
                    "type": "function_call",
                    "name": "signaldeck_memory_lookup",
                    "call_id": "call_memory_lookup",
                    "arguments": "{",
                }
            ],
            "usage": {"total_tokens": 3},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


class _RuntimeRetryingResponsesToolClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        call_index = len(type(self).create_calls)
        if call_index == 1:
            arguments = "{"
        elif call_index == 2:
            arguments = _RuntimeRecordingChatCompletionsClient._memory_lookup_arguments()
        else:
            return {"id": "resp_final", "output_text": '{"summary": "responses retry output"}'}
        return {
            "id": f"resp_tool_{call_index}",
            "output": [
                {
                    "type": "function_call",
                    "name": "signaldeck_memory_lookup",
                    "call_id": f"call_{call_index}",
                    "arguments": arguments,
                }
            ],
            "usage": {"total_tokens": 3},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


class _RuntimeUsageLessResponsesClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        return {
            "id": "resp_usage_missing",
            "output_text": '{"summary": "usage omitted"}',
        }

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []


class _RuntimeReasoningRejectingChatClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.chat = self
        self.completions = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        if "reasoning_effort" in kwargs:
            raise ApiError(
                status_code=400,
                code="invalid_request_error",
                message="Unsupported reasoning fields were rejected by the provider.",
            )
        return {
            "choices": [{"message": {"content": '{"summary": "reasoning omitted"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


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


def _package_source_with_memory_lookup(*, package_key: str) -> str:
    source = _package_source(package_key=package_key)
    source = source.replace(
        "  capabilityProfiles: []\n  outputSchemas:",
        """  capabilityProfiles:
    - key: memory_context_tools
      name: Memory Context Tools
      toolKeys:
        - signaldeck.memory.lookup
  outputSchemas:""",
        1,
    )
    return source.replace(
        "      capabilityProfiles: []\n  workflows:",
        "      capabilityProfiles: [memory_context_tools]\n  workflows:",
        1,
    )


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


def _package_source_with_digital_oracle_phase1_tools(*, package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Digital Oracle Runtime Fixture
  description: Runtime fixture for finance-owned phase-1 tool grants.
spec:
  inputs:
    type: object
    properties:
      researchQuestion:
        type: string
    required: [researchQuestion]
  capabilityProfiles:
    - key: digital_oracle_phase1_tools
      name: Digital Oracle Phase 1 Tools
      toolKeys:
        - signaldeck.prediction_markets.lookup
        - signaldeck.sec_filings.lookup
        - signaldeck.market_sentiment.lookup
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
          researchQuestion:
            type: string
        required: [researchQuestion]
      outputSchema: summary_output
      capabilityProfiles: [digital_oracle_phase1_tools]
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          researchQuestion:
            type: string
        required: [researchQuestion]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          researchQuestion: ${{{{ inputs.researchQuestion }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


def _package_source_with_inline_private_mcp(*, package_key: str) -> str:
    return (
        _package_source(package_key=package_key)
        .replace(
            "  agents:\n",
            """  mcpServers:
    - key: exa
      name: Exa Web Search
      transport: http-sse
      url: https://mcp.exa.ai/mcp?tools=web_search_exa
      headers:
        Authorization: Bearer inline-header-secret
      query:
        exaApiKey: inline-query-secret
      toolKeys: [web_search_exa]
  agents:
""",
            1,
        )
        .replace(
            "      capabilityProfiles: []",
            "      capabilityProfiles: []\n      mcpServers: [exa]",
            1,
        )
    )


_PACKAGE_READ_OPERATION_FIELDS = {
    "status",
    "blockingErrors",
    "canRun",
    "health",
    "last" + "LaunchedAt",
    "lastPreflightAt",
    "preflightSummary",
    "ready",
    "validation" + "Summary",
    "warnings",
}


def _assert_package_read_is_artifact_inventory(body: dict[str, object]) -> None:
    assert _PACKAGE_READ_OPERATION_FIELDS.isdisjoint(body)


def _create_package(
    client: TestClient,
    *,
    package_key: str = "runtime_package",
) -> dict[str, object]:
    return _create_package_from_source(
        client,
        manifest_source=_package_source(package_key=package_key),
    )


def _create_package_from_source(
    client: TestClient,
    *,
    manifest_source: str,
) -> dict[str, object]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert response.status_code == 201, response.json()
    body = cast(dict[str, object], response.json())
    _assert_package_read_is_artifact_inventory(body)
    return body


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "sk-package-runtime-v1",
    connection_kind: str = "provider",
    base_url: str = "https://runtime-v1.example.com/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
    capabilities: dict[str, Any] | None = None,
    output_strategy_policy: str = "prefer_strict_schema",
    parallel_tool_calls_policy: str = "serialize",
    reasoning_policy: str = "allow",
    streaming_policy: str = "allow",
) -> None:
    with session_factory() as session:
        payload = {} if api_key is None else {"apiKey": api_key}
        session.add(
            ModelConnection(
                key="package_runtime_model",
                status="active",
                connection_kind=connection_kind,
                name="Package Runtime Model",
                description="Package runtime model binding.",
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="high",
                api_style=api_style,
                capabilities=capabilities or {},
                output_strategy_policy=output_strategy_policy,
                parallel_tool_calls_policy=parallel_tool_calls_policy,
                reasoning_policy=reasoning_policy,
                streaming_policy=streaming_policy,
                timeout_seconds=31,
                secret_payload=payload,
            )
        )
        session.commit()


def _disable_finance_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
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


def _assert_runtime_input_payload_error(payload: object, expected_issue: str) -> None:
    with pytest.raises(ApiError) as exc_info:
        _ = validate_runtime_input_payload_safety(payload)
    exc = exc_info.value
    assert exc.status_code == 422
    assert exc.code == "validation_error"
    assert exc.message == "Runtime input payload validation failed"
    assert exc.details[0]["issue"] == expected_issue


def _runtime_input_payload_over_depth_limit() -> dict[str, Any]:
    root: dict[str, Any] = {}
    current = root
    for _ in range(RUNTIME_INPUT_PAYLOAD_MAX_DEPTH):
        child: dict[str, Any] = {}
        current["child"] = child
        current = child
    return root


def _create_runtime_input_launch(
    session_factory: sessionmaker[Session],
    package_id: int,
    *,
    ticker: str,
) -> int:
    with session_factory() as session:
        launched = RunService(session, session_factory).create_workflow_package_launch(
            package_id,
            WorkflowPackageLaunchCreateRequest(
                workflow_key="runtime_workflow",
                parameters={"ticker": ticker},
            ),
        )
        return launched.id


def test_run_scheduler_locked_settings_defaults_and_lease_owner_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in (
        "RUN_SCHEDULER_MAX_ACTIVE_RUNS",
        "RUN_SCHEDULER_MAX_ACTIVE_PER_PACKAGE",
        "RUN_SCHEDULER_POLL_INTERVAL_SECONDS",
        "RUN_SCHEDULER_HEARTBEAT_SECONDS",
        "RUN_SCHEDULER_LEASE_TTL_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings.model_validate({})

    assert settings.run_scheduler_max_active_runs == 4
    assert settings.run_scheduler_max_active_per_package == 1
    assert settings.run_scheduler_poll_interval_seconds == 1.0
    assert settings.run_scheduler_heartbeat_seconds == 10.0
    assert settings.run_scheduler_lease_ttl_seconds == 60.0
    assert scheduler_lease_owner(hostname="test-host", pid=1234, slot=2) == (
        "scheduler:test-host:1234:2"
    )


def test_workflow_package_launch_enqueues_without_request_worker(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="enqueue_only_worker_boundary_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    time.sleep(0.1)
    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "queued"
        assert run.attempt_count == 0
        assert run.last_claimed_at is None
        assert run.lease_owner is None
        assert run.lease_expires_at is None
        assert run.heartbeat_at is None
    assert _RuntimeRecordingOpenAIClient.create_calls == []


def test_run_queue_stale_lease_recovery_frees_serial_worker_lane(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="stale_lease_worker_lane_package")
    launch_payload = {"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}}
    first = client.post(f"/api/workflow-packages/{created['id']}/launches", json=launch_payload)
    second = client.post(f"/api/workflow-packages/{created['id']}/launches", json=launch_payload)
    assert first.status_code == 201, first.json()
    assert second.status_code == 201, second.json()
    first_run_id = int(first.json()["id"])
    second_run_id = int(second.json()["id"])

    first_worker = scheduler_lease_owner(hostname="test-host", pid=100, slot=1)
    second_worker = scheduler_lease_owner(hostname="test-host", pid=100, slot=2)

    with session_factory() as session:
        claimed_id = RunQueueService(
            session,
            session_factory,
            lease_owner=first_worker,
            lease_ttl_seconds=1.0,
        ).claim_next_run()
        assert claimed_id == first_run_id

    expired_at = utcnow() - timedelta(seconds=5)
    with session_factory() as session:
        blocked = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).claim_next_run()
        assert blocked is None
        running = session.get(Run, first_run_id)
        assert running is not None
        running.lease_expires_at = expired_at
        running.heartbeat_at = expired_at
        session.commit()

    recovered_at = utcnow()
    with session_factory() as session:
        recovered = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).recover_stale_leases(now=recovered_at)
        assert recovered == 1

    with session_factory() as session:
        next_claim = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).claim_next_run()
        assert next_claim == second_run_id
        recovered_run = session.get(Run, first_run_id)
        assert recovered_run is not None
        assert recovered_run.status == "failed"
        assert recovered_run.lease_owner is None
        assert "scheduler lease expired" in str(recovered_run.error)


def test_runtime_input_payload_validation_accepts_schema_agnostic_object_and_launch_still_validates(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_payload_validation_package")
    payload = {"unexpected": {"still": ["safe", "json", "object"]}}

    assert validate_runtime_input_payload_safety(payload) == payload

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": payload},
    )
    assert launch.status_code == 400, launch.json()
    assert launch.json()["code"] == "run_invalid_input"


@pytest.mark.parametrize("payload", [None, [], "ticker", 7, True])
def test_runtime_input_payload_validation_rejects_non_object_json(payload: object) -> None:
    _assert_runtime_input_payload_error(payload, "Payload must be a JSON object")


def test_runtime_input_payload_validation_rejects_size_depth_and_structural_limits() -> None:
    _assert_runtime_input_payload_error(
        {"blob": "x" * RUNTIME_INPUT_PAYLOAD_MAX_BYTES},
        f"Payload must serialize to at most {RUNTIME_INPUT_PAYLOAD_MAX_BYTES} bytes",
    )
    _assert_runtime_input_payload_error(
        _runtime_input_payload_over_depth_limit(),
        f"Payload nesting depth must be at most {RUNTIME_INPUT_PAYLOAD_MAX_DEPTH}",
    )
    _assert_runtime_input_payload_error(
        {"items": [0] * RUNTIME_INPUT_PAYLOAD_MAX_NODES},
        f"Payload may contain at most {RUNTIME_INPUT_PAYLOAD_MAX_NODES} JSON nodes",
    )
    _assert_runtime_input_payload_error(
        {f"k{index}": index for index in range(RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS + 1)},
        f"Payload objects may contain at most {RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS} keys",
    )


def test_runtime_input_stale_metadata_is_explanatory_and_entries_stay_loadable(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_stale_metadata_package")
    package_id = cast(int, created["id"])
    payload = {"unexpected": {"saved": True}}

    assert runtime_input_schema_fingerprint({"b": 2, "a": 1}) == runtime_input_schema_fingerprint(
        {"a": 1, "b": 2}
    )

    with session_factory() as session:
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        current = build_runtime_input_current_metadata(
            workflow_key="runtime_workflow",
            manifest_hash=package.manifest_hash,
            compiled_hash=package.compiled_hash,
            compiled_plan=package.compiled_plan,
        )
        assert current is not None
        entry = WorkflowPackageRuntimeInputEntry(
            package_id=package.id,
            workflow_key=current.workflow_key,
            owner_type="local_user",
            owner_id="default",
            slot="personal",
            name="Stale but loadable",
            payload=validate_runtime_input_payload_safety(payload),
            source_kind="manual",
            manifest_hash=current.manifest_hash,
            compiled_hash=current.compiled_hash,
            schema_fingerprint=current.schema_fingerprint,
            input_schema_snapshot=current.input_schema,
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id

        changed_schema = {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "horizonDays": {"type": "integer"},
            },
            "required": ["ticker", "horizonDays"],
        }
        changed_workflows: list[dict[str, Any]] = []
        for workflow in cast(list[dict[str, Any]], package.compiled_plan["workflows"]):
            next_workflow = dict(workflow)
            if next_workflow.get("key") == "runtime_workflow":
                next_workflow["inputSchema"] = changed_schema
            changed_workflows.append(next_workflow)
        changed_plan = dict(package.compiled_plan)
        changed_plan["workflows"] = changed_workflows
        package.compiled_plan = changed_plan
        package.manifest_hash = "d" * 64
        package.compiled_hash = "e" * 64
        session.commit()

        loaded = session.get(WorkflowPackageRuntimeInputEntry, entry_id)
        assert loaded is not None
        refreshed_package = session.get(WorkflowPackage, package_id)
        assert refreshed_package is not None
        current_after_drift = build_runtime_input_current_metadata(
            workflow_key=loaded.workflow_key,
            manifest_hash=refreshed_package.manifest_hash,
            compiled_hash=refreshed_package.compiled_hash,
            compiled_plan=refreshed_package.compiled_plan,
        )
        assert current_after_drift is not None
        stored = RuntimeInputStoredMetadata(
            workflow_key=loaded.workflow_key,
            manifest_hash=loaded.manifest_hash,
            compiled_hash=loaded.compiled_hash,
            schema_fingerprint=loaded.schema_fingerprint,
        )
        evaluation = evaluate_runtime_input_staleness(stored, current_after_drift)

        assert evaluation.to_payload()["stale"] is True
        assert [reason["field"] for reason in evaluation.reasons] == [
            "manifestHash",
            "compiledHash",
            "schemaFingerprint",
        ]
        assert loaded.payload == payload
        assert validate_runtime_input_payload_safety(loaded.payload) == payload

        loaded.payload = {"stillArbitrary": {"afterStale": True}}
        session.commit()
        session.expire_all()
        reloaded = session.get(WorkflowPackageRuntimeInputEntry, entry_id)
        assert reloaded is not None
        assert reloaded.payload == {"stillArbitrary": {"afterStale": True}}

        missing_workflow = evaluate_runtime_input_staleness(stored, None)
        assert missing_workflow.to_payload() == {
            "stale": True,
            "reasons": [
                {
                    "field": "workflowKey",
                    "issue": "Saved workflow is no longer present in the current package",
                    "stored": "runtime_workflow",
                    "current": None,
                }
            ],
        }


def test_runtime_input_service_limits(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_service_limits_package")
    package_id = cast(int, created["id"])

    with session_factory() as session:
        service = WorkflowPackageRuntimeInputRegistryService(session)
        personal_entries = [
            service.create_personal_entry(
                package_id,
                "runtime_workflow",
                name="Duplicate preset name",
                payload={"ticker": f"TICKER{index}"},
            )
            for index in range(RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT)
        ]

        assert len({entry.id for entry in personal_entries}) == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT
        assert all(entry.name == "Duplicate preset name" for entry in personal_entries)
        assert all(entry.slot == "personal" for entry in personal_entries)
        assert all(
            entry.stale.to_payload() == {"stale": False, "reasons": []}
            for entry in personal_entries
        )

        with pytest.raises(ApiError) as exc_info:
            _ = service.create_personal_entry(
                package_id,
                "runtime_workflow",
                name="Overflow preset",
                payload={"ticker": "OVERFLOW"},
            )
        exc = exc_info.value
        assert exc.status_code == 409
        assert exc.code == "workflow_package_runtime_input_personal_limit_reached"
        assert exc.details == [
            {
                "field": "personal",
                "issue": "Personal runtime input entries are limited to 20 per scope",
                "limit": RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
                "actual": RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
            }
        ]
        registry_after_limit = service.list_registry(package_id, "runtime_workflow")
        assert registry_after_limit.owner_type == "local_user"
        assert registry_after_limit.owner_id == "default"
        assert len(registry_after_limit.personal) == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT
        assert registry_after_limit.history == []
        assert not hasattr(service, "append_history_entry")


def test_runtime_input_service_personal_cap_uses_scope_lock_for_concurrent_creates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_personal_lock_package")
    package_id = cast(int, created["id"])
    with session_factory() as session:
        service = WorkflowPackageRuntimeInputRegistryService(session)
        for index in range(RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT - 1):
            _ = service.create_personal_entry(
                package_id,
                "runtime_workflow",
                name="Existing preset",
                payload={"ticker": f"EXISTING{index:02d}"},
            )

    first_create_started = Event()
    first_create_can_continue = Event()
    delay_lock = Lock()
    delayed_once = False
    original_create = WorkflowPackageRepository.create_runtime_input_personal_entry

    def delayed_create(
        self: WorkflowPackageRepository,
        *args: Any,
        **kwargs: Any,
    ) -> WorkflowPackageRuntimeInputEntry:
        nonlocal delayed_once
        should_delay = False
        with delay_lock:
            if not delayed_once:
                delayed_once = True
                should_delay = True
        if should_delay:
            first_create_started.set()
            assert first_create_can_continue.wait(timeout=5)
        return original_create(self, *args, **kwargs)

    monkeypatch.setattr(
        WorkflowPackageRepository,
        "create_runtime_input_personal_entry",
        delayed_create,
    )

    def create_concurrent_personal(ticker: str) -> tuple[str, int | str]:
        with session_factory() as session:
            try:
                entry = WorkflowPackageRuntimeInputRegistryService(session).create_personal_entry(
                    package_id,
                    "runtime_workflow",
                    name="Concurrent preset",
                    payload={"ticker": ticker},
                )
            except ApiError as exc:
                return ("error", exc.code)
            return ("created", entry.id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_concurrent_personal, "LOCK_A")
        assert first_create_started.wait(timeout=5)
        second = executor.submit(create_concurrent_personal, "LOCK_B")
        try:
            time.sleep(0.2)
            assert not second.done()
        finally:
            first_create_can_continue.set()
        results = [first.result(timeout=5), second.result(timeout=5)]

    assert sorted(result[0] for result in results) == ["created", "error"]
    assert ("error", "workflow_package_runtime_input_personal_limit_reached") in results
    with session_factory() as session:
        registry = WorkflowPackageRuntimeInputRegistryService(session).list_registry(
            package_id,
            "runtime_workflow",
        )
        assert len(registry.personal) == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT


def test_runtime_input_service_schema_deferred(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(
        client,
        package_key="runtime_input_service_schema_deferred_package",
    )
    package_id = cast(int, created["id"])
    schema_agnostic_payload = {"unexpected": {"still": ["safe", "json", "object"]}}

    with session_factory() as session:
        service = WorkflowPackageRuntimeInputRegistryService(session)
        created_entry = service.create_personal_entry(
            package_id,
            "runtime_workflow",
            name="Schema agnostic preset",
            payload=schema_agnostic_payload,
        )
        assert created_entry.payload == schema_agnostic_payload
        assert created_entry.stale.to_payload() == {"stale": False, "reasons": []}

        updated_entry = service.update_personal_entry(
            package_id,
            "runtime_workflow",
            created_entry.id,
            payload={"stillArbitrary": {"afterUpdate": True}},
        )
        assert updated_entry.payload == {"stillArbitrary": {"afterUpdate": True}}
        assert updated_entry.stale.stale is False

        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        changed_schema = {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "horizonDays": {"type": "integer"},
            },
            "required": ["ticker", "horizonDays"],
        }
        changed_workflows: list[dict[str, Any]] = []
        for workflow in cast(list[dict[str, Any]], package.compiled_plan["workflows"]):
            next_workflow = dict(workflow)
            if next_workflow.get("key") == "runtime_workflow":
                next_workflow["inputSchema"] = changed_schema
            changed_workflows.append(next_workflow)
        changed_plan = dict(package.compiled_plan)
        changed_plan["workflows"] = changed_workflows
        package.compiled_plan = changed_plan
        package.manifest_hash = "f" * 64
        package.compiled_hash = "0" * 64
        session.commit()

        registry_after_drift = service.list_registry(package_id, "runtime_workflow")
        [stale_entry] = registry_after_drift.personal
        assert stale_entry.stale.stale is True
        assert [reason["field"] for reason in stale_entry.stale.reasons] == [
            "manifestHash",
            "compiledHash",
            "schemaFingerprint",
        ]

        renamed_entry = service.update_personal_entry(
            package_id,
            "runtime_workflow",
            created_entry.id,
            name="Renamed stale preset",
        )
        assert renamed_entry.name == "Renamed stale preset"
        assert renamed_entry.stale.stale is True

        resaved_entry = service.update_personal_entry(
            package_id,
            "runtime_workflow",
            created_entry.id,
            payload={"noTicker": True},
        )
        assert resaved_entry.payload == {"noTicker": True}
        assert resaved_entry.stale.to_payload() == {"stale": False, "reasons": []}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"noTicker": True}},
    )
    assert launch.status_code == 400, launch.json()
    assert launch.json()["code"] == "run_invalid_input"


def test_runtime_input_registry_api_contract_and_personal_mutations(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_registry_api_package")
    package_id = cast(int, created["id"])

    empty = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert empty.status_code == 200, empty.json()
    empty_body = cast(dict[str, Any], empty.json())
    assert empty_body["packageId"] == package_id
    assert empty_body["packageKey"] == "runtime_input_registry_api_package"
    assert empty_body["workflowKey"] == "runtime_workflow"
    assert "ownerType" not in empty_body
    assert "ownerId" not in empty_body
    current_metadata = cast(dict[str, Any], empty_body["currentMetadata"])
    assert current_metadata["workflowKey"] == "runtime_workflow"
    assert current_metadata["inputSchema"]["required"] == ["ticker"]
    assert empty_body["personal"] == []
    assert empty_body["history"] == []

    created_entry = client.post(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "  Morning preset  ", "payload": {"unexpected": {"saved": True}}},
    )
    assert created_entry.status_code == 201, created_entry.json()
    created_entry_body = cast(dict[str, Any], created_entry.json())
    entry_id = int(created_entry_body["id"])
    assert created_entry_body["packageId"] == package_id
    assert created_entry_body["workflowKey"] == "runtime_workflow"
    assert created_entry_body["slot"] == "personal"
    assert created_entry_body["name"] == "Morning preset"
    assert created_entry_body["payload"] == {"unexpected": {"saved": True}}
    assert created_entry_body["sourceKind"] == "manual"
    assert created_entry_body["sourceRunId"] is None
    assert created_entry_body["inputSchemaSnapshot"]["required"] == ["ticker"]
    assert created_entry_body["stale"] == {"stale": False, "reasons": []}
    assert "ownerType" not in created_entry_body
    assert "ownerId" not in created_entry_body

    invalid_payload = client.post(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "Not an object", "payload": []},
    )
    assert invalid_payload.status_code == 422, invalid_payload.json()
    invalid_body = invalid_payload.json()
    assert invalid_body["code"] == "validation_error"
    assert invalid_body["message"] == "Runtime input payload validation failed"
    assert invalid_body["details"] == [
        {"field": "payload", "issue": "Payload must be a JSON object"}
    ]

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "HIST"}},
    )
    assert launch.status_code == 201, launch.json()
    source_run_id = int(launch.json()["id"])

    registry = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert registry.status_code == 200, registry.json()
    registry_body = cast(dict[str, Any], registry.json())
    personal = cast(list[dict[str, Any]], registry_body["personal"])
    history = cast(list[dict[str, Any]], registry_body["history"])
    [history_entry] = history
    history_id = int(history_entry["id"])
    assert [entry["id"] for entry in personal] == [entry_id]
    assert history_entry["slot"] == "history"
    assert history_entry["name"] is None
    assert history_entry["sourceKind"] == "launch"
    assert history_entry["sourceRunId"] == source_run_id
    assert history_entry["payload"] == {"ticker": "HIST"}

    history_update = client.patch(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{history_id}",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "History must stay immutable"},
    )
    assert history_update.status_code == 404, history_update.json()

    updated = client.patch(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{entry_id}",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "Renamed preset", "payload": {"stillArbitrary": True}},
    )
    assert updated.status_code == 200, updated.json()
    updated_body = cast(dict[str, Any], updated.json())
    assert updated_body["id"] == entry_id
    assert updated_body["name"] == "Renamed preset"
    assert updated_body["payload"] == {"stillArbitrary": True}
    assert updated_body["stale"] == {"stale": False, "reasons": []}

    deleted = client.delete(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{entry_id}",
        params={"workflowKey": "runtime_workflow"},
    )
    assert deleted.status_code == 204, deleted.text

    history_delete = client.delete(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{history_id}",
        params={"workflowKey": "runtime_workflow"},
    )
    assert history_delete.status_code == 404, history_delete.json()

    after_delete = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert after_delete.status_code == 200, after_delete.json()
    after_delete_body = cast(dict[str, Any], after_delete.json())
    assert after_delete_body["personal"] == []
    assert len(cast(list[dict[str, Any]], after_delete_body["history"])) == 1

    with session_factory() as session:
        service = WorkflowPackageRuntimeInputRegistryService(session)
        for index in range(RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT):
            _ = service.create_personal_entry(
                package_id,
                "runtime_workflow",
                name="Duplicate API preset",
                payload={"ticker": f"CAP{index}"},
            )

    overflow = client.post(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "Overflow", "payload": {"ticker": "OVERFLOW"}},
    )
    assert overflow.status_code == 409, overflow.json()
    overflow_body = overflow.json()
    assert overflow_body["code"] == "workflow_package_runtime_input_personal_limit_reached"
    assert overflow_body["details"] == [
        {
            "field": "personal",
            "issue": "Personal runtime input entries are limited to 20 per scope",
            "limit": RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
            "actual": RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
        }
    ]


def test_runtime_input_registry_api_allows_duplicate_personal_names_as_distinct_ids(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_duplicate_names_package")
    package_id = cast(int, created["id"])
    endpoint = f"/api/workflow-packages/{package_id}/runtime-input-registry/personal"
    params = {"workflowKey": "runtime_workflow"}

    first = client.post(
        endpoint,
        params=params,
        json={"name": "Morning preset", "payload": {"ticker": "AAPL"}},
    )
    second = client.post(
        endpoint,
        params=params,
        json={"name": "Morning preset", "payload": {"ticker": "MSFT"}},
    )

    assert first.status_code == 201, first.json()
    assert second.status_code == 201, second.json()
    first_body = cast(dict[str, Any], first.json())
    second_body = cast(dict[str, Any], second.json())
    assert first_body["id"] != second_body["id"]
    assert first_body["name"] == second_body["name"] == "Morning preset"

    registry = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params=params,
    )
    assert registry.status_code == 200, registry.json()
    personal = cast(list[dict[str, Any]], registry.json()["personal"])
    assert [entry["id"] for entry in personal] == [second_body["id"], first_body["id"]]
    assert [entry["payload"] for entry in personal] == [
        {"ticker": "MSFT"},
        {"ticker": "AAPL"},
    ]

    deleted = client.delete(
        f"{endpoint}/{first_body['id']}",
        params=params,
    )
    assert deleted.status_code == 204, deleted.text

    after_delete = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params=params,
    )
    assert after_delete.status_code == 200, after_delete.json()
    remaining = cast(list[dict[str, Any]], after_delete.json()["personal"])
    assert [entry["id"] for entry in remaining] == [second_body["id"]]
    assert remaining[0]["name"] == "Morning preset"


def test_runtime_input_registry_stale_workflow_read_remains_available(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_registry_stale_package")
    package_id = cast(int, created["id"])

    with session_factory() as session:
        service = WorkflowPackageRuntimeInputRegistryService(session)
        personal_entry = service.create_personal_entry(
            package_id,
            "runtime_workflow",
            name="Removed workflow preset",
            payload={"ticker": "MSFT"},
        )
        personal_id = personal_entry.id

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AAPL"}},
    )
    assert launch.status_code == 201, launch.json()
    [history_entry] = _runtime_input_history_entries(client, package_id)
    history_id = int(history_entry["id"])

    with session_factory() as session:
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        changed_plan = dict(package.compiled_plan)
        changed_plan["workflows"] = []
        package.compiled_plan = changed_plan
        package.manifest_hash = "a" * 64
        package.compiled_hash = "b" * 64
        session.commit()

    stale_read = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert stale_read.status_code == 200, stale_read.json()
    stale_body = cast(dict[str, Any], stale_read.json())
    assert stale_body["packageId"] == package_id
    assert stale_body["workflowKey"] == "runtime_workflow"
    assert stale_body["currentMetadata"] is None
    assert "ownerType" not in stale_body
    assert "ownerId" not in stale_body
    personal = cast(list[dict[str, Any]], stale_body["personal"])
    history = cast(list[dict[str, Any]], stale_body["history"])
    assert [entry["id"] for entry in personal] == [personal_id]
    assert [entry["id"] for entry in history] == [history_id]
    expected_stale = {
        "stale": True,
        "reasons": [
            {
                "field": "workflowKey",
                "issue": "Saved workflow is no longer present in the current package",
                "stored": "runtime_workflow",
                "current": None,
            }
        ],
    }
    assert personal[0]["stale"] == expected_stale
    assert history[0]["stale"] == expected_stale
    assert personal[0]["payload"] == {"ticker": "MSFT"}
    assert history[0]["payload"] == {"ticker": "AAPL"}

    renamed = client.patch(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{personal_id}",
        params={"workflowKey": "runtime_workflow"},
        json={"name": "Renamed removed workflow preset"},
    )
    assert renamed.status_code == 200, renamed.json()
    renamed_body = cast(dict[str, Any], renamed.json())
    assert renamed_body["name"] == "Renamed removed workflow preset"
    assert renamed_body["stale"] == expected_stale

    deleted = client.delete(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal/{personal_id}",
        params={"workflowKey": "runtime_workflow"},
    )
    assert deleted.status_code == 204, deleted.text

    after_delete = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert after_delete.status_code == 200, after_delete.json()
    after_delete_body = cast(dict[str, Any], after_delete.json())
    assert after_delete_body["currentMetadata"] is None
    assert after_delete_body["personal"] == []
    assert cast(list[dict[str, Any]], after_delete_body["history"])[0]["id"] == history_id


def test_runtime_input_registry_openapi_contract_is_scope_safe(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.json()
    openapi = cast(dict[str, Any], response.json())
    components = cast(dict[str, Any], openapi["components"])
    paths = cast(dict[str, dict[str, Any]], openapi["paths"])
    schemas = cast(dict[str, dict[str, Any]], components["schemas"])

    registry_path = "/api/workflow-packages/{package_id}/runtime-input-registry"
    personal_path = "/api/workflow-packages/{package_id}/runtime-input-registry/personal"
    personal_item_path = f"{personal_path}/{{entry_id}}"
    assert registry_path in paths
    assert personal_path in paths
    assert personal_item_path in paths
    assert f"{registry_path}/history" not in paths
    assert f"{registry_path}/history/{{entry_id}}" not in paths

    for path, method in (
        (registry_path, "get"),
        (personal_path, "post"),
        (personal_item_path, "patch"),
        (personal_item_path, "delete"),
    ):
        operation = cast(dict[str, Any], paths[path][method])
        parameters = cast(list[dict[str, Any]], operation.get("parameters") or [])
        parameter_names = {str(parameter["name"]) for parameter in parameters}
        assert {"package_id", "workflowKey"} <= parameter_names
        assert {"ownerType", "ownerId", "slot"}.isdisjoint(parameter_names)

    registry_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageRuntimeInputRegistryRead"]["properties"],
    )
    entry_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageRuntimeInputEntryRead"]["properties"],
    )
    create_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageRuntimeInputPersonalEntryCreateRequest"]["properties"],
    )
    update_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageRuntimeInputPersonalEntryUpdateRequest"]["properties"],
    )

    assert set(registry_properties) == {
        "packageId",
        "packageKey",
        "workflowKey",
        "currentMetadata",
        "personal",
        "history",
    }
    assert {"ownerType", "ownerId"}.isdisjoint(entry_properties)
    assert set(create_properties) == {"name", "payload"}
    assert set(update_properties) == {"name", "payload"}

    workflow_package_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageRead"]["properties"],
    )
    manifest_properties = cast(
        dict[str, Any],
        schemas["WorkflowPackageManifestRead"]["properties"],
    )
    assert "runtimeInputRegistry" not in workflow_package_properties
    assert "runtimeInputRegistry" not in manifest_properties


def test_workflow_package_read_contract_is_artifact_inventory_and_launch_keeps_live_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_read_contract_package")
    package_id = cast(int, created["id"])

    detail = client.get(f"/api/workflow-packages/{package_id}")
    assert detail.status_code == 200, detail.json()
    detail_body = cast(dict[str, object], detail.json())
    _assert_package_read_is_artifact_inventory(detail_body)
    assert_removed_contract_tokens_absent(detail_body, context="package detail")

    package_list = client.get("/api/workflow-packages")
    assert package_list.status_code == 200, package_list.json()
    list_body = cast(dict[str, object], package_list.json())
    items = cast(list[dict[str, object]], list_body["items"])
    [listed] = [item for item in items if item["id"] == package_id]
    _assert_package_read_is_artifact_inventory(listed)
    assert_removed_contract_tokens_absent(listed, context="package list item")

    launch = client.get(
        f"/api/workflow-packages/{package_id}/launch",
        params={"workflowKey": "runtime_workflow"},
    )
    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert {"ready", "blockingErrors", "warnings"} <= set(launch_body)
    assert_removed_contract_tokens_absent(launch_body, context="launch readiness")

    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        params={"workflowKey": "runtime_workflow"},
    )
    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert {"ready", "blockingErrors", "warnings"} <= set(preflight_body)
    assert_removed_contract_tokens_absent(preflight_body, context="preflight readiness")


def test_workflow_package_launch_rejects_unknown_root_parameter_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_unknown_root_package")

    response = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "unexpected": True},
        },
    )

    assert response.status_code == 400, response.json()
    body = response.json()
    assert body["code"] == "run_invalid_input"
    assert body["details"] == [{"field": "unexpected", "issue": "Extra inputs are not permitted"}]
    with session_factory() as session:
        assert session.query(Run).count() == 0


def test_workflow_package_launch_rejects_unknown_nested_parameter_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    original_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    nested_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "          context:\n"
        "            type: object\n"
        "            properties:\n"
        "              sector:\n"
        "                type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    manifest_source = _package_source(package_key="runtime_unknown_nested_package").replace(
        original_input_schema,
        nested_input_schema,
        1,
    )
    created_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert created_response.status_code == 201, created_response.json()
    created = cast(dict[str, object], created_response.json())

    response = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {
                "ticker": "MSFT",
                "context": {"sector": "semiconductors", "unexpected": True},
            },
        },
    )

    assert response.status_code == 400, response.json()
    body = response.json()
    assert body["code"] == "run_invalid_input"
    assert body["details"] == [
        {"field": "context.unexpected", "issue": "Extra inputs are not permitted"}
    ]
    with session_factory() as session:
        assert session.query(Run).count() == 0


def test_workflow_package_launch_executes_with_live_model_connection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package live runtime output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    gateway_calls: list[str] = []
    original_gateway_invoke = ModelExecutionGateway.invoke

    def _recording_gateway_invoke(
        self: ModelExecutionGateway,
        request: Any,
        *,
        tool_executor: Any,
    ) -> Any:
        gateway_calls.append(request.agent_key)
        return original_gateway_invoke(self, request, tool_executor=tool_executor)

    monkeypatch.setattr(
        "app.services.model_gateway.ModelExecutionGateway.invoke",
        _recording_gateway_invoke,
    )

    _seed_model_connection(session_factory)
    created = _create_package(client)
    package_id = cast(int, created["id"])

    with session_factory() as session:
        package_before_launch = session.get(WorkflowPackage, package_id)
        assert package_before_launch is not None
        package_updated_at_before_launch = package_before_launch.updated_at
        removed_launch_column = "_".join(("last", "launched", "at"))
        assert not hasattr(package_before_launch, removed_launch_column)
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-v2.example.com/v1"
        connection.model_id = "gpt-package-v2"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "sk-package-runtime-v2"}
        session.commit()

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    assert_removed_contract_tokens_absent(launch.json(), context="launch response")
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        package_after_launch = session.get(WorkflowPackage, package_id)
        assert package_after_launch is not None
        assert package_after_launch.updated_at == package_updated_at_before_launch
        assert not hasattr(package_after_launch, removed_launch_column)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert snapshot is not None
        assert snapshot.workflow_package_key == "runtime_package"
        assert snapshot.workflow_key == "runtime_workflow"
        assert snapshot.launch_parameters == {"ticker": "MSFT"}

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)
    assert_removed_contract_tokens_absent(detail, context="run detail")

    assert detail["status"] == "succeeded"
    assert detail["targetKind"] == "workflowPackage"
    assert detail["targetId"] == created["id"]
    assert detail["targetKey"] == "runtime_package"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert_removed_contract_tokens_absent(provenance, context="package provenance")
    assert provenance["workflowPackageKey"] == "runtime_package"
    assert provenance["workflowKey"] == "runtime_workflow"
    assert "workflowPackageVersion" not in provenance
    assert provenance["launchSnapshot"]["parameters"] == {"ticker": "MSFT"}
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["agentRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "package_analyst",
        "version": 1,
    }
    assert invocation["outputSchemaRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "summary_output",
        "version": 1,
    }
    assert "agentId" not in invocation
    assert "outputSchemaId" not in invocation
    assert detail["finalOutput"] == {"summary": "package live runtime output"}
    assert detail["executedTokens"] == 23
    assert gateway_calls == ["package_analyst"]
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["usage"] == {"totalTokens": 23}
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "enabled",
        "reasoningEffort": "low",
        "streamingStrategy": "disabled",
    }
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-package-runtime-v2",
        "base_url": "https://runtime-v2.example.com/v1",
        "timeout": 91.0,
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-package-v2"
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["reasoning"] == {"effort": "low"}

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert snapshot is not None
        assert run.workflow_package_key == "runtime_package"
        assert run.workflow_package_workflow_key == "runtime_workflow"
        assert snapshot.manifest_hash == package.manifest_hash
        assert snapshot.compiled_hash == package.compiled_hash
        assert snapshot.workflow_key == "runtime_workflow"
        assert snapshot.launch_parameters == {"ticker": "MSFT"}
        assert snapshot.resolved_model_connections[0]["modelId"] == "gpt-package-v2"
        assert session.query(Agent).count() == 0
        assert session.query(Workflow).count() == 0
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert invocation.agent_id == 1
        assert invocation.agent_key == "package_analyst"
        assert invocation.output_schema_id == 1
        assert invocation.output == {"summary": "package live runtime output"}


def test_workflow_package_runtime_strict_json_schema_strategy_sends_native_schema(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "strict schema output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_strict_schema_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "strict schema output"}
    text_format = _RuntimeRecordingOpenAIClient.create_calls[-1]["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert text_format["schema"]["properties"]["summary"]["type"] == "string"


def test_workflow_package_runtime_forbidden_reasoning_and_streaming_policies_record_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "policy output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        reasoning_policy="forbid",
        streaming_policy="forbid",
    )
    created = _create_package(client, package_key="runtime_policy_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "disabledByPolicy",
        "streamingStrategy": "disabledByPolicy",
    }
    assert gateway_metadata["usage"] == {"totalTokens": 23}
    assert "reasoning" not in _RuntimeRecordingOpenAIClient.create_calls[-1]
    assert detail["finalOutput"] == {"summary": "policy output"}


def test_workflow_package_runtime_reasoning_unsupported_is_normalized_before_provider_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeReasoningRejectingChatClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeReasoningRejectingChatClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        capabilities={
            "reasoningHints": {"status": "unsupported"},
        },
    )
    created = _create_package(client, package_key="runtime_reasoning_unsupported_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_reasoning_unsupported"
    assert invocation["errorDetails"][0]["field"] == "reasoningHints"
    assert _RuntimeReasoningRejectingChatClient.create_calls == []


def test_workflow_package_runtime_missing_usage_metadata_stays_secret_safe_and_successful(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeUsageLessResponsesClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeUsageLessResponsesClient)

    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_usage_missing_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "usage omitted"}
    assert detail["executedTokens"] == 0
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["usage"] == {"totalTokens": 0}
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "enabled",
        "reasoningEffort": "high",
        "streamingStrategy": "disabled",
    }


def test_workflow_package_runtime_json_object_validation_retries_once_and_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        '{"notSummary": "invalid"}',
        '{"summary": "json fallback corrected output"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "unsupported"},
            "jsonObjectOutput": {"status": "supported"},
        },
        output_strategy_policy="allow_json_object_validation",
    )
    created = _create_package(client, package_key="runtime_json_validation_retry_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "json fallback corrected output"}
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 2
    assert _RuntimeRecordingOpenAIClient.create_calls[0]["text"] == {
        "format": {"type": "json_object"}
    }
    assert "server-side schema validation" in _RuntimeRecordingOpenAIClient.create_calls[1]["input"]


def test_workflow_package_runtime_json_object_validation_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        '{"notSummary": "invalid"}',
        '{"stillWrong": "invalid"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "unsupported"},
            "jsonObjectOutput": {"status": "supported"},
        },
        output_strategy_policy="allow_json_object_validation",
    )
    created = _create_package(client, package_key="runtime_json_validation_exhausted_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "model_output_retry_exhausted"
    assert invocation["errorDetails"][0]["field"] == "summary"
    assert (
        cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]["selectedStrategies"][
            "outputStrategy"
        ]
        == "jsonObjectWithValidation"
    )
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 2


def test_workflow_package_runtime_chat_completions_adapter_executes_tool_calls_and_usage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.reasoning_content = "preserved thinking trace"
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        model_id="chat-runtime-model",
        api_style="chat_completions",
    )
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(package_key="runtime_chat_tool_package"),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "package chat runtime output"}
    assert detail["executedTokens"] == 28
    assert _RuntimeRecordingChatCompletionsClient.init_calls[-1] == {
        "api_key": "sk-package-runtime-v1",
        "base_url": "https://runtime-v1.example.com/v1",
        "timeout": 31.0,
    }
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 2

    first_call = _RuntimeRecordingChatCompletionsClient.create_calls[0]
    assert first_call["model"] == "chat-runtime-model"
    assert first_call["reasoning_effort"] == "high"
    assert first_call["messages"][0]["role"] == "system"
    assert first_call["messages"][1]["role"] == "user"
    assert first_call["response_format"]["type"] == "json_schema"
    assert first_call["parallel_tool_calls"] is False
    tool_names = [tool["function"]["name"] for tool in first_call["tools"]]
    assert "signaldeck_memory_lookup" in tool_names

    second_call = _RuntimeRecordingChatCompletionsClient.create_calls[1]
    assistant_message = second_call["messages"][-2]
    tool_message = second_call["messages"][-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["reasoning_content"] == "preserved thinking trace"
    assert assistant_message["tool_calls"][0]["id"] == "call_memory_lookup"
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_memory_lookup"
    tool_payload = json.loads(tool_message["content"])
    assert tool_payload["toolKey"] == "signaldeck.memory.lookup"
    assert tool_payload["scopeMode"] == "current-context-fallback"
    assert tool_payload["count"] == 0

    with session_factory() as session:
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert invocation.status == "succeeded"
        assert invocation.tokens == 28
        assert invocation.output == {"summary": "package chat runtime output"}
        gateway_metadata = cast(dict[str, Any], invocation.graph_metadata)["modelGateway"]
        assert gateway_metadata["usage"] == {
            "inputTokens": 18,
            "outputTokens": 10,
            "totalTokens": 28,
        }
        assert gateway_metadata["selectedStrategies"] == {
            "outputStrategy": "strictJsonSchema",
            "toolCallStrategy": "serialize",
            "parallelToolCalls": False,
            "reasoningStrategy": "enabled",
            "reasoningEffort": "high",
            "streamingStrategy": "disabled",
        }


def test_workflow_package_runtime_chat_tool_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = [
        "{",
        _RuntimeRecordingChatCompletionsClient._memory_lookup_arguments(),
    ]
    _RuntimeRecordingChatCompletionsClient.final_output_text = (
        '{"summary": "chat parser retry output"}'
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_chat_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat parser retry output"}
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    retry_prompt = _RuntimeRecordingChatCompletionsClient.create_calls[1]["messages"][-1]
    assert retry_prompt["role"] == "user"
    assert "toolCallRetry" in retry_prompt["content"]
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["maxAttempts"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is False
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    assert retry_failure["failureTaxonomy"]["retryable"] is True


def test_workflow_package_runtime_native_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    invalid_arguments = json.loads(
        _RuntimeRecordingChatCompletionsClient._memory_lookup_arguments()
    )
    invalid_arguments["limit"] = 0
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = [
        json.dumps(invalid_arguments, sort_keys=True),
        _RuntimeRecordingChatCompletionsClient._memory_lookup_arguments(),
    ]
    _RuntimeRecordingChatCompletionsClient.final_output_text = (
        '{"summary": "native parser retry output"}'
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_native_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "native parser retry output"}
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == ("native_tool_argument_validation")
    assert retry_failure["toolName"] == "signaldeck_memory_lookup"
    assert "limit" in retry_failure["details"][0]["field"]


def test_workflow_package_runtime_chat_tool_parser_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = ["{", "{"]
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_chat_malformed_tool_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_tool_call_retry_exhausted"
    assert invocation["errorDetails"][0]["lastFailureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["failureTaxonomy"]["failureClass"] == "retry_bound_exhausted"
    assert gateway_metadata["failureTaxonomy"]["retryable"] is False
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is True
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 2


def test_workflow_package_runtime_responses_tool_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRetryingResponsesToolClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRetryingResponsesToolClient,
    )

    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_responses_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "responses retry output"}
    assert len(_RuntimeRetryingResponsesToolClient.create_calls) == 3
    retry_input = _RuntimeRetryingResponsesToolClient.create_calls[1]["input"]
    assert isinstance(retry_input, str)
    assert "toolCallRetry" in retry_input
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == (
        "provider_tool_argument_json_invalid"
    )


def test_workflow_package_runtime_responses_tool_parser_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeMalformedResponsesToolClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeMalformedResponsesToolClient,
    )

    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_responses_malformed_tool_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_tool_call_retry_exhausted"
    assert invocation["errorDetails"][0]["lastFailureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["failureTaxonomy"]["failureClass"] == "retry_bound_exhausted"
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is True
    assert len(_RuntimeMalformedResponsesToolClient.create_calls) == 2
    assert _RuntimeMalformedResponsesToolClient.create_calls[0]["parallel_tool_calls"] is False


def test_workflow_package_runtime_tool_policy_forbid_blocks_tool_dependent_package(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        parallel_tool_calls_policy="forbid",
    )
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_memory_lookup(
            package_key="runtime_tool_policy_forbid_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 422, launch.json()
    assert launch.json()["code"] == "validation_error"
    assert launch.json()["message"] == "Workflow package launch validation failed"
    assert {
        "field": "spec.capabilityProfiles.memory_context_tools.toolKeys",
        "code": "model_capability_required_missing",
        "agentKey": "package_analyst",
        "modelConnectionKey": "package_runtime_model",
        "requirement": "nativeToolCalls",
        "issue": (
            "This workflow requires native tool calls, but the selected model connection "
            "forbids tool calls."
        ),
    } in launch.json()["details"]
    assert _RuntimeRecordingChatCompletionsClient.create_calls == []


def test_workflow_package_runtime_digital_oracle_toolKeys_capture_dependency_snapshot(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_digital_oracle_phase1_tools(
            package_key="runtime_digital_oracle_dependency_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"researchQuestion": "Will rates fall this quarter?"},
        },
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200, detail.json()
    dependencies = cast(list[dict[str, object]], detail.json()["extensionDependencies"])
    assert len(dependencies) == 1
    dependency = dependencies[0]
    surfaces = set(cast(list[str], dependency["surfaces"]))
    assert dependency["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert set(cast(list[str], dependency["fields"])) == {
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[0]",
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
        "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[2]",
    }
    assert {f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS} <= surfaces
    assert {f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS} <= surfaces


def test_workflow_package_runtime_digital_oracle_toolKeys_disabled_extension_shape(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_digital_oracle_phase1_tools(
            package_key="runtime_digital_oracle_disabled_extension_package"
        ),
    )
    _disable_finance_extension(session_factory)

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"researchQuestion": "Will rates fall this quarter?"},
        },
    )

    assert launch.status_code == 422, launch.json()
    body = launch.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package launch validation failed"
    assert body["details"] == _expected_digital_oracle_disabled_tool_errors()


def test_workflow_package_runtime_chat_completions_adapter_normalizes_empty_response_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.return_empty_choices = True
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package(client, package_key="runtime_chat_empty_response_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "agent_provider_response_empty"
    assert "choice message" in invocation["errorMessage"]
    assert invocation["tokens"] == 0
    assert detail["executedTokens"] == 0


def test_workflow_package_runtime_uses_smoke_kind_without_openai(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    class _UnexpectedOpenAIClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            raise AssertionError("OpenAI should not be used for deterministic smoke runs")

    monkeypatch.setattr("app.services.run_service.OpenAI", _UnexpectedOpenAIClient)

    _seed_model_connection(
        session_factory,
        api_key=None,
        connection_kind="deterministic_smoke",
        base_url="https://not-a-smoke-host.example.com/v1",
        model_id="smoke-runtime-model",
        api_style="chat_completions",
    )
    created = _create_package(client, package_key="runtime_smoke_kind_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AMD"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "deterministic summary"}
    assert detail["executedTokens"] == 1


def test_workflow_package_runtime_without_finance_dependencies_succeeds_when_finance_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    class _UnexpectedOpenAIClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            raise AssertionError("OpenAI should not be used for deterministic smoke runs")

    monkeypatch.setattr("app.services.run_service.OpenAI", _UnexpectedOpenAIClient)

    _seed_model_connection(
        session_factory,
        api_key=None,
        connection_kind="deterministic_smoke",
        base_url="https://not-a-smoke-host.example.com/v1",
        model_id="smoke-runtime-model",
        api_style="chat_completions",
    )
    created = _create_package(client, package_key="runtime_core_no_finance_package")
    _disable_finance_extension(session_factory)

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "AMD"},
        },
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "deterministic summary"}
    assert detail["extensionDependencies"] == []


def test_workflow_package_validation_redacts_inline_private_mcp_values_but_authoring_preserves_them(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _package_source_with_inline_private_mcp(
        package_key="runtime_private_mcp_projection_package"
    )

    validation = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": manifest_source},
    )
    assert validation.status_code == 200, validation.json()
    validation_body = cast(dict[str, Any], validation.json())
    validation_payload = json.dumps(validation_body, sort_keys=True)
    assert_removed_contract_tokens_absent(validation_body, context="validation payload")
    assert "inline-header-secret" not in validation_payload
    assert "inline-query-secret" not in validation_payload
    assert "[REDACTED]" in validation_payload
    validation_spec = cast(dict[str, Any], validation_body["packageDefinition"])["spec"]
    validation_mcp = cast(list[dict[str, Any]], validation_spec["mcpServers"])[0]
    assert validation_mcp["headers"] == {"Authorization": "[REDACTED]"}
    assert validation_mcp["query"] == {"exaApiKey": "[REDACTED]"}
    compiled_mcp = cast(list[dict[str, Any]], validation_body["compiledPlan"]["mcpServers"])[0]
    assert compiled_mcp["headers"] == {"Authorization": "[REDACTED]"}
    assert compiled_mcp["query"] == {"exaApiKey": "[REDACTED]"}
    descriptor = cast(list[dict[str, Any]], compiled_mcp["toolDescriptors"])[0]
    assert descriptor["ownerExtensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert descriptor["schemaHash"].startswith("sha256:")
    assert descriptor["redactionPolicy"] == "mcp.output.redact_text"

    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    manifest = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert manifest.status_code == 200, manifest.json()
    assert_removed_contract_tokens_absent(manifest.json(), context="manifest hydration")
    assert "inline-header-secret" in json.dumps(manifest.json(), sort_keys=True)
    assert "inline-query-secret" in json.dumps(manifest.json(), sort_keys=True)
    exported = client.get(f"/api/workflow-packages/{package_id}/export")
    assert exported.status_code == 200, exported.text
    assert_removed_contract_tokens_absent(exported.text, context="manifest export")
    assert "Authorization: Bearer inline-header-secret" in exported.text
    assert "exaApiKey: inline-query-secret" in exported.text


def test_workflow_package_runtime_provider_kind_ignores_deterministic_hostname(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package provider host output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        base_url="https://signaldeck-deterministic-model.local/v1",
    )
    created = _create_package(client, package_key="runtime_provider_host_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "NVDA"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "package provider host output"}
    assert detail["executedTokens"] == 23
    assert _RuntimeRecordingOpenAIClient.init_calls[-1] == {
        "api_key": "sk-package-runtime-v1",
        "base_url": "https://signaldeck-deterministic-model.local/v1",
        "timeout": 31.0,
    }
    assert _RuntimeRecordingOpenAIClient.create_calls[-1]["model"] == "gpt-package-v1"


def test_workflow_package_save_allows_missing_model_connection_and_launch_rejects_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key="runtime_missing_model_package")},
    )

    assert create.status_code == 201, create.json()
    package_id = int(create.json()["id"])
    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 422, launch.json()
    body = cast(dict[str, object], launch.json())
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package launch validation failed"
    details = cast(list[dict[str, object]], body["details"])
    assert {
        "field": "spec.agents[0].modelConnection",
        "issue": "Model connection 'package_runtime_model' was not found",
    } in details
    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert (
            session.query(WorkflowPackage).filter_by(key="runtime_missing_model_package").count()
            == 1
        )


def _package_source_with_runtime_input_default(*, package_key: str) -> str:
    original_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    defaulted_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "          horizonDays:\n"
        "            type: integer\n"
        "            default: 14\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    return _package_source(package_key=package_key).replace(
        original_input_schema,
        defaulted_input_schema,
        1,
    )


def _runtime_input_history_entries(
    client: TestClient,
    package_id: int,
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert response.status_code == 200, response.json()
    return cast(list[dict[str, Any]], response.json()["history"])


def test_runtime_input_history_on_launch_persists_validated_payload_source_run_and_trims(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "runtime input source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_runtime_input_default(
                package_key="runtime_input_history_on_launch_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    submitted_payload = {"ticker": "MSFT"}
    expected_validated_payload = {"ticker": "MSFT", "horizonDays": 14}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": submitted_payload},
    )
    assert launch.status_code == 201, launch.json()
    source_run_id = int(launch.json()["id"])

    history = _runtime_input_history_entries(client, package_id)
    assert len(history) == 1
    assert history[0]["slot"] == "history"
    assert history[0]["name"] is None
    assert history[0]["sourceKind"] == "launch"
    assert history[0]["sourceRunId"] == source_run_id
    assert history[0]["payload"] == expected_validated_payload

    with session_factory() as session:
        run = session.get(Run, source_run_id)
        assert run is not None
        assert run.input == expected_validated_payload
        entry = (
            session.query(WorkflowPackageRuntimeInputEntry)
            .filter_by(
                package_id=package_id,
                workflow_key="runtime_workflow",
                slot="history",
            )
            .one()
        )
        assert entry.payload == run.input
        assert entry.source_run_id == source_run_id

    _drain_run_queue(session_factory)
    source_detail = _wait_for_run(client, source_run_id)
    assert source_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], source_detail["steps"][0]["invocations"][0])
    source_invocation_id = int(source_invocation["id"])
    assert source_invocation["resolvedInput"] == {"ticker": "MSFT"}

    rerun = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun.status_code == 201, rerun.json()
    assert len(_runtime_input_history_entries(client, package_id)) == 1
    _drain_run_queue(session_factory)

    fork_draft = client.get(
        f"/api/runs/{source_run_id}/fork-draft",
        params={"sourceInvocationId": source_invocation_id},
    )
    fork = client.post(
        f"/api/runs/{source_run_id}/forks",
        json={
            "sourceInvocationId": source_invocation_id,
            "invocationInput": {"ticker": "TSLA"},
        },
    )
    assert fork_draft.status_code == 200, fork_draft.json()
    fork_draft_body = cast(dict[str, Any], fork_draft.json())
    assert fork_draft_body["sourceRunId"] == source_run_id
    assert fork_draft_body["sourceInvocationId"] == source_invocation_id
    assert fork_draft_body["invocationInput"] == {"ticker": "MSFT"}
    assert fork.status_code == 201, fork.json()
    fork_id = int(fork.json()["id"])
    assert len(_runtime_input_history_entries(client, package_id)) == 1

    with session_factory() as session:
        source_run = session.get(Run, source_run_id)
        fork_run = session.get(Run, fork_id)
        source_snapshot = session.get(RunWorkflowPackageSnapshot, source_run_id)
        fork_snapshot = session.get(RunWorkflowPackageSnapshot, fork_id)
        fork_artifact = session.get(RunFork, fork_id)
        target_invocation = (
            session.query(RunAgentInvocation)
            .filter_by(run_id=fork_id, step_index=1, slot="analysis")
            .one()
        )
        assert source_run is not None
        assert fork_run is not None
        assert source_snapshot is not None
        assert fork_snapshot is not None
        assert fork_artifact is not None
        assert fork_run.input == source_run.input == expected_validated_payload
        assert fork_snapshot.launch_parameters == source_snapshot.launch_parameters
        assert fork_artifact.source_run_id == source_run_id
        assert fork_artifact.lineage_root_run_id == source_run_id
        assert fork_artifact.source_invocation_id == source_invocation_id
        assert fork_artifact.source_step_index == 1
        assert fork_artifact.resume_step_index == 1
        assert fork_artifact.invocation_input == {"ticker": "TSLA"}
        assert target_invocation.source_invocation_id == source_invocation_id
        assert target_invocation.resolved_input == {"ticker": "TSLA"}
        assert target_invocation.resolved_input_origin == "edited"

    with session_factory() as session:
        RunService(session, session_factory).execute_run(fork_id)
    fork_detail = _wait_for_run(client, fork_id)
    fork_invocation = cast(dict[str, Any], fork_detail["steps"][0]["invocations"][0])
    assert fork_detail["input"] == expected_validated_payload
    assert fork_invocation["resolvedInput"] == {"ticker": "TSLA"}
    assert fork_invocation["resolvedInputOrigin"] == "edited"

    for index in range(RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT):
        next_launch = client.post(
            f"/api/workflow-packages/{package_id}/launches",
            json={
                "workflowKey": "runtime_workflow",
                "parameters": {"ticker": f"HIST{index:02d}"},
            },
        )
        assert next_launch.status_code == 201, next_launch.json()

    trimmed_history = _runtime_input_history_entries(client, package_id)
    trimmed_payloads = [entry["payload"] for entry in trimmed_history]
    assert len(trimmed_history) == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT
    assert expected_validated_payload not in trimmed_payloads
    assert trimmed_payloads[0] == {"ticker": "HIST19", "horizonDays": 14}
    assert trimmed_payloads[-1] == {"ticker": "HIST00", "horizonDays": 14}
    assert all(entry["sourceKind"] == "launch" for entry in trimmed_history)
    assert all(entry["sourceRunId"] is not None for entry in trimmed_history)


def test_runtime_input_history_trim_uses_scope_lock_for_concurrent_launches(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_history_lock_package")
    package_id = cast(int, created["id"])
    for index in range(RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT):
        _ = _create_runtime_input_launch(
            session_factory,
            package_id,
            ticker=f"PRE{index:02d}",
        )
    assert (
        len(_runtime_input_history_entries(client, package_id))
        == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT
    )

    first_trim_entered = Event()
    first_trim_can_continue = Event()
    second_trim_entered = Event()
    delay_lock = Lock()
    delayed_once = False
    original_trim = WorkflowPackageRepository.trim_runtime_input_history_overflow

    def delayed_trim(
        self: WorkflowPackageRepository,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        nonlocal delayed_once
        should_delay = False
        with delay_lock:
            if not delayed_once:
                delayed_once = True
                should_delay = True
        if should_delay:
            first_trim_entered.set()
            assert first_trim_can_continue.wait(timeout=5)
        elif first_trim_entered.is_set() and not first_trim_can_continue.is_set():
            second_trim_entered.set()
        return original_trim(self, *args, **kwargs)

    monkeypatch.setattr(
        WorkflowPackageRepository,
        "trim_runtime_input_history_overflow",
        delayed_trim,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            _create_runtime_input_launch,
            session_factory,
            package_id,
            ticker="CONCURRENT_A",
        )
        assert first_trim_entered.wait(timeout=5)
        second = executor.submit(
            _create_runtime_input_launch,
            session_factory,
            package_id,
            ticker="CONCURRENT_B",
        )
        try:
            assert not second_trim_entered.wait(timeout=0.2)
        finally:
            first_trim_can_continue.set()
        source_run_ids = {first.result(timeout=5), second.result(timeout=5)}

    trimmed_history = _runtime_input_history_entries(client, package_id)
    payload_tickers = [entry["payload"]["ticker"] for entry in trimmed_history]
    assert len(trimmed_history) == RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT
    assert {"CONCURRENT_A", "CONCURRENT_B"} <= set(payload_tickers)
    assert {"PRE00", "PRE01"}.isdisjoint(payload_tickers)
    assert source_run_ids <= {int(entry["sourceRunId"]) for entry in trimmed_history}


def test_runtime_input_no_history_on_invalid_launch_or_preflight(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_input_no_history_invalid_package")
    package_id = cast(int, created["id"])

    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        params={"workflowKey": "runtime_workflow"},
    )
    assert preflight.status_code == 200, preflight.json()
    assert _runtime_input_history_entries(client, package_id) == []

    invalid_launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "unexpected": True},
        },
    )
    assert invalid_launch.status_code == 400, invalid_launch.json()
    assert invalid_launch.json()["code"] == "run_invalid_input"
    assert _runtime_input_history_entries(client, package_id) == []

    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert session.query(WorkflowPackageRuntimeInputEntry).count() == 0
