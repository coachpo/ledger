from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.workflow_spec import WorkflowSpec
from app.repositories.runtime_approval import RuntimeApprovalRepository
from app.repositories.runtime_checkpoint import RuntimeCheckpointRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.schemas.runtime import RuntimeRunCreate
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.execution_adapters import (
    ExecutionAdapterRequest,
    ExecutionAdapterResult,
    ExecutionAdapterTraceEvent,
    ExecutionApprovalRequest,
    ExecutionArtifactPatch,
    ExecutionCheckpointRecord,
)


def _build_agent_spec(
    *,
    key: str,
    version: int,
    status: str,
    default_capability_bundle_keys: list[str] | None = None,
    default_persona_profile_keys: list[str] | None = None,
) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        instructions=f"Instructions for {key}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=list(default_capability_bundle_keys or []),
        default_persona_profile_keys=list(default_persona_profile_keys or []),
    )


def _build_workflow_spec(
    *,
    key: str,
    version: int,
    status: str,
    graph_definition: dict[str, object],
    default_tool_ids: list[str] | None = None,
    allowed_capability_bundle_keys: list[str] | None = None,
) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        graph_definition=graph_definition,
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        mention_policy={"version": 1, "allow_characters": False, "allowed_builtin_handles": []},
        execution_mode=None,
        default_tool_ids=list(default_tool_ids or []),
        allowed_capability_bundle_keys=list(allowed_capability_bundle_keys or []),
        connector_ids=[],
        review_mode=None,
        approval_policy_overrides=[],
    )


def _build_persona_profile(
    *,
    key: str,
    version: int,
    status: str,
    default_capability_bundle_keys: list[str] | None = None,
) -> PersonaProfile:
    return PersonaProfile(
        key=key,
        version=version,
        origin="managed",
        status=status,
        kind="managed_persona",
        display_name=f"{key}-{version}",
        enabled=True,
        handle=None,
        canonical_target_id=f"persona:{key}",
        parent_profile_key=None,
        parent_profile_version=None,
        legacy_source_version=None,
        system_prompt_fragment="System prompt",
        prompt_append_fragment="Prompt append",
        default_capability_bundle_keys=list(default_capability_bundle_keys or []),
    )


def _build_tool_entry(*, key: str, version: int, status: str) -> CapabilityRegistryEntry:
    return CapabilityRegistryEntry(
        key=key,
        version=version,
        origin="managed",
        status=status,
        type="tool",
        display_name=f"{key}-{version}",
        description="Tool capability",
        approval_mode="not_required",
        adapter_key=key,
        config_schema={"type": "object"},
        transport=None,
        lifecycle=None,
    )


def _build_connector_entry(*, key: str, version: int, status: str) -> CapabilityRegistryEntry:
    return CapabilityRegistryEntry(
        key=key,
        version=version,
        origin="managed",
        status=status,
        type="connector",
        display_name=f"{key}-{version}",
        description="Connector capability",
        approval_mode="required",
        adapter_key=key,
        config_schema={"type": "object"},
        transport="mcp",
        lifecycle="approved",
    )


def _build_bundle_entry(
    *,
    key: str,
    version: int,
    status: str,
    bundle_members: list[dict[str, object]],
) -> CapabilityRegistryEntry:
    return CapabilityRegistryEntry(
        key=key,
        version=version,
        origin="managed",
        status=status,
        type="bundle",
        display_name=f"{key}-{version}",
        description="Bundle capability",
        approval_mode="not_required",
        adapter_key=None,
        bundle_members=bundle_members,
        transport=None,
        lifecycle=None,
    )


def _seed_runtime_rows(session: Session) -> None:
    session.add_all(
        [
            _build_tool_entry(key="tool.workflow", version=1, status="ACTIVE"),
            _build_tool_entry(key="tool.agent", version=1, status="ACTIVE"),
            _build_connector_entry(key="connector.persona", version=1, status="ACTIVE"),
            _build_bundle_entry(
                key="bundle.agent",
                version=1,
                status="ACTIVE",
                bundle_members=[{"key": "tool.agent", "type": "tool", "version": 1}],
            ),
            _build_bundle_entry(
                key="bundle.persona",
                version=1,
                status="ACTIVE",
                bundle_members=[{"key": "connector.persona", "type": "connector", "version": 1}],
            ),
            _build_persona_profile(
                key="persona.agent",
                version=1,
                status="ACTIVE",
                default_capability_bundle_keys=["bundle.persona"],
            ),
            _build_agent_spec(
                key="alpha_agent",
                version=1,
                status="ACTIVE",
                default_capability_bundle_keys=["bundle.agent"],
                default_persona_profile_keys=["persona.agent"],
            ),
            _build_workflow_spec(
                key="alpha_workflow",
                version=1,
                status="ACTIVE",
                graph_definition={
                    "entryStepKey": "analysis",
                    "steps": [{"stepKey": "analysis", "agentSpecKey": "alpha_agent"}],
                },
                default_tool_ids=["tool.workflow"],
                allowed_capability_bundle_keys=["bundle.agent", "bundle.persona"],
            ),
        ]
    )
    session.commit()


def _mutate_latest_active_rows(session: Session) -> None:
    for model, key in [
        (WorkflowSpec, "alpha_workflow"),
        (AgentSpec, "alpha_agent"),
        (PersonaProfile, "persona.agent"),
        (CapabilityRegistryEntry, "tool.workflow"),
        (CapabilityRegistryEntry, "tool.agent"),
        (CapabilityRegistryEntry, "connector.persona"),
        (CapabilityRegistryEntry, "bundle.agent"),
        (CapabilityRegistryEntry, "bundle.persona"),
    ]:
        current = session.scalar(select(model).where(model.key == key, model.status == "ACTIVE"))
        assert current is not None
        current.status = "DEPRECATED"

    session.add_all(
        [
            _build_tool_entry(key="tool.workflow", version=2, status="ACTIVE"),
            _build_tool_entry(key="tool.agent", version=2, status="ACTIVE"),
            _build_connector_entry(key="connector.persona", version=2, status="ACTIVE"),
            _build_bundle_entry(
                key="bundle.agent",
                version=2,
                status="ACTIVE",
                bundle_members=[{"key": "tool.agent", "type": "tool", "version": 2}],
            ),
            _build_bundle_entry(
                key="bundle.persona",
                version=2,
                status="ACTIVE",
                bundle_members=[{"key": "connector.persona", "type": "connector", "version": 2}],
            ),
            _build_persona_profile(
                key="persona.agent",
                version=2,
                status="ACTIVE",
                default_capability_bundle_keys=["bundle.persona"],
            ),
            _build_agent_spec(
                key="alpha_agent",
                version=2,
                status="ACTIVE",
                default_capability_bundle_keys=["bundle.agent"],
                default_persona_profile_keys=["persona.agent"],
            ),
            _build_workflow_spec(
                key="alpha_workflow",
                version=2,
                status="ACTIVE",
                graph_definition={
                    "entryStepKey": "analysis",
                    "steps": [{"stepKey": "analysis", "agentSpecKey": "alpha_agent"}],
                },
                default_tool_ids=["tool.workflow"],
                allowed_capability_bundle_keys=["bundle.agent", "bundle.persona"],
            ),
        ]
    )
    session.commit()


def _build_payload() -> RuntimeRunCreate:
    return RuntimeRunCreate.model_validate(
        {
            "callerType": "api",
            "callerId": 99,
            "callerScopeKey": "agent-runtime-service",
            "executionKind": "workflow",
            "workflowSpecKey": "alpha_workflow",
            "inputs": {"ticker": "MSFT"},
        }
    )


class RecordingAdapter:
    def __init__(
        self,
        *,
        results: dict[str, ExecutionAdapterResult] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.results = dict(results or {})
        self.errors = dict(errors or {})
        self.requests: list[ExecutionAdapterRequest] = []

    def execute(self, request: ExecutionAdapterRequest) -> ExecutionAdapterResult:
        self.requests.append(request)
        error = self.errors.get(request.dispatch_mode)
        if error is not None:
            raise error
        try:
            return self.results[request.dispatch_mode]
        except KeyError as exc:  # pragma: no cover - defensive test helper
            raise AssertionError(
                f"No adapter result configured for {request.dispatch_mode}"
            ) from exc


def test_adapter_failure_after_shell_creation_leaves_frozen_run_inspectable(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_runtime_rows(session)
        service = AgentRuntimeService(session)
        adapter = RecordingAdapter(errors={"start": RuntimeError("adapter boom")})

        with pytest.raises(RuntimeError, match="adapter boom"):
            service.run(_build_payload(), adapter)

        run = RuntimeRunRepository(session).get_latest_attempt(
            caller_type="api",
            caller_id=99,
            caller_scope_key="agent-runtime-service",
        )
        assert run is not None
        read_run = service.get_run(run.id)
        artifact = service.get_artifact(run.id)
        trace_events = RuntimeTraceEventRepository(session).list_for_run(run.id)

        assert read_run.status == "FAILED"
        assert read_run.model_dump(mode="json", by_alias=True)["terminalError"] == {
            "code": "adapter_execution_failed",
            "message": "adapter boom",
        }
        assert trace_events[0].event_type == "RUN_CREATED"
        assert trace_events[-1].event_type == "RUN_FAILED"
        assert artifact.resolved_workflow_agent_refs is not None
        assert artifact.resolved_workflow_agent_refs[0].agent_spec_version == 1
        assert [cap.capability_version for cap in artifact.resolved_capabilities] == [1, 1, 1]


def test_waiting_approval_persists_checkpoint_and_resume_uses_frozen_snapshot(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_runtime_rows(session)
        service = AgentRuntimeService(session)
        adapter = RecordingAdapter(
            results={
                "start": ExecutionAdapterResult(
                    status="WAITING_APPROVAL",
                    trace_events=(
                        ExecutionAdapterTraceEvent(event_type="STEP_STARTED", step_key="analysis"),
                    ),
                    approval_requests=(
                        ExecutionApprovalRequest(
                            step_key="analysis",
                            capability_key="connector.persona",
                        ),
                    ),
                    checkpoints=(
                        ExecutionCheckpointRecord(
                            checkpoint_index=0,
                            step_key="analysis",
                            serialized_state={"cursor": "approval"},
                        ),
                    ),
                ),
                "resume": ExecutionAdapterResult(
                    status="SUCCEEDED",
                    trace_events=(
                        ExecutionAdapterTraceEvent(
                            event_type="STEP_COMPLETED", step_key="analysis"
                        ),
                    ),
                    artifact_patch=ExecutionArtifactPatch(final_output={"message": "done"}),
                ),
            }
        )

        initial_run = service.run(_build_payload(), adapter)
        assert initial_run.status == "WAITING_APPROVAL"
        assert initial_run.approval_summary.pending_count == 1

        approval = RuntimeApprovalRepository(session).list_pending_for_run(initial_run.run_id)[0]
        checkpoint = RuntimeCheckpointRepository(session).get_latest_for_run(initial_run.run_id)
        assert checkpoint is not None
        assert checkpoint.serialized_state == {"cursor": "approval"}

        _mutate_latest_active_rows(session)

        approval.status = "APPROVED"
        approval.actor = "tester"
        approval.reason = "approved"
        approval.resolved_at = utcnow()
        session.commit()

        resumed = service.resume_run(initial_run.run_id, adapter)
        resume_request = adapter.requests[-1]

        assert resume_request.dispatch_mode == "resume"
        assert resume_request.snapshot.workflow_spec_version == 1
        assert resume_request.snapshot.resolved_workflow_agent_refs[0].agent_spec_version == 1
        assert [
            ref.persona_profile_version
            for ref in resume_request.snapshot.resolved_persona_profile_refs
        ] == [1]
        assert [
            cap.capability_version
            for cap in resume_request.snapshot.resolved_capabilities
            if cap.capability_key in {"tool.workflow", "tool.agent", "connector.persona"}
        ] == [1, 1, 1]
        assert resume_request.current_checkpoint is not None
        assert resume_request.current_checkpoint.serialized_state == {"cursor": "approval"}
        assert [approval_state.status for approval_state in resume_request.approvals] == [
            "APPROVED"
        ]
        assert resumed.status == "SUCCEEDED"
        assert resumed.final_output == {"message": "done"}


def test_retry_uses_frozen_snapshot_not_latest_active_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_runtime_rows(session)
        service = AgentRuntimeService(session)
        failing_adapter = RecordingAdapter(errors={"start": RuntimeError("retry me")})

        with pytest.raises(RuntimeError, match="retry me"):
            service.run(_build_payload(), failing_adapter)

        failed_run = RuntimeRunRepository(session).get_latest_attempt(
            caller_type="api",
            caller_id=99,
            caller_scope_key="agent-runtime-service",
        )
        assert failed_run is not None

        _mutate_latest_active_rows(session)

        retry_adapter = RecordingAdapter(
            results={
                "retry": ExecutionAdapterResult(
                    status="SUCCEEDED",
                    trace_events=(
                        ExecutionAdapterTraceEvent(
                            event_type="STEP_COMPLETED", step_key="analysis"
                        ),
                    ),
                    artifact_patch=ExecutionArtifactPatch(final_output={"message": "retried"}),
                )
            }
        )

        retried = service.retry_run(failed_run.id, retry_adapter)
        retry_request = retry_adapter.requests[0]

        assert retry_request.dispatch_mode == "retry"
        assert retry_request.snapshot.workflow_spec_version == 1
        assert retry_request.snapshot.resolved_workflow_agent_refs[0].agent_spec_version == 1
        assert [
            ref.persona_profile_version
            for ref in retry_request.snapshot.resolved_persona_profile_refs
        ] == [1]
        assert [
            cap.capability_version
            for cap in retry_request.snapshot.resolved_capabilities
            if cap.capability_key in {"tool.workflow", "tool.agent", "connector.persona"}
        ] == [1, 1, 1]
        assert retried.status == "SUCCEEDED"
        assert retried.attempt_number == 2
        assert retried.final_output == {"message": "retried"}
