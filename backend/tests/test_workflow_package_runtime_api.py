from __future__ import annotations

import json
import time
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService


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
        cls.output_text = '{"summary": "package runtime output"}'
        cls.total_tokens = 23


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
      budgetUsd: "0.10"
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
        .replace('      budgetUsd: "0.10"', '      mcpServers: [exa]\n      budgetUsd: "0.10"', 1)
    )


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
    api_key: str | None = "sk-package-runtime-v1",
    connection_kind: str = "provider",
    base_url: str = "https://runtime-v1.example.com/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
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


def test_workflow_package_launch_rejects_unknown_root_parameter_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_unknown_root_package")

    response = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "version": 1,
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
            "version": 1,
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
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    _seed_model_connection(session_factory)
    created = _create_package(client)

    with session_factory() as session:
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-v2.example.com/v1"
        connection.model_id = "gpt-package-v2"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "sk-package-runtime-v2"}
        session.commit()

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["targetKind"] == "workflowPackage"
    assert detail["targetId"] == created["id"]
    assert detail["targetKey"] == "runtime_package"
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
    assert invocation["agentId"] == 1
    assert invocation["outputSchemaId"] == 1
    assert detail["finalOutput"] == {"summary": "package live runtime output"}
    assert detail["executedTokens"] == 23
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
        package_version = (
            session.query(WorkflowPackageVersion)
            .filter_by(package_id=created["id"], version=1)
            .one()
        )
        assert run.workflow_package_key == "runtime_package"
        assert run.workflow_package_version == 1
        assert run.workflow_package_manifest_hash == package_version.manifest_hash
        assert run.workflow_package_compiled_hash == package_version.compiled_hash
        assert run.workflow_package_workflow_key == "runtime_workflow"
        assert run.launch_snapshot is not None
        assert run.launch_snapshot["workflowKey"] == "runtime_workflow"
        assert run.launch_snapshot["parameters"] == {"ticker": "MSFT"}
        assert session.query(Agent).count() == 0
        assert session.query(Workflow).count() == 0
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert invocation.agent_id == 1
        assert invocation.agent_key == "package_analyst"
        assert invocation.output_schema_id == 1
        assert invocation.output == {"summary": "package live runtime output"}


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
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

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
        json={"version": 1, "workflowKey": "runtime_workflow", "parameters": {"ticker": "AMD"}},
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
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

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
            "version": 1,
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
    assert "inline-header-secret" in json.dumps(manifest.json(), sort_keys=True)
    assert "inline-query-secret" in json.dumps(manifest.json(), sort_keys=True)
    exported = client.get(f"/api/workflow-packages/{package_id}/export")
    assert exported.status_code == 200, exported.text
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
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    _seed_model_connection(
        session_factory,
        base_url="https://signaldeck-deterministic-model.local/v1",
    )
    created = _create_package(client, package_key="runtime_provider_host_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "runtime_workflow", "parameters": {"ticker": "NVDA"}},
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


def test_workflow_package_create_rejects_missing_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key="runtime_missing_model_package")},
    )

    assert create.status_code == 422, create.json()
    body = create.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package manifest validation failed"
    assert body["details"] == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'package_runtime_model' was not found",
        }
    ]
    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert (
            session.query(WorkflowPackage).filter_by(key="runtime_missing_model_package").count()
            == 0
        )
        assert (
            session.query(WorkflowPackageVersion)
            .join(
                WorkflowPackage,
                WorkflowPackageVersion.package_id == WorkflowPackage.id,
            )
            .filter(WorkflowPackage.key == "runtime_missing_model_package")
            .count()
            == 0
        )
