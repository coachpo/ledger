from __future__ import annotations

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db.session import init_db
from app.db.upgrades import upgrade_legacy_schema
from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.runtime_run import RuntimeRun
from app.models.workflow_spec import WorkflowSpec
from app.services.runtime_seed_catalog import (
    SEEDED_AGENT_SPECS,
    SEEDED_BUILTIN_SPECS,
    SEEDED_CAPABILITY_BUNDLE_SPECS,
    SEEDED_CONNECTOR_SPECS,
    SEEDED_TOOL_SPECS,
)

RUNTIME_V2_TABLE_NAMES = {
    "agent_specs",
    "workflow_specs",
    "persona_profiles",
    "capability_registry_entries",
    "runtime_runs",
    "runtime_trace_events",
    "runtime_approvals",
    "runtime_checkpoints",
    "runtime_run_artifacts",
    "persona_projection_events",
}

_SEEDED_BUILTIN_BY_KEY = {
    builtin.canonical_target_id: builtin.description for builtin in SEEDED_BUILTIN_SPECS
}

_SEEDED_CAPABILITY_BY_KEY = {
    **{tool.tool_id: tool.description for tool in SEEDED_TOOL_SPECS},
    **{bundle.bundle_key: bundle.description for bundle in SEEDED_CAPABILITY_BUNDLE_SPECS},
    **{connector.connector_id: connector.description for connector in SEEDED_CONNECTOR_SPECS},
}

_DECISION_WRITER_LEGACY_BACKTEST_INSTRUCTIONS = (
    "Render the final backtest analysis report and translate reviewed analyses into "
    "Ledger trade decisions."
)
_CYCLE_CONTEXT_LOOKUP_LEGACY_DESCRIPTION = (
    "Read prepared cycle prompt and runtime artifacts from the historical "
    "simulation execution path."
)


def test_init_db_creates_runtime_v2_tables_and_indexes(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        assert RUNTIME_V2_TABLE_NAMES <= set(inspector.get_table_names())

        with engine.connect() as connection:
            agent_spec_indexes = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'agent_specs'"
                )
            }

        assert {
            "uq_agent_specs_active_key",
            "uq_agent_specs_draft_key",
        } <= agent_spec_indexes
        assert {
            constraint["name"] for constraint in inspector.get_unique_constraints("runtime_runs")
        } >= {"uq_runtime_runs_caller_scope_attempt"}
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_recreates_missing_runtime_v2_tables(session_factory) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            for table_name in sorted(RUNTIME_V2_TABLE_NAMES):
                connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')

    upgrade_legacy_schema(engine)

    table_names = set(inspect(engine).get_table_names())
    assert RUNTIME_V2_TABLE_NAMES <= table_names


def test_init_db_archives_legacy_seeded_workflow_specs(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with Session(engine) as session:
            session.add_all(
                [
                    WorkflowSpec(
                        key="seeded_internal_backtest_v1",
                        version=1,
                        origin="seeded",
                        status="ACTIVE",
                        name="Legacy seeded backtest workflow",
                        graph_definition={"steps": []},
                        final_output_contract={"kind": "json", "schema": {}, "description": ""},
                        mention_policy={
                            "version": 1,
                            "allowCharacterPersonas": False,
                            "allowedBuiltinHandles": [],
                        },
                        execution_mode="structured_output",
                        default_tool_ids=[],
                        allowed_capability_bundle_keys=[],
                        connector_ids=[],
                        review_mode=None,
                        approval_policy_overrides=[],
                    ),
                    WorkflowSpec(
                        key="managed_runtime_workflow",
                        version=1,
                        origin="managed",
                        status="ACTIVE",
                        name="Managed runtime workflow",
                        graph_definition={"steps": []},
                        final_output_contract={"kind": "json", "schema": {}, "description": ""},
                        mention_policy={
                            "version": 1,
                            "allowCharacterPersonas": True,
                            "allowedBuiltinHandles": [],
                        },
                        execution_mode="structured_output",
                        default_tool_ids=[],
                        allowed_capability_bundle_keys=[],
                        connector_ids=[],
                        review_mode=None,
                        approval_policy_overrides=[],
                    ),
                ]
            )
            session.commit()

        init_db(database_url)

        with Session(engine) as session:
            rows = session.scalars(select(WorkflowSpec).order_by(WorkflowSpec.key.asc())).all()

        assert [(row.key, row.origin, row.status) for row in rows] == [
            ("managed_runtime_workflow", "managed", "ACTIVE"),
            ("seeded_internal_backtest_v1", "seeded", "ARCHIVED"),
        ]
    finally:
        engine.dispose()


def test_init_db_is_idempotent_and_preserves_existing_runtime_rows(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with Session(engine) as session:
            session.add(
                AgentSpec(
                    key="idempotent_agent",
                    version=1,
                    origin="managed",
                    status="ACTIVE",
                    name="Idempotent Agent",
                    instructions="Remain stable.",
                    model_policy={"model": "gpt-5.4-mini"},
                    final_output_contract={
                        "kind": "text",
                        "schema": None,
                        "description": "Stable output",
                    },
                    default_capability_bundle_keys=[],
                    default_persona_profile_keys=[],
                )
            )
            session.add(
                RuntimeRun(
                    caller_type="tryout",
                    caller_id=None,
                    execution_kind="workflow",
                    workflow_spec_key="runtime_idempotent_workflow",
                    workflow_spec_version=1,
                    agent_spec_key=None,
                    agent_spec_version=None,
                    caller_scope_key=None,
                    caller_identity_key=None,
                    attempt_number=1,
                    status="QUEUED",
                    input_hash="a" * 64,
                    output_hash=None,
                    retention_class="persistent",
                )
            )
            session.commit()

        init_db(database_url)

        with engine.connect() as connection:
            counts = connection.exec_driver_sql(
                "SELECT "
                "(SELECT COUNT(*) FROM agent_specs WHERE origin = 'managed'), "
                "(SELECT COUNT(*) FROM agent_specs WHERE origin = 'seeded'), "
                "(SELECT COUNT(*) FROM runtime_runs), "
                "(SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND indexname = 'uq_runtime_runs_caller_scope_attempt')"
            ).one()

        assert counts == (1, len(SEEDED_AGENT_SPECS), 1, 1)
    finally:
        engine.dispose()


def test_init_db_rewrites_known_legacy_seeded_runtime_text_drift(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        decision_writer = next(
            agent for agent in SEEDED_AGENT_SPECS if agent.key == "decision_writer"
        )

        with Session(engine) as session:
            seeded_agent_row = session.scalar(
                select(AgentSpec).where(
                    AgentSpec.key == decision_writer.key,
                    AgentSpec.version == 1,
                    AgentSpec.origin == "seeded",
                )
            )
            seeded_capability_row = session.scalar(
                select(CapabilityRegistryEntry).where(
                    CapabilityRegistryEntry.key == "ledger.cycle_context_lookup",
                    CapabilityRegistryEntry.version == 1,
                    CapabilityRegistryEntry.origin == "seeded",
                )
            )
            assert seeded_agent_row is not None
            assert seeded_capability_row is not None
            seeded_agent_row.instructions = _DECISION_WRITER_LEGACY_BACKTEST_INSTRUCTIONS
            seeded_capability_row.description = _CYCLE_CONTEXT_LOOKUP_LEGACY_DESCRIPTION
            session.commit()

        init_db(database_url)

        with Session(engine) as session:
            rewritten_agent_row = session.scalar(
                select(AgentSpec).where(
                    AgentSpec.key == decision_writer.key,
                    AgentSpec.version == 1,
                    AgentSpec.origin == "seeded",
                )
            )
            rewritten_capability_row = session.scalar(
                select(CapabilityRegistryEntry).where(
                    CapabilityRegistryEntry.key == "ledger.cycle_context_lookup",
                    CapabilityRegistryEntry.version == 1,
                    CapabilityRegistryEntry.origin == "seeded",
                )
            )
            assert rewritten_agent_row is not None
            assert rewritten_capability_row is not None
            assert rewritten_agent_row.instructions == decision_writer.system_prompt
            assert (
                rewritten_capability_row.description
                == _SEEDED_CAPABILITY_BY_KEY["ledger.cycle_context_lookup"]
            )
    finally:
        engine.dispose()



def test_init_db_replay_preserves_seeded_and_managed_runtime_seed_mirror_rows(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    seeded_agent = SEEDED_AGENT_SPECS[0]
    seeded_builtin = SEEDED_BUILTIN_SPECS[0]
    seeded_connector = SEEDED_CONNECTOR_SPECS[0]

    try:
        with Session(engine) as session:
            session.add_all(
                [
                    AgentSpec(
                        key=seeded_agent.key,
                        version=2,
                        origin="managed",
                        status="DRAFT",
                        name=f"{seeded_agent.role} Draft",
                        instructions="Managed draft instructions.",
                        model_policy={"model": "gpt-5.4-mini"},
                        final_output_contract={
                            "kind": "text",
                            "schema": None,
                            "description": "Managed draft output",
                        },
                        default_capability_bundle_keys=[],
                        default_persona_profile_keys=[],
                    ),
                    WorkflowSpec(
                        key="managed_runtime_workflow",
                        version=2,
                        origin="managed",
                        status="DRAFT",
                        name="Managed runtime workflow draft",
                        graph_definition={
                            "kind": "managed_workflow",
                            "steps": [
                                {
                                    "key": "analysis",
                                    "agent_key": seeded_agent.key,
                                    "agent_version": 2,
                                }
                            ],
                        },
                        final_output_contract={
                            "kind": "json_schema",
                            "schema": {"type": "object"},
                            "description": "Managed draft contract",
                        },
                        mention_policy={
                            "version": 1,
                            "allow_characters": True,
                            "allowed_builtin_handles": ["librarian"],
                        },
                        execution_mode="structured_output",
                        default_tool_ids=[],
                        allowed_capability_bundle_keys=[],
                        connector_ids=[],
                        review_mode=None,
                        approval_policy_overrides=[],
                    ),
                    PersonaProfile(
                        key=seeded_builtin.canonical_target_id,
                        version=2,
                        origin="managed",
                        status="DRAFT",
                        kind="managed_persona",
                        display_name=f"Managed {seeded_builtin.display_name} Draft",
                        enabled=True,
                        handle=seeded_builtin.handle,
                        canonical_target_id=seeded_builtin.canonical_target_id,
                        parent_profile_key=None,
                        parent_profile_version=None,
                        legacy_entity_type=None,
                        legacy_entity_key=None,
                        legacy_source_version=None,
                        system_prompt_fragment="Managed draft system prompt.",
                        prompt_append_fragment="Managed draft append.",
                        default_capability_bundle_keys=list(seeded_builtin.capability_bundle_keys),
                    ),
                    CapabilityRegistryEntry(
                        key=seeded_connector.connector_id,
                        version=2,
                        origin="managed",
                        status="DRAFT",
                        type="connector",
                        display_name=f"Managed {seeded_connector.display_name} Draft",
                        description="Managed connector draft.",
                        approval_mode="required",
                        adapter_key=seeded_connector.connector_id,
                        config_schema={
                            "type": "object",
                            "properties": {"symbol": {"type": "string"}},
                            "required": ["symbol"],
                            "additionalProperties": False,
                        },
                        bundle_members=None,
                        transport=seeded_connector.transport,
                        lifecycle=seeded_connector.lifecycle,
                    ),
                ]
            )
            session.commit()

        init_db(database_url)

        with Session(engine) as session:
            managed_agent_rows = session.scalars(
                select(AgentSpec).where(AgentSpec.origin == "managed")
            ).all()
            managed_workflow_rows = session.scalars(
                select(WorkflowSpec).where(WorkflowSpec.origin == "managed")
            ).all()
            managed_persona_rows = session.scalars(
                select(PersonaProfile).where(PersonaProfile.origin == "managed")
            ).all()
            managed_capability_rows = session.scalars(
                select(CapabilityRegistryEntry).where(CapabilityRegistryEntry.origin == "managed")
            ).all()

            assert len(managed_agent_rows) == 1
            assert len(managed_workflow_rows) == 1
            assert len(managed_persona_rows) == 1
            assert len(managed_capability_rows) == 1

            assert len(
                session.scalars(select(AgentSpec).where(AgentSpec.origin == "seeded")).all()
            ) == len(SEEDED_AGENT_SPECS)
            assert (
                len(
                    session.scalars(
                        select(WorkflowSpec).where(WorkflowSpec.origin == "seeded")
                    ).all()
                )
                == 0
            )
            assert len(
                session.scalars(
                    select(PersonaProfile).where(PersonaProfile.origin == "seeded")
                ).all()
            ) == len(SEEDED_BUILTIN_SPECS)
            assert len(
                session.scalars(
                    select(CapabilityRegistryEntry).where(
                        CapabilityRegistryEntry.origin == "seeded"
                    )
                ).all()
            ) == (
                len(SEEDED_TOOL_SPECS)
                + len(SEEDED_CONNECTOR_SPECS)
                + len(SEEDED_CAPABILITY_BUNDLE_SPECS)
            )

            agent_rows = session.scalars(
                select(AgentSpec)
                .where(AgentSpec.key == seeded_agent.key)
                .order_by(AgentSpec.version.asc())
            ).all()
            workflow_rows = session.scalars(
                select(WorkflowSpec)
                .where(WorkflowSpec.key == "managed_runtime_workflow")
                .order_by(WorkflowSpec.version.asc())
            ).all()
            persona_rows = session.scalars(
                select(PersonaProfile)
                .where(PersonaProfile.key == seeded_builtin.canonical_target_id)
                .order_by(PersonaProfile.version.asc())
            ).all()
            capability_rows = session.scalars(
                select(CapabilityRegistryEntry)
                .where(CapabilityRegistryEntry.key == seeded_connector.connector_id)
                .order_by(CapabilityRegistryEntry.version.asc())
            ).all()

        assert [(row.version, row.origin, row.status) for row in agent_rows] == [
            (1, "seeded", "ACTIVE"),
            (2, "managed", "DRAFT"),
        ]
        assert agent_rows[1].name == f"{seeded_agent.role} Draft"
        assert agent_rows[1].model_policy == {"model": "gpt-5.4-mini"}

        assert [(row.version, row.origin, row.status) for row in workflow_rows] == [
            (2, "managed", "DRAFT"),
        ]
        assert workflow_rows[0].graph_definition == {
            "kind": "managed_workflow",
            "steps": [
                {
                    "key": "analysis",
                    "agent_key": seeded_agent.key,
                    "agent_version": 2,
                }
            ],
        }
        assert workflow_rows[0].mention_policy == {
            "version": 1,
            "allow_characters": True,
            "allowed_builtin_handles": ["librarian"],
        }

        assert [(row.version, row.origin, row.status) for row in persona_rows] == [
            (1, "seeded", "ACTIVE"),
            (2, "managed", "DRAFT"),
        ]
        assert persona_rows[1].display_name == f"Managed {seeded_builtin.display_name} Draft"
        assert persona_rows[1].handle == seeded_builtin.handle
        assert persona_rows[1].prompt_append_fragment == "Managed draft append."

        assert [(row.version, row.origin, row.status) for row in capability_rows] == [
            (1, "seeded", "ACTIVE"),
            (2, "managed", "DRAFT"),
        ]
        assert capability_rows[1].type == "connector"
        assert capability_rows[1].transport == seeded_connector.transport
        assert capability_rows[1].lifecycle == seeded_connector.lifecycle
        assert capability_rows[1].bundle_members is None
    finally:
        engine.dispose()
