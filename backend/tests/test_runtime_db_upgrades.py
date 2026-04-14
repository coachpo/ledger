from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db.session import init_db
from app.db.upgrades import upgrade_legacy_schema
from app.langgraph.seeds import (
    BACKTEST_PATTERN_SPECS,
    SEEDED_AGENT_SPECS,
    SEEDED_BUILTIN_SPECS,
    SEEDED_CAPABILITY_BUNDLE_SPECS,
    SEEDED_CONNECTOR_SPECS,
    SEEDED_TOOL_SPECS,
)
from app.models.agent_spec import AgentSpec
from app.models.backtest import Backtest
from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot
from app.models.balance import Balance
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate
from app.models.workflow_spec import WorkflowSpec
from app.services.runtime_control_service import RuntimeControlService

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
    "runtime_control_flags",
    "runtime_flag_change_events",
}


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
            runtime_run_indexes = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = 'runtime_runs'"
                )
            }

        assert {
            "uq_agent_specs_active_key",
            "uq_agent_specs_draft_key",
        } <= agent_spec_indexes
        assert "uq_runtime_runs_active_backtest_cycle" in runtime_run_indexes
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


def test_init_db_is_idempotent_and_preserves_existing_runtime_and_snapshot_rows(
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

            portfolio = Portfolio(
                name="Idempotent Portfolio",
                slug="idempotent_portfolio",
                base_currency="USD",
            )
            session.add(portfolio)
            session.flush()

            balance = Balance(
                portfolio_id=portfolio.id,
                label="Cash",
                operation_type="DEPOSIT",
                amount=Decimal("1000.00"),
                currency="USD",
            )
            template = TextTemplate(name="Idempotent Template", content="# Snapshot")
            session.add_all([balance, template])
            session.flush()

            backtest = Backtest(
                portfolio_id=portfolio.id,
                deposit_balance_id=balance.id,
                name="Idempotent Backtest",
                status="RUNNING",
                frequency="DAILY",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 31),
                total_cycles=5,
                completed_cycles=1,
                template_id=template.id,
                webhook_url="http://localhost:5678/webhook/idempotent",
                webhook_timeout=600,
                price_mode="CLOSING_PRICE",
                commission_mode="ZERO",
                commission_value=Decimal("0"),
                benchmark_symbols=["^GSPC"],
            )
            session.add(backtest)
            session.flush()

            session.add(
                BacktestOrchestrationSnapshot(
                    backtest_id=backtest.id,
                    cycle_date=date(2024, 6, 21),
                    prompt_report_slug="backtest_1_prompt_20240621",
                    orchestration_pattern_key="seeded_internal_backtest_v1",
                    pattern_policy_version=1,
                    entry_prompt_hash="1" * 64,
                    full_user_prompt_hash="2" * 64,
                    execution_mode="structured_output",
                    resolved_mentions=[{"handle": "librarian"}],
                    mentioned_target_outputs=[],
                    resolved_builtin_versions=[],
                    resolved_role_versions=[],
                    resolved_character_versions=[],
                    resolved_bundle_versions=[],
                    resolved_tool_versions=[],
                    resolved_connector_versions=[],
                    tool_call_trace=[],
                    approval_trace="not_required",
                )
            )
            session.commit()

            RuntimeControlService(session).set_backtest_runtime_v2_enabled(
                enabled=True,
                actor="test",
                reason="preserve enabled runtime flag across init",
            )

        init_db(database_url)

        with engine.connect() as connection:
            counts = connection.exec_driver_sql(
                "SELECT "
                "(SELECT COUNT(*) FROM agent_specs WHERE origin = 'managed'), "
                "(SELECT COUNT(*) FROM agent_specs WHERE origin = 'seeded'), "
                "(SELECT COUNT(*) FROM runtime_control_flags), "
                "(SELECT COUNT(*) FROM backtest_orchestration_snapshots), "
                "(SELECT enabled FROM runtime_control_flags "
                "WHERE flag_key = 'AGENT_RUNTIME_V2_BACKTESTS_ENABLED'), "
                "(SELECT COUNT(*) FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND indexname = 'uq_runtime_runs_active_backtest_cycle')"
            ).one()
            snapshot_row = connection.exec_driver_sql(
                "SELECT prompt_report_slug, orchestration_pattern_key, approval_trace "
                "FROM backtest_orchestration_snapshots "
                "WHERE cycle_date = DATE '2024-06-21'"
            ).one()

        assert counts == (1, len(SEEDED_AGENT_SPECS), 1, 1, True, 1)
        assert snapshot_row == (
            "backtest_1_prompt_20240621",
            "seeded_internal_backtest_v1",
            "not_required",
        )
    finally:
        engine.dispose()


def test_init_db_replay_preserves_seeded_and_managed_runtime_seed_mirror_rows(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    seeded_agent = SEEDED_AGENT_SPECS[0]
    seeded_workflow = BACKTEST_PATTERN_SPECS[0]
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
                        key=seeded_workflow.key,
                        version=2,
                        origin="managed",
                        status="DRAFT",
                        name="Managed seeded workflow draft",
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
                            "version": seeded_workflow.mention_policy.version,
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
            assert len(
                session.scalars(select(WorkflowSpec).where(WorkflowSpec.origin == "seeded")).all()
            ) == len(BACKTEST_PATTERN_SPECS)
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
                .where(WorkflowSpec.key == seeded_workflow.key)
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
            (1, "seeded", "ACTIVE"),
            (2, "managed", "DRAFT"),
        ]
        assert workflow_rows[1].graph_definition == {
            "kind": "managed_workflow",
            "steps": [
                {
                    "key": "analysis",
                    "agent_key": seeded_agent.key,
                    "agent_version": 2,
                }
            ],
        }
        assert workflow_rows[1].mention_policy == {
            "version": seeded_workflow.mention_policy.version,
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
