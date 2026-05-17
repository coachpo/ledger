from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db.session import init_db

_WORKFLOW_PACKAGE_TABLES = {"workflow_packages", "workflow_package_versions"}
_REFERENCE_TABLES = {
    "workflow_package_version_model_connections",
    "workflow_agent_refs",
    "agent_capability_refs",
    "agent_mcp_server_refs",
}
_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_id",
    "workflow_package_key",
    "workflow_package_version_id",
    "workflow_package_version",
    "workflow_package_manifest_hash",
    "workflow_package_compiled_hash",
    "workflow_package_workflow_key",
    "launch_snapshot",
}
_DETERMINISTIC_SMOKE_BASE_URL = "https://signaldeck-deterministic-model.local/v1"


def _assert_workflow_package_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert _WORKFLOW_PACKAGE_TABLES | _REFERENCE_TABLES <= table_names

    package_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_packages")
    }
    version_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_package_versions")
    }
    run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
    package_indexes = {index["name"] for index in inspector.get_indexes("workflow_packages")}
    version_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_package_versions")
    }
    run_indexes = {index["name"] for index in inspector.get_indexes("runs")}
    version_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("workflow_package_versions")
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
        (
            tuple(str(column) for column in foreign_key["constrained_columns"]),
            str(foreign_key["referred_table"]),
            str(foreign_key.get("options", {}).get("ondelete")),
        )
        for foreign_key in inspector.get_foreign_keys("workflow_agent_refs")
    }

    assert {
        "id",
        "key",
        "name",
        "description",
        "status",
        "latest_version_id",
        "draft_source",
        "created_at",
        "updated_at",
    } <= set(package_columns)
    assert {
        "id",
        "package_id",
        "version",
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
        "extension_dependencies",
        "validation_summary",
        "created_at",
        "launched_at",
    } <= set(version_columns)
    assert _RUN_PROVENANCE_COLUMNS <= set(run_columns)
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
    assert version_columns["package_definition"]["nullable"] is False
    assert version_columns["compiled_plan"]["nullable"] is False
    assert version_columns["extension_dependencies"]["nullable"] is False
    assert "uq_workflow_packages_active_key" in package_indexes
    assert "uq_workflow_package_versions_package_version" in version_unique_constraints
    assert "ix_workflow_package_versions_compiled_hash" in version_indexes
    assert {
        "ix_runs_workflow_package",
        "ix_runs_workflow_package_key",
        "ix_runs_workflow_package_manifest_hash",
        "ix_runs_workflow_package_compiled_hash",
        "ix_runs_workflow_package_workflow_key",
    } <= run_indexes
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


def test_init_db_creates_workflow_package_tables_and_run_provenance(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_package_schema(engine)
    finally:
        engine.dispose()


def test_workflow_package_upgrade_is_idempotent(database_url: str) -> None:
    init_db(database_url)
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_package_schema(engine)
        with engine.begin() as connection:
            package_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (key, name, description, status, draft_source)
                    VALUES ('idempotent_package', 'Idempotent Package', '', 'active', '')
                    RETURNING id
                    """
                )
            ).scalar_one()
            version_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_versions (
                        package_id, version, manifest_source, manifest_hash, package_definition,
                        compiled_plan, compiled_hash, validation_summary
                    ) VALUES (
                        :package_id, 1, 'manifest', :manifest_hash,
                        '{"metadata":{"key":"idempotent_package"}}'::jsonb,
                        '{"packageKey":"idempotent_package"}'::jsonb,
                        :compiled_hash, '{"diagnostics":[]}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"compiled_hash": "b" * 64, "manifest_hash": "a" * 64, "package_id": package_id},
            ).scalar_one()
            connection.execute(
                text("UPDATE workflow_packages SET latest_version_id = :version_id WHERE id = :id"),
                {"id": package_id, "version_id": version_id},
            )

        init_db(database_url)
        init_db(database_url)

        _assert_workflow_package_schema(engine)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT package.key, version.version, package.latest_version_id
                    FROM workflow_packages AS package
                    JOIN workflow_package_versions AS version ON version.package_id = package.id
                    WHERE package.id = :package_id
                    """
                ),
                {"package_id": package_id},
            ).one()
        assert row == ("idempotent_package", 1, version_id)
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
            package_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (key, name, description, status, draft_source)
                    VALUES ('duplicate_package', 'Duplicate Package', '', 'active', '')
                    RETURNING id
                    """
                )
            ).scalar_one()
            version_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_versions (
                        package_id, version, manifest_source, manifest_hash, package_definition,
                        compiled_plan, compiled_hash, validation_summary
                    ) VALUES (
                        :package_id, 1, 'manifest', :manifest_hash,
                        '{"metadata":{"key":"duplicate_package"}}'::jsonb,
                        '{"packageKey":"duplicate_package"}'::jsonb,
                        :compiled_hash, '{"diagnostics":[]}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"compiled_hash": "b" * 64, "manifest_hash": "a" * 64, "package_id": package_id},
            ).scalar_one()
            connection.execute(
                text("UPDATE workflow_packages SET latest_version_id = :version_id WHERE id = :id"),
                {"id": package_id, "version_id": version_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (
                        key, name, description, status, draft_source, archived_at, archived_by,
                        archived_reason
                    ) VALUES (
                        'duplicate_package', 'Duplicate Package Archived', '', 'archived', '',
                        now(), 'tester', 'removed during hard delete cutover'
                    )
                    """
                )
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


def test_workflow_package_upgrade_backfills_refs_and_removes_dangling_model_refs(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            model_connection_id = connection.execute(
                text(
                    """
                    INSERT INTO model_connections (
                        key, status, name, description, base_url, model_id, reasoning_effort,
                        api_style, timeout_seconds, secret_payload, created_at, updated_at
                    ) VALUES (
                        'live_model', 'active', 'Live Model', '', 'https://api.openai.com/v1',
                        'openai:gpt-5.4-mini', 'medium', 'responses', 60, '{}'::jsonb,
                        NOW(), NOW()
                    ) RETURNING id
                    """
                )
            ).scalar_one()
            output_schema_id = connection.execute(
                text(
                    """
                    INSERT INTO output_schemas (
                        key, version, status, kind, name, description, json_schema, registry_refs,
                        created_at, updated_at
                    ) VALUES (
                        'live_ref_schema', 1, 'published', 'standalone', 'Live Ref Schema', '',
                        '{"type":"object"}'::jsonb, '[]'::jsonb, NOW(), NOW()
                    ) RETURNING id
                    """
                )
            ).scalar_one()
            agent_id = connection.execute(
                text(
                    """
                    INSERT INTO agents (
                        key, version, status, name, description, model_connection_id,
                        model_connection_snapshot, model, system_prompt, input_schema,
                        output_schema_id, output_schema_version, capabilities, mcp_servers
                    ) VALUES (
                        'review_agent', 1, 'published', 'Review Agent', '', :model_connection_id,
                        '{}'::jsonb, 'openai:gpt-5.4-mini', 'Review.', '{"type":"object"}'::jsonb,
                        :output_schema_id, 1, '[]'::jsonb, '[]'::jsonb
                    ) RETURNING id
                    """
                ),
                {"model_connection_id": model_connection_id, "output_schema_id": output_schema_id},
            ).scalar_one()
            workflow_id = connection.execute(
                text(
                    """
                    INSERT INTO workflows (
                        key, version, status, name, description, input_schema, steps, output_spec
                    ) VALUES (
                        'daily', 1, 'published', 'Daily', '', '{"type":"object"}'::jsonb,
                        jsonb_build_array(
                            jsonb_build_object(
                                'index', 1,
                                'agents', jsonb_build_array(
                                    jsonb_build_object('agentId', :agent_id)
                                )
                            )
                        ),
                        '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"agent_id": agent_id},
            ).scalar_one()
            live_package_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (key, name, description, status, draft_source)
                    VALUES ('live_refs', 'Live Refs', '', 'active', '')
                    RETURNING id
                    """
                )
            ).scalar_one()
            dangling_package_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (key, name, description, status, draft_source)
                    VALUES ('dangling_refs', 'Dangling Refs', '', 'active', '')
                    RETURNING id
                    """
                )
            ).scalar_one()
            live_version_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_versions (
                        package_id, version, manifest_source, manifest_hash, package_definition,
                        compiled_plan, compiled_hash, validation_summary
                    ) VALUES (
                        :package_id, 1, 'manifest', :manifest_hash,
                        '{"metadata":{"key":"live_refs"}}'::jsonb,
                        '{"agents":[{"key":"review_agent","modelConnection":"live_model"}],"workflows":[{"key":"daily","steps":[{"agents":[{"agentKey":"review_agent"}]}]}]}'::jsonb,
                        :compiled_hash, '{"diagnostics":[]}'::jsonb
                    ) RETURNING id
                    """
                ),
                {
                    "compiled_hash": "d" * 64,
                    "manifest_hash": "c" * 64,
                    "package_id": live_package_id,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_versions (
                        package_id, version, manifest_source, manifest_hash, package_definition,
                        compiled_plan, compiled_hash, validation_summary
                    ) VALUES (
                        :package_id, 1, 'manifest', :manifest_hash,
                        '{"metadata":{"key":"dangling_refs"}}'::jsonb,
                        '{"agents":[{"key":"broken_agent","modelConnection":"missing_model"}],"workflows":[]}'::jsonb,
                        :compiled_hash, '{"diagnostics":[]}'::jsonb
                    )
                    """
                ),
                {
                    "compiled_hash": "f" * 64,
                    "manifest_hash": "e" * 64,
                    "package_id": dangling_package_id,
                },
            )
            connection.execute(
                text("UPDATE workflow_packages SET latest_version_id = :version_id WHERE id = :id"),
                {"id": live_package_id, "version_id": live_version_id},
            )

        init_db(database_url)

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT package.key, COUNT(model_ref.id)
                    FROM workflow_packages AS package
                    LEFT JOIN workflow_package_versions AS version
                      ON version.package_id = package.id
                    LEFT JOIN workflow_package_version_model_connections AS model_ref
                      ON model_ref.workflow_package_version_id = version.id
                    GROUP BY package.key
                    ORDER BY package.key
                    """
                )
            ).all()
            workflow_agent_refs = connection.execute(
                text("SELECT workflow_id, agent_id FROM workflow_agent_refs")
            ).all()
            assert rows == [("live_refs", 1)]
            assert workflow_agent_refs == []
            assert workflow_id is not None
            assert agent_id is not None
    finally:
        engine.dispose()


def test_model_connection_upgrade_backfills_connection_kind_for_deterministic_smoke_rows(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
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
