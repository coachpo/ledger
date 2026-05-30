from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.models.model_connection import ModelConnection
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.workflow_package import WorkflowPackage, WorkflowPackageRuntimeInputEntry
from app.schemas.model_connection import default_model_connection_capabilities
from app.schemas.run import RunPackageProvenanceRead, RunRead

UTC_TZ = timezone.utc  # noqa: UP017


def _runtime_input_registry_boundary_source(*, package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Runtime Boundary Package
  description: Runtime boundary fixture.
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


def _seed_runtime_input_registry_boundary_model_connection(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="package_runtime_model",
                status="active",
                name="Package Runtime Model",
                description="Runtime boundary model binding.",
                base_url="https://runtime-boundary.example.com/v1",
                model_id="gpt-runtime-boundary",
                reasoning_effort="high",
                api_style="responses",
                timeout_seconds=31,
                secret_payload={"apiKey": "sk-runtime-boundary"},
            )
        )
        session.commit()


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
                "protocolProfile": "openai_responses",
                "baseUrl": "https://runtime.example.com/v1",
                "modelId": "gpt-package-runtime",
                "reasoningEffort": "high",
                "capabilities": default_model_connection_capabilities(
                    "openai_responses"
                ).model_dump(mode="json", by_alias=True),
                "outputStrategyPolicy": "prefer_strict_schema",
                "parallelToolCallsPolicy": "serialize",
                "reasoningPolicy": "allow",
                "streamingPolicy": "allow",
                "probeCacheTtlSeconds": 900,
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
        "progress": {
            "unit": "invocation",
            "terminalCount": 0,
            "totalCount": 0,
            "percent": 0,
        },
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
        assert payload["workflowPackageStatus"] == "active"
        assert payload["workflowPackageManifestHash"] == "a" * 64
        assert cast(dict[str, object], payload["launchSnapshot"])["parameters"] == {
            "ticker": "AAPL",
        }
        assert payload["currentPackage"] == {
            "available": True,
            "manifestHash": "a" * 64,
            "compiledHash": "b" * 64,
            "manifestHashMatchesSnapshot": True,
            "compiledHashMatchesSnapshot": True,
            "unavailableReason": None,
        }


def test_runtime_input_registry_boundary_does_not_mutate_manifest_export_import_or_run_reporting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_runtime_input_registry_boundary_model_connection(session_factory)
    package_key = "runtime_boundary_package"
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _runtime_input_registry_boundary_source(package_key=package_key)},
    )
    assert create_response.status_code == 201, create_response.json()
    package_id = int(create_response.json()["id"])

    personal_response = client.post(
        f"/api/workflow-packages/{package_id}/runtime-input-registry/personal",
        params={"workflowKey": "runtime_workflow"},
        json={
            "name": "Registry-only preset",
            "payload": {"ticker": "MSFT", "notes": ["registry only"]},
        },
    )
    assert personal_response.status_code == 201, personal_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AAPL"}},
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])

    registry_response = client.get(
        f"/api/workflow-packages/{package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert registry_response.status_code == 200, registry_response.json()
    registry_body = cast(dict[str, object], registry_response.json())
    assert len(cast(list[object], registry_body["personal"])) == 1
    history = cast(list[dict[str, object]], registry_body["history"])
    assert len(history) == 1
    assert history[0]["sourceRunId"] == run_id
    assert history[0]["payload"] == {"ticker": "AAPL"}

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, object], detail_response.json())
    package_provenance = cast(dict[str, object], detail["packageProvenance"])
    launch_snapshot = cast(dict[str, object], package_provenance["launchSnapshot"])
    assert launch_snapshot["parameters"] == {"ticker": "AAPL"}
    serialized_detail = json.dumps(detail, sort_keys=True)
    assert "Registry-only preset" not in serialized_detail
    assert "runtimeInput" not in serialized_detail
    assert "registry only" not in serialized_detail

    manifest_response = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert manifest_response.status_code == 200, manifest_response.json()
    serialized_manifest = json.dumps(manifest_response.json(), sort_keys=True)
    assert "Registry-only preset" not in serialized_manifest
    assert "runtimeInput" not in serialized_manifest
    assert "registry only" not in serialized_manifest

    export_response = client.get(f"/api/workflow-packages/{package_id}/export")
    assert export_response.status_code == 200, export_response.text
    exported_source = export_response.text
    assert package_key in exported_source
    assert "Registry-only preset" not in exported_source
    assert "runtimeInput" not in exported_source
    assert "registry only" not in exported_source

    imported_source = exported_source.replace(
        package_key,
        "runtime_boundary_package_imported",
        1,
    )
    import_response = client.post(
        "/api/workflow-packages/import",
        json={"manifestSource": imported_source},
    )
    assert import_response.status_code == 201, import_response.json()
    imported_package_id = int(import_response.json()["id"])
    imported_registry = client.get(
        f"/api/workflow-packages/{imported_package_id}/runtime-input-registry",
        params={"workflowKey": "runtime_workflow"},
    )
    assert imported_registry.status_code == 200, imported_registry.json()
    assert imported_registry.json()["personal"] == []
    assert imported_registry.json()["history"] == []

    with session_factory() as session:
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        run = session.get(Run, run_id)
        assert run is not None
        snapshot = run.workflow_package_snapshot
        assert snapshot is not None
        assert snapshot.launch_parameters == {"ticker": "AAPL"}
        serialized_artifacts = json.dumps(
            {
                "manifestSource": package.manifest_source,
                "packageDefinition": package.package_definition,
                "compiledPlan": package.compiled_plan,
            },
            sort_keys=True,
        )
        assert "Registry-only preset" not in serialized_artifacts
        assert "runtimeInput" not in serialized_artifacts
        assert "registry only" not in serialized_artifacts
        assert (
            session.query(WorkflowPackageRuntimeInputEntry).filter_by(package_id=package_id).count()
            == 2
        )


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
