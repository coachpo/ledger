from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.session import init_db
from app.db.upgrades import upgrade_legacy_schema
from app.models.mcp_server import McpServer
from app.reset_seed import (
    MAG7_COMPANIES,
    STARTER_PORTFOLIO_SLUG,
    STARTER_TEMPLATE_NAMES,
    STARTER_WORKFLOW_KEY,
    STOCK_ANALYSIS_MCP_SERVER_KEY,
    STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
    STOCK_ANALYSIS_SKILL_KEY,
    STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
    TRADING_DECISION_SCHEMA_KEY,
)

AGENT_PLATFORM_TABLE_NAMES = {
    "agents",
    "mcp_servers",
    "model_connections",
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
RETIRED_STOCK_ANALYSIS_AGENT_KEYS = STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS + (
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
)
RETIRED_STOCK_ANALYSIS_REPORT_SLUGS = tuple(company["reportSlug"] for company in MAG7_COMPANIES)
_LIVE_OUTPUT_SCHEMA_KEY = "market_review_note"
_LIVE_SKILL_KEY = "market_review_tools"
_LIVE_MCP_SERVER_KEY = "market_review_data"
_LIVE_AGENT_KEY = "market_review_agent"
_LIVE_WORKFLOW_KEY = "market_review"
_LIVE_TEMPLATE_NAME = "Quarterly Review"
_LIVE_REPORT_SLUG = "market_review_report"
_LIVE_PORTFOLIO_SLUG = "income_core"
_CUSTOM_STALE_SKILL_KEY = "stock_analysis_ws1_verify"
_RETIRED_REPORT_LOOKUP_TOOL = "ledger.stock_analysis.report_lookup"
_REPAIRED_REPORT_LOOKUP_TOOL = "ledger.reports.lookup"


def _seed_stock_analysis_upgrade_rows(connection) -> int:
    model_connection_id = connection.execute(
        text(
            "INSERT INTO model_connections ("
            "status, name, description, base_url, organization, project, "
            "model_id, reasoning_effort, "
            "timeout_seconds, secret_payload, has_api_key, created_at, updated_at"
            ") VALUES ("
            "'active', :name, :description, 'https://api.openai.com/v1', NULL, NULL, "
            ":model_id, 'medium', 60, '{}'::jsonb, FALSE, NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "name": "Upgrade test connection",
            "description": "Shared connection for stock-analysis sanitation upgrade tests.",
            "model_id": "openai:gpt-5.4-mini",
        },
    ).scalar_one()
    live_output_schema_id = connection.execute(
        text(
            "INSERT INTO output_schemas ("
            "key, version, status, kind, name, description, json_schema, "
            "registry_refs, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', 'standalone', :name, :description, "
            "CAST(:json_schema AS jsonb), '[]'::jsonb, NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "key": _LIVE_OUTPUT_SCHEMA_KEY,
            "name": "Market Review Note",
            "description": "Live output schema that must survive startup sanitation.",
            "json_schema": json.dumps({"type": "object", "additionalProperties": False}),
        },
    ).scalar_one()
    retired_note_schema_id = connection.execute(
        text(
            "INSERT INTO output_schemas ("
            "key, version, status, kind, name, description, json_schema, "
            "registry_refs, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', 'standalone', :name, :description, "
            "CAST(:json_schema AS jsonb), '[]'::jsonb, NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "key": STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
            "name": "Stock Analysis Note",
            "description": "Retired stock-analysis output schema persisted before upgrade.",
            "json_schema": json.dumps({"type": "object", "additionalProperties": False}),
        },
    ).scalar_one()
    retired_decision_schema_id = connection.execute(
        text(
            "INSERT INTO output_schemas ("
            "key, version, status, kind, name, description, json_schema, "
            "registry_refs, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', 'standalone', :name, :description, "
            "CAST(:json_schema AS jsonb), '[]'::jsonb, NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "key": TRADING_DECISION_SCHEMA_KEY,
            "name": "Trading Decision",
            "description": "Retired stock-analysis decision schema persisted before upgrade.",
            "json_schema": json.dumps({"type": "object", "additionalProperties": False}),
        },
    ).scalar_one()
    connection.execute(
        text(
            "INSERT INTO skills ("
            "key, version, status, name, description, tool_definitions, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', :name, :description, "
            "CAST(:tool_definitions AS jsonb), NOW(), NOW()"
            ")"
        ),
        [
            {
                "key": _LIVE_SKILL_KEY,
                "name": "Market Review Tools",
                "description": "Live skill that must remain after startup sanitation.",
                "tool_definitions": json.dumps([{"tool": "ledger.reports.lookup"}]),
            },
            {
                "key": STOCK_ANALYSIS_SKILL_KEY,
                "name": "Stock Analysis Tools",
                "description": "Retired stock-analysis skill persisted before upgrade.",
                "tool_definitions": json.dumps([{"tool": "ledger.stock_analysis.report_lookup"}]),
            },
        ],
    )
    connection.execute(
        text(
            "INSERT INTO mcp_servers ("
            "key, version, status, config, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', CAST(:config AS jsonb), NOW(), NOW()"
            ")"
        ),
        [
            {
                "key": _LIVE_MCP_SERVER_KEY,
                "config": json.dumps(
                    {
                        "name": "Market Review Data",
                        "enabled": True,
                        "transport": "http-sse",
                        "url": "https://example.com/live-mcp",
                    }
                ),
            },
            {
                "key": STOCK_ANALYSIS_MCP_SERVER_KEY,
                "config": json.dumps(
                    {
                        "name": "Stock Analysis Data",
                        "enabled": True,
                        "transport": "stdio",
                        "command": "python3",
                        "args": ["-V"],
                    }
                ),
            },
        ],
    )
    connection.execute(
        text(
            "INSERT INTO agents ("
            "key, version, status, name, description, model_connection_id, model, "
            "system_prompt, input_schema, output_schema_id, output_schema_version, skills, "
            "mcp_servers, budget_usd, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', :name, :description, :model_connection_id, :model, "
            ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, 1, "
            "CAST(:skills AS jsonb), CAST(:mcp_servers AS jsonb), 0, NOW(), NOW()"
            ")"
        ),
        [
            {
                "key": _LIVE_AGENT_KEY,
                "name": "Market Review Agent",
                "description": "Live agent that must remain after startup sanitation.",
                "model_connection_id": model_connection_id,
                "model": "openai:gpt-5.4-mini",
                "system_prompt": "Summarize the market review context.",
                "input_schema": json.dumps({"type": "object", "additionalProperties": False}),
                "output_schema_id": live_output_schema_id,
                "skills": json.dumps([{"skillKey": _LIVE_SKILL_KEY, "skillVersion": 1}]),
                "mcp_servers": json.dumps(
                    [{"mcpServerKey": _LIVE_MCP_SERVER_KEY, "mcpServerVersion": 1}]
                ),
            },
            *[
                {
                    "key": agent_key,
                    "name": agent_key.replace("_", " ").title(),
                    "description": f"Retired stock-analysis agent for {agent_key}.",
                    "model_connection_id": model_connection_id,
                    "model": "openai:gpt-5.4-mini",
                    "system_prompt": f"Retired stock-analysis agent prompt for {agent_key}.",
                    "input_schema": json.dumps({"type": "object", "additionalProperties": False}),
                    "output_schema_id": (
                        retired_decision_schema_id
                        if agent_key == STOCK_ANALYSIS_SYNTHESIZER_KEY
                        else retired_note_schema_id
                    ),
                    "skills": json.dumps(
                        [{"skillKey": STOCK_ANALYSIS_SKILL_KEY, "skillVersion": 1}]
                    ),
                    "mcp_servers": json.dumps(
                        [
                            {
                                "mcpServerKey": STOCK_ANALYSIS_MCP_SERVER_KEY,
                                "mcpServerVersion": 1,
                            }
                        ]
                    ),
                }
                for agent_key in RETIRED_STOCK_ANALYSIS_AGENT_KEYS
            ],
        ],
    )
    connection.execute(
        text(
            "INSERT INTO workflows ("
            "key, version, status, name, description, input_schema, steps, output_spec, "
            "aggregate_budget_usd, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', :name, :description, CAST(:input_schema AS jsonb), "
            "CAST(:steps AS jsonb), CAST(:output_spec AS jsonb), 0, NOW(), NOW()"
            ")"
        ),
        [
            {
                "key": _LIVE_WORKFLOW_KEY,
                "name": "Market Review",
                "description": "Live workflow that must remain after startup sanitation.",
                "input_schema": json.dumps({"type": "object", "additionalProperties": False}),
                "steps": json.dumps(
                    [
                        {
                            "index": 1,
                            "agents": [
                                {
                                    "agentKey": _LIVE_AGENT_KEY,
                                    "slot": "review",
                                    "wiring": {},
                                }
                            ],
                        }
                    ]
                ),
                "output_spec": json.dumps({"kind": "slot", "stepIndex": 1, "slot": "review"}),
            },
            {
                "key": STARTER_WORKFLOW_KEY,
                "name": "Stock Analysis",
                "description": "Retired stock-analysis workflow persisted before upgrade.",
                "input_schema": json.dumps({"type": "object", "additionalProperties": False}),
                "steps": json.dumps(
                    [
                        {
                            "index": 1,
                            "agents": [
                                {
                                    "agentKey": RETIRED_STOCK_ANALYSIS_AGENT_KEYS[0],
                                    "slot": RETIRED_STOCK_ANALYSIS_AGENT_KEYS[0],
                                    "wiring": {},
                                }
                            ],
                        }
                    ]
                ),
                "output_spec": json.dumps(
                    {
                        "kind": "slot",
                        "stepIndex": 1,
                        "slot": RETIRED_STOCK_ANALYSIS_AGENT_KEYS[0],
                    }
                ),
            },
        ],
    )
    retired_portfolio_id = connection.execute(
        text(
            "INSERT INTO portfolios ("
            "name, slug, description, base_currency, created_at, updated_at"
            ") VALUES ("
            ":name, :slug, :description, 'USD', NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "name": "Mag7 Core Portfolio",
            "slug": STARTER_PORTFOLIO_SLUG,
            "description": "Retired starter portfolio persisted before upgrade.",
        },
    ).scalar_one()
    live_portfolio_id = connection.execute(
        text(
            "INSERT INTO portfolios ("
            "name, slug, description, base_currency, created_at, updated_at"
            ") VALUES ("
            ":name, :slug, :description, 'USD', NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "name": "Income Core",
            "slug": _LIVE_PORTFOLIO_SLUG,
            "description": "Live portfolio that must remain after startup sanitation.",
        },
    ).scalar_one()
    connection.execute(
        text(
            "INSERT INTO balances ("
            "portfolio_id, label, operation_type, amount, currency, created_at, updated_at"
            ") VALUES ("
            ":portfolio_id, :label, :operation_type, :amount, 'USD', NOW(), NOW()"
            ")"
        ),
        [
            {
                "portfolio_id": retired_portfolio_id,
                "label": "Core Cash",
                "operation_type": "DEPOSIT",
                "amount": "250000.00",
            },
            {
                "portfolio_id": live_portfolio_id,
                "label": "Income Cash",
                "operation_type": "DEPOSIT",
                "amount": "80000.00",
            },
        ],
    )
    connection.execute(
        text(
            "INSERT INTO positions ("
            "portfolio_id, symbol, name, quantity, average_cost, currency, last_source, "
            "created_at, updated_at"
            ") VALUES ("
            ":portfolio_id, :symbol, :name, :quantity, :average_cost, 'USD', 'manual', "
            "NOW(), NOW()"
            ")"
        ),
        [
            {
                "portfolio_id": retired_portfolio_id,
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "quantity": "40.00000000",
                "average_cost": "185.50000000",
            },
            {
                "portfolio_id": live_portfolio_id,
                "symbol": "BND",
                "name": "Vanguard Total Bond Market ETF",
                "quantity": "12.00000000",
                "average_cost": "72.10000000",
            },
        ],
    )
    connection.execute(
        text(
            "INSERT INTO text_templates (name, content, created_at, updated_at) VALUES ("
            ":name, :content, NOW(), NOW()"
            ")"
        ),
        [
            {
                "name": STARTER_TEMPLATE_NAMES[0],
                "content": "Retired Mag7 portfolio snapshot template.",
            },
            {
                "name": STARTER_TEMPLATE_NAMES[1],
                "content": "Retired Mag7 ticker review template.",
            },
            {
                "name": _LIVE_TEMPLATE_NAME,
                "content": "Live template that must remain after startup sanitation.",
            },
        ],
    )
    connection.execute(
        text(
            "INSERT INTO reports ("
            "name, slug, source, content, metadata, created_at, updated_at"
            ") VALUES ("
            ":name, :slug, 'uploaded', :content, CAST(:metadata AS jsonb), NOW(), NOW()"
            ")"
        ),
        [
            *[
                {
                    "name": f"{company['symbol']} Seed Analysis",
                    "slug": company["reportSlug"],
                    "content": f"Retired stock-analysis seed report for {company['symbol']}.",
                    "metadata": json.dumps(
                        {
                            "author": "Seeded Mag7 Workspace",
                            "tags": ["mag7", "seed", company["reportTag"]],
                            "analysis": {
                                "ticker": company["symbol"],
                                "portfolioSlug": STARTER_PORTFOLIO_SLUG,
                            },
                        }
                    ),
                }
                for company in MAG7_COMPANIES
            ],
            {
                "name": "Market Review Report",
                "slug": _LIVE_REPORT_SLUG,
                "content": "Live report that must remain after startup sanitation.",
                "metadata": json.dumps({"tags": ["live"]}),
            },
        ],
    )
    return retired_portfolio_id


def _stock_analysis_sanitation_snapshot(
    connection,
    *,
    retired_portfolio_id: int,
) -> dict[str, object]:
    output_schema_keys = (
        connection.execute(text("SELECT key FROM output_schemas ORDER BY key")).scalars().all()
    )
    skill_keys = connection.execute(text("SELECT key FROM skills ORDER BY key")).scalars().all()
    mcp_server_keys = (
        connection.execute(text("SELECT key FROM mcp_servers ORDER BY key")).scalars().all()
    )
    agent_keys = connection.execute(text("SELECT key FROM agents ORDER BY key")).scalars().all()
    workflow_keys = (
        connection.execute(text("SELECT key FROM workflows ORDER BY key")).scalars().all()
    )
    template_names = (
        connection.execute(text("SELECT name FROM text_templates ORDER BY name")).scalars().all()
    )
    report_slugs = (
        connection.execute(text("SELECT slug FROM reports ORDER BY slug")).scalars().all()
    )
    portfolio_slugs = (
        connection.execute(text("SELECT slug FROM portfolios ORDER BY slug")).scalars().all()
    )
    retired_balance_count = connection.execute(
        text("SELECT COUNT(*) FROM balances WHERE portfolio_id = :portfolio_id"),
        {"portfolio_id": retired_portfolio_id},
    ).scalar_one()
    retired_position_count = connection.execute(
        text("SELECT COUNT(*) FROM positions WHERE portfolio_id = :portfolio_id"),
        {"portfolio_id": retired_portfolio_id},
    ).scalar_one()
    live_balance_count = connection.execute(
        text(
            "SELECT COUNT(*) FROM balances WHERE portfolio_id = ("
            "SELECT id FROM portfolios WHERE slug = :slug"
            ")"
        ),
        {"slug": _LIVE_PORTFOLIO_SLUG},
    ).scalar_one()
    live_position_count = connection.execute(
        text(
            "SELECT COUNT(*) FROM positions WHERE portfolio_id = ("
            "SELECT id FROM portfolios WHERE slug = :slug"
            ")"
        ),
        {"slug": _LIVE_PORTFOLIO_SLUG},
    ).scalar_one()

    return {
        "output_schema_keys": output_schema_keys,
        "skill_keys": skill_keys,
        "mcp_server_keys": mcp_server_keys,
        "agent_keys": agent_keys,
        "workflow_keys": workflow_keys,
        "template_names": template_names,
        "report_slugs": report_slugs,
        "portfolio_slugs": portfolio_slugs,
        "retired_balance_count": retired_balance_count,
        "retired_position_count": retired_position_count,
        "live_balance_count": live_balance_count,
        "live_position_count": live_position_count,
    }


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
                "target_kind, target_id, target_key, target_version, status, input, "
                "per_step_outputs"
                ") VALUES ('workflow', 1, 'stock_analysis', 1, 'running', '{}'::jsonb, '{}'::jsonb)"
            )

        init_db(database_url)

        with engine.connect() as connection:
            repaired_run = connection.exec_driver_sql(
                "SELECT status, error, finished_at IS NOT NULL FROM runs"
            ).one()

        assert repaired_run == ("failed", _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE, True)
    finally:
        engine.dispose()


def test_init_db_sanitize_stock_analysis_resources_is_idempotent(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            retired_portfolio_id = _seed_stock_analysis_upgrade_rows(connection)

        init_db(database_url)

        with engine.connect() as connection:
            first_snapshot = _stock_analysis_sanitation_snapshot(
                connection,
                retired_portfolio_id=retired_portfolio_id,
            )

        assert first_snapshot == {
            "output_schema_keys": [_LIVE_OUTPUT_SCHEMA_KEY],
            "skill_keys": [_LIVE_SKILL_KEY],
            "mcp_server_keys": [_LIVE_MCP_SERVER_KEY],
            "agent_keys": [_LIVE_AGENT_KEY],
            "workflow_keys": [_LIVE_WORKFLOW_KEY],
            "template_names": [_LIVE_TEMPLATE_NAME],
            "report_slugs": [_LIVE_REPORT_SLUG],
            "portfolio_slugs": [_LIVE_PORTFOLIO_SLUG],
            "retired_balance_count": 0,
            "retired_position_count": 0,
            "live_balance_count": 1,
            "live_position_count": 1,
        }

        init_db(database_url)

        with engine.connect() as connection:
            second_snapshot = _stock_analysis_sanitation_snapshot(
                connection,
                retired_portfolio_id=retired_portfolio_id,
            )

        assert second_snapshot == first_snapshot
    finally:
        engine.dispose()


def test_init_db_repairs_custom_key_stale_skill_tool_definitions_idempotently(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            stale_skill_id = connection.execute(
                text(
                    "INSERT INTO skills ("
                    "key, version, status, name, description, tool_definitions, "
                    "created_at, updated_at"
                    ") VALUES ("
                    ":key, 1, 'draft', :name, :description, CAST(:tool_definitions AS jsonb), "
                    "NOW(), NOW()"
                    ") RETURNING id"
                ),
                {
                    "key": _CUSTOM_STALE_SKILL_KEY,
                    "name": "Stock Analysis Workspace Verify",
                    "description": "Custom-key stale tool definition repaired during startup.",
                    "tool_definitions": json.dumps(
                        [{"tool": _RETIRED_REPORT_LOOKUP_TOOL}],
                        separators=(",", ":"),
                    ),
                },
            ).scalar_one()

        init_db(database_url)

        with engine.connect() as connection:
            first_row = (
                connection.execute(
                    text(
                        "SELECT key, version, status, tool_definitions, ctid::text AS row_pointer "
                        "FROM skills WHERE id = :skill_id"
                    ),
                    {"skill_id": stale_skill_id},
                )
                .mappings()
                .one()
            )
            retired_reference_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM skills "
                    "WHERE tool_definitions @> CAST(:retired_tool_filter AS jsonb)"
                ),
                {
                    "retired_tool_filter": json.dumps(
                        [{"tool": _RETIRED_REPORT_LOOKUP_TOOL}],
                        separators=(",", ":"),
                    )
                },
            ).scalar_one()

        assert first_row["key"] == _CUSTOM_STALE_SKILL_KEY
        assert first_row["version"] == 1
        assert first_row["status"] == "draft"
        assert first_row["tool_definitions"] == [{"tool": _REPAIRED_REPORT_LOOKUP_TOOL}]
        assert retired_reference_count == 0

        init_db(database_url)

        with engine.connect() as connection:
            second_row = (
                connection.execute(
                    text(
                        "SELECT tool_definitions, ctid::text AS row_pointer "
                        "FROM skills WHERE id = :skill_id"
                    ),
                    {"skill_id": stale_skill_id},
                )
                .mappings()
                .one()
            )

        assert second_row["tool_definitions"] == first_row["tool_definitions"]
        assert second_row["row_pointer"] == first_row["row_pointer"]
    finally:
        engine.dispose()


def test_init_db_repairs_legacy_run_identity_columns_to_target_columns(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE runs (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    workflow_id INTEGER NOT NULL,
                    workflow_key VARCHAR(120) NOT NULL,
                    workflow_version INTEGER NOT NULL,
                    input JSONB NOT NULL,
                    per_step_outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
                    final_output JSONB,
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
                    trace_id VARCHAR(255),
                    error TEXT,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_runs_status CHECK (
                        status IN ('running', 'succeeded', 'failed')
                    ),
                    CONSTRAINT ck_runs_workflow_version_positive CHECK (workflow_version > 0),
                    CONSTRAINT ck_runs_total_tokens_non_negative CHECK (total_tokens >= 0),
                    CONSTRAINT ck_runs_total_cost_non_negative CHECK (total_cost_usd >= 0)
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_runs_workflow ON runs (workflow_id, workflow_version)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_runs_workflow_key ON runs (workflow_key, workflow_version)"
            )
            connection.exec_driver_sql(
                "INSERT INTO runs ("
                "workflow_id, workflow_key, workflow_version, input, per_step_outputs, "
                "final_output, status, total_tokens, total_cost_usd, trace_id"
                ") VALUES ("
                "7, 'market_review', 3, '{}'::jsonb, '{}'::jsonb, '{\"headline\":\"Buy\"}'::jsonb, "
                "'succeeded', 321, 0.15, 'trace-legacy-run'"
                ")"
            )

        init_db(database_url)
        init_db(database_url)

        run_columns = {column["name"]: column for column in inspect(engine).get_columns("runs")}
        run_indexes = {index["name"] for index in inspect(engine).get_indexes("runs")}
        run_constraints = {
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints("runs")
            if constraint.get("name")
        }

        with engine.connect() as connection:
            migrated_run = connection.execute(
                text(
                    "SELECT target_kind, target_id, target_key, target_version, final_output "
                    "FROM runs WHERE trace_id = :trace_id"
                ),
                {"trace_id": "trace-legacy-run"},
            ).one()

        assert {"target_kind", "target_id", "target_key", "target_version"} <= set(run_columns)
        assert {"workflow_id", "workflow_key", "workflow_version"}.isdisjoint(run_columns)
        assert run_columns["target_kind"]["nullable"] is False
        assert run_columns["target_id"]["nullable"] is False
        assert run_columns["target_key"]["nullable"] is False
        assert run_columns["target_version"]["nullable"] is False
        assert {"ix_runs_status", "ix_runs_target", "ix_runs_target_key"} <= run_indexes
        assert {"ix_runs_workflow", "ix_runs_workflow_key"}.isdisjoint(run_indexes)
        assert {"ck_runs_target_kind", "ck_runs_target_version_positive"} <= run_constraints
        assert "ck_runs_workflow_version_positive" not in run_constraints
        assert migrated_run == ("workflow", 7, "market_review", 3, {"headline": "Buy"})
    finally:
        engine.dispose()


def test_init_db_rejects_conflicting_legacy_and_target_run_identity(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE runs (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    workflow_id INTEGER NOT NULL,
                    workflow_key VARCHAR(120) NOT NULL,
                    workflow_version INTEGER NOT NULL,
                    target_kind VARCHAR(20),
                    target_id INTEGER,
                    target_key VARCHAR(120),
                    target_version INTEGER,
                    input JSONB NOT NULL,
                    per_step_outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
                    final_output JSONB,
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
                    trace_id VARCHAR(255),
                    error TEXT,
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_runs_status CHECK (
                        status IN ('running', 'succeeded', 'failed')
                    ),
                    CONSTRAINT ck_runs_workflow_version_positive CHECK (workflow_version > 0),
                    CONSTRAINT ck_runs_total_tokens_non_negative CHECK (total_tokens >= 0),
                    CONSTRAINT ck_runs_total_cost_non_negative CHECK (total_cost_usd >= 0)
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO runs ("
                "workflow_id, workflow_key, workflow_version, target_kind, target_id, target_key, "
                "target_version, input, per_step_outputs, status"
                ") VALUES ("
                "7, 'market_review', 3, 'agent', 9, 'different_target', "
                "4, '{}'::jsonb, '{}'::jsonb, 'succeeded'"
                ")"
            )

        with pytest.raises(RuntimeError, match="Cannot auto-upgrade runs table"):
            init_db(database_url)
    finally:
        engine.dispose()


def test_init_db_fresh_schema_makes_agent_model_connection_id_non_null(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert agent_columns["model_connection_id"]["nullable"] is False
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


def test_init_db_backfills_legacy_agent_models_into_placeholder_model_connections(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE agents (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    model VARCHAR(200) NOT NULL,
                    system_prompt TEXT NOT NULL,
                    input_schema JSONB NOT NULL,
                    output_schema_id INTEGER NOT NULL,
                    output_schema_version INTEGER NOT NULL,
                    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
                    mcp_servers JSONB NOT NULL DEFAULT '[]'::jsonb,
                    budget_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_agents_status CHECK (
                        status IN ('draft', 'published', 'deprecated', 'archived')
                    ),
                    CONSTRAINT ck_agents_version_positive CHECK (version > 0),
                    CONSTRAINT ck_agents_output_schema_version_positive CHECK (
                        output_schema_version > 0
                    ),
                    CONSTRAINT ck_agents_budget_usd_non_negative CHECK (budget_usd >= 0),
                    CONSTRAINT uq_agents_key_version UNIQUE (key, version)
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model, system_prompt, input_schema, "
                    "output_schema_id, output_schema_version, skills, mcp_servers, budget_usd"
                    ") VALUES ("
                    ":key, :version, :status, :name, :description, :model, :system_prompt, "
                    "CAST(:input_schema AS jsonb), :output_schema_id, :output_schema_version, "
                    "CAST(:skills AS jsonb), CAST(:mcp_servers AS jsonb), :budget_usd"
                    ")"
                ),
                [
                    {
                        "key": "research_agent_alpha",
                        "version": 1,
                        "status": "published",
                        "name": "Research Agent Alpha",
                        "description": "Legacy agent row",
                        "model": "openai:gpt-5.4-mini",
                        "system_prompt": "Analyze the ticker.",
                        "input_schema": '{"type":"object"}',
                        "output_schema_id": 1,
                        "output_schema_version": 1,
                        "skills": "[]",
                        "mcp_servers": "[]",
                        "budget_usd": 0,
                    },
                    {
                        "key": "research_agent_beta",
                        "version": 1,
                        "status": "published",
                        "name": "Research Agent Beta",
                        "description": "Legacy agent row",
                        "model": "openai:gpt-5.4-mini",
                        "system_prompt": "Analyze the ticker.",
                        "input_schema": '{"type":"object"}',
                        "output_schema_id": 1,
                        "output_schema_version": 1,
                        "skills": "[]",
                        "mcp_servers": "[]",
                        "budget_usd": 0,
                    },
                    {
                        "key": "research_agent_gamma",
                        "version": 1,
                        "status": "draft",
                        "name": "Research Agent Gamma",
                        "description": "Legacy agent row",
                        "model": "openai:gpt-5.4",
                        "system_prompt": "Analyze the ticker.",
                        "input_schema": '{"type":"object"}',
                        "output_schema_id": 1,
                        "output_schema_version": 1,
                        "skills": "[]",
                        "mcp_servers": "[]",
                        "budget_usd": 0,
                    },
                ],
            )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            placeholder_rows = connection.execute(
                text(
                    "SELECT name, model_id, base_url, reasoning_effort, "
                    "timeout_seconds, has_api_key "
                    "FROM model_connections ORDER BY model_id ASC"
                )
            ).all()
            linked_agents = connection.execute(
                text(
                    "SELECT a.key, a.model, a.model_connection_id, mc.model_id "
                    "FROM agents AS a "
                    "JOIN model_connections AS mc ON mc.id = a.model_connection_id "
                    "ORDER BY a.key ASC"
                )
            ).all()
            unresolved_agents = connection.execute(
                text("SELECT COUNT(*) FROM agents WHERE model_connection_id IS NULL")
            ).scalar_one()
            shared_placeholder_ids = connection.execute(
                text(
                    "SELECT COUNT(DISTINCT model_connection_id) "
                    "FROM agents WHERE model = 'openai:gpt-5.4-mini'"
                )
            ).scalar_one()

        repaired_agent_columns = {
            column["name"]: column for column in inspect(engine).get_columns("agents")
        }
        linked_agent_by_key = {row[0]: row for row in linked_agents}

        assert placeholder_rows == [
            (
                "openai:gpt-5.4",
                "openai:gpt-5.4",
                "https://api.openai.com/v1",
                "medium",
                60,
                False,
            ),
            (
                "openai:gpt-5.4-mini",
                "openai:gpt-5.4-mini",
                "https://api.openai.com/v1",
                "medium",
                60,
                False,
            ),
        ]
        assert unresolved_agents == 0
        assert linked_agent_by_key["research_agent_alpha"][1:] == (
            "openai:gpt-5.4-mini",
            linked_agent_by_key["research_agent_alpha"][2],
            "openai:gpt-5.4-mini",
        )
        assert linked_agent_by_key["research_agent_beta"][1:] == (
            "openai:gpt-5.4-mini",
            linked_agent_by_key["research_agent_alpha"][2],
            "openai:gpt-5.4-mini",
        )
        assert linked_agent_by_key["research_agent_gamma"][1:] == (
            "openai:gpt-5.4",
            linked_agent_by_key["research_agent_gamma"][2],
            "openai:gpt-5.4",
        )
        assert shared_placeholder_ids == 1
        assert repaired_agent_columns["model_connection_id"]["nullable"] is False
        assert {"temperature", "max_tool_rounds", "streaming"}.isdisjoint(repaired_agent_columns)
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_repairs_existing_nullable_model_connection_column(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE agents ALTER COLUMN model_connection_id DROP NOT NULL"
            )
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model_connection_id, model, "
                    "system_prompt, input_schema, output_schema_id, output_schema_version, skills, "
                    "mcp_servers, budget_usd"
                    ") VALUES ("
                    ":key, :version, :status, :name, :description, NULL, :model, "
                    ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, "
                    ":output_schema_version, CAST(:skills AS jsonb), CAST(:mcp_servers AS jsonb), "
                    ":budget_usd"
                    ")"
                ),
                {
                    "key": "repair_nullable_agent",
                    "version": 1,
                    "status": "published",
                    "name": "Repair Nullable Agent",
                    "description": "Partial-upgrade agent row",
                    "model": "openai:gpt-5.4-mini",
                    "system_prompt": "Analyze the ticker.",
                    "input_schema": '{"type":"object"}',
                    "output_schema_id": 1,
                    "output_schema_version": 1,
                    "skills": "[]",
                    "mcp_servers": "[]",
                    "budget_usd": 0,
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            placeholder_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections WHERE model_id = :model_id"),
                {"model_id": "openai:gpt-5.4-mini"},
            ).scalar_one()
            linked_agent = connection.execute(
                text(
                    "SELECT model_connection_id IS NOT NULL "
                    "FROM agents WHERE key = :key AND version = 1"
                ),
                {"key": "repair_nullable_agent"},
            ).scalar_one()

        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert placeholder_count == 1
        assert linked_agent is True
        assert agent_columns["model_connection_id"]["nullable"] is False
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_rehardens_nullable_model_connection_column_when_already_linked(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            linked_model_connection_id = connection.execute(
                text(
                    "INSERT INTO model_connections ("
                    "status, name, description, base_url, organization, project, model_id, "
                    "reasoning_effort, timeout_seconds, secret_payload, has_api_key, "
                    "created_at, updated_at"
                    ") VALUES ("
                    "'active', :name, '', 'https://api.openai.com/v1', NULL, NULL, :model_id, "
                    "'medium', 60, '{}'::jsonb, FALSE, NOW(), NOW()"
                    ") RETURNING id"
                ),
                {"name": "prelinked-connection", "model_id": "openai:gpt-5.4-mini"},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model_connection_id, model, "
                    "system_prompt, input_schema, output_schema_id, output_schema_version, skills, "
                    "mcp_servers, budget_usd"
                    ") VALUES ("
                    ":key, :version, :status, :name, :description, :model_connection_id, :model, "
                    ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, "
                    ":output_schema_version, CAST(:skills AS jsonb), CAST(:mcp_servers AS jsonb), "
                    ":budget_usd"
                    ")"
                ),
                {
                    "key": "already_linked_agent",
                    "version": 1,
                    "status": "published",
                    "name": "Already Linked Agent",
                    "description": "Nullable-column no-backfill row",
                    "model_connection_id": linked_model_connection_id,
                    "model": "openai:gpt-5.4-mini",
                    "system_prompt": "Analyze the ticker.",
                    "input_schema": '{"type":"object"}',
                    "output_schema_id": 1,
                    "output_schema_version": 1,
                    "skills": "[]",
                    "mcp_servers": "[]",
                    "budget_usd": 0,
                },
            )
            connection.exec_driver_sql(
                "ALTER TABLE agents ALTER COLUMN model_connection_id DROP NOT NULL"
            )

        init_db(database_url)

        with engine.connect() as connection:
            linked_agent_id = connection.execute(
                text("SELECT model_connection_id FROM agents WHERE key = :key AND version = 1"),
                {"key": "already_linked_agent"},
            ).scalar_one()
            placeholder_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections WHERE model_id = :model_id"),
                {"model_id": "openai:gpt-5.4-mini"},
            ).scalar_one()

        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert linked_agent_id == linked_model_connection_id
        assert placeholder_count == 1
        assert agent_columns["model_connection_id"]["nullable"] is False
    finally:
        engine.dispose()


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
