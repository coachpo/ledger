from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.db.session import init_db

_WORKFLOW_PACKAGE_TABLES = {"workflow_packages", "workflow_package_versions"}
_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_id",
    "workflow_package_key",
    "workflow_package_version_id",
    "workflow_package_version",
    "workflow_package_hash",
    "workflow_package_workflow_key",
}


def _assert_workflow_package_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert _WORKFLOW_PACKAGE_TABLES <= table_names

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

    assert {
        "id",
        "key",
        "name",
        "description",
        "status",
        "latest_version_id",
        "draft_source",
        "archived_at",
        "archived_by",
        "archived_reason",
        "deleted_at",
        "deleted_by",
        "deleted_reason",
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
        "validation_summary",
        "created_at",
        "launched_at",
    } <= set(version_columns)
    assert _RUN_PROVENANCE_COLUMNS <= set(run_columns)
    assert package_columns["key"]["nullable"] is False
    assert version_columns["package_definition"]["nullable"] is False
    assert version_columns["compiled_plan"]["nullable"] is False
    assert "uq_workflow_packages_active_key" in package_indexes
    assert "uq_workflow_package_versions_package_version" in version_unique_constraints
    assert "ix_workflow_package_versions_compiled_hash" in version_indexes
    assert {
        "ix_runs_workflow_package",
        "ix_runs_workflow_package_key",
        "ix_runs_workflow_package_workflow_key",
    } <= run_indexes


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
