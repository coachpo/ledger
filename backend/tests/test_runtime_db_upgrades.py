from __future__ import annotations

import json

from sqlalchemy import create_engine, inspect, text

from app.db.session import init_db
from app.db.upgrades import upgrade_legacy_schema
from app.models.mcp_server import McpServer

AGENT_PLATFORM_TABLE_NAMES = {
    "agents",
    "mcp_servers",
    "output_schemas",
    "runs",
    "skills",
    "workflows",
}
LEGACY_BACKEND_TABLE_NAMES = {
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
    "orchestration_roles",
    "orchestration_characters",
}
_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE = (
    "Run marked as failed during startup recovery because the previous process exited while "
    "it was still running."
)


def test_init_db_creates_agent_platform_tables_and_drops_legacy_backend_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        table_names = set(inspect(engine).get_table_names())
        assert AGENT_PLATFORM_TABLE_NAMES <= table_names
        assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(table_names)
    finally:
        engine.dispose()


def test_init_db_running_run_recovery_marks_new_platform_runs_failed(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO runs ("
                "workflow_id, workflow_key, workflow_version, status, input, per_step_outputs"
                ") VALUES (1, 'stock_analysis', 1, 'running', '{}'::jsonb, '{}'::jsonb)"
            )

        init_db(database_url)

        with engine.connect() as connection:
            repaired_run = connection.exec_driver_sql(
                "SELECT status, error, finished_at IS NOT NULL FROM runs"
            ).one()

        assert repaired_run == ("failed", _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE, True)
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_drops_preexisting_legacy_backend_tables(session_factory) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS agent_specs (id INTEGER)")
            connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS workflow_specs (id INTEGER)")
            connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS runtime_runs (id INTEGER)")
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS orchestration_roles (id INTEGER)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS orchestration_characters (id INTEGER)"
            )

    upgrade_legacy_schema(engine)

    table_names = set(inspect(engine).get_table_names())
    assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(table_names)


def test_upgrade_legacy_schema_flattens_wrapped_mcp_rows(session_factory) -> None:
    flat_config = {
        "name": "Market Data",
        "description": "Published MCP server",
        "enabled": True,
        "transport": "http-sse",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer secret-token"},
    }

    with session_factory() as session:
        engine = session.get_bind()
        session.add(
            McpServer(
                key="market_data",
                version=1,
                status="draft",
                config={"mcpServers": {"market_data": flat_config}},
            )
        )
        session.commit()

    upgrade_legacy_schema(engine)

    with session_factory() as session:
        stored = session.query(McpServer).filter_by(key="market_data", version=1).one()
        assert stored.config == flat_config
        assert stored.flat_config == flat_config
        assert stored.transport == "http-sse"
        assert stored.enabled is True


def test_upgrade_legacy_schema_leaves_mismatched_wrapped_mcp_rows_unchanged(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    legacy_payload = {
        "mcpServers": {
            "other_key": {
                "name": "Market Data",
                "description": "Mismatched wrapper key",
                "enabled": True,
                "transport": "http-sse",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": "Bearer secret-token"},
            }
        }
    }

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO mcp_servers (key, version, status, config, created_at, "
                    "updated_at) "
                    "VALUES (:key, :version, :status, CAST(:config AS jsonb), NOW(), NOW())"
                ),
                {
                    "key": "market_data",
                    "version": 1,
                    "status": "draft",
                    "config": json.dumps(legacy_payload, sort_keys=True, separators=(",", ":")),
                },
            )

        upgrade_legacy_schema(engine)

        with engine.connect() as connection:
            stored = connection.execute(
                text("SELECT config FROM mcp_servers WHERE key = :key AND version = :version"),
                {"key": "market_data", "version": 1},
            ).scalar_one()

        assert stored == legacy_payload
    finally:
        engine.dispose()
