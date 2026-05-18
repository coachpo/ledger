from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.models.run import Run, RunWorkflowPackageSnapshot
from app.schemas.run import RunPackageProvenanceRead, RunRead

UTC_TZ = timezone.utc  # noqa: UP017


def _workflow_package_run() -> Run:
    return Run(
        target_kind="workflowPackage",
        target_id=101,
        target_key="artifact_runtime_package",
        target_version=1,
        workflow_package_key="artifact_runtime_package",
        workflow_package_workflow_key="runtime_workflow",
        input={"ticker": "AAPL"},
        status="queued",
        total_tokens=0,
        inherited_tokens=0,
        executed_tokens=0,
    )


def _generic_workflow_run() -> Run:
    return Run(
        target_kind="workflow",
        target_id=7,
        target_key="generic_workflow",
        target_version=1,
        input={"ticker": "AAPL"},
        status="queued",
        total_tokens=0,
        inherited_tokens=0,
        executed_tokens=0,
    )


def _snapshot() -> RunWorkflowPackageSnapshot:
    return RunWorkflowPackageSnapshot(
        workflow_package_id=101,
        workflow_package_key="artifact_runtime_package",
        workflow_package_name="Artifact Runtime Package",
        workflow_package_description="Runtime package fixture.",
        workflow_package_status="active",
        workflow_key="runtime_workflow",
        workflow_name="Runtime Workflow",
        workflow_description="Compile a one-step runtime workflow.",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source="apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n",
        package_definition={
            "metadata": {"key": "artifact_runtime_package"},
            "spec": {"workflows": [{"key": "runtime_workflow"}]},
        },
        compiled_plan={
            "agents": [{"key": "package_analyst"}],
            "outputSchemas": [{"key": "summary_output"}],
            "capabilityProfiles": [],
            "mcpServers": [],
            "workflows": [{"key": "runtime_workflow", "name": "Runtime Workflow"}],
        },
        extension_dependencies=[
            {
                "extensionKey": "signaldeck.finance",
                "surfaces": ["tool.market_quote"],
                "fields": [],
            }
        ],
        local_resource_refs={
            "agents": ["package_analyst"],
            "outputSchemas": ["summary_output"],
            "capabilityProfiles": [],
            "mcpServers": [],
            "workflows": ["runtime_workflow"],
        },
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        launch_parameters={"ticker": "AAPL"},
        resolved_model_connections=[
            {
                "key": "package_runtime_model",
                "name": "Package Runtime Model",
                "connectionKind": "provider",
                "baseUrl": "https://runtime.example.com/v1",
                "modelId": "gpt-package-runtime",
                "reasoningEffort": "high",
                "apiStyle": "responses",
                "timeoutSeconds": 31,
                "hasApiKey": True,
            }
        ],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )


def _provenance_from_snapshot(
    snapshot: RunWorkflowPackageSnapshot,
) -> RunPackageProvenanceRead:
    return RunPackageProvenanceRead.model_validate(
        {
            "workflowPackageId": snapshot.workflow_package_id,
            "workflowPackageKey": snapshot.workflow_package_key,
            "workflowPackageName": snapshot.workflow_package_name,
            "workflowPackageDescription": snapshot.workflow_package_description,
            "workflowPackageStatus": snapshot.workflow_package_status,
            "workflowPackageManifestHash": snapshot.manifest_hash,
            "workflowPackageCompiledHash": snapshot.compiled_hash,
            "workflowKey": snapshot.workflow_key,
            "workflowName": snapshot.workflow_name,
            "workflowDescription": snapshot.workflow_description,
            "manifestSource": snapshot.manifest_source,
            "packageDefinition": snapshot.package_definition,
            "compiledPlan": snapshot.compiled_plan,
            "launchSnapshot": {
                "workflowKey": snapshot.workflow_key,
                "workflowName": snapshot.workflow_name,
                "workflowDescription": snapshot.workflow_description,
                "inputSchema": snapshot.input_schema,
                "parameters": snapshot.launch_parameters,
            },
            "extensionDependencies": snapshot.extension_dependencies,
            "localResourceRefs": snapshot.local_resource_refs,
            "resolvedModelConnections": snapshot.resolved_model_connections,
            "preflightSummary": snapshot.preflight_summary,
            "currentPackage": {
                "available": True,
                "status": snapshot.workflow_package_status,
                "manifestHash": snapshot.manifest_hash,
                "compiledHash": snapshot.compiled_hash,
                "manifestHashMatchesSnapshot": True,
                "compiledHashMatchesSnapshot": True,
                "unavailableReason": None,
            },
        }
    )


def _run_read_payload(*, target_kind: str) -> dict[str, object]:
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC_TZ)
    target_id = 101 if target_kind == "workflowPackage" else 7
    target_key = "artifact_runtime_package" if target_kind == "workflowPackage" else "workflow"
    return {
        "id": 42,
        "targetKind": target_kind,
        "targetId": target_id,
        "targetKey": target_key,
        "input": {"ticker": "AAPL"},
        "resumeStepIndex": 1,
        "finalOutput": None,
        "status": "queued",
        "totalTokens": 0,
        "inheritedTokens": 0,
        "executedTokens": 0,
        "traceId": None,
        "error": None,
        "queuedAt": now,
        "startedAt": None,
        "finishedAt": None,
        "createdAt": now,
        "updatedAt": now,
        "extensionDependencies": [],
        "steps": [],
        "memoryArtifacts": [],
    }


def test_workflow_package_run_persists_run_owned_executable_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _workflow_package_run()
        run.workflow_package_snapshot = _snapshot()
        session.add(run)
        session.commit()
        session.refresh(run)

        stored_run = session.get(Run, run.id)
        assert stored_run is not None
        stored_snapshot = session.get(RunWorkflowPackageSnapshot, run.id)
        assert stored_snapshot is not None
        assert stored_run.workflow_package_snapshot is stored_snapshot
        assert stored_snapshot.run_id == stored_run.id
        assert not hasattr(stored_snapshot, "id")
        assert stored_snapshot.workflow_package_id == 101
        assert stored_snapshot.workflow_package_key == "artifact_runtime_package"
        assert stored_snapshot.workflow_key == "runtime_workflow"
        assert stored_snapshot.manifest_source.startswith("apiVersion:")
        assert stored_snapshot.package_definition["metadata"]["key"] == "artifact_runtime_package"
        assert stored_snapshot.compiled_plan["agents"] == [{"key": "package_analyst"}]
        assert stored_snapshot.local_resource_refs["agents"] == ["package_analyst"]
        assert stored_snapshot.input_schema["required"] == ["ticker"]
        assert stored_snapshot.launch_parameters == {"ticker": "AAPL"}
        assert stored_snapshot.preflight_summary == {
            "ready": True,
            "blockingErrors": [],
            "warnings": [],
        }

        provenance = _provenance_from_snapshot(stored_snapshot)
        payload = cast(dict[str, object], provenance.model_dump(mode="json", by_alias=True))
        serialized = json.dumps(payload, sort_keys=True)
        assert "workflowPackage" + "Version" not in serialized
        assert "last" + "LaunchedAt" not in serialized
        assert "apiKey" not in serialized
        assert payload["workflowPackageManifestHash"] == "a" * 64
        assert cast(dict[str, object], payload["launchSnapshot"])["parameters"] == {
            "ticker": "AAPL",
        }
        assert payload["currentPackage"] == {
            "available": True,
            "status": "active",
            "manifestHash": "a" * 64,
            "compiledHash": "b" * 64,
            "manifestHashMatchesSnapshot": True,
            "compiledHashMatchesSnapshot": True,
            "unavailableReason": None,
        }


def test_workflow_package_run_requires_run_owned_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_workflow_package_run())
        with pytest.raises(ValueError, match="run-owned executable snapshot"):
            session.commit()
        session.rollback()


def test_generic_run_persists_without_workflow_package_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _generic_workflow_run()
        session.add(run)
        session.commit()
        session.refresh(run)
        stored_run = session.get(Run, run.id)
        assert stored_run is not None
        assert stored_run.workflow_package_snapshot is None

    detail = RunRead.model_validate(_run_read_payload(target_kind="workflow"))
    assert detail.package_provenance is None


def test_workflow_package_run_read_requires_snapshot_provenance() -> None:
    payload = _run_read_payload(target_kind="workflowPackage")
    with pytest.raises(ValidationError):
        _ = RunRead.model_validate(payload)

    snapshot = _snapshot()
    payload["packageProvenance"] = _provenance_from_snapshot(snapshot).model_dump(
        mode="json",
        by_alias=True,
    )
    detail = RunRead.model_validate(payload)

    assert detail.package_provenance is not None
    assert detail.package_provenance.workflow_package_key == "artifact_runtime_package"
    assert detail.package_provenance.workflow_key == "runtime_workflow"
