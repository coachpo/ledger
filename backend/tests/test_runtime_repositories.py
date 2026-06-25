from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
from typing import Protocol, TypedDict, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.model_connection import ModelConnection
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_fork import RunFork
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage, WorkflowPackageRuntimeInputEntry
from app.models.workflow_package_schedule import WorkflowPackageSchedule
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.run import RunRepository
from app.repositories.run_fork import RunForkRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.repositories.workflow_package_schedule import (
    WorkflowPackageScheduleFireRepository,
    WorkflowPackageScheduleRepository,
)
from app.schemas.model_connection import default_model_connection_capabilities
from app.schemas.run import RunAgentInvocationRead, RunRead, RunStatus
from app.services.model_connection_service import ModelConnectionService
from app.services.run_service import RunService

UTC_TZ = timezone.utc  # noqa: UP017


class RuntimeInputScope(TypedDict):
    package_id: int
    workflow_key: str


class RuntimeInputMetadata(TypedDict):
    source_kind: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema_snapshot: dict[str, object]


class RuntimeInputRegistryRepository(Protocol):
    runtime_input_history_limit: int

    def list_runtime_input_preset_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> list[WorkflowPackageRuntimeInputEntry]: ...

    def list_runtime_input_history_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> list[WorkflowPackageRuntimeInputEntry]: ...

    def count_runtime_input_preset_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> int: ...

    def create_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        name: str | None,
        payload: dict[str, object],
        source_kind: str,
        manifest_hash: str,
        compiled_hash: str,
        schema_fingerprint: str,
        input_schema_snapshot: dict[str, object] | None,
        source_run_id: int | None = None,
    ) -> WorkflowPackageRuntimeInputEntry: ...

    def append_runtime_input_history_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        payload: dict[str, object],
        source_kind: str,
        manifest_hash: str,
        compiled_hash: str,
        schema_fingerprint: str,
        input_schema_snapshot: dict[str, object] | None,
        source_run_id: int | None = None,
    ) -> WorkflowPackageRuntimeInputEntry: ...

    def trim_runtime_input_history_overflow(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> int: ...

    def get_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
    ) -> WorkflowPackageRuntimeInputEntry | None: ...

    def update_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
        **fields: object,
    ) -> WorkflowPackageRuntimeInputEntry | None: ...

    def delete_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
    ) -> bool: ...


def _build_model_connection(
    *,
    name: str,
    key: str | None = None,
    api_key: str,
    model_id: str = "gpt-5.4-mini",
    api_style: str = "responses",
) -> ModelConnection:
    return ModelConnection(
        key=key or name.strip().lower().replace(" ", "_"),
        name=name,
        description=f"{name} description",
        base_url="https://api.openai.com/v1",
        model_id=model_id,
        reasoning_effort="medium",
        api_style=api_style,
        timeout_seconds=60,
        secret_payload={"apiKey": api_key},
    )


def _build_agent_platform_run(
    *,
    package_id: int,
    package_key: str,
    workflow_key: str,
    status: str,
    total_tokens: int,
    started_at: datetime | None,
    finished_at: datetime | None,
    trace_id: str | None,
    final_output: object | None,
) -> Run:
    run = Run(
        target_kind="workflowPackage",
        target_id=package_id,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key=workflow_key,
        input={"ticker": "NVDA", "horizonDays": 30},
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        trace_id=trace_id,
        started_at=started_at,
        finished_at=finished_at,
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package_id,
        workflow_package_key=package_key,
        workflow_package_name=f"{package_key} package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key=workflow_key,
        workflow_name=workflow_key.replace("_", " ").title(),
        workflow_description="Runtime workflow",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=(f"apiVersion: signaldeck.workflowPackage/v1\\nkey: {package_key}\\n"),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": workflow_key}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": [workflow_key]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    return run


def _seed_workflow_package_target(
    session: Session,
    *,
    key_prefix: str,
) -> WorkflowPackage:
    package_key = f"{key_prefix}_package"
    package = WorkflowPackage(
        key=package_key,
        name=f"{key_prefix} package",
        description="Package target fixture",
        manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
        manifest_hash="a" * 64,
        package_definition={"metadata": {"key": package_key, "name": f"{key_prefix} package"}},
        compiled_plan={"workflows": []},
        compiled_hash="b" * 64,
        extension_dependencies=[],
    )
    session.add(package)
    session.flush()
    return package


def _build_workflow_package_queue_run(
    package: WorkflowPackage,
    *,
    queued_at: datetime,
    workflow_key: str = "runtime_workflow",
) -> Run:
    run = Run(
        target_kind="workflowPackage",
        target_id=package.id,
        target_key=package.key,
        target_version=1,
        workflow_package_id=package.id,
        workflow_package_key=package.key,
        workflow_package_workflow_key=workflow_key,
        extension_dependencies=[],
        input={"ticker": "NVDA"},
        status=RunStatus.QUEUED.value,
        queued_at=queued_at,
        started_at=None,
        finished_at=None,
        total_tokens=0,
        inherited_tokens=0,
        executed_tokens=0,
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package.id,
        workflow_package_key=package.key,
        workflow_package_name=package.name,
        workflow_package_description=package.description,
        workflow_package_status=None,
        workflow_key=workflow_key,
        workflow_name="Runtime Workflow",
        workflow_description="",
        manifest_hash=package.manifest_hash,
        compiled_hash=package.compiled_hash,
        manifest_source=package.manifest_source,
        package_definition=package.package_definition,
        compiled_plan=package.compiled_plan,
        extension_dependencies=package.extension_dependencies,
        local_resource_refs={"workflows": [workflow_key]},
        input_schema={},
        launch_parameters={"ticker": "NVDA"},
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    return run


def _runtime_input_scope(
    package: WorkflowPackage,
    *,
    workflow_key: str = "runtime_workflow",
) -> RuntimeInputScope:
    return {
        "package_id": package.id,
        "workflow_key": workflow_key,
    }


def _runtime_input_metadata(
    package: WorkflowPackage,
    *,
    source_kind: str = "manual",
) -> RuntimeInputMetadata:
    return {
        "source_kind": source_kind,
        "manifest_hash": package.manifest_hash,
        "compiled_hash": package.compiled_hash,
        "schema_fingerprint": "c" * 64,
        "input_schema_snapshot": {"type": "object"},
    }


def test_runtime_input_entry_invalid_slot_or_constraint_rejected(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="runtime_input_constraint")
        session.commit()
        package_id = package.id
        manifest_hash = package.manifest_hash
        compiled_hash = package.compiled_hash

        base_entry = {
            "package_id": package_id,
            "workflow_key": "runtime_workflow",
            "payload": {"ticker": "AAPL"},
            "source_kind": "manual",
            "manifest_hash": manifest_hash,
            "compiled_hash": compiled_hash,
            "schema_fingerprint": "c" * 64,
            "input_schema_snapshot": {"type": "object"},
        }
        session.add(WorkflowPackageRuntimeInputEntry(slot="favorite", **base_entry))
        with pytest.raises(sqlalchemy_exc.IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            WorkflowPackageRuntimeInputEntry(
                slot="history",
                name="History rows are unnamed",
                **base_entry,
            )
        )
        with pytest.raises(sqlalchemy_exc.IntegrityError):
            session.commit()
        session.rollback()


def test_workflow_package_runtime_input_repository_scopes_orders_and_trims_history(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="runtime_input_repo")
        other_package = _seed_workflow_package_target(
            session,
            key_prefix="runtime_input_repo_other",
        )
        repo = cast(
            RuntimeInputRegistryRepository,
            cast(object, WorkflowPackageRepository(session)),
        )
        scope = _runtime_input_scope(package)
        other_workflow_scope = _runtime_input_scope(package, workflow_key="other_workflow")
        other_package_scope = _runtime_input_scope(other_package)
        metadata = _runtime_input_metadata(package)

        first_preset = repo.create_runtime_input_preset_entry(
            **scope,
            name="First preset",
            payload={"ticker": "AAPL"},
            **metadata,
        )
        second_preset = repo.create_runtime_input_preset_entry(
            **scope,
            name="Second preset",
            payload={"ticker": "MSFT"},
            **metadata,
        )
        _ = repo.create_runtime_input_preset_entry(
            **other_workflow_scope,
            name="Other workflow preset",
            payload={"ticker": "GOOG"},
            **metadata,
        )
        _ = repo.create_runtime_input_preset_entry(
            **other_package_scope,
            name="Other package preset",
            payload={"ticker": "AMZN"},
            **_runtime_input_metadata(other_package),
        )
        session.flush()

        shared_updated_at = datetime(2026, 5, 19, 12, 0, tzinfo=UTC_TZ)
        first_preset.updated_at = shared_updated_at
        second_preset.updated_at = shared_updated_at
        session.flush()

        preset_entries = repo.list_runtime_input_preset_entries(**scope)
        assert repo.count_runtime_input_preset_entries(**scope) == 2
        assert [entry.id for entry in preset_entries] == [
            second_preset.id,
            first_preset.id,
        ]
        assert [entry.name for entry in preset_entries] == [
            "Second preset",
            "First preset",
        ]

        history_entries = [
            repo.append_runtime_input_history_entry(
                **scope,
                payload={"ticker": "NVDA"},
                **_runtime_input_metadata(package, source_kind="launch"),
            )
            for _ in range(21)
        ]
        other_history = repo.append_runtime_input_history_entry(
            **other_workflow_scope,
            payload={"ticker": "NVDA"},
            **_runtime_input_metadata(package, source_kind="launch"),
        )
        session.flush()

        shared_created_at = datetime(2026, 5, 19, 13, 0, tzinfo=UTC_TZ)
        for entry in [first_preset, second_preset, *history_entries, other_history]:
            entry.created_at = shared_created_at
            entry.updated_at = shared_created_at
        session.flush()

        assert repo.trim_runtime_input_history_overflow(**scope) == 1
        scoped_history = repo.list_runtime_input_history_entries(**scope)

        assert len(scoped_history) == repo.runtime_input_history_limit
        assert [entry.id for entry in scoped_history] == [
            entry.id for entry in reversed(history_entries[1:])
        ]
        assert all(entry.payload == {"ticker": "NVDA"} for entry in scoped_history)
        assert session.get(WorkflowPackageRuntimeInputEntry, history_entries[0].id) is None
        assert session.get(WorkflowPackageRuntimeInputEntry, first_preset.id) is not None
        assert session.get(WorkflowPackageRuntimeInputEntry, second_preset.id) is not None
        assert session.get(WorkflowPackageRuntimeInputEntry, other_history.id) is not None
        assert [
            entry.id for entry in repo.list_runtime_input_history_entries(**other_workflow_scope)
        ] == [other_history.id]


def test_runtime_input_cross_scope_lookup_update_delete_blocked(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="runtime_input_cross_scope")
        other_package = _seed_workflow_package_target(
            session,
            key_prefix="runtime_input_cross_scope_other",
        )
        repo = cast(
            RuntimeInputRegistryRepository,
            cast(object, WorkflowPackageRepository(session)),
        )
        scope = _runtime_input_scope(package)
        metadata = _runtime_input_metadata(package)
        entry = repo.create_runtime_input_preset_entry(
            **scope,
            name="Scoped preset",
            payload={"ticker": "AAPL"},
            **metadata,
        )
        history_entry = repo.append_runtime_input_history_entry(
            **scope,
            payload={"ticker": "AAPL"},
            **_runtime_input_metadata(package, source_kind="launch"),
        )
        session.flush()

        wrong_scope_cases = [
            (
                "same package/different workflow",
                _runtime_input_scope(package, workflow_key="other_workflow"),
            ),
            ("different package/same workflow", _runtime_input_scope(other_package)),
        ]
        for _, wrong_scope in wrong_scope_cases:
            assert repo.get_runtime_input_preset_entry(**wrong_scope, entry_id=entry.id) is None
            assert (
                repo.update_runtime_input_preset_entry(
                    **wrong_scope,
                    entry_id=entry.id,
                    name="Leaked preset",
                    payload={"ticker": "LEAK"},
                )
                is None
            )
            assert repo.delete_runtime_input_preset_entry(**wrong_scope, entry_id=entry.id) is False

        assert repo.get_runtime_input_preset_entry(**scope, entry_id=history_entry.id) is None
        assert (
            repo.update_runtime_input_preset_entry(
                **scope,
                entry_id=history_entry.id,
                name="Mutated history",
            )
            is None
        )
        assert repo.delete_runtime_input_preset_entry(**scope, entry_id=history_entry.id) is False
        session.flush()
        session.refresh(entry)
        session.refresh(history_entry)
        assert entry.name == "Scoped preset"
        assert entry.payload == {"ticker": "AAPL"}
        assert history_entry.name is None

        updated_entry = repo.update_runtime_input_preset_entry(
            **scope,
            entry_id=entry.id,
            name="Updated preset",
            payload={"ticker": "MSFT"},
        )
        assert updated_entry is not None
        assert updated_entry.name == "Updated preset"
        assert updated_entry.payload == {"ticker": "MSFT"}
        assert repo.delete_runtime_input_preset_entry(**scope, entry_id=entry.id) is True
        session.flush()
        assert session.get(WorkflowPackageRuntimeInputEntry, entry.id) is None
        assert session.get(WorkflowPackageRuntimeInputEntry, history_entry.id) is not None


def test_agent_platform_model_connection_repository_lists_rows_by_name(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        alpha = _build_model_connection(
            name="Alpha Model",
            key="alpha_openai",
            api_key="sk-alpha-1111",
        )
        beta = _build_model_connection(
            name="Beta Model",
            key="beta_openai",
            api_key="sk-beta-2222",
        )
        session.add_all([beta, alpha])
        session.commit()

        repo = ModelConnectionRepository(session)
        all_connections = repo.list_connections()

        assert [item.id for item in all_connections] == [alpha.id, beta.id]


def test_agent_platform_model_connection_repository_and_service_resolve_by_key(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        active = _build_model_connection(
            name="Primary OpenAI",
            key="primary_openai",
            api_key="sk-active-1111",
        )
        session.add(active)
        session.commit()

        repo = ModelConnectionRepository(session)
        service = ModelConnectionService(session)

        resolved = repo.get_by_key("primary_openai")

        assert resolved is not None and resolved.id == active.id
        assert service.resolve_connection_by_key("PRIMARY_OPENAI").id == active.id

        with pytest.raises(ApiError) as missing_error:
            _ = service.resolve_connection_by_key("missing_openai")
        assert missing_error.value.code == "validation_error"
        assert missing_error.value.details == [
            {
                "field": "modelConnection",
                "issue": "Model connection 'missing_openai' was not found",
            }
        ]


def test_model_connection_delete_unused_hard_deletes_row(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        connection = _build_model_connection(
            name="Delete Unused Model",
            key="delete_unused_model",
            api_key="sk-unused-delete-1111",
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id

    first = client.delete(f"/api/model-connections/{connection_id}")
    assert first.status_code == 204, first.text
    assert first.content == b""

    get_after_delete = client.get(f"/api/model-connections/{connection_id}")
    assert get_after_delete.status_code == 404, get_after_delete.json()

    second = client.delete(f"/api/model-connections/{connection_id}")
    assert second.status_code == 404, second.json()

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None


def test_model_connection_delete_allows_current_package_ref_as_future_readiness_dependency(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-package-readiness-2222"
    with session_factory() as session:
        connection = _build_model_connection(
            name="Package Referenced Model",
            key="package_referenced_model",
            api_key=secret_value,
        )
        session.add(connection)
        session.flush()
        package = WorkflowPackageRepository(session).create_package(
            key="package_delete_readiness",
            name="Package Delete Readiness",
            manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
            manifest_hash="p" * 64,
            package_definition={"metadata": {"key": "package_delete_readiness"}},
            compiled_plan={"agents": [{"key": "local_agent", "modelConnection": connection.key}]},
            compiled_hash="c" * 64,
        )
        session.commit()
        connection_id = connection.id
        package_id = package.id
        refs = ModelConnectionRepository(session).list_current_package_refs(connection.key)
        assert [(ref.ref_type, ref.ref_id, ref.ref_key) for ref in refs] == [
            ("workflowPackage", package_id, "package_delete_readiness")
        ]

    response = client.delete(f"/api/model-connections/{connection_id}")

    assert response.status_code == 204, response.text
    assert response.content == b""
    assert secret_value not in response.text
    assert "secretPayload" not in response.text

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None
        assert session.get(WorkflowPackage, package_id) is not None
        refs = ModelConnectionRepository(session).list_current_package_refs(
            "package_referenced_model"
        )
        assert [(ref.ref_type, ref.ref_id, ref.ref_key) for ref in refs] == [
            ("workflowPackage", package_id, "package_delete_readiness")
        ]


@pytest.mark.parametrize("run_status", ["queued", "running", "succeeded", "failed"])
def test_model_connection_delete_ignores_run_snapshot_refs(
    client: TestClient,
    session_factory: sessionmaker[Session],
    run_status: str,
) -> None:
    package_key = f"snapshot_delete_ignored_{run_status}"
    workflow_key = "runtime_workflow"
    with session_factory() as session:
        connection = _build_model_connection(
            name=f"Snapshot Ignored Model {run_status}",
            key=f"snapshot_ignored_model_{run_status}",
            api_key="sk-snapshot-ignored",
        )
        session.add(connection)
        session.flush()
        run = Run(
            target_kind="workflowPackage",
            target_id=9001,
            target_key=package_key,
            target_version=1,
            workflow_package_key=package_key,
            workflow_package_workflow_key=workflow_key,
            input={"ticker": "MSFT"},
            status=run_status,
            total_tokens=0,
            inherited_tokens=0,
            executed_tokens=0,
        )
        run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=9001,
            workflow_package_key=package_key,
            workflow_package_name="Snapshot Delete Ignored",
            workflow_package_description="",
            workflow_package_status=None,
            workflow_key=workflow_key,
            workflow_name="Runtime Workflow",
            workflow_description="",
            manifest_hash="s" * 64,
            compiled_hash="r" * 64,
            manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
            package_definition={"metadata": {"key": package_key}},
            compiled_plan={
                "agents": [{"key": "local_agent", "modelConnection": connection.key}],
                "workflows": [{"key": workflow_key}],
            },
            extension_dependencies=[],
            local_resource_refs={
                "agents": ["local_agent"],
                "outputSchemas": [],
                "capabilityProfiles": [],
                "mcpServers": [],
                "workflows": [workflow_key],
            },
            input_schema={},
            launch_parameters={"ticker": "MSFT"},
            resolved_model_connections=[
                {
                    "key": connection.key,
                    "name": connection.name,
                    "protocolProfile": connection.protocol_profile,
                    "baseUrl": connection.base_url,
                    "modelId": connection.model_id,
                    "reasoningEffort": connection.reasoning_effort,
                    "capabilities": default_model_connection_capabilities(
                        connection.protocol_profile
                    ).model_dump(mode="json", by_alias=True),
                    "outputStrategyPolicy": connection.output_strategy_policy,
                    "parallelToolCallsPolicy": connection.parallel_tool_calls_policy,
                    "reasoningPolicy": connection.reasoning_policy,
                    "streamingPolicy": connection.streaming_policy,
                    "probeCacheTtlSeconds": connection.probe_cache_ttl_seconds,
                    "apiStyle": connection.api_style,
                    "timeoutSeconds": connection.timeout_seconds,
                    "hasApiKey": True,
                }
            ],
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(run)
        session.commit()
        connection_id = connection.id
        run_id = run.id

    response = client.delete(f"/api/model-connections/{connection_id}")

    assert response.status_code == 204, response.text
    assert response.content == b""

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, object], detail_response.json())
    provenance = cast(dict[str, object], detail["packageProvenance"])
    assert provenance["resolvedModelConnections"] == [
        {
            "key": f"snapshot_ignored_model_{run_status}",
            "name": f"Snapshot Ignored Model {run_status}",
            "protocolProfile": connection.protocol_profile,
            "baseUrl": "https://api.openai.com/v1",
            "modelId": "gpt-5.4-mini",
            "reasoningEffort": "medium",
            "capabilities": default_model_connection_capabilities(
                connection.protocol_profile
            ).model_dump(mode="json", by_alias=True),
            "outputStrategyPolicy": connection.output_strategy_policy,
            "parallelToolCallsPolicy": connection.parallel_tool_calls_policy,
            "reasoningPolicy": connection.reasoning_policy,
            "streamingPolicy": connection.streaming_policy,
            "probeCacheTtlSeconds": connection.probe_cache_ttl_seconds,
            "apiStyle": "responses",
            "timeoutSeconds": 60,
            "hasApiKey": True,
        }
    ]
    assert cast(dict[str, object], provenance["currentPackage"])["available"] is False

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None


def test_delete_package_with_queued_running_runs_deletes_package_runs(
    session_factory: sessionmaker[Session],
) -> None:
    statuses = ("queued", "running", "succeeded", "failed")
    with session_factory() as session:
        package = _seed_workflow_package_target(
            session,
            key_prefix="cascade_fk",
        )
        package_runs: list[Run] = []
        for status_value in statuses:
            package_run = _build_deletable_run(
                target_kind="workflowPackage",
                target_id=package.id,
                target_key=package.key,
                workflow_key="runtime_workflow",
            )
            package_run.status = status_value
            package_run.workflow_package_id = package.id
            package_run.workflow_package_key = package.key
            package_run.workflow_package_workflow_key = "runtime_workflow"
            package_run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
                workflow_package_id=package.id,
                workflow_package_key=package.key,
                workflow_package_name=package.name,
                workflow_package_description=package.description,
                workflow_package_status="active",
                workflow_key="runtime_workflow",
                workflow_name="Runtime Workflow",
                workflow_description="",
                manifest_hash=package.manifest_hash,
                compiled_hash=package.compiled_hash,
                manifest_source=package.manifest_source,
                package_definition=package.package_definition,
                compiled_plan=package.compiled_plan,
                extension_dependencies=package.extension_dependencies,
                local_resource_refs={"workflows": ["runtime_workflow"]},
                input_schema={},
                launch_parameters={},
                resolved_model_connections=[],
                preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
            )
            package_runs.append(package_run)
        session.add_all(package_runs)
        session.commit()
        package_run_ids = [run.id for run in package_runs]
        package_id = package.id

        session.expunge_all()
        target = session.get(WorkflowPackage, package_id)
        assert target is not None
        session.delete(target)
        session.commit()
        session.expunge_all()

        assert all(session.get(Run, run_id) is None for run_id in package_run_ids)
        assert all(
            session.get(RunWorkflowPackageSnapshot, run_id) is None for run_id in package_run_ids
        )


def test_agent_platform_run_detail_repository_returns_persisted_monitor_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="market_review")
        workflow_key = "market_review"
        agent_id = 1
        agent_key = "research_agent"
        agent_version = 1
        output_schema_id = 1
        output_schema_version = 1

        earlier_run = _build_agent_platform_run(
            package_id=package.id,
            package_key=package.key,
            workflow_key=workflow_key,
            status="failed",
            total_tokens=120,
            started_at=datetime(2026, 4, 19, 9, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 9, 1, tzinfo=UTC_TZ),
            trace_id="trace-older",
            final_output=None,
        )
        earlier_run.queued_at = datetime(2026, 4, 19, 8, 59, tzinfo=UTC_TZ)
        queued_run = _build_agent_platform_run(
            package_id=package.id,
            package_key=package.key,
            workflow_key=workflow_key,
            status=RunStatus.QUEUED.value,
            total_tokens=0,
            started_at=None,
            finished_at=None,
            trace_id=None,
            final_output=None,
        )
        queued_run.queued_at = datetime(2026, 4, 19, 11, 0, tzinfo=UTC_TZ)
        latest_run = _build_agent_platform_run(
            package_id=package.id,
            package_key=package.key,
            workflow_key=workflow_key,
            status="succeeded",
            total_tokens=321,
            started_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ),
            trace_id="trace-latest",
            final_output={"headline": "Buy"},
        )
        latest_run.queued_at = datetime(2026, 4, 19, 9, 59, tzinfo=UTC_TZ)
        session.add_all([earlier_run, latest_run, queued_run])
        session.flush()
        latest_step = RunStep(
            run_id=latest_run.id,
            step_index=1,
            status="succeeded",
            origin="planned",
            started_at=latest_run.started_at,
            finished_at=latest_run.finished_at,
            persisted_at=latest_run.finished_at,
        )
        session.add(latest_step)
        session.flush()
        session.add(
            RunAgentInvocation(
                run_step_id=latest_step.id,
                run_id=latest_run.id,
                step_index=1,
                slot="analysis",
                position=0,
                agent_id=agent_id,
                agent_key=agent_key,
                agent_version=agent_version,
                output_schema_id=output_schema_id,
                output_schema_version=output_schema_version,
                input_mode="passthrough",
                wiring={},
                optional=False,
                status="succeeded",
                resolved_input={"ticker": "NVDA"},
                resolved_input_origin="passthrough",
                output={"headline": "Buy"},
                output_origin="executed",
                tokens=321,
                duration_ms=1450,
                trace_span_id="span-latest",
                started_at=latest_run.started_at,
                finished_at=latest_run.finished_at,
                persisted_at=latest_run.finished_at,
            )
        )
        session.commit()

        run_repo = RunRepository(session)

        run_detail = run_repo.get_detail(latest_run.id)
        listed_runs = run_repo.list_for_workflow_package_key(
            workflow_package_key="market_review_package",
            workflow_key="market_review",
        )
        filtered_runs = run_repo.list_all(
            workflow_package_key="market_review_package",
            package_workflow_key="market_review",
            status="succeeded",
        )
        queued_runs = run_repo.list_all(
            workflow_package_key="market_review_package",
            package_workflow_key="market_review",
            status="queued",
        )
        latest_for_workflow = run_repo.get_latest_for_workflow_package_key(
            workflow_package_key="market_review_package",
            workflow_key="market_review",
        )

        assert run_detail is not None
        detail_steps = cast(list[RunStep], run_detail.steps)
        assert len(detail_steps) == 1
        assert detail_steps[0].step_index == 1
        detail_invocations = cast(list[RunAgentInvocation], detail_steps[0].invocations)
        assert len(detail_invocations) == 1
        assert detail_invocations[0].trace_span_id == "span-latest"
        assert detail_invocations[0].resolved_input == {"ticker": "NVDA"}
        serialized_detail = cast(
            dict[str, object],
            RunRead.model_validate(
                {
                    "id": run_detail.id,
                    "targetKind": run_detail.target_kind,
                    "targetId": run_detail.target_id,
                    "targetKey": run_detail.target_key,
                    "input": run_detail.input,
                    "sourceRunId": run_detail.source_run_id,
                    "lineageRootRunId": run_detail.lineage_root_run_id,
                    "replayStepIndex": run_detail.forked_from_step_index,
                    "resumeStepIndex": run_detail.resume_step_index,
                    "finalOutput": run_detail.final_output,
                    "status": run_detail.status,
                    "progress": {
                        "unit": "invocation",
                        "terminalCount": 1,
                        "totalCount": 1,
                        "percent": 100,
                    },
                    "queue": None,
                    "totalTokens": run_detail.total_tokens,
                    "inheritedTokens": run_detail.inherited_tokens,
                    "executedTokens": run_detail.executed_tokens,
                    "traceId": run_detail.trace_id,
                    "error": run_detail.error,
                    "queuedAt": run_detail.queued_at,
                    "startedAt": run_detail.started_at,
                    "finishedAt": run_detail.finished_at,
                    "createdAt": run_detail.created_at,
                    "updatedAt": run_detail.updated_at,
                    "extensionDependencies": [],
                    "steps": [],
                    "scheduleProvenance": {
                        "scheduleId": 42,
                        "scheduleFireId": 77,
                        "scheduleName": "Archived cleanup schedule",
                        "packageId": 9,
                        "packageKey": "schedule_archive_cleanup_package",
                        "workflowKey": "schedule_archive_cleanup_workflow",
                        "timezone": "UTC",
                        "recurrence": {"type": "daily"},
                        "fireKey": "archived-cleanup-fire",
                        "reason": "scheduled",
                        "scheduledFor": datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ),
                        "scheduledLocalDate": "2026-04-19",
                        "scheduledLocalTime": "10:00:00",
                        "scheduledLocalDateTime": "2026-04-19T10:00:00",
                        "materializedAt": datetime(2026, 4, 19, 9, 59, tzinfo=UTC_TZ),
                        "scheduleDeletedAt": datetime(2026, 4, 20, 12, 0, tzinfo=UTC_TZ),
                    },
                    "packageProvenance": {
                        "workflowPackageId": package.id,
                        "workflowPackageKey": package.key,
                        "workflowPackageName": package.name,
                        "workflowPackageDescription": package.description,
                        "workflowPackageStatus": "active",
                        "workflowPackageManifestHash": "a" * 64,
                        "workflowPackageCompiledHash": "b" * 64,
                        "workflowKey": workflow_key,
                        "workflowName": "Market Review",
                        "workflowDescription": "Runtime workflow",
                        "manifestSource": (
                            "apiVersion: signaldeck.workflowPackage/v1\n"
                            "key: market_review_package\n"
                        ),
                        "packageDefinition": {"metadata": {"key": "market_review_package"}},
                        "compiledPlan": {"workflows": [{"key": workflow_key}]},
                        "launchSnapshot": None,
                        "extensionDependencies": [],
                        "localResourceRefs": {
                            "agents": [],
                            "outputSchemas": [],
                            "capabilityProfiles": [],
                            "mcpServers": [],
                            "workflows": [workflow_key],
                        },
                        "resolvedModelConnections": [],
                        "preflightSummary": None,
                        "currentPackage": None,
                    },
                }
            ).model_dump(mode="json", by_alias=True),
        )
        serialized_invocation = cast(
            dict[str, object],
            RunAgentInvocationRead.model_validate(detail_invocations[0]).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        assert "perStepOutputs" not in serialized_detail
        assert set(serialized_detail) == {
            "id",
            "targetKind",
            "targetId",
            "targetKey",
            "input",
            "sourceRunId",
            "lineageRootRunId",
            "scheduleId",
            "scheduleFireId",
            "scheduledFor",
            "scheduleReason",
            "replayStepIndex",
            "resumeStepIndex",
            "finalOutput",
            "status",
            "progress",
            "queue",
            "totalTokens",
            "inheritedTokens",
            "executedTokens",
            "traceId",
            "error",
            "queuedAt",
            "startedAt",
            "finishedAt",
            "createdAt",
            "updatedAt",
            "extensionDependencies",
            "steps",
            "workflowMemoryEvidence",
            "scheduleProvenance",
            "packageProvenance",
        }
        assert serialized_detail["queuedAt"] == "2026-04-19T09:59:00Z"
        assert serialized_detail["scheduleProvenance"] == {
            "scheduleId": 42,
            "scheduleFireId": 77,
            "scheduleName": "Archived cleanup schedule",
            "packageId": 9,
            "packageKey": "schedule_archive_cleanup_package",
            "workflowKey": "schedule_archive_cleanup_workflow",
            "timezone": "UTC",
            "recurrence": {"type": "daily"},
            "fireKey": "archived-cleanup-fire",
            "reason": "scheduled",
            "scheduledFor": "2026-04-19T10:00:00Z",
            "scheduledLocalDate": "2026-04-19",
            "scheduledLocalTime": "10:00:00",
            "scheduledLocalDateTime": "2026-04-19T10:00:00",
            "materializedAt": "2026-04-19T09:59:00Z",
            "scheduleDeletedAt": "2026-04-20T12:00:00Z",
        }
        assert detail_steps[0].step_index == 1
        assert set(serialized_invocation) == {
            "id",
            "runStepId",
            "runId",
            "stepIndex",
            "slot",
            "position",
            "agentRef",
            "outputSchemaRef",
            "agentKey",
            "agentVersion",
            "outputSchemaVersion",
            "inputMode",
            "wiring",
            "graphMetadata",
            "optional",
            "status",
            "resolvedInput",
            "resolvedInputOrigin",
            "output",
            "outputOrigin",
            "errorCode",
            "errorMessage",
            "errorDetails",
            "tokens",
            "durationMs",
            "traceSpanId",
            "sourceInvocationId",
            "startedAt",
            "finishedAt",
            "persistedAt",
            "createdAt",
            "updatedAt",
        }
        assert serialized_invocation["agentRef"] == {
            "scope": "global",
            "id": agent_id,
            "key": agent_key,
            "version": agent_version,
        }
        assert serialized_invocation["outputSchemaRef"] == {
            "scope": "global",
            "id": output_schema_id,
            "version": output_schema_version,
        }
        assert serialized_invocation["traceSpanId"] == "span-latest"
        assert run_detail.total_tokens == 321
        assert run_detail.trace_id == "trace-latest"
        assert run_detail.final_output == {"headline": "Buy"}
        assert [run.id for run in listed_runs] == [queued_run.id, latest_run.id, earlier_run.id]
        assert [run.id for run in filtered_runs] == [latest_run.id]
        assert [run.id for run in queued_runs] == [queued_run.id]
        assert latest_for_workflow is not None
        assert latest_for_workflow.id == queued_run.id


def test_run_detail_loads_fork_artifact_and_replay_lineage(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source_run = _build_deletable_run(target_id=9301, target_key="fork_source")
        fork_run = _build_deletable_run(target_id=9302, target_key="fork_descendant")
        replay_run = _build_deletable_run(target_id=9303, target_key="replay_lineage")
        session.add(source_run)
        session.flush()

        source_step = RunStep(
            run_id=source_run.id,
            step_index=2,
            status="succeeded",
            origin="planned",
        )
        session.add(source_step)
        session.flush()
        source_invocation = RunAgentInvocation(
            run_step_id=source_step.id,
            run_id=source_run.id,
            step_index=2,
            slot="analysis",
            position=0,
            agent_id=1,
            agent_key="fork_agent",
            agent_version=1,
            output_schema_id=1,
            output_schema_version=1,
            input_mode="passthrough",
            wiring={},
            optional=False,
            status="succeeded",
            resolved_input={"ticker": "NVDA"},
            resolved_input_origin="passthrough",
            output={"decision": "hold"},
            output_origin="executed",
            tokens=13,
        )
        session.add(source_invocation)
        session.flush()

        fork_run.source_run_id = source_run.id
        fork_run.lineage_root_run_id = source_run.id
        fork_run.resume_step_index = 2
        replay_run.source_run_id = source_run.id
        replay_run.lineage_root_run_id = source_run.id
        replay_run.forked_from_step_index = 2
        replay_run.resume_step_index = 2
        session.add_all([fork_run, replay_run])
        session.flush()
        RunForkRepository(session).create_fork(
            run_id=fork_run.id,
            source_run_id=source_run.id,
            lineage_root_run_id=source_run.id,
            source_invocation_id=source_invocation.id,
            source_step_index=2,
            resume_step_index=2,
            invocation_input={"ticker": "MSFT", "horizonDays": 45},
        )
        session.commit()
        source_run_id = source_run.id
        source_invocation_id = source_invocation.id
        fork_run_id = fork_run.id
        replay_run_id = replay_run.id
        session.expunge_all()

        run_repo = RunRepository(session)
        fork_repo = RunForkRepository(session)

        fork_detail = run_repo.get_detail(fork_run_id)
        replay_detail = run_repo.get_detail(replay_run_id)
        persisted_fork = fork_repo.get_by_run_id(fork_run_id)

        assert fork_detail is not None
        assert replay_detail is not None
        assert "fork" not in sqlalchemy_inspect(fork_detail).unloaded
        assert "fork" not in sqlalchemy_inspect(replay_detail).unloaded
        assert fork_detail.fork is not None
        fork_artifact = cast(RunFork, fork_detail.fork)
        assert fork_artifact.run_id == fork_run_id
        assert fork_artifact.source_run_id == source_run_id
        assert fork_artifact.lineage_root_run_id == source_run_id
        assert fork_artifact.source_invocation_id == source_invocation_id
        assert fork_artifact.source_step_index == 2
        assert fork_artifact.resume_step_index == 2
        assert fork_artifact.invocation_input == {"ticker": "MSFT", "horizonDays": 45}
        assert persisted_fork is not None
        assert persisted_fork.run_id == fork_run_id
        assert [fork.run_id for fork in fork_repo.list_by_source_run(source_run_id)] == [
            fork_run_id
        ]
        assert [
            fork.run_id for fork in fork_repo.list_by_source_invocation(source_invocation_id)
        ] == [fork_run_id]
        assert isinstance(fork_artifact, RunFork)
        assert replay_detail.fork is None
        assert replay_detail.source_run_id == source_run_id
        assert replay_detail.lineage_root_run_id == source_run_id
        assert replay_detail.forked_from_step_index == 2
        assert replay_detail.resume_step_index == 2


def _create_schedule_fixture(
    repo: WorkflowPackageScheduleRepository,
    package: WorkflowPackage,
    *,
    name: str,
    status: str = "enabled",
    next_fire_at: datetime | None,
) -> WorkflowPackageSchedule:
    return repo.create_schedule(
        package_id=package.id,
        workflow_key="daily_research",
        name=name,
        timezone="UTC",
        recurrence={"type": "daily", "atLocalTime": "09:00"},
        status=status,
        next_fire_at=next_fire_at,
    )


def test_due_schedule_selection_is_lock_safe_and_deterministic(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 10, 2, tzinfo=UTC_TZ)
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="schedule_due")
        repo = WorkflowPackageScheduleRepository(session)
        first_due = _create_schedule_fixture(
            repo,
            package,
            name="First due",
            next_fire_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC_TZ),
        )
        second_due = _create_schedule_fixture(
            repo,
            package,
            name="Second due",
            next_fire_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC_TZ),
        )
        _ = _create_schedule_fixture(
            repo,
            package,
            name="Future",
            next_fire_at=datetime(2026, 6, 1, 10, 3, tzinfo=UTC_TZ),
        )
        _ = _create_schedule_fixture(
            repo,
            package,
            name="Paused due",
            status="paused",
            next_fire_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC_TZ),
        )
        session.commit()
        first_due_id = first_due.id
        second_due_id = second_due.id

    with session_factory() as session:
        selected = WorkflowPackageScheduleRepository(session).list_due(now=now, limit=10)
        assert [schedule.id for schedule in selected] == [first_due_id, second_due_id]

    first_session = session_factory()
    second_session = session_factory()
    try:
        first_locked = WorkflowPackageScheduleRepository(first_session).list_due_for_update(
            now=now,
            limit=1,
        )
        assert [schedule.id for schedule in first_locked] == [first_due_id]

        second_locked = WorkflowPackageScheduleRepository(second_session).list_due_for_update(
            now=now,
            limit=10,
        )
        assert [schedule.id for schedule in second_locked] == [second_due_id]
    finally:
        first_session.rollback()
        second_session.rollback()
        first_session.close()
        second_session.close()


def test_schedule_fire_idempotency_inserts_one_row_per_schedule_fire_key(
    session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime(2026, 6, 1, 13, 0, tzinfo=UTC_TZ)
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="schedule_fire_idempotency")
        schedule = _create_schedule_fixture(
            WorkflowPackageScheduleRepository(session),
            package,
            name="Daily research",
            next_fire_at=scheduled_for,
        )
        session.flush()
        fire_repo = WorkflowPackageScheduleFireRepository(session)

        first_fire = fire_repo.insert_idempotent(
            schedule_id=schedule.id,
            fire_key="daily-research-2026-06-01T13:00:00Z",
            scheduled_for=scheduled_for,
            rendered_parameters={"ticker": "NVDA"},
        )
        session.flush()
        duplicate_fire = fire_repo.insert_idempotent(
            schedule_id=schedule.id,
            fire_key="daily-research-2026-06-01T13:00:00Z",
            scheduled_for=scheduled_for,
            rendered_parameters={"ticker": "MSFT"},
        )
        session.flush()

        assert duplicate_fire.id == first_fire.id
        assert fire_repo.count_for_schedule(schedule.id) == 1
        existing_fire = fire_repo.get_by_schedule_fire_key(
            schedule_id=schedule.id,
            fire_key="daily-research-2026-06-01T13:00:00Z",
        )
        assert existing_fire is not None
        assert existing_fire.id == first_fire.id


def test_run_repository_lists_only_direct_schedule_owned_runs(
    session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime(2026, 6, 1, 13, 0, tzinfo=UTC_TZ)
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="schedule_run_lookup")
        schedule_repo = WorkflowPackageScheduleRepository(session)
        fire_repo = WorkflowPackageScheduleFireRepository(session)
        schedule = _create_schedule_fixture(
            schedule_repo,
            package,
            name="Daily research",
            next_fire_at=scheduled_for,
        )
        other_schedule = _create_schedule_fixture(
            schedule_repo,
            package,
            name="Other research",
            next_fire_at=scheduled_for,
        )
        session.flush()
        fire = fire_repo.insert_idempotent(
            schedule_id=schedule.id,
            fire_key="daily-research-2026-06-01T13:00:00Z",
            scheduled_for=scheduled_for,
            rendered_parameters={"ticker": "NVDA"},
        )
        session.flush()

        direct_by_schedule = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC_TZ),
        )
        direct_by_schedule.schedule_id = schedule.id
        direct_by_schedule.scheduled_for = scheduled_for
        direct_by_schedule.schedule_reason = "scheduled"

        direct_by_fire = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 6, 1, 13, 1, tzinfo=UTC_TZ),
        )
        direct_by_fire.status = RunStatus.RUNNING.value
        direct_by_fire.started_at = datetime(2026, 6, 1, 13, 1, tzinfo=UTC_TZ)
        direct_by_fire.schedule_fire_id = fire.id
        direct_by_fire.scheduled_for = scheduled_for
        direct_by_fire.schedule_reason = "manual"

        other_schedule_run = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 6, 1, 13, 2, tzinfo=UTC_TZ),
        )
        other_schedule_run.schedule_id = other_schedule.id
        other_schedule_run.scheduled_for = scheduled_for
        other_schedule_run.schedule_reason = "scheduled"

        session.add_all([direct_by_schedule, direct_by_fire, other_schedule_run])
        session.flush()

        rerun_descendant = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 6, 1, 13, 3, tzinfo=UTC_TZ),
        )
        rerun_descendant.source_run_id = direct_by_schedule.id
        rerun_descendant.lineage_root_run_id = direct_by_schedule.id

        fork_descendant = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 6, 1, 13, 4, tzinfo=UTC_TZ),
        )
        fork_descendant.source_run_id = direct_by_fire.id
        fork_descendant.lineage_root_run_id = direct_by_fire.id
        fork_descendant.forked_from_step_index = 1
        fork_descendant.resume_step_index = 1

        session.add_all([rerun_descendant, fork_descendant])
        session.commit()
        schedule_id = schedule.id
        fire_id = fire.id
        direct_by_schedule_id = direct_by_schedule.id
        direct_by_fire_id = direct_by_fire.id

    with session_factory() as session:
        selected = RunRepository(session).list_directly_owned_by_schedule(
            schedule_id=schedule_id,
            fire_ids=[fire_id],
        )
        assert [run.id for run in selected] == [direct_by_schedule_id, direct_by_fire_id]


def test_run_repository_claim_next_queued_serializes_same_package_scope(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="serial_claim")
        first_run = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 5, 20, 10, 0, tzinfo=UTC_TZ),
        )
        second_run = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 5, 20, 10, 1, tzinfo=UTC_TZ),
        )
        session.add_all([first_run, second_run])
        session.commit()
        first_run_id = first_run.id
        second_run_id = second_run.id
        execution_scope_key = first_run.execution_scope_key

    first_session = session_factory()
    second_session = session_factory()
    try:
        first_claim = RunRepository(first_session).claim_next_queued()
        assert first_claim is not None
        assert first_claim.id == first_run_id
        assert first_claim.execution_scope_key == execution_scope_key
        assert first_claim.concurrency_policy == "serial"
        assert first_claim.attempt_count == 1
        assert first_claim.last_claimed_at is not None

        blocked_claim = RunRepository(second_session).claim_next_queued()
        assert blocked_claim is None
        second_session.rollback()
        first_session.commit()
    finally:
        first_session.close()
        second_session.close()

    with session_factory() as session:
        assert RunRepository(session).claim_next_queued() is None
        running_run = session.get(Run, first_run_id)
        queued_run = session.get(Run, second_run_id)
        assert running_run is not None
        assert queued_run is not None
        assert running_run.status == RunStatus.RUNNING.value
        assert queued_run.status == RunStatus.QUEUED.value
        running_run.status = RunStatus.SUCCEEDED.value
        running_run.finished_at = datetime(2026, 5, 20, 10, 5, tzinfo=UTC_TZ)
        session.commit()

    with session_factory() as session:
        next_claim = RunRepository(session).claim_next_queued()
        assert next_claim is not None
        assert next_claim.id == second_run_id
        assert next_claim.status == RunStatus.RUNNING.value


def test_run_repository_claim_next_queued_allows_different_package_concurrent_claims(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first_package = _seed_workflow_package_target(session, key_prefix="parallel_claim_a")
        second_package = _seed_workflow_package_target(session, key_prefix="parallel_claim_b")
        first_run = _build_workflow_package_queue_run(
            first_package,
            queued_at=datetime(2026, 5, 20, 11, 0, tzinfo=UTC_TZ),
        )
        second_run = _build_workflow_package_queue_run(
            second_package,
            queued_at=datetime(2026, 5, 20, 11, 1, tzinfo=UTC_TZ),
        )
        session.add_all([first_run, second_run])
        session.commit()
        first_run_id = first_run.id
        second_run_id = second_run.id

    first_session = session_factory()
    second_session = session_factory()
    try:
        first_claim = RunRepository(first_session).claim_next_queued()
        assert first_claim is not None
        assert first_claim.id == first_run_id

        second_claim = RunRepository(second_session).claim_next_queued()
        assert second_claim is not None
        assert second_claim.id == second_run_id
        assert second_claim.execution_scope_key != first_claim.execution_scope_key
        second_session.commit()
        first_session.commit()
    finally:
        first_session.close()
        second_session.close()

    with session_factory() as session:
        statuses = {
            run.id: run.status
            for run in session.query(Run).filter(Run.id.in_([first_run_id, second_run_id]))
        }
    assert statuses == {
        first_run_id: RunStatus.RUNNING.value,
        second_run_id: RunStatus.RUNNING.value,
    }


def test_run_serial_partial_index_allows_one_concurrent_running_claim_per_scope(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _seed_workflow_package_target(session, key_prefix="serial_index_race")
        first_run = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC_TZ),
        )
        second_run = _build_workflow_package_queue_run(
            package,
            queued_at=datetime(2026, 5, 20, 12, 1, tzinfo=UTC_TZ),
        )
        session.add_all([first_run, second_run])
        session.commit()
        run_ids = (first_run.id, second_run.id)
        assert first_run.execution_scope_key == second_run.execution_scope_key

    start = Event()

    def force_running(run_id: int) -> tuple[str, int | str]:
        assert start.wait(timeout=5)
        with session_factory() as session:
            run = session.get(Run, run_id)
            assert run is not None
            run.status = RunStatus.RUNNING.value
            try:
                session.commit()
            except sqlalchemy_exc.IntegrityError as exc:
                session.rollback()
                return ("loser", exc.__class__.__name__)
            return ("winner", run_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(force_running, run_id) for run_id in run_ids]
        start.set()
        results = [future.result(timeout=5) for future in futures]

    assert sorted(result[0] for result in results) == ["loser", "winner"]
    assert ("loser", "IntegrityError") in results
    winner_ids = [result[1] for result in results if result[0] == "winner"]
    assert len(winner_ids) == 1

    with session_factory() as session:
        rows = session.query(Run).filter(Run.id.in_(run_ids)).all()
    assert sum(1 for row in rows if row.status == RunStatus.RUNNING.value) == 1
    assert sum(1 for row in rows if row.status == RunStatus.QUEUED.value) == 1


def _build_deletable_run(
    *,
    target_kind: str = "workflowPackage",
    target_id: int = 9001,
    target_key: str = "delete_target_package",
    workflow_key: str = "delete_target",
) -> Run:
    run = Run(
        target_kind=target_kind,
        target_id=target_id,
        target_key=target_key,
        target_version=1,
        workflow_package_key=target_key if target_kind == "workflowPackage" else None,
        workflow_package_workflow_key=workflow_key if target_kind == "workflowPackage" else None,
        input={"ticker": "NVDA"},
        status="succeeded",
        final_output={"summary": "done"},
        total_tokens=11,
        inherited_tokens=0,
        executed_tokens=11,
    )
    if target_kind == "workflowPackage":
        run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=target_id,
            workflow_package_key=target_key,
            workflow_package_name=target_key,
            workflow_package_description="",
            workflow_package_status="active",
            workflow_key=workflow_key,
            workflow_name=workflow_key,
            workflow_description="",
            manifest_hash="a" * 64,
            compiled_hash="b" * 64,
            manifest_source=f"apiVersion: signaldeck.workflowPackage/v1\\nkey: {target_key}\\n",
            package_definition={"metadata": {"key": target_key}},
            compiled_plan={"workflows": [{"key": workflow_key}]},
            extension_dependencies=[],
            local_resource_refs={"workflows": [workflow_key]},
            input_schema={},
            launch_parameters=run.input,
            resolved_model_connections=[],
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
    return run


def _build_run_memory_report(run_id: int, *, slug: str, source: str = "agent") -> Report:
    return Report(
        name=slug,
        slug=slug,
        source=source,
        content="memory",
        metadata_={
            "analysis": {
                "reviewType": "agent_memory",
                "versionGroup": "agent_memory/v1",
                "runId": run_id,
            }
        },
    )


def test_run_delete_cascades_steps_invocations_and_agent_memory_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_deletable_run()
        session.add(run)
        session.flush()
        step = RunStep(run_id=run.id, step_index=1, status="succeeded", origin="planned")
        session.add(step)
        session.flush()
        invocation = RunAgentInvocation(
            run_step_id=step.id,
            run_id=run.id,
            step_index=1,
            slot="decision",
            position=0,
            agent_id=1,
            agent_key="delete_agent",
            agent_version=1,
            output_schema_id=1,
            output_schema_version=1,
            input_mode="passthrough",
            wiring={},
            optional=False,
            status="succeeded",
            resolved_input={"ticker": "NVDA"},
            resolved_input_origin="passthrough",
            output={"decision": "buy"},
            output_origin="executed",
            tokens=11,
        )
        retained = _build_run_memory_report(run.id + 100, slug="retained_memory")
        external = _build_run_memory_report(run.id, slug="external_memory", source="external")
        non_memory = Report(
            name="agent_non_memory",
            slug="agent_non_memory",
            source="agent",
            content="not memory",
            metadata_={"analysis": {"reviewType": "other", "runId": run.id}},
        )
        owned = _build_run_memory_report(run.id, slug="owned_memory")
        session.add_all([invocation, owned, retained, external, non_memory])
        session.commit()
        run_id = run.id
        step_id = step.id
        invocation_id = invocation.id

        RunService(session).delete_run(run_id)
        session.expunge_all()

        assert session.get(Run, run_id) is None
        assert session.get(RunStep, step_id) is None
        assert session.get(RunAgentInvocation, invocation_id) is None
        remaining_slugs = {report.slug for report in session.query(Report).all()}
        assert remaining_slugs == {"retained_memory", "external_memory", "agent_non_memory"}


def test_lineage_set_null_on_run_delete(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        source = _build_deletable_run(target_id=9101, target_key="source_run")
        session.add(source)
        session.flush()
        descendant = _build_deletable_run(target_id=9102, target_key="descendant_run")
        descendant.source_run_id = source.id
        descendant.lineage_root_run_id = source.id
        session.add(descendant)
        session.commit()
        source_id = source.id
        descendant_id = descendant.id

        RunService(session).delete_run(source_id)
        session.expire_all()

        persisted = session.get(Run, descendant_id)
        assert persisted is not None
        assert persisted.source_run_id is None
        assert persisted.lineage_root_run_id is None


def test_delete_run_route_returns_204_then_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_deletable_run(target_id=9201, target_key="route_delete")
        session.add(run)
        session.flush()
        session.add(_build_run_memory_report(run.id, slug="route_owned_memory"))
        session.commit()
        run_id = run.id

    first = client.delete(f"/api/runs/{run_id}")
    assert first.status_code == 204, first.text
    assert first.content == b""

    second = client.delete(f"/api/runs/{run_id}")
    assert second.status_code == 404, second.json()

    with session_factory() as session:
        assert session.query(Report).filter_by(slug="route_owned_memory").one_or_none() is None
