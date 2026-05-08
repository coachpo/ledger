from __future__ import annotations

import json
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.services.run_service import RunService
from tests.test_workflow_package_runtime_api import (
    _create_package,
    _drain_run_queue,
    _RuntimeRecordingOpenAIClient,
    _seed_model_connection,
    _wait_for_run,
)


def test_workflow_package_runtime_persists_step_and_invocation_artifacts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "artifact package output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)

    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="artifact_runtime_package")
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"version": 1, "workflowKey": "runtime_workflow", "parameters": {"ticker": "AAPL"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "artifact package output"}
    assert detail["totalTokens"] == 23
    assert len(detail["steps"]) == 1
    step = cast(dict[str, object], detail["steps"][0])
    assert step["status"] == "succeeded"
    assert step["origin"] == "planned"
    invocations = cast(list[dict[str, object]], step["invocations"])
    assert len(invocations) == 1
    invocation = invocations[0]
    assert invocation["agentId"] == 1
    assert invocation["agentKey"] == "package_analyst"
    assert invocation["agentVersion"] == 1
    assert invocation["outputSchemaId"] == 1
    assert invocation["outputSchemaVersion"] == 1
    assert invocation["resolvedInput"] == {"ticker": "AAPL"}
    assert invocation["output"] == {"summary": "artifact package output"}
    assert invocation["outputOrigin"] == "executed"
    assert invocation["sourceInvocationId"] is None

    serialized_detail = json.dumps(detail, sort_keys=True)
    assert "sk-package-runtime" not in serialized_detail

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.workflow_package_key == "artifact_runtime_package"
        assert run.workflow_package_workflow_key == "runtime_workflow"
        steps = session.query(RunStep).filter_by(run_id=run_id).all()
        assert len(steps) == 1
        assert steps[0].status == "succeeded"
        db_invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert db_invocation.status == "succeeded"
        assert db_invocation.resolved_input == {"ticker": "AAPL"}
        assert db_invocation.output == {"summary": "artifact package output"}
        assert db_invocation.tokens == 23
