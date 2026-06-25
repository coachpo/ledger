# ruff: noqa: E501
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, RowMapping

from app.db.session import init_db

_WORKFLOW_PACKAGE_TABLES = {
    "workflow_packages",
    "workflow_package_runtime_input_entries",
    "workflow_package_secret_bindings",
    "run_workflow_package_snapshots",
}
_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_id",
    "workflow_package_key",
    "workflow_package_workflow_key",
}
_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_EXPECTED_TRADINGAGENTS_MANIFEST_WORKFLOW_KEYS = (
    "advisory_research",
    "market_research",
    "news_research",
    "fundamentals_research",
)
_DB_UPGRADE_MARKER_TABLE = "db_upgrade_markers"


def _workflow_package_payload(
    key: str,
    *,
    workflow_key: str = "daily",
    model_connection_key: str = "live_model",
) -> dict[str, Any]:
    package_definition = {
        "metadata": {"key": key, "name": key.replace("_", " ").title()},
        "spec": {
            "agents": [{"key": "review_agent", "modelConnection": model_connection_key}],
            "workflows": [{"key": workflow_key}],
        },
    }
    compiled_plan = {
        "packageKey": key,
        "agents": [{"key": "review_agent", "modelConnection": model_connection_key}],
        "workflows": [{"key": workflow_key, "inputSchema": {}}],
    }
    return {
        "key": key,
        "name": key.replace("_", " ").title(),
        "manifest_source": f"apiVersion: signaldeck.workflowPackage/v1\nkey: {key}\n",
        "manifest_hash": "a" * 64,
        "package_definition": json.dumps(package_definition, sort_keys=True),
        "compiled_plan": json.dumps(compiled_plan, sort_keys=True),
        "compiled_hash": "b" * 64,
        "extension_dependencies": json.dumps([]),
        "workflow_key": workflow_key,
    }


def _insert_current_package(connection: Connection, key: str, **overrides: str) -> int:
    payload = _workflow_package_payload(key)
    payload.update(overrides)
    return int(
        connection.execute(
            text(
                """
                INSERT INTO workflow_packages (
                    key, name, description, manifest_source, manifest_hash,
                    package_definition, compiled_plan, compiled_hash,
                    extension_dependencies
                ) VALUES (
                    :key, :name, '', :manifest_source, :manifest_hash,
                    CAST(:package_definition AS jsonb), CAST(:compiled_plan AS jsonb),
                    :compiled_hash, CAST(:extension_dependencies AS jsonb)
                ) RETURNING id
                """
            ),
            payload,
        ).scalar_one()
    )


def _insert_run_snapshot(
    connection: Connection,
    *,
    run_id: int,
    package_id: int,
    key: str,
    resolved_model_connections: list[object] | None = None,
) -> None:
    payload = _workflow_package_payload(key)
    connection.execute(
        text(
            """
            INSERT INTO run_workflow_package_snapshots (
                run_id, workflow_package_id, workflow_package_key, workflow_package_name,
                workflow_package_description, workflow_package_status, workflow_key,
                workflow_name, workflow_description, manifest_hash, compiled_hash,
                manifest_source, package_definition, compiled_plan, extension_dependencies,
                local_resource_refs, input_schema, launch_parameters,
                resolved_model_connections, preflight_summary, created_at, updated_at
            ) VALUES (
                :run_id, :package_id, :key, :name, '', 'active', :workflow_key,
                :workflow_key, '', :manifest_hash, :compiled_hash, :manifest_source,
                CAST(:package_definition AS jsonb), CAST(:compiled_plan AS jsonb),
                CAST(:extension_dependencies AS jsonb), '{}'::jsonb, '{}'::jsonb,
                '{}'::jsonb, CAST(:resolved_model_connections AS jsonb), '{}'::jsonb,
                NOW(), NOW()
            )
            """
        ),
        {
            **payload,
            "package_id": package_id,
            "resolved_model_connections": json.dumps(resolved_model_connections or []),
            "run_id": run_id,
        },
    )


def _manifest_workflow_keys(row: RowMapping) -> tuple[str, ...]:
    package_definition = row["package_definition"]
    assert isinstance(package_definition, dict)
    spec = package_definition.get("spec")
    assert isinstance(spec, dict)
    workflows = spec.get("workflows")
    assert isinstance(workflows, list)
    return tuple(
        str(workflow.get("key")) for workflow in workflows if isinstance(workflow, Mapping)
    )


def _foreign_key_signature(
    foreign_key: Mapping[str, object],
) -> tuple[tuple[str, ...], str | None, str | None]:
    options = foreign_key.get("options")
    ondelete = options.get("ondelete") if isinstance(options, dict) else None
    constrained_columns = foreign_key.get("constrained_columns")
    columns = (
        tuple(str(column) for column in constrained_columns)
        if isinstance(constrained_columns, list | tuple)
        else ()
    )
    return columns, str(foreign_key.get("referred_table")), ondelete


def _assert_workflow_package_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert _WORKFLOW_PACKAGE_TABLES <= table_names

    package_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_packages")
    }
    run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
    snapshot_columns = {
        column["name"]: column for column in inspector.get_columns("run_workflow_package_snapshots")
    }
    package_indexes = {index["name"] for index in inspector.get_indexes("workflow_packages")}
    run_indexes = {index["name"] for index in inspector.get_indexes("runs")}
    snapshot_indexes = {
        index["name"] for index in inspector.get_indexes("run_workflow_package_snapshots")
    }
    snapshot_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_workflow_package_snapshots")
    }
    model_connection_columns = {
        column["name"]: column for column in inspector.get_columns("model_connections")
    }
    assert {
        "id",
        "key",
        "name",
        "description",
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
        "extension_dependencies",
        "created_at",
        "updated_at",
    } <= set(package_columns)
    assert _RUN_PROVENANCE_COLUMNS <= set(run_columns)
    assert {
        "run_id",
        "workflow_package_id",
        "workflow_package_key",
        "workflow_package_name",
        "workflow_package_description",
        "workflow_package_status",
        "workflow_key",
        "workflow_name",
        "workflow_description",
        "manifest_hash",
        "compiled_hash",
        "manifest_source",
        "package_definition",
        "compiled_plan",
        "extension_dependencies",
        "local_resource_refs",
        "input_schema",
        "launch_parameters",
        "resolved_model_connections",
        "preflight_summary",
        "created_at",
        "updated_at",
    } == set(snapshot_columns)
    assert package_columns["key"]["nullable"] is False
    assert package_columns["manifest_source"]["nullable"] is False
    assert package_columns["package_definition"]["nullable"] is False
    assert package_columns["compiled_plan"]["nullable"] is False
    assert package_columns["extension_dependencies"]["nullable"] is False
    assert "uq_workflow_packages_key" in package_indexes
    assert {
        "ix_runs_workflow_package",
        "ix_runs_workflow_package_key",
        "ix_runs_workflow_package_workflow_key",
    } <= run_indexes
    assert {
        "ix_run_workflow_package_snapshots_package_key",
        "ix_run_workflow_package_snapshots_workflow_key",
        "ix_run_workflow_package_snapshots_manifest_hash",
        "ix_run_workflow_package_snapshots_compiled_hash",
    } <= snapshot_indexes
    assert snapshot_foreign_keys == {(("run_id",), "runs", "CASCADE")}
    assert {
        "id",
        "key",
        "status",
        "name",
        "description",
        "base_url",
        "model_id",
        "reasoning_effort",
        "protocol_profile",
        "capabilities",
        "output_strategy_policy",
        "parallel_tool_calls_policy",
        "reasoning_policy",
        "streaming_policy",
        "last_probed_at",
        "probe_cache_ttl_seconds",
        "timeout_seconds",
        "secret_payload",
        "last_tested_at",
        "last_test_ok",
        "last_test_message",
        "created_at",
        "updated_at",
    } <= set(model_connection_columns)


def test_init_db_creates_current_workflow_package_and_run_snapshot_schema(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_package_schema(engine)
    finally:
        engine.dispose()


def test_init_db_seeds_tradingagents_preset_with_canonical_manifest_workflow_keys(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT package_definition
                        FROM workflow_packages
                        WHERE key = :package_key
                        """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )

        assert _manifest_workflow_keys(row) == _EXPECTED_TRADINGAGENTS_MANIFEST_WORKFLOW_KEYS
    finally:
        engine.dispose()


def test_workflow_package_upgrade_reseeds_stale_first_party_preset_row(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            clean_row = (
                connection.execute(
                    text(
                        """
                        SELECT id, name, description, manifest_source, manifest_hash,
                               package_definition, compiled_plan, compiled_hash,
                               extension_dependencies
                        FROM workflow_packages
                        WHERE key = :package_key
                        """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
        stale_id = int(clean_row["id"])

        with engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {_DB_UPGRADE_MARKER_TABLE}"))
            connection.execute(
                text(
                    """
                    UPDATE workflow_packages
                    SET name = 'Stale TradingAgents Preset',
                        description = 'stale preset row',
                        manifest_source = 'stale manifest',
                        manifest_hash = :manifest_hash,
                        package_definition = '{"stale": true}'::jsonb,
                        compiled_plan = '{"stale": true}'::jsonb,
                        compiled_hash = :compiled_hash,
                        extension_dependencies = '[]'::jsonb,
                        updated_at = NOW()
                    WHERE key = :package_key
                    """
                ),
                {
                    "compiled_hash": "1" * 64,
                    "manifest_hash": "0" * 64,
                    "package_key": _TRADINGAGENTS_PRESET_KEY,
                },
            )

        init_db(database_url)
        init_db(database_url)

        _assert_workflow_package_schema(engine)
        with engine.connect() as connection:
            reseeded_row = (
                connection.execute(
                    text(
                        """
                        SELECT id, name, description, manifest_source, manifest_hash,
                               package_definition, compiled_plan, compiled_hash,
                               extension_dependencies
                        FROM workflow_packages
                        WHERE key = :package_key
                        """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
            marker_count = connection.execute(
                text(f"SELECT COUNT(*) FROM {_DB_UPGRADE_MARKER_TABLE}")
            ).scalar_one()

        assert int(reseeded_row["id"]) != stale_id
        for field in (
            "name",
            "description",
            "manifest_source",
            "manifest_hash",
            "package_definition",
            "compiled_plan",
            "compiled_hash",
            "extension_dependencies",
        ):
            assert reseeded_row[field] == clean_row[field]
        assert marker_count == 1
    finally:
        engine.dispose()


def test_workflow_package_upgrade_reseeds_stale_marked_first_party_preset_row(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            clean_row = (
                connection.execute(
                    text(
                        """
                        SELECT id, name, description, manifest_source, manifest_hash,
                               package_definition, compiled_plan, compiled_hash,
                               extension_dependencies
                        FROM workflow_packages
                        WHERE key = :package_key
                        """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
        stale_id = int(clean_row["id"])

        with engine.begin() as connection:
            removed_budget_field = "budget" + "Usd"
            connection.execute(
                text(
                    """
                    UPDATE workflow_packages
                    SET manifest_source = manifest_source || E'\n# stale preset artifact\n'
                            || :removed_budget_field || E': "10"\n',
                        manifest_hash = :manifest_hash,
                        package_definition = jsonb_set(
                            package_definition,
                            CAST(:package_budget_path AS text[]),
                            '10'::jsonb,
                            true
                        ),
                        compiled_plan = jsonb_set(
                            compiled_plan,
                            CAST(:plan_budget_path AS text[]),
                            '10'::jsonb,
                            true
                        ),
                        updated_at = NOW()
                    WHERE key = :package_key
                    """
                ),
                {
                    "manifest_hash": "0" * 64,
                    "package_budget_path": "{"
                    + ",".join(("spec", "agents", "0", removed_budget_field))
                    + "}",
                    "package_key": _TRADINGAGENTS_PRESET_KEY,
                    "plan_budget_path": "{" + ",".join(("agents", "0", removed_budget_field)) + "}",
                    "removed_budget_field": removed_budget_field,
                },
            )
            marker_count_before = connection.execute(
                text(f"SELECT COUNT(*) FROM {_DB_UPGRADE_MARKER_TABLE}")
            ).scalar_one()

        assert marker_count_before == 1
        init_db(database_url)
        _assert_workflow_package_schema(engine)
        init_db(database_url)

        _assert_workflow_package_schema(engine)
        with engine.connect() as connection:
            reseeded_row = (
                connection.execute(
                    text(
                        """
                        SELECT id, name, description, manifest_source, manifest_hash,
                               package_definition, compiled_plan, compiled_hash,
                               extension_dependencies
                        FROM workflow_packages
                        WHERE key = :package_key
                        """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
            marker_count_after = connection.execute(
                text(f"SELECT COUNT(*) FROM {_DB_UPGRADE_MARKER_TABLE}")
            ).scalar_one()

        assert int(reseeded_row["id"]) != stale_id
        for field in (
            "name",
            "description",
            "manifest_source",
            "manifest_hash",
            "package_definition",
            "compiled_plan",
            "compiled_hash",
            "extension_dependencies",
        ):
            assert reseeded_row[field] == clean_row[field]
        assert marker_count_after == 1
    finally:
        engine.dispose()


def test_workflow_package_upgrade_is_idempotent_for_current_package_and_snapshot(
    database_url: str,
) -> None:
    init_db(database_url)
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_package_schema(engine)
        with engine.begin() as connection:
            package_id = _insert_current_package(connection, "idempotent_package")
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, input, status
                    ) VALUES (
                        'workflowPackage', :package_id, 'idempotent_package', 1,
                        :package_id, 'idempotent_package', 'daily', '{}'::jsonb, 'queued'
                    ) RETURNING id
                    """
                ),
                {"package_id": package_id},
            ).scalar_one()
            _insert_run_snapshot(
                connection,
                run_id=int(run_id),
                package_id=package_id,
                key="idempotent_package",
            )

        init_db(database_url)
        init_db(database_url)

        _assert_workflow_package_schema(engine)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT package.key, snapshot.workflow_key
                    FROM workflow_packages AS package
                    JOIN run_workflow_package_snapshots AS snapshot
                      ON snapshot.workflow_package_id = package.id
                    WHERE package.id = :package_id
                    """
                ),
                {"package_id": package_id},
            ).one()
        assert row == ("idempotent_package", "daily")
    finally:
        engine.dispose()


def test_workflow_package_upgrade_keeps_current_package_refs(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            _insert_current_package(connection, "live_refs")
            _insert_current_package(
                connection,
                "dangling_refs",
                compiled_plan=json.dumps(
                    {
                        "agents": [{"key": "broken_agent", "modelConnection": "missing_model"}],
                        "workflows": [],
                    },
                    sort_keys=True,
                ),
            )

        init_db(database_url)

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT key
                    FROM workflow_packages
                    WHERE key IN ('dangling_refs', 'live_refs')
                    ORDER BY key
                    """
                )
            ).all()

        assert rows == [("dangling_refs",), ("live_refs",)]
    finally:
        engine.dispose()
