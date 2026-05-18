from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from app.db.session import init_db

_WORKFLOW_PACKAGE_TABLES = {
    "workflow_packages",
    "workflow_package_secret_bindings",
    "run_workflow_package_snapshots",
}
_REMOVED_PACKAGE_HISTORY_TABLES = {
    "workflow_package_versions",
    "workflow_package_version_model_connections",
}
_REFERENCE_TABLES = {
    "workflow_agent_refs",
    "agent_capability_refs",
    "agent_mcp_server_refs",
}
_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_id",
    "workflow_package_key",
    "workflow_package_workflow_key",
}
_REMOVED_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_version_id",
    "workflow_package_version",
    "workflow_package_manifest_hash",
    "workflow_package_compiled_hash",
    "launch_snapshot",
}
_DETERMINISTIC_SMOKE_BASE_URL = "https://signaldeck-deterministic-model.local/v1"


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
        "validation_summary": json.dumps({"diagnostics": []}),
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
                    key, name, description, status, manifest_source, manifest_hash,
                    package_definition, compiled_plan, compiled_hash,
                    extension_dependencies, validation_summary
                ) VALUES (
                    :key, :name, '', 'active', :manifest_source, :manifest_hash,
                    CAST(:package_definition AS jsonb), CAST(:compiled_plan AS jsonb),
                    :compiled_hash, CAST(:extension_dependencies AS jsonb),
                    CAST(:validation_summary AS jsonb)
                ) RETURNING id
                """
            ),
            payload,
        ).scalar_one()
    )


def _insert_run_snapshot(connection: Connection, *, run_id: int, package_id: int, key: str) -> None:
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
                '{}'::jsonb, '[]'::jsonb, '{}'::jsonb, NOW(), NOW()
            )
            """
        ),
        {**payload, "package_id": package_id, "run_id": run_id},
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
    assert _WORKFLOW_PACKAGE_TABLES | _REFERENCE_TABLES <= table_names
    assert _REMOVED_PACKAGE_HISTORY_TABLES.isdisjoint(table_names)

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
    model_connection_check_sql = {
        constraint["name"]: str(constraint["sqltext"])
        for constraint in inspector.get_check_constraints("model_connections")
    }
    package_check_sql = {
        constraint["name"]: str(constraint["sqltext"])
        for constraint in inspector.get_check_constraints("workflow_packages")
    }
    workflow_agent_columns = {
        column["name"] for column in inspector.get_columns("workflow_agent_refs")
    }
    workflow_agent_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("workflow_agent_refs")
    }

    assert {
        "id",
        "key",
        "name",
        "description",
        "status",
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
        "extension_dependencies",
        "validation_summary",
        "created_at",
        "updated_at",
        "last_launched_at",
    } <= set(package_columns)
    assert {"latest_version_id", "draft_source"}.isdisjoint(package_columns)
    assert _RUN_PROVENANCE_COLUMNS <= set(run_columns)
    assert _REMOVED_RUN_PROVENANCE_COLUMNS.isdisjoint(run_columns)
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
    removed_archive_status = "arch" + "ived"
    removed_archive_columns = {
        "_".join((removed_archive_status, suffix)) for suffix in ("at", "by", "reason")
    }
    assert {
        *removed_archive_columns,
        "deleted_at",
        "deleted_by",
        "deleted_reason",
    }.isdisjoint(package_columns)
    assert removed_archive_status not in package_check_sql["ck_workflow_packages_status"]
    assert {"id", "workflow_id", "agent_id"} <= workflow_agent_columns
    assert "workflow_package_version_id" not in workflow_agent_columns
    assert (("workflow_id",), "workflows", "CASCADE") in workflow_agent_foreign_keys
    assert (("agent_id",), "agents", "RESTRICT") in workflow_agent_foreign_keys
    assert package_columns["key"]["nullable"] is False
    assert package_columns["manifest_source"]["nullable"] is False
    assert package_columns["package_definition"]["nullable"] is False
    assert package_columns["compiled_plan"]["nullable"] is False
    assert package_columns["extension_dependencies"]["nullable"] is False
    assert package_columns["validation_summary"]["nullable"] is False
    assert "uq_workflow_packages_active_key" in package_indexes
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
    assert (("workflow_package_id",), "workflow_packages", "CASCADE") not in snapshot_foreign_keys
    assert {
        "id",
        "key",
        "status",
        "connection_kind",
        "name",
        "description",
        "base_url",
        "model_id",
        "reasoning_effort",
        "api_style",
        "timeout_seconds",
        "secret_payload",
        "last_tested_at",
        "last_test_ok",
        "last_test_message",
        "created_at",
        "updated_at",
    } <= set(model_connection_columns)
    assert model_connection_columns["connection_kind"]["nullable"] is False
    assert "provider" in model_connection_check_sql["ck_model_connections_connection_kind"]
    assert (
        "deterministic_smoke" in model_connection_check_sql["ck_model_connections_connection_kind"]
    )


def test_init_db_creates_current_workflow_package_and_run_snapshot_schema(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_package_schema(engine)
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


def test_workflow_package_upgrade_deletes_archived_duplicates_before_index_creation(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.execute(text("DROP INDEX IF EXISTS uq_workflow_packages_active_key"))
            connection.execute(
                text(
                    "ALTER TABLE workflow_packages DROP CONSTRAINT IF EXISTS "
                    "ck_workflow_packages_status"
                )
            )
            connection.execute(
                text("ALTER TABLE workflow_packages ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP")
            )
            connection.execute(
                text("ALTER TABLE workflow_packages ADD COLUMN IF NOT EXISTS archived_by TEXT")
            )
            connection.execute(
                text("ALTER TABLE workflow_packages ADD COLUMN IF NOT EXISTS archived_reason TEXT")
            )
            _insert_current_package(connection, "duplicate_package")
            archived_payload = _workflow_package_payload("duplicate_package")
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (
                        key, name, description, status, manifest_source, manifest_hash,
                        package_definition, compiled_plan, compiled_hash,
                        extension_dependencies, validation_summary, archived_at,
                        archived_by, archived_reason
                    ) VALUES (
                        'duplicate_package', 'Duplicate Package Archived', '', 'archived',
                        :manifest_source, :manifest_hash, CAST(:package_definition AS jsonb),
                        CAST(:compiled_plan AS jsonb), :compiled_hash,
                        CAST(:extension_dependencies AS jsonb),
                        CAST(:validation_summary AS jsonb), NOW(), 'tester',
                        'removed during hard delete cutover'
                    )
                    """
                ),
                archived_payload,
            )

        init_db(database_url)

        _assert_workflow_package_schema(engine)
        with engine.connect() as connection:
            package_rows = connection.execute(
                text(
                    """
                    SELECT key, status
                    FROM workflow_packages
                    WHERE key = 'duplicate_package'
                    ORDER BY status
                    """
                )
            ).all()
            assert package_rows == [("duplicate_package", "active")]
    finally:
        engine.dispose()


def test_workflow_package_upgrade_drops_package_history_tables_and_keeps_current_refs(
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
            table_names = set(inspect(connection).get_table_names())
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
            workflow_agent_refs = connection.execute(
                text("SELECT workflow_id, agent_id FROM workflow_agent_refs")
            ).all()

        assert _REMOVED_PACKAGE_HISTORY_TABLES.isdisjoint(table_names)
        assert rows == [("dangling_refs",), ("live_refs",)]
        assert workflow_agent_refs == []
    finally:
        engine.dispose()


def test_model_connection_upgrade_backfills_connection_kind_for_deterministic_smoke_rows(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE model_connections (
                        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        name VARCHAR(200) NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        base_url VARCHAR(500) NOT NULL,
                        model_id VARCHAR(200) NOT NULL,
                        reasoning_effort VARCHAR(20) NOT NULL DEFAULT 'medium',
                        api_style VARCHAR(30) NOT NULL DEFAULT 'responses',
                        timeout_seconds INTEGER NOT NULL DEFAULT 60,
                        secret_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        last_tested_at TIMESTAMPTZ,
                        last_test_ok BOOLEAN,
                        last_test_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT ck_model_connections_status CHECK (status IN ('active')),
                        CONSTRAINT ck_model_connections_reasoning_effort CHECK (
                            reasoning_effort IN ('low', 'medium', 'high')
                        ),
                        CONSTRAINT ck_model_connections_api_style CHECK (
                            api_style IN ('responses', 'chat_completions')
                        )
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO model_connections (
                        status, name, description, base_url, model_id, reasoning_effort,
                        api_style, timeout_seconds, secret_payload, created_at, updated_at
                    ) VALUES (
                        'active', :name, '', :base_url, :model_id, 'medium', 'responses', 60,
                        '{}'::jsonb, NOW(), NOW()
                    )
                    """
                ),
                [
                    {
                        "base_url": _DETERMINISTIC_SMOKE_BASE_URL,
                        "model_id": "openai:gpt-5.4-mini",
                        "name": "Deterministic Smoke",
                    },
                    {
                        "base_url": "https://api.openai.com/v1",
                        "model_id": "openai:gpt-5.4-mini",
                        "name": "Primary Provider",
                    },
                ],
            )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT key, connection_kind, base_url
                    FROM model_connections
                    ORDER BY key
                    """
                )
            ).all()
            model_connection_columns = {
                column["name"]: column
                for column in inspect(engine).get_columns("model_connections")
            }
            model_connection_check_sql = {
                constraint["name"]: str(constraint["sqltext"])
                for constraint in inspect(engine).get_check_constraints("model_connections")
            }

        assert rows == [
            ("deterministic_smoke", "deterministic_smoke", _DETERMINISTIC_SMOKE_BASE_URL),
            ("primary_provider", "provider", "https://api.openai.com/v1"),
        ]
        assert model_connection_columns["connection_kind"]["nullable"] is False
        assert "provider" in model_connection_check_sql["ck_model_connections_connection_kind"]
        assert (
            "deterministic_smoke"
            in model_connection_check_sql["ck_model_connections_connection_kind"]
        )
    finally:
        engine.dispose()
