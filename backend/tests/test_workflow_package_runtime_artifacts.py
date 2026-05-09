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


def test_workflow_package_runtime_persists_target_fk_step_and_invocation_artifacts(
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

    provenance = cast(dict[str, object], detail["packageProvenance"])
    availability = cast(dict[str, object], provenance["availability"])
    assert availability["packageStatus"] == "active"
    assert availability["packageVersionAvailable"] is True
    assert "canDeletePackage" not in availability
    serialized_detail = json.dumps(detail, sort_keys=True)
    assert "sk-package-runtime" not in serialized_detail
    assert "canDeletePackage" not in serialized_detail
    assert "can" + "ArchivePackage" not in serialized_detail
    assert "package" + "Arch" + "ived" not in serialized_detail

    rerun = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"ticker": "MSFT"}},
    )
    assert rerun.status_code == 201, rerun.json()
    replay = client.post(
        f"/api/runs/{run_id}/step-replays",
        json={"replayStepIndex": 1, "parameters": {"ticker": "TSLA"}},
    )
    assert replay.status_code == 201, replay.json()

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
        assert run.agent_id is None
        assert run.target_workflow_id is None
        assert run.workflow_package_id == created["id"]
        assert run.workflow_package_version_id is not None
        rerun_run = session.get(Run, int(rerun.json()["id"]))
        replay_run = session.get(Run, int(replay.json()["id"]))
        assert rerun_run is not None
        assert replay_run is not None
        assert rerun_run.workflow_package_id == run.workflow_package_id
        assert rerun_run.workflow_package_version_id == run.workflow_package_version_id
        assert replay_run.workflow_package_id == run.workflow_package_id
        assert replay_run.workflow_package_version_id == run.workflow_package_version_id
