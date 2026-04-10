from __future__ import annotations

from importlib import import_module

from sqlalchemy import inspect

from app.db.upgrades import upgrade_legacy_schema
from app.models.base import Base

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
        "resolved_mentions",
        "mentioned_target_outputs",
        "resolved_builtin_versions",
        "resolved_role_versions",
        "resolved_character_versions",
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
        "resolved_mentions",
        "mentioned_target_outputs",
        "resolved_builtin_versions",
        "resolved_role_versions",
        "resolved_character_versions",
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
                resolved_mentions,
                mentioned_target_outputs,
                resolved_builtin_versions,
                resolved_role_versions,
                resolved_character_versions
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
    assert row[5] == [{"handle": "analyst"}]
    assert row[6] == [{"handle": "analyst", "output_markdown": "summary"}]
    assert row[7] == [{"canonical_target_id": "builtin:librarian", "revision": 1}]
    assert row[8] == [{"canonical_target_id": "role:analyst_role", "version": 3}]
    assert row[9] == [{"canonical_target_id": "character:analyst", "version": 4}]
