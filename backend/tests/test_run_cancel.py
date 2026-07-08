from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.models.run import Run
from app.repositories.run import RunRepository
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_dto import (
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelExecutionUsage,
    ModelToolExecutor,
)
from app.services.run_service import RunService


def _seed_model_connection(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="package_runtime_model",
                name="Package Runtime Model",
                description="Package runtime model binding.",
                base_url="https://provider-runtime.example.test/v1",
                model_id="gpt-package-v1",
                reasoning_effort="high",
                api_style="responses",
                capabilities={},
                output_strategy_policy="prefer_strict_schema",
                parallel_tool_calls_policy="serialize",
                reasoning_policy="allow",
                streaming_policy="allow",
                timeout_seconds=31,
                secret_payload={"apiKey": "test-api-key"},
            )
        )
        session.commit()


def _one_step_package_source(package_key: str) -> str:
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


def _two_step_package_source(package_key: str) -> str:
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
    - key: first_agent
      name: First Agent
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
    - key: second_agent
      name: Second Agent
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
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
        kind: sequence
        id: root_sequence
        nodes:
          - kind: step
            id: first_step
            slot: first
            uses: first_agent
            with:
              ticker: ${{{{ inputs.ticker }}}}
          - kind: step
            id: second_step
            slot: second
            uses: second_agent
            with:
              summary: ${{{{ nodes.first_step.outputs.first.summary }}}}
      output:
        from: ${{{{ nodes.second_step.outputs.second }}}}
"""


def _create_package(
    client: TestClient,
    *,
    manifest_source: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _launch_run(client: TestClient, package_id: int) -> int:
    response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert response.status_code == 201, response.json()
    return int(response.json()["id"])


def _claim_run(session_factory: sessionmaker[Session], run_id: int) -> None:
    with session_factory() as session:
        run = RunRepository(session).claim_next_queued(run_id=run_id)
        assert run is not None
        session.commit()


def test_cancel_queued_run_marks_cancelled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(
        client,
        manifest_source=_one_step_package_source("cancel_queued_package"),
    )
    run_id = _launch_run(client, int(package["id"]))

    response = client.post(f"/api/runs/{run_id}/cancel")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["finishedAt"] is not None
    assert body["queue"] is None
    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.lease_owner is None
        assert run.lease_expires_at is None
        assert run.heartbeat_at is None
    with session_factory() as session:
        assert RunRepository(session).claim_next_queued(run_id=run_id) is None


def test_cancel_finished_run_conflicts(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(
        client,
        manifest_source=_one_step_package_source("cancel_finished_package"),
    )
    run_id = _launch_run(client, int(package["id"]))
    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        run.status = "succeeded"
        run.started_at = utcnow()
        run.finished_at = utcnow()
        session.commit()

    response = client.post(f"/api/runs/{run_id}/cancel")

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "run_cancel_conflict"


def test_running_run_stops_at_next_step_boundary(
    client: TestClient,
    monkeypatch: Any,
    session_factory: sessionmaker[Session],
) -> None:
    first_step_started = Event()
    release_first_step = Event()
    agent_calls: list[str] = []

    def invoke(
        self: ModelExecutionGateway,
        request: ModelExecutionRequest,
        *,
        tool_executor: ModelToolExecutor,
    ) -> ModelExecutionResult:
        del self, tool_executor
        agent_calls.append(request.agent_key)
        if request.agent_key == "first_agent":
            first_step_started.set()
            assert release_first_step.wait(timeout=3.0)
            return ModelExecutionResult(
                output={"summary": "step one"},
                usage=ModelExecutionUsage(total_tokens=5),
            )
        return ModelExecutionResult(
            output={"summary": "step two"},
            usage=ModelExecutionUsage(total_tokens=7),
        )

    monkeypatch.setattr(
        "app.services.model_gateway.ModelExecutionGateway.invoke",
        invoke,
    )
    _seed_model_connection(session_factory)
    package = _create_package(
        client,
        manifest_source=_two_step_package_source("cancel_running_package"),
    )
    run_id = _launch_run(client, int(package["id"]))
    _claim_run(session_factory, run_id)

    def execute() -> None:
        with session_factory() as session:
            RunService(session, session_factory).execute_claimed_run(run_id)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(execute)
        assert first_step_started.wait(timeout=3.0)
        cancel_response = client.post(f"/api/runs/{run_id}/cancel")
        assert cancel_response.status_code == 200, cancel_response.json()
        assert cancel_response.json()["status"] == "running"
        release_first_step.set()
        future.result(timeout=3.0)

    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["error"] == "cancelled by operator"
    assert body["finishedAt"] is not None
    assert agent_calls == ["first_agent"]
    assert body["steps"][0]["status"] == "succeeded"
    assert body["steps"][1]["status"] == "skipped"
    assert body["steps"][1]["error"] == "cancelled by operator"
    assert body["steps"][1]["invocations"][0]["status"] == "skipped"
    assert body["steps"][1]["invocations"][0]["errorMessage"] == "cancelled by operator"
