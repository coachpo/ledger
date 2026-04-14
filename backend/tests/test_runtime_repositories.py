from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.workflow_spec import WorkflowSpec
from app.repositories.agent_spec import AgentSpecRepository
from app.repositories.capability_registry_entry import CapabilityRegistryEntryRepository
from app.repositories.persona_profile import PersonaProfileRepository
from app.repositories.runtime_approval import RuntimeApprovalRepository
from app.repositories.runtime_control_flag import RuntimeControlFlagRepository
from app.repositories.runtime_flag_change_event import RuntimeFlagChangeEventRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_run_artifact import RuntimeRunArtifactRepository
from app.repositories.workflow_spec import WorkflowSpecRepository
from app.services.runtime_control_service import RuntimeControlService


def _build_agent_spec(*, key: str, version: int, status: str) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        instructions="Follow the workflow.",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "text", "schema": None, "description": "Output"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_workflow_spec(*, key: str, version: int, status: str) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        graph_definition={
            "entryStepKey": "step-1",
            "steps": [{"stepKey": "step-1", "agentSpecKey": "alpha_agent"}],
        },
        final_output_contract={"kind": "markdown", "schema": None, "description": "Output"},
        mention_policy={"version": 1, "allowCharacterPersonas": False, "allowedBuiltinHandles": []},
        execution_mode=None,
        default_tool_ids=[],
        allowed_capability_bundle_keys=[],
        connector_ids=[],
        review_mode=None,
        approval_policy_overrides=[],
    )


def _build_persona_profile(*, key: str, version: int, status: str) -> PersonaProfile:
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
        default_capability_bundle_keys=[],
    )


def _build_capability_entry(*, key: str, version: int, status: str) -> CapabilityRegistryEntry:
    return CapabilityRegistryEntry(
        key=key,
        version=version,
        origin="managed",
        status=status,
        type="tool",
        display_name=f"{key}-{version}",
        description="Capability description",
        approval_mode="not_required",
        adapter_key=key,
        config_schema={"type": "object"},
        transport=None,
        lifecycle=None,
    )


def _build_runtime_run(
    *,
    caller_type: str,
    caller_id: int | None,
    caller_scope_key: str | None,
    workflow_spec_key: str | None,
    workflow_spec_version: int | None,
    agent_spec_key: str | None,
    agent_spec_version: int | None,
    attempt_number: int,
    status: str,
    input_hash_seed: str,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type=caller_type,
        caller_id=caller_id,
        execution_kind="workflow" if workflow_spec_key is not None else "single_agent",
        workflow_spec_key=workflow_spec_key,
        workflow_spec_version=workflow_spec_version,
        agent_spec_key=agent_spec_key,
        agent_spec_version=agent_spec_version,
        caller_scope_key=caller_scope_key,
        caller_identity_key=None,
        attempt_number=attempt_number,
        status=status,
        input_hash=input_hash_seed * 64,
        output_hash=None,
        retention_class="persistent",
    )


def _seed_versioned_rows(session: Session) -> None:
    session.add_all(
        [
            _build_agent_spec(key="alpha_agent", version=1, status="ACTIVE"),
            _build_agent_spec(key="alpha_agent", version=2, status="DRAFT"),
            _build_agent_spec(key="beta_agent", version=1, status="ACTIVE"),
            _build_workflow_spec(key="alpha_workflow", version=1, status="ACTIVE"),
            _build_workflow_spec(key="alpha_workflow", version=2, status="DRAFT"),
            _build_persona_profile(key="alpha_persona", version=1, status="ACTIVE"),
            _build_persona_profile(key="alpha_persona", version=2, status="DRAFT"),
            _build_capability_entry(key="tool.alpha", version=1, status="ACTIVE"),
            _build_capability_entry(key="tool.alpha", version=2, status="DRAFT"),
        ]
    )
    session.commit()


def test_versioned_repositories_resolve_active_versions_and_latest_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_versioned_rows(session)

        agent_repo = AgentSpecRepository(session)
        workflow_repo = WorkflowSpecRepository(session)
        persona_repo = PersonaProfileRepository(session)
        capability_repo = CapabilityRegistryEntryRepository(session)

        active_agent = agent_repo.resolve_version("alpha_agent", None)
        draft_agent = agent_repo.resolve_version("alpha_agent", 2)
        assert active_agent is not None
        assert active_agent.version == 1
        assert draft_agent is not None
        assert draft_agent.status == "DRAFT"
        assert [item.version for item in agent_repo.list_versions("alpha_agent")] == [2, 1]
        assert [item.key for item in agent_repo.list_latest_versions(origin="managed")] == [
            "alpha_agent",
            "beta_agent",
        ]

        active_workflow = workflow_repo.get_active_by_key("alpha_workflow")
        draft_workflow = workflow_repo.get_draft_by_key("alpha_workflow")
        assert active_workflow is not None
        assert active_workflow.version == 1
        assert draft_workflow is not None
        assert draft_workflow.version == 2

        active_persona = persona_repo.get_active_by_key("alpha_persona")
        draft_persona = persona_repo.get_draft_by_key("alpha_persona")
        assert active_persona is not None
        assert active_persona.version == 1
        assert draft_persona is not None
        assert draft_persona.version == 2

        active_capability = capability_repo.get_active_by_key("tool.alpha")
        draft_capability = capability_repo.get_draft_by_key("tool.alpha")
        assert active_capability is not None
        assert active_capability.version == 1
        assert draft_capability is not None
        assert draft_capability.version == 2


def test_runtime_repositories_filter_by_caller_scope_and_artifact_contracts(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first_run = _build_runtime_run(
            caller_type="backtest",
            caller_id=42,
            caller_scope_key="2026-01-06",
            workflow_spec_key="seeded_internal_backtest_v1",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            attempt_number=1,
            status="FAILED",
            input_hash_seed="1",
        )
        second_run = _build_runtime_run(
            caller_type="backtest",
            caller_id=42,
            caller_scope_key="2026-01-06",
            workflow_spec_key="seeded_internal_backtest_v1",
            workflow_spec_version=1,
            agent_spec_key=None,
            agent_spec_version=None,
            attempt_number=2,
            status="RUNNING",
            input_hash_seed="2",
        )
        tryout_run = _build_runtime_run(
            caller_type="tryout",
            caller_id=None,
            caller_scope_key=None,
            workflow_spec_key=None,
            workflow_spec_version=None,
            agent_spec_key="alpha_agent",
            agent_spec_version=1,
            attempt_number=1,
            status="WAITING_APPROVAL",
            input_hash_seed="3",
        )
        session.add_all([first_run, second_run, tryout_run])
        session.commit()

        approval = RuntimeApproval(
            run_id=second_run.id,
            step_key="review",
            capability_key="tool.alpha",
            status="PENDING",
        )
        session.add(approval)
        session.add(
            RuntimeRunArtifact(
                run_id=second_run.id,
                entry_prompt_hash="a" * 64,
                full_user_prompt_hash="b" * 64,
                raw_mention_handles=["@librarian"],
                resolved_persona_profile_refs=[
                    {
                        "personaProfileKey": "alpha_persona",
                        "personaProfileVersion": 1,
                        "canonicalTargetId": "persona:alpha_persona",
                    }
                ],
                resolved_builtin_versions=[],
                resolved_role_versions=[],
                resolved_character_versions=[],
                resolved_bundle_versions=[],
                resolved_tool_versions=[],
                resolved_connector_versions=[],
                mentioned_target_outputs=[],
                resolved_mentions=[],
                resolved_capabilities=[
                    {
                        "capabilityKey": "tool.alpha",
                        "capabilityVersion": 1,
                        "capabilityType": "tool",
                        "approvalMode": "not_required",
                        "effectiveConfig": {},
                    }
                ],
            )
        )
        session.commit()

        RuntimeControlService(session).set_backtest_runtime_v2_enabled(
            enabled=True,
            actor="system",
            reason="rollout",
        )

        run_repo = RuntimeRunRepository(session)
        approval_repo = RuntimeApprovalRepository(session)
        artifact_repo = RuntimeRunArtifactRepository(session)
        control_flag_repo = RuntimeControlFlagRepository(session)
        flag_event_repo = RuntimeFlagChangeEventRepository(session)

        scoped_runs = run_repo.list_for_caller(
            caller_type="backtest",
            caller_id=42,
            caller_scope_key="2026-01-06",
        )
        assert [run.attempt_number for run in scoped_runs] == [2, 1]
        latest_attempt = run_repo.get_latest_attempt(
            caller_type="backtest",
            caller_id=42,
            caller_scope_key="2026-01-06",
        )
        active_run = run_repo.get_active_for_caller(
            caller_type="backtest",
            caller_id=42,
            caller_scope_key="2026-01-06",
        )
        assert latest_attempt is not None
        assert latest_attempt.attempt_number == 2
        assert active_run is not None
        assert active_run.status == "RUNNING"
        assert [run.caller_type for run in run_repo.list_tryouts()] == ["tryout"]

        filtered_approvals = approval_repo.list_all(
            caller_type="backtest",
            caller_id=42,
            workflow_spec_key="seeded_internal_backtest_v1",
            capability_key="tool.alpha",
            status="PENDING",
        )
        assert [item.id for item in filtered_approvals] == [approval.id]

        filtered_artifacts = artifact_repo.list_all(
            caller_type="backtest",
            caller_id=42,
            workflow_spec_key="seeded_internal_backtest_v1",
            persona_profile_key="alpha_persona",
            capability_key="tool.alpha",
        )
        assert [item.run_id for item in filtered_artifacts] == [second_run.id]

        flag = control_flag_repo.get_by_key("AGENT_RUNTIME_V2_BACKTESTS_ENABLED")
        assert flag is not None
        assert flag.enabled is True
        assert [
            event.result
            for event in flag_event_repo.list_for_flag("AGENT_RUNTIME_V2_BACKTESTS_ENABLED")
        ] == ["applied"]
