from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.workflow_spec import WorkflowSpec
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.schemas.runtime import RuntimeRunCreate
from app.services.agent_runtime_service import AgentRuntimeService


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
    connector_ids: list[str] | None = None,
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
        connector_ids=list(connector_ids or []),
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


def _seed_resolution_rows(session: Session) -> None:
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


def test_prepare_run_persists_complete_frozen_shell_before_execution(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_resolution_rows(session)
        service = AgentRuntimeService(session)
        payload = RuntimeRunCreate.model_validate(
            {
                "callerType": "api",
                "callerId": 12,
                "callerScopeKey": "resolution-shell",
                "executionKind": "workflow",
                "workflowSpecKey": "alpha_workflow",
                "inputs": {"ticker": "MSFT"},
            }
        )

        prepared = service.prepare_run(payload)
        run = service.get_run(prepared.run_id)
        artifact = service.get_artifact(prepared.run_id)
        trace_events = RuntimeTraceEventRepository(session).list_for_run(prepared.run_id)

        assert run.status == "QUEUED"
        assert run.trace_summary.event_count == 1
        assert run.approval_summary.total_count == 0
        assert prepared.snapshot.workflow_spec_version == 1
        assert [step.step_key for step in prepared.snapshot.resolved_workflow_agent_refs] == [
            "analysis"
        ]
        assert [
            (step.agent_spec_key, step.agent_spec_version)
            for step in prepared.snapshot.resolved_workflow_agent_refs
        ] == [("alpha_agent", 1)]
        assert [
            ref.persona_profile_key for ref in prepared.snapshot.resolved_persona_profile_refs
        ] == ["persona.agent"]
        assert [cap.capability_key for cap in prepared.snapshot.resolved_capabilities] == [
            "connector.persona",
            "tool.agent",
            "tool.workflow",
        ]
        assert [bundle.bundle_key for bundle in prepared.snapshot.resolved_bundle_versions] == [
            "bundle.agent",
            "bundle.persona",
        ]
        assert [tool.tool_id for tool in prepared.snapshot.resolved_tool_versions] == [
            "tool.agent",
            "tool.workflow",
        ]
        assert [
            connector.connector_id for connector in prepared.snapshot.resolved_connector_versions
        ] == ["connector.persona"]

        assert artifact.resolved_workflow_agent_refs is not None
        assert [step.step_key for step in artifact.resolved_workflow_agent_refs] == ["analysis"]
        assert [cap.capability_key for cap in artifact.resolved_capabilities] == [
            "connector.persona",
            "tool.agent",
            "tool.workflow",
        ]
        assert trace_events[0].event_type == "RUN_CREATED"
        assert trace_events[0].payload["inputs"] == {"ticker": "MSFT"}


def test_prepare_run_derives_step_plan_from_seeded_topology_shape(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_agent_spec(key="alpha_agent", version=1, status="ACTIVE"),
                _build_agent_spec(key="review_agent", version=1, status="ACTIVE"),
                _build_workflow_spec(
                    key="seeded_topology_workflow",
                    version=1,
                    status="ACTIVE",
                    graph_definition={
                        "kind": "seeded_langgraph_topology",
                        "topology_key": "seeded_topology_workflow",
                        "entry_agent_key": "alpha_agent",
                        "agent_order": ["alpha_agent", "review_agent"],
                        "review_mode": "conservative",
                    },
                ),
            ]
        )
        session.commit()

        service = AgentRuntimeService(session)
        payload = RuntimeRunCreate.model_validate(
            {
                "callerType": "api",
                "callerId": 13,
                "callerScopeKey": "seeded-topology",
                "executionKind": "workflow",
                "workflowSpecKey": "seeded_topology_workflow",
                "inputs": {"topic": "AAPL"},
            }
        )

        prepared = service.prepare_run(payload)

        assert [step.step_key for step in prepared.snapshot.resolved_workflow_agent_refs] == [
            "alpha_agent",
            "review_agent",
        ]
        assert [step.agent_spec_key for step in prepared.snapshot.resolved_workflow_agent_refs] == [
            "alpha_agent",
            "review_agent",
        ]
