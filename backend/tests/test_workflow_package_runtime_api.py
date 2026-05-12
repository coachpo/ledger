from __future__ import annotations

import time
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackageVersion
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
    return f"""apiVersion: ledger.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Runtime Package
  description: Runtime package fixture.
spec:
  inputs:
    type: object
    additionalProperties: false
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
        additionalProperties: false
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
        additionalProperties: false
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
        additionalProperties: false
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
        assert run.workflow_package_key == "runtime_package"
        assert run.workflow_package_version == 1
        assert run.workflow_package_hash is not None
        assert run.workflow_package_workflow_key == "runtime_workflow"
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
        base_url="https://ledger-deterministic-model.local/v1",
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
        "base_url": "https://ledger-deterministic-model.local/v1",
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
        assert session.query(WorkflowPackageVersion).count() == 0
