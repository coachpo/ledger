from __future__ import annotations

from datetime import date
from decimal import Decimal
from importlib import import_module

from sqlalchemy import inspect

from app.db.upgrades import _migrate_legacy_version_entries, upgrade_legacy_schema
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.base import Base
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate

BacktestOrchestrationSnapshot = import_module(
    "app.models.backtest_orchestration_snapshot"
).BacktestOrchestrationSnapshot


def test_backtest_orchestration_snapshot_table_is_registered() -> None:
    assert BacktestOrchestrationSnapshot.__tablename__ in Base.metadata.tables

    table = Base.metadata.tables[BacktestOrchestrationSnapshot.__tablename__]
    assert {column.name for column in table.columns} == {
        "id",
        "created_at",
        "updated_at",
        "backtest_id",
        "cycle_date",
        "prompt_report_slug",
        "orchestration_pattern_key",
        "pattern_policy_version",
        "entry_prompt_hash",
        "full_user_prompt_hash",
        "execution_mode",
        "resolved_mentions",
        "mentioned_target_outputs",
        "resolved_builtin_versions",
        "resolved_role_versions",
        "resolved_character_versions",
        "resolved_bundle_versions",
        "resolved_tool_versions",
        "resolved_connector_versions",
        "tool_call_trace",
        "approval_trace",
    }


def test_backtest_orchestration_snapshot_table_is_created_by_upgrade(
    session_factory,
) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'DROP TABLE IF EXISTS "backtest_orchestration_snapshots" CASCADE'
            )

    upgrade_legacy_schema(engine)

    with session_factory() as session:
        table_names = (
            session.connection()
            .exec_driver_sql("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
            .scalars()
            .all()
        )

    assert "backtest_orchestration_snapshots" in table_names


def test_new_snapshot_rows_default_plan_b_columns_to_explicit_empty_markers(
    session_factory,
) -> None:
    with session_factory() as session:
        portfolio = Portfolio(
            name="Snapshot Portfolio", slug="snapshot_portfolio", base_currency="USD"
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
        template = TextTemplate(name="Snapshot Template", content="# Snapshot")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Snapshot Backtest",
            status="RUNNING",
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=21,
            completed_cycles=0,
            template_id=template.id,
            webhook_url="http://localhost:5678/webhook/test",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        session.add(backtest)
        session.flush()

        snapshot = BacktestOrchestrationSnapshot(
            backtest_id=backtest.id,
            cycle_date=date(2024, 6, 19),
            prompt_report_slug="backtest_1_prompt_20240619",
            orchestration_pattern_key="seeded_internal_backtest_v1",
            pattern_policy_version=1,
            entry_prompt_hash="5" * 64,
            full_user_prompt_hash="6" * 64,
            resolved_mentions=[{"handle": "librarian"}],
            mentioned_target_outputs=[{"handle": "librarian", "output_markdown": "summary"}],
            resolved_builtin_versions=[{"canonical_target_id": "builtin:librarian", "revision": 1}],
            resolved_role_versions=[],
            resolved_character_versions=[],
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)

        assert {
            "execution_mode": snapshot.execution_mode,
            "resolved_bundle_versions": list(snapshot.resolved_bundle_versions),
            "resolved_tool_versions": list(snapshot.resolved_tool_versions),
            "resolved_connector_versions": list(snapshot.resolved_connector_versions),
            "tool_call_trace": list(snapshot.tool_call_trace),
            "approval_trace": snapshot.approval_trace,
        } == {
            "execution_mode": "structured_output",
            "resolved_bundle_versions": [],
            "resolved_tool_versions": [],
            "resolved_connector_versions": [],
            "tool_call_trace": [],
            "approval_trace": "not_required",
        }


def test_migrate_legacy_version_entries_sorts_object_maps_by_canonical_target_id() -> None:
    migrated = _migrate_legacy_version_entries(
        {
            "role:zeta_role": "7",
            "role:alpha_role": 2,
            "role:beta_role": "v3",
        },
        id_field="role_id",
    )

    assert migrated == [
        {
            "canonical_target_id": "role:alpha_role",
            "role_id": None,
            "version": 2,
        },
        {
            "canonical_target_id": "role:beta_role",
            "role_id": None,
            "version": 3,
        },
        {
            "canonical_target_id": "role:zeta_role",
            "role_id": None,
            "version": 7,
        },
    ]


def test_upgrade_legacy_snapshot_table_replaces_opaque_payload_with_explicit_columns(
    session_factory,
) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'DROP TABLE IF EXISTS "backtest_orchestration_snapshots" CASCADE'
            )
            connection.exec_driver_sql('DROP TABLE IF EXISTS "backtests" CASCADE')
            connection.exec_driver_sql(
                """
                CREATE TABLE backtests (
                    id SERIAL PRIMARY KEY
                )
                """
            )
            connection.exec_driver_sql("INSERT INTO backtests (id) VALUES (1)")
            connection.exec_driver_sql(
                """
                CREATE TABLE backtest_orchestration_snapshots (
                    id SERIAL PRIMARY KEY,
                    backtest_id INTEGER NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
                    cycle_date DATE NOT NULL,
                    snapshot_type VARCHAR(50) NOT NULL,
                    snapshot JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_backtest_orchestration_snapshots_cycle
                        UNIQUE (backtest_id, cycle_date)
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO backtest_orchestration_snapshots (
                    backtest_id,
                    cycle_date,
                    snapshot_type,
                    snapshot
                ) VALUES (
                    1,
                    DATE '2024-06-17',
                    'mentioned_targets',
                    jsonb_build_object(
                        'prompt_report_slug', 'backtest_1_prompt_20240617',
                        'orchestration_pattern_key', 'analyst_reviewer_v1',
                        'pattern_policy_version', 1,
                        'entry_prompt_hash', repeat('1', 64),
                        'full_user_prompt_hash', repeat('2', 64),
                        'resolved_mentions', jsonb_build_array(
                            jsonb_build_object('handle', 'analyst')
                        ),
                        'mentioned_target_outputs', jsonb_build_array(
                            jsonb_build_object('handle', 'analyst', 'output_markdown', 'summary')
                        ),
                        'resolved_builtin_versions', jsonb_build_array(
                            jsonb_build_object(
                                'canonical_target_id',
                                'builtin:librarian',
                                'revision',
                                1
                            )
                        ),
                        'resolved_role_versions', jsonb_build_array(
                            jsonb_build_object(
                                'canonical_target_id',
                                'role:analyst_role',
                                'version',
                                3
                            )
                        ),
                        'resolved_character_versions', jsonb_build_array(
                            jsonb_build_object(
                                'canonical_target_id',
                                'character:analyst',
                                'version',
                                4
                            )
                        )
                    )
                )
                """
            )

    upgrade_legacy_schema(engine)

    columns = {
        column["name"] for column in inspect(engine).get_columns("backtest_orchestration_snapshots")
    }
    assert "snapshot_type" not in columns
    assert "snapshot" not in columns
    assert {
        "prompt_report_slug",
        "orchestration_pattern_key",
        "pattern_policy_version",
        "entry_prompt_hash",
        "full_user_prompt_hash",
        "execution_mode",
        "resolved_mentions",
        "mentioned_target_outputs",
        "resolved_builtin_versions",
        "resolved_role_versions",
        "resolved_character_versions",
        "resolved_bundle_versions",
        "resolved_tool_versions",
        "resolved_connector_versions",
        "tool_call_trace",
        "approval_trace",
    } <= columns

    with session_factory() as session:
        row = (
            session.connection()
            .exec_driver_sql(
                """
            SELECT
                prompt_report_slug,
                orchestration_pattern_key,
                pattern_policy_version,
                entry_prompt_hash,
                full_user_prompt_hash,
                execution_mode,
                resolved_mentions,
                mentioned_target_outputs,
                resolved_builtin_versions,
                resolved_role_versions,
                resolved_character_versions,
                resolved_bundle_versions,
                resolved_tool_versions,
                resolved_connector_versions,
                tool_call_trace,
                approval_trace
            FROM backtest_orchestration_snapshots
            WHERE backtest_id = 1 AND cycle_date = DATE '2024-06-17'
            """
            )
            .one()
        )

    assert row[0] == "backtest_1_prompt_20240617"
    assert row[1] == "analyst_reviewer_v1"
    assert row[2] == 1
    assert row[3] == "1111111111111111111111111111111111111111111111111111111111111111"
    assert row[4] == "2222222222222222222222222222222222222222222222222222222222222222"
    assert row[5] == "structured_output"
    assert row[6] == [{"handle": "analyst"}]
    assert row[7] == [{"handle": "analyst", "output_markdown": "summary"}]
    assert row[8] == [{"canonical_target_id": "builtin:librarian", "revision": 1}]
    assert row[9] == [{"canonical_target_id": "role:analyst_role", "version": 3}]
    assert row[10] == [{"canonical_target_id": "character:analyst", "version": 4}]
    assert row[11] == []
    assert row[12] == []
    assert row[13] == []
    assert row[14] == []
    assert row[15] == "not_required"


def test_upgrade_current_snapshot_table_keeps_explicit_rows_readable(
    session_factory,
) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql(
                'DROP TABLE IF EXISTS "backtest_orchestration_snapshots" CASCADE'
            )
            connection.exec_driver_sql('DROP TABLE IF EXISTS "backtests" CASCADE')
            connection.exec_driver_sql(
                """
                CREATE TABLE backtests (
                    id SERIAL PRIMARY KEY
                )
                """
            )
            connection.exec_driver_sql("INSERT INTO backtests (id) VALUES (1)")
            connection.exec_driver_sql(
                """
                CREATE TABLE backtest_orchestration_snapshots (
                    id SERIAL PRIMARY KEY,
                    backtest_id INTEGER NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,
                    cycle_date DATE NOT NULL,
                    prompt_report_slug VARCHAR(200) NOT NULL DEFAULT '',
                    orchestration_pattern_key VARCHAR(120) NOT NULL DEFAULT
                        'seeded_internal_backtest_v1',
                    pattern_policy_version INTEGER NOT NULL DEFAULT 1,
                    entry_prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
                    full_user_prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
                    resolved_mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    mentioned_target_outputs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    resolved_builtin_versions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    resolved_role_versions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    resolved_character_versions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_backtest_orchestration_snapshots_cycle
                        UNIQUE (backtest_id, cycle_date)
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO backtest_orchestration_snapshots (
                    backtest_id,
                    cycle_date,
                    prompt_report_slug,
                    orchestration_pattern_key,
                    pattern_policy_version,
                    entry_prompt_hash,
                    full_user_prompt_hash,
                    resolved_mentions,
                    mentioned_target_outputs,
                    resolved_builtin_versions,
                    resolved_role_versions,
                    resolved_character_versions
                ) VALUES (
                    1,
                    DATE '2024-06-18',
                    'backtest_1_prompt_20240618',
                    'seeded_internal_backtest_v1',
                    1,
                    repeat('3', 64),
                    repeat('4', 64),
                    jsonb_build_array(
                        jsonb_build_object(
                            'handle',
                            'librarian',
                            'canonical_target_id',
                            'builtin:librarian',
                            'target_type',
                            'builtin',
                            'mention_order',
                            0
                        )
                    ),
                    jsonb_build_array(
                        jsonb_build_object(
                            'handle',
                            'librarian',
                            'canonical_target_id',
                            'builtin:librarian',
                            'target_type',
                            'builtin',
                            'output_markdown',
                            'context summary'
                        )
                    ),
                    jsonb_build_array(
                        jsonb_build_object(
                            'canonical_target_id',
                            'builtin:librarian',
                            'handle',
                            'librarian',
                            'revision',
                            1
                        )
                    ),
                    '[]'::jsonb,
                    '[]'::jsonb
                )
                """
            )

    upgrade_legacy_schema(engine)

    with session_factory() as session:
        row = (
            session.connection()
            .exec_driver_sql(
                """
                SELECT
                    prompt_report_slug,
                    orchestration_pattern_key,
                    pattern_policy_version,
                    entry_prompt_hash,
                    full_user_prompt_hash,
                    execution_mode,
                    resolved_mentions,
                    mentioned_target_outputs,
                    resolved_builtin_versions,
                    resolved_role_versions,
                    resolved_character_versions,
                    resolved_bundle_versions,
                    resolved_tool_versions,
                    resolved_connector_versions,
                    tool_call_trace,
                    approval_trace
                FROM backtest_orchestration_snapshots
                WHERE backtest_id = 1 AND cycle_date = DATE '2024-06-18'
                """
            )
            .one()
        )

    assert row[0] == "backtest_1_prompt_20240618"
    assert row[1] == "seeded_internal_backtest_v1"
    assert row[2] == 1
    assert row[3] == "3333333333333333333333333333333333333333333333333333333333333333"
    assert row[4] == "4444444444444444444444444444444444444444444444444444444444444444"
    assert row[5] == "structured_output"
    assert row[6] == [
        {
            "handle": "librarian",
            "canonical_target_id": "builtin:librarian",
            "target_type": "builtin",
            "mention_order": 0,
        }
    ]
    assert row[7] == [
        {
            "handle": "librarian",
            "canonical_target_id": "builtin:librarian",
            "target_type": "builtin",
            "output_markdown": "context summary",
        }
    ]
    assert row[8] == [
        {
            "canonical_target_id": "builtin:librarian",
            "handle": "librarian",
            "revision": 1,
        }
    ]
    assert row[9] == []
    assert row[10] == []
    assert row[11] == []
    assert row[12] == []
    assert row[13] == []
    assert row[14] == []
    assert row[15] == "not_required"
