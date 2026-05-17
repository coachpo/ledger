from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.db.session import init_db
from app.db.upgrades import _ensure_agent_model_connection_snapshot_support, upgrade_legacy_schema
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.mcp_server import McpServer
from app.reset_seed import (
    MAG7_COMPANIES,
    STARTER_PORTFOLIO_SLUG,
    STARTER_TEMPLATE_NAMES,
    STARTER_WORKFLOW_KEY,
    STOCK_ANALYSIS_CAPABILITY_KEY,
    STOCK_ANALYSIS_MCP_SERVER_KEY,
    STOCK_ANALYSIS_NOTE_SCHEMA_KEY,
    STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS,
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
    TRADING_DECISION_SCHEMA_KEY,
)
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

AGENT_PLATFORM_TABLE_NAMES = {
    "agents",
    "mcp_servers",
    "model_connections",
    "output_schemas",
    "run_agent_invocations",
    "run_operation_invocations",
    "run_steps",
    "runs",
    "capabilities",
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
_AGENT_PLATFORM_PENDING_SKIP_MESSAGE = (
    "Runtime row skipped during startup recovery because the parent run failed before it started."
)
RETIRED_STOCK_ANALYSIS_AGENT_KEYS = STOCK_ANALYSIS_STEP_ONE_AGENT_KEYS + (
    STOCK_ANALYSIS_SYNTHESIZER_KEY,
)
RETIRED_STOCK_ANALYSIS_REPORT_SLUGS = tuple(company["reportSlug"] for company in MAG7_COMPANIES)
_LIVE_OUTPUT_SCHEMA_KEY = "market_review_note"
_LIVE_CAPABILITY_KEY = "market_review_tools"
_LIVE_MCP_SERVER_KEY = "market_review_data"
_LIVE_AGENT_KEY = "market_review_agent"
_LIVE_WORKFLOW_KEY = "market_review"
_LIVE_TEMPLATE_NAME = "Quarterly Review"
_LIVE_REPORT_SLUG = "market_review_report"
_LIVE_PORTFOLIO_SLUG = "income_core"
_CUSTOM_STALE_SKILL_KEY = "stock_analysis_ws1_verify"
_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS = (
    "_".join(("has", "api", "key")),
    "_".join(("api", "key", "last4")),
)
_RUN_HEADER_COLUMNS = {
    "id",
    "agent_id",
    "workflow_id",
    "target_kind",
    "target_id",
    "target_key",
    "target_version",
    "extension_dependencies",
    "input",
    "status",
    "source_run_id",
    "lineage_root_run_id",
    "forked_from_step_index",
    "resume_step_index",
    "final_output",
    "total_tokens",
    "inherited_tokens",
    "executed_tokens",
    "trace_id",
    "error",
    "queued_at",
    "started_at",
    "finished_at",
    "created_at",
    "updated_at",
}
_RUN_STEP_COLUMNS = {
    "id",
    "run_id",
    "step_index",
    "status",
    "origin",
    "source_run_step_id",
    "source_run_id",
    "source_step_index",
    "graph_metadata",
    "error",
    "started_at",
    "finished_at",
    "persisted_at",
    "created_at",
    "updated_at",
}
_RUN_AGENT_INVOCATION_COLUMNS = {
    "id",
    "run_step_id",
    "run_id",
    "step_index",
    "slot",
    "position",
    "agent_id",
    "agent_key",
    "agent_version",
    "output_schema_id",
    "output_schema_version",
    "input_mode",
    "wiring",
    "graph_metadata",
    "optional",
    "status",
    "resolved_input",
    "resolved_input_origin",
    "output",
    "output_origin",
    "error_code",
    "error_message",
    "error_details",
    "tokens",
    "duration_ms",
    "trace_span_id",
    "source_invocation_id",
    "started_at",
    "finished_at",
    "persisted_at",
    "created_at",
    "updated_at",
}
_RUN_OPERATION_INVOCATION_COLUMNS = {
    "id",
    "run_step_id",
    "run_id",
    "step_index",
    "slot",
    "position",
    "operation_key",
    "operation_kind",
    "output_schema_id",
    "output_schema_version",
    "method",
    "timeout_seconds",
    "request_metadata",
    "response_metadata",
    "graph_metadata",
    "optional",
    "status",
    "output",
    "output_origin",
    "error_code",
    "error_message",
    "error_details",
    "duration_ms",
    "trace_span_id",
    "source_operation_invocation_id",
    "source_run_id",
    "source_run_step_id",
    "source_step_index",
    "started_at",
    "finished_at",
    "persisted_at",
    "created_at",
    "updated_at",
}
_RUNTIME_COST_WORD = "cost"
_RUNTIME_COST_CURRENCY = "usd"
_RUN_COST_COLUMNS = tuple(
    f"{scope}_{_RUNTIME_COST_WORD}_{_RUNTIME_COST_CURRENCY}"
    for scope in ("total", "inherited", "executed")
)
_RUN_COST_CHECKS = tuple(
    f"ck_runs_{scope}_{_RUNTIME_COST_WORD}_non_negative"
    for scope in ("total", "inherited", "executed")
)
_INVOCATION_COST_COLUMN = f"{_RUNTIME_COST_WORD}_{_RUNTIME_COST_CURRENCY}"
_INVOCATION_COST_CHECK = f"ck_run_agent_invocations_{_RUNTIME_COST_WORD}_non_negative"
_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_TRADINGAGENTS_MODEL_CONNECTION_KEY = "tradingagents_primary_model"
_TRADINGAGENTS_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_TRADINGAGENTS_PRESET_SQL_PATH = (
    Path(__file__).parents[1] / "app" / "db" / "tradingagents_advisory_research.sql"
)


def _insert_representable_workflow_package(
    connection: Connection,
    *,
    key: str,
    workflow_key: str = "upgrade_workflow",
) -> dict[str, object]:
    manifest_hash = "a" * 64
    compiled_hash = "b" * 64
    package_id = cast(
        int,
        connection.execute(
            text(
                """
                INSERT INTO workflow_packages (key, name, description, status, draft_source)
                VALUES (:key, :name, '', 'active', '')
                RETURNING id
                """
            ),
            {"key": key, "name": key.replace("_", " ").title()},
        ).scalar_one(),
    )
    version_id = cast(
        int,
        connection.execute(
            text(
                """
                INSERT INTO workflow_package_versions (
                    package_id, version, manifest_source, manifest_hash, package_definition,
                    compiled_plan, compiled_hash, validation_summary
                ) VALUES (
                    :package_id, 1, 'manifest', :manifest_hash,
                    CAST(:package_definition AS jsonb), CAST(:compiled_plan AS jsonb),
                    :compiled_hash, '{"diagnostics": []}'::jsonb
                ) RETURNING id
                """
            ),
            {
                "compiled_hash": compiled_hash,
                "compiled_plan": json.dumps(
                    {"packageKey": key, "workflows": [{"key": workflow_key}]}
                ),
                "manifest_hash": manifest_hash,
                "package_definition": json.dumps(
                    {"metadata": {"key": key}, "spec": {"workflows": [{"key": workflow_key}]}}
                ),
                "package_id": package_id,
            },
        ).scalar_one(),
    )
    _ = connection.execute(
        text("UPDATE workflow_packages SET latest_version_id = :version_id WHERE id = :id"),
        {"id": package_id, "version_id": version_id},
    )
    return {
        "package_id": package_id,
        "package_key": key,
        "version_id": version_id,
        "version": 1,
        "manifest_hash": manifest_hash,
        "compiled_hash": compiled_hash,
        "workflow_key": workflow_key,
    }


def _seed_stock_analysis_upgrade_rows(connection) -> int:
    model_connection_id = connection.execute(
        text(
            "INSERT INTO model_connections ("
            "key, status, name, description, base_url, model_id, reasoning_effort, "
            "timeout_seconds, secret_payload, created_at, updated_at"
            ") VALUES ("
            ":key, 'active', :name, :description, 'https://api.openai.com/v1', "
            ":model_id, 'medium', 60, '{}'::jsonb, NOW(), NOW()"
            ") RETURNING id"
        ),
        {
            "key": "upgrade_test_connection",
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
            "INSERT INTO capabilities ("
            "key, version, status, name, description, tool_keys, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', :name, :description, "
            "CAST(:tool_keys AS jsonb), NOW(), NOW()"
            ")"
        ),
        [
            {
                "key": _LIVE_CAPABILITY_KEY,
                "name": "Market Review Tools",
                "description": "Live capability that must remain after startup sanitation.",
                "tool_keys": json.dumps(["signaldeck.reports.lookup"]),
            },
            {
                "key": STOCK_ANALYSIS_CAPABILITY_KEY,
                "name": "Stock Analysis Tools",
                "description": "Retired stock-analysis capability persisted before upgrade.",
                "tool_keys": json.dumps(["signaldeck.reports.lookup"]),
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
            "system_prompt, input_schema, output_schema_id, output_schema_version, capabilities, "
            "mcp_servers, budget_usd, created_at, updated_at"
            ") VALUES ("
            ":key, 1, 'published', :name, :description, :model_connection_id, :model, "
            ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, 1, "
            "CAST(:capabilities AS jsonb), CAST(:mcp_servers AS jsonb), 0, NOW(), NOW()"
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
                "capabilities": json.dumps(
                    [{"capabilityKey": _LIVE_CAPABILITY_KEY, "capabilityVersion": 1}]
                ),
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
                    "capabilities": json.dumps(
                        [
                            {
                                "capabilityKey": STOCK_ANALYSIS_CAPABILITY_KEY,
                                "capabilityVersion": 1,
                            }
                        ]
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


def _agent_memory_report_metadata(**analysis_overrides: object) -> dict[str, object]:
    analysis: dict[str, object] = {
        "reviewType": "agent_memory",
        "versionGroup": "agent_memory/v1",
        "runId": 4242,
        "agentKey": "portfolio_manager",
        "agentVersion": 7,
        "agentName": "Portfolio Manager",
        "workflowKey": "memory_workflow",
        "workflowVersion": 2,
        "stepId": "write_memory",
        "slot": "decision",
        "traceId": "trace-123",
    }
    analysis.update(analysis_overrides)
    return {
        "analysis": analysis,
        "createdBy": {"type": "external", "agentKey": "spoofed"},
        "tags": ["legacy"],
    }


def _insert_report_upgrade_row(
    connection: Connection,
    *,
    slug: str,
    source: str,
    metadata: dict[str, object],
) -> None:
    _ = connection.execute(
        text(
            """
            INSERT INTO reports (name, slug, source, content, metadata, created_at, updated_at)
            VALUES (:name, :slug, :source, :content, CAST(:metadata AS jsonb), NOW(), NOW())
            """
        ),
        {
            "content": f"Report content for {slug}.",
            "metadata": json.dumps(metadata, sort_keys=True),
            "name": slug.replace("_", " ").title(),
            "slug": slug,
            "source": source,
        },
    )


def _report_upgrade_rows_by_slug(
    engine: Engine,
    slugs: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """
                    SELECT slug, source, metadata
                    FROM reports
                    WHERE slug IN :slugs
                    ORDER BY slug ASC
                    """
                ).bindparams(bindparam("slugs", expanding=True)),
                {"slugs": slugs},
            )
            .mappings()
            .all()
        )
    return {
        str(row["slug"]): {"source": row["source"], "metadata": row["metadata"]} for row in rows
    }


def _foreign_key_signature(
    foreign_key: dict[str, object],
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


def _model_connection_reasoning_effort_check_sql(engine: Engine) -> str:
    return next(
        str(constraint["sqltext"])
        for constraint in inspect(engine).get_check_constraints("model_connections")
        if constraint.get("name") == "ck_model_connections_reasoning_effort"
    )


def _assert_flexible_model_connection_reasoning_effort_check(engine: Engine) -> None:
    check_sql = _model_connection_reasoning_effort_check_sql(engine)
    normalized_sql = " ".join(check_sql.lower().split())
    assert "reasoning_effort" in normalized_sql
    assert "is null" in normalized_sql
    assert "length" in normalized_sql
    assert "btrim" in normalized_sql
    assert "128" in normalized_sql


def _insert_model_connection_reasoning_effort_row(
    connection: Connection,
    *,
    key: str,
    reasoning_effort: object,
    api_style: str = "responses",
) -> int:
    model_connection_id = cast(
        int,
        connection.execute(
            text(
                """
                INSERT INTO model_connections (
                    key, status, name, description, base_url, model_id, reasoning_effort,
                    api_style, timeout_seconds, secret_payload, created_at, updated_at
                ) VALUES (
                    :key, 'active', :name, '', 'https://api.openai.com/v1', :model_id,
                    :reasoning_effort, :api_style, 60, '{}'::jsonb, NOW(), NOW()
                ) RETURNING id
                """
            ),
            {
                "api_style": api_style,
                "key": key,
                "model_id": f"openai:{key}",
                "name": key.replace("_", " ").title(),
                "reasoning_effort": reasoning_effort,
            },
        ).scalar_one(),
    )
    return model_connection_id


def _insert_agent_model_connection_snapshot_row(
    connection: Connection,
    *,
    key: str,
    model_connection_id: int,
    model_id: str,
    model_connection_snapshot: dict[str, object],
) -> None:
    _ = connection.execute(
        text(
            """
            INSERT INTO output_schemas (
                key, version, status, kind, name, description, json_schema,
                registry_refs, created_at, updated_at
            ) VALUES (
                'agent_snapshot_output', 1, 'published', 'standalone',
                'Agent Snapshot Output', '', '{"type":"object"}'::jsonb,
                '[]'::jsonb, NOW(), NOW()
            ) ON CONFLICT (key, version) DO NOTHING
            """
        )
    )
    _ = connection.execute(
        text(
            """
            INSERT INTO agents (
                key, version, status, name, description, model_connection_id, model,
                system_prompt, input_schema, output_schema_id, output_schema_version,
                capabilities, mcp_servers, budget_usd, model_connection_snapshot
            ) VALUES (
                :key, 1, 'published', :name, '', :model_connection_id, :model_id,
                :system_prompt, '{"type":"object"}'::jsonb, 1, 1,
                '[]'::jsonb, '[]'::jsonb, 0, CAST(:model_connection_snapshot AS jsonb)
            )
            """
        ),
        {
            "key": key,
            "model_connection_id": model_connection_id,
            "model_connection_snapshot": json.dumps(model_connection_snapshot),
            "model_id": model_id,
            "name": key.replace("_", " ").title(),
            "system_prompt": "Analyze the ticker.",
        },
    )


def test_agent_model_connection_snapshot_upgrade_drops_legacy_org_project_keys(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO output_schemas (
                        key, version, status, kind, name, description, json_schema,
                        registry_refs, created_at, updated_at
                    ) VALUES (
                        'snapshot_cleanup_output', 1, 'published', 'standalone',
                        'Snapshot Cleanup Output', '', '{"type":"object"}'::jsonb,
                        '[]'::jsonb, NOW(), NOW()
                    )
                    """
                )
            )
            model_connection_id = _insert_model_connection_reasoning_effort_row(
                connection,
                key="snapshot_cleanup_connection",
                reasoning_effort="medium",
            )
            _insert_agent_model_connection_snapshot_row(
                connection,
                key="snapshot_cleanup_agent",
                model_connection_id=model_connection_id,
                model_id="openai:snapshot_cleanup_connection",
                model_connection_snapshot={
                    "base_url": "https://api.openai.com/v1",
                    "model_id": "openai:snapshot_cleanup_connection",
                    "reasoning_effort": "medium",
                    "api_style": "responses",
                    "timeout_seconds": 60,
                    "organization": "legacy-org",
                    "project": "legacy-project",
                },
            )

        _ensure_agent_model_connection_snapshot_support(
            engine,
            set(inspect(engine).get_table_names()),
        )

        with engine.connect() as connection:
            snapshot = connection.execute(
                text(
                    "SELECT model_connection_snapshot FROM agents "
                    "WHERE key = 'snapshot_cleanup_agent'"
                )
            ).scalar_one()

        assert snapshot == {
            "base_url": "https://api.openai.com/v1",
            "model_id": "openai:snapshot_cleanup_connection",
            "reasoning_effort": "medium",
            "api_style": "responses",
            "timeout_seconds": 60,
        }
    finally:
        engine.dispose()


def _assert_model_connection_reasoning_effort_direct_sql_contract(
    engine: Engine,
    *,
    key_prefix: str,
) -> None:
    with engine.begin() as connection:
        _ = _insert_model_connection_reasoning_effort_row(
            connection,
            key=f"{key_prefix}_null",
            reasoning_effort=None,
        )
        _ = _insert_model_connection_reasoning_effort_row(
            connection,
            key=f"{key_prefix}_xhigh",
            reasoning_effort="xhigh",
        )

    with engine.connect() as connection:
        accepted_rows = connection.execute(
            text(
                """
                SELECT key, reasoning_effort FROM model_connections
                WHERE key IN :keys ORDER BY key ASC
                """
            ).bindparams(bindparam("keys", expanding=True)),
            {"keys": (f"{key_prefix}_null", f"{key_prefix}_xhigh")},
        ).all()

    assert accepted_rows == [
        (f"{key_prefix}_null", None),
        (f"{key_prefix}_xhigh", "xhigh"),
    ]
    for invalid_index, invalid_reasoning_effort in enumerate(("", "   "), start=1):
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                _ = _insert_model_connection_reasoning_effort_row(
                    connection,
                    key=f"{key_prefix}_invalid_{invalid_index}",
                    reasoning_effort=invalid_reasoning_effort,
                )


def _assert_runtime_execution_table_shape(engine) -> None:
    inspector = inspect(engine)
    run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
    run_step_columns = {column["name"]: column for column in inspector.get_columns("run_steps")}
    invocation_columns = {
        column["name"]: column for column in inspector.get_columns("run_agent_invocations")
    }
    operation_columns = {
        column["name"]: column for column in inspector.get_columns("run_operation_invocations")
    }
    run_indexes = {index["name"] for index in inspector.get_indexes("runs")}
    run_step_indexes = {index["name"] for index in inspector.get_indexes("run_steps")}
    invocation_indexes = {index["name"] for index in inspector.get_indexes("run_agent_invocations")}
    operation_indexes = {
        index["name"] for index in inspector.get_indexes("run_operation_invocations")
    }
    run_check_constraints = inspector.get_check_constraints("runs")
    run_checks = {
        constraint["name"] for constraint in run_check_constraints if constraint.get("name")
    }
    run_status_sql = next(
        constraint["sqltext"]
        for constraint in run_check_constraints
        if constraint.get("name") == "ck_runs_status"
    )
    run_step_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("run_steps")
        if constraint.get("name")
    }
    invocation_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("run_agent_invocations")
        if constraint.get("name")
    }
    operation_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("run_operation_invocations")
        if constraint.get("name")
    }
    run_step_unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("run_steps")
    }
    invocation_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("run_agent_invocations")
    }
    operation_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("run_operation_invocations")
    }
    run_foreign_keys = {
        _foreign_key_signature(foreign_key) for foreign_key in inspector.get_foreign_keys("runs")
    }
    run_step_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_steps")
    }
    invocation_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_agent_invocations")
    }
    operation_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_operation_invocations")
    }

    assert _RUN_HEADER_COLUMNS <= set(run_columns)
    assert {
        "workflow_key",
        "workflow_version",
        "per_step_outputs",
        *_RUN_COST_COLUMNS,
    }.isdisjoint(run_columns)
    assert run_columns["source_run_id"]["nullable"] is True
    assert run_columns["lineage_root_run_id"]["nullable"] is True
    assert run_columns["resume_step_index"]["nullable"] is False
    assert run_columns["extension_dependencies"]["nullable"] is False
    assert run_columns["queued_at"]["nullable"] is False
    assert run_columns["started_at"]["nullable"] is True
    assert all(status in run_status_sql for status in ("queued", "running", "succeeded", "failed"))
    assert {
        "ix_runs_status",
        "ix_runs_target",
        "ix_runs_target_key",
        "ix_runs_source_run",
        "ix_runs_lineage_root",
    } <= run_indexes
    assert {
        "ck_runs_target_kind",
        "ck_runs_status",
        "ck_runs_target_version_positive",
        "ck_runs_resume_step_index_positive",
        "ck_runs_forked_from_step_index_positive",
        "ck_runs_total_tokens_non_negative",
        "ck_runs_inherited_tokens_non_negative",
        "ck_runs_executed_tokens_non_negative",
    } <= run_checks
    assert set(_RUN_COST_CHECKS).isdisjoint(run_checks)
    assert (("source_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("lineage_root_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("agent_id",), "agents", "CASCADE") in run_foreign_keys
    assert (("workflow_id",), "workflows", "CASCADE") in run_foreign_keys
    assert (("workflow_package_id",), "workflow_packages", "CASCADE") in run_foreign_keys
    assert (
        ("workflow_package_version_id",),
        "workflow_package_versions",
        "CASCADE",
    ) in run_foreign_keys

    assert _RUN_STEP_COLUMNS <= set(run_step_columns)
    assert run_step_columns["run_id"]["nullable"] is False
    assert run_step_columns["step_index"]["nullable"] is False
    assert {
        "ix_run_steps_run_step_index",
        "ix_run_steps_run_status",
        "ix_run_steps_source_run_step",
    } <= run_step_indexes
    assert {
        "ck_run_steps_step_index_positive",
        "ck_run_steps_status",
        "ck_run_steps_origin",
        "ck_run_steps_source_step_index_positive",
    } <= run_step_checks
    assert "uq_run_steps_run_step_index" in run_step_unique_constraints
    assert (("run_id",), "runs", "CASCADE") in run_step_foreign_keys
    assert (("source_run_step_id",), "run_steps", "SET NULL") in run_step_foreign_keys
    assert (("source_run_id",), "runs", "SET NULL") in run_step_foreign_keys

    assert _RUN_AGENT_INVOCATION_COLUMNS <= set(invocation_columns)
    assert _INVOCATION_COST_COLUMN not in invocation_columns
    assert invocation_columns["run_step_id"]["nullable"] is False
    assert invocation_columns["run_id"]["nullable"] is False
    assert invocation_columns["slot"]["nullable"] is False
    assert {
        "ix_run_agent_invocations_run_step_index",
        "ix_run_agent_invocations_run_status",
        "ix_run_agent_invocations_agent_version",
        "ix_run_agent_invocations_source_invocation",
    } <= invocation_indexes
    assert {
        "ck_run_agent_invocations_step_index_positive",
        "ck_run_agent_invocations_position_non_negative",
        "ck_run_agent_invocations_agent_id_positive",
        "ck_run_agent_invocations_agent_version_positive",
        "ck_run_agent_invocations_output_schema_id_positive",
        "ck_run_agent_invocations_output_schema_version_positive",
        "ck_run_agent_invocations_input_mode",
        "ck_run_agent_invocations_status",
        "ck_run_agent_invocations_resolved_input_origin",
        "ck_run_agent_invocations_output_origin",
        "ck_run_agent_invocations_tokens_non_negative",
        "ck_run_agent_invocations_duration_non_negative",
    } <= invocation_checks
    assert _INVOCATION_COST_CHECK not in invocation_checks
    assert "uq_run_agent_invocations_step_slot" in invocation_unique_constraints
    assert (("run_step_id",), "run_steps", "CASCADE") in invocation_foreign_keys
    assert (("run_id",), "runs", "CASCADE") in invocation_foreign_keys
    assert (
        ("source_invocation_id",),
        "run_agent_invocations",
        "SET NULL",
    ) in invocation_foreign_keys

    assert _RUN_OPERATION_INVOCATION_COLUMNS <= set(operation_columns)
    assert operation_columns["run_step_id"]["nullable"] is False
    assert operation_columns["run_id"]["nullable"] is False
    assert operation_columns["slot"]["nullable"] is False
    assert operation_columns["request_metadata"]["nullable"] is False
    assert operation_columns["response_metadata"]["nullable"] is False
    assert {
        "ix_run_operation_invocations_run_step_index",
        "ix_run_operation_invocations_run_status",
        "ix_run_operation_invocations_operation_key",
        "ix_run_operation_invocations_source_operation",
        "ix_run_operation_invocations_source_run",
        "ix_run_operation_invocations_source_run_step",
    } <= operation_indexes
    assert {
        "ck_run_operation_invocations_step_index_positive",
        "ck_run_operation_invocations_position_non_negative",
        "ck_run_operation_invocations_operation_kind",
        "ck_run_operation_invocations_status",
        "ck_run_operation_invocations_output_schema_id_positive",
        "ck_run_operation_invocations_output_schema_version_positive",
        "ck_run_operation_invocations_source_step_index_positive",
        "ck_run_operation_invocations_output_origin",
        "ck_run_operation_invocations_duration_non_negative",
        "ck_run_operation_invocations_timeout_positive",
    } <= operation_checks
    assert "uq_run_operation_invocations_step_slot" in operation_unique_constraints
    assert (("run_step_id",), "run_steps", "CASCADE") in operation_foreign_keys
    assert (("run_id",), "runs", "CASCADE") in operation_foreign_keys
    assert (
        ("source_operation_invocation_id",),
        "run_operation_invocations",
        "SET NULL",
    ) in operation_foreign_keys
    assert (("source_run_id",), "runs", "SET NULL") in operation_foreign_keys
    assert (("source_run_step_id",), "run_steps", "SET NULL") in operation_foreign_keys


def _stock_analysis_sanitation_snapshot(
    connection,
    *,
    retired_portfolio_id: int,
) -> dict[str, object]:
    output_schema_keys = (
        connection.execute(text("SELECT key FROM output_schemas ORDER BY key")).scalars().all()
    )
    capability_keys = (
        connection.execute(text("SELECT key FROM capabilities ORDER BY key")).scalars().all()
    )
    mcp_server_keys = (
        connection.execute(text("SELECT key FROM mcp_servers ORDER BY key")).scalars().all()
    )
    model_connection_keys = (
        connection.execute(text("SELECT key FROM model_connections ORDER BY key")).scalars().all()
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
        "capability_keys": capability_keys,
        "mcp_server_keys": mcp_server_keys,
        "model_connection_keys": model_connection_keys,
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


def test_init_db_creates_capability_tool_keys_and_drops_legacy_backend_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        table_names = set(inspect(engine).get_table_names())
        assert AGENT_PLATFORM_TABLE_NAMES <= table_names
        assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(table_names)
        capability_columns = {
            column["name"] for column in inspect(engine).get_columns("capabilities")
        }
        agent_columns = {column["name"] for column in inspect(engine).get_columns("agents")}
        assert "tool_keys" in capability_columns
        assert "tool_grants" not in capability_columns
        assert "tool_definitions" not in capability_columns
        assert "capabilities" in agent_columns
        assert "skills" not in agent_columns
        _assert_runtime_execution_table_shape(engine)
    finally:
        engine.dispose()


def test_init_db_creates_run_operation_invocations_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_runtime_execution_table_shape(engine)
    finally:
        engine.dispose()


def test_init_db_creates_workflow_package_secret_binding_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("workflow_package_secret_bindings")
        }
        indexes = {
            index["name"] for index in inspector.get_indexes("workflow_package_secret_bindings")
        }
        unique_constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("workflow_package_secret_bindings")
        }
        foreign_keys = {
            _foreign_key_signature(cast(dict[str, object], cast(object, foreign_key)))
            for foreign_key in inspector.get_foreign_keys("workflow_package_secret_bindings")
        }

        assert {
            "id",
            "package_id",
            "key",
            "secret_payload",
            "created_at",
            "updated_at",
        } <= set(columns)
        assert columns["secret_payload"]["nullable"] is False
        assert "ix_workflow_package_secret_bindings_package" in indexes
        assert "ix_workflow_package_secret_bindings_key" in indexes
        assert "uq_workflow_package_secret_bindings_package_key" in unique_constraints
        assert (("package_id",), "workflow_packages", "CASCADE") in foreign_keys
    finally:
        engine.dispose()


def test_init_db_seeds_tradingagents_advisory_preset_without_secret_state(
    database_url: str,
) -> None:
    fixture_source = _TRADINGAGENTS_FIXTURE_PATH.read_text(encoding="utf-8")
    preset_sql = _TRADINGAGENTS_PRESET_SQL_PATH.read_text(encoding="utf-8")
    assert "INSERT INTO workflow_packages" in preset_sql
    assert "INSERT INTO workflow_package_versions" in preset_sql
    assert "INSERT INTO model_connections" not in preset_sql
    assert "workflow_package_secret_bindings (" not in preset_sql
    assert "INSERT INTO runs" not in preset_sql
    compiled = compile_workflow_package_manifest(fixture_source)
    expected_package_definition = cast(dict[str, object], compiled["packageDefinition"])
    expected_compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    expected_agents = cast(
        list[dict[str, object]],
        cast(dict[str, object], expected_package_definition["spec"])["agents"],
    )

    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT
                        package.id AS package_id,
                        package.key,
                        package.name,
                        package.description,
                        package.status,
                        package.latest_version_id,
                        package.draft_source,
                        version.id AS version_id,
                        version.version,
                        version.manifest_source,
                        version.manifest_hash,
                        version.package_definition,
                        version.compiled_plan,
                        version.compiled_hash,
                        version.extension_dependencies,
                        version.validation_summary
                    FROM workflow_packages AS package
                    JOIN workflow_package_versions AS version
                      ON version.id = package.latest_version_id
                    WHERE package.key = :package_key
                    """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
            package_count = connection.execute(
                text("SELECT COUNT(*) FROM workflow_packages")
            ).scalar_one()
            version_count = connection.execute(
                text("SELECT COUNT(*) FROM workflow_package_versions")
            ).scalar_one()
            model_connection_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections")
            ).scalar_one()
            non_empty_model_secret_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections WHERE secret_payload <> '{}'::jsonb")
            ).scalar_one()
            preset_model_connection_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections WHERE key = :key"),
                {"key": _TRADINGAGENTS_MODEL_CONNECTION_KEY},
            ).scalar_one()
            secret_binding_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_secret_bindings
                    WHERE package_id = :package_id
                    """
                ),
                {"package_id": row["package_id"]},
            ).scalar_one()
            preset_reference_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_version_model_connections
                    WHERE workflow_package_version_id = :version_id
                    """
                ),
                {"version_id": row["version_id"]},
            ).scalar_one()
            run_count = connection.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()

        assert package_count == 1
        assert version_count == 1
        assert row["key"] == _TRADINGAGENTS_PRESET_KEY
        assert row["name"] == "TradingAgents Advisory Research"
        assert (
            row["description"]
            == cast(dict[str, object], expected_package_definition["metadata"])["description"]
        )
        assert row["status"] == "active"
        assert row["latest_version_id"] == row["version_id"]
        assert row["version"] == 1
        assert row["draft_source"] == fixture_source
        assert row["manifest_source"] == fixture_source
        assert row["manifest_hash"] == compiled["manifestHash"]
        assert row["compiled_hash"] == compiled["compiledHash"]
        assert row["package_definition"] == expected_package_definition
        assert row["compiled_plan"] == expected_compiled_plan
        extension_dependencies = cast(list[dict[str, object]], row["extension_dependencies"])
        assert extension_dependencies
        assert extension_dependencies[0]["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
        assert "runtime.tool.signaldeck.market_data.quote_lookup" in cast(
            list[str],
            extension_dependencies[0]["surfaces"],
        )

        validation_summary = cast(dict[str, object], row["validation_summary"])
        assert validation_summary["diagnostics"] == []
        warnings = cast(list[dict[str, object]], validation_summary["warnings"])
        assert len(warnings) == len(expected_agents)
        assert all(
            warning["issue"]
            == f"Model connection {_TRADINGAGENTS_MODEL_CONNECTION_KEY!r} was not found"
            for warning in warnings
        )
        assert validation_summary["dbUpgradePreset"] == {
            "allowMissingModelConnections": True,
            "secretSafe": True,
            "source": "phase_b_db_upgrade",
        }

        serialized_preset = (
            fixture_source
            + json.dumps(row["package_definition"], sort_keys=True)
            + json.dumps(row["compiled_plan"], sort_keys=True)
            + json.dumps(row["validation_summary"], sort_keys=True)
        )
        for forbidden_value in (
            "encrypted",
            "requiredBindings",
            "secretPayload",
            "secretRefs",
        ):
            assert forbidden_value not in serialized_preset
        assert re.search(r"\bsk-[A-Za-z0-9_-]{16,}", serialized_preset) is None
        assert model_connection_count == 0
        assert non_empty_model_secret_count == 0
        assert preset_model_connection_count == 0
        assert secret_binding_count == 0
        assert preset_reference_count == 0
        assert run_count == 0

        package_id = row["package_id"]
        version_id = row["version_id"]
        upgrade_legacy_schema(engine)
        with engine.connect() as connection:
            idempotent_row = (
                connection.execute(
                    text(
                        """
                    SELECT package.id AS package_id, version.id AS version_id
                    FROM workflow_packages AS package
                    JOIN workflow_package_versions AS version
                      ON version.id = package.latest_version_id
                    WHERE package.key = :package_key
                    """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
        assert idempotent_row["package_id"] == package_id
        assert idempotent_row["version_id"] == version_id
    finally:
        engine.dispose()


def test_init_db_removes_cost_columns_and_deletes_non_package_runtime_rows(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            for column_name in _RUN_COST_COLUMNS:
                _ = connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD COLUMN {column_name} NUMERIC(20, 8) NOT NULL DEFAULT 0"
                )
            for column_name, constraint_name in zip(
                _RUN_COST_COLUMNS,
                _RUN_COST_CHECKS,
                strict=True,
            ):
                _ = connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD CONSTRAINT {constraint_name} CHECK ({column_name} >= 0)"
                )
            statement = (
                "ALTER TABLE run_agent_invocations ADD COLUMN "
                + f"{_INVOCATION_COST_COLUMN} NUMERIC(20, 8) NOT NULL DEFAULT 0"
            )
            _ = connection.exec_driver_sql(statement)
            statement = (
                "ALTER TABLE run_agent_invocations ADD CONSTRAINT "
                + f"{_INVOCATION_COST_CHECK} CHECK ({_INVOCATION_COST_COLUMN} >= 0)"
            )
            _ = connection.exec_driver_sql(statement)

            package = _insert_representable_workflow_package(
                connection,
                key="cost_package",
                workflow_key="cost_workflow",
            )
            run_cost_columns_sql = ", ".join(_RUN_COST_COLUMNS)
            run_cost_placeholders_sql = ", ".join(
                f":run_legacy_amount_{index}" for index, _ in enumerate(_RUN_COST_COLUMNS)
            )
            run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "input, status, total_tokens, inherited_tokens, executed_tokens, "
                    f"{run_cost_columns_sql}"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, '{}'::jsonb, 'succeeded', 17, 5, 12, "
                    f"{run_cost_placeholders_sql}"
                    ") RETURNING id"
                ),
                {
                    **package,
                    **{
                        f"run_legacy_amount_{index}": index + 1
                        for index, _ in enumerate(_RUN_COST_COLUMNS)
                    },
                },
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, input, status, "
                    "total_tokens, inherited_tokens, executed_tokens, "
                    f"{run_cost_columns_sql}"
                    ") VALUES ("
                    "'workflow', 42, 'legacy_cost_workflow', 1, '{}'::jsonb, 'succeeded', "
                    "31, 11, 20, "
                    f"{run_cost_placeholders_sql}"
                    ")"
                ),
                {
                    f"run_legacy_amount_{index}": index + 1
                    for index, _ in enumerate(_RUN_COST_COLUMNS)
                },
            )
            step_id = connection.execute(
                text(
                    "INSERT INTO run_steps (run_id, step_index, status, origin, persisted_at) "
                    "VALUES (:run_id, 1, 'succeeded', 'planned', NOW()) RETURNING id"
                ),
                {"run_id": run_id},
            ).scalar_one()
            invocation_id = connection.execute(
                text(
                    "INSERT INTO run_agent_invocations ("
                    "run_step_id, run_id, step_index, slot, position, agent_id, agent_key, "
                    "agent_version, output_schema_id, output_schema_version, status, "
                    "resolved_input, tokens, "
                    f"{_INVOCATION_COST_COLUMN}"
                    ") VALUES ("
                    ":step_id, :run_id, 1, 'review', 0, 7, 'legacy_cost_agent', "
                    "1, 1, 1, 'succeeded', '{}'::jsonb, 19, :invocation_legacy_amount"
                    ") RETURNING id"
                ),
                {"invocation_legacy_amount": 4, "run_id": run_id, "step_id": step_id},
            ).scalar_one()

        init_db(database_url)
        init_db(database_url)

        inspector = inspect(engine)
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        invocation_columns = {
            column["name"] for column in inspector.get_columns("run_agent_invocations")
        }
        run_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("runs")
            if constraint.get("name")
        }
        invocation_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("run_agent_invocations")
            if constraint.get("name")
        }
        with engine.connect() as connection:
            runtime_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM runs), "
                    "(SELECT COUNT(*) FROM run_steps), "
                    "(SELECT COUNT(*) FROM run_agent_invocations)"
                )
            ).one()
            preserved_run = connection.execute(
                text("SELECT target_key, status, total_tokens FROM runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).one()
            preserved_invocation = connection.execute(
                text(
                    "SELECT agent_key, status, tokens "
                    "FROM run_agent_invocations WHERE id = :invocation_id"
                ),
                {"invocation_id": invocation_id},
            ).one()

        assert runtime_counts == (1, 1, 1)
        assert preserved_run == ("cost_package", "succeeded", 17)
        assert preserved_invocation == ("legacy_cost_agent", "succeeded", 19)
        assert set(_RUN_COST_COLUMNS).isdisjoint(run_columns)
        assert _INVOCATION_COST_COLUMN not in invocation_columns
        assert set(_RUN_COST_CHECKS).isdisjoint(run_constraints)
        assert _INVOCATION_COST_CHECK not in invocation_constraints
    finally:
        engine.dispose()


def test_init_db_deletes_legacy_skill_storage_and_global_agents_idempotently(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE skills (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    tool_definitions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            legacy_capability_id = connection.execute(
                text(
                    "INSERT INTO skills ("
                    "key, version, status, name, description, tool_definitions"
                    ") VALUES ("
                    ":key, 1, 'published', :name, :description, "
                    "CAST(:tool_definitions AS jsonb)"
                    ") RETURNING id"
                ),
                {
                    "key": "legacy_report_lookup",
                    "name": "Legacy Report Lookup",
                    "description": "Migrated from legacy Skill storage.",
                    "tool_definitions": json.dumps([{"tool": "signaldeck.reports.lookup"}]),
                },
            ).scalar_one()
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
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, model, system_prompt, input_schema, "
                    "output_schema_id, output_schema_version, skills, mcp_servers"
                    ") VALUES ("
                    ":key, 1, 'published', :name, 'gpt-5.4-mini', :system_prompt, "
                    "CAST(:input_schema AS jsonb), 1, 1, CAST(:skills AS jsonb), '[]'::jsonb"
                    ")"
                ),
                {
                    "key": "legacy_agent",
                    "name": "Legacy Agent",
                    "system_prompt": "Use reports.",
                    "input_schema": json.dumps({"type": "object", "additionalProperties": False}),
                    "skills": json.dumps(
                        [
                            {
                                "skillId": legacy_capability_id,
                                "skillKey": "legacy_report_lookup",
                                "skillVersion": 1,
                            }
                        ]
                    ),
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            capability_columns = {
                column["name"] for column in inspector.get_columns("capabilities")
            }
            agent_columns = {column["name"] for column in inspector.get_columns("agents")}
            first_snapshot = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM capabilities), "
                    "(SELECT COUNT(*) FROM agents WHERE key = :key)"
                ),
                {"key": "legacy_agent"},
            ).one()

        assert "skills" not in table_names
        assert "tool_keys" in capability_columns
        assert "tool_grants" not in capability_columns
        assert "tool_definitions" not in capability_columns
        assert "skills" not in agent_columns
        assert first_snapshot == (0, 0)

        init_db(database_url)

        with engine.connect() as connection:
            second_snapshot = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM capabilities), "
                    "(SELECT COUNT(*) FROM agents WHERE key = :key)"
                ),
                {"key": "legacy_agent"},
            ).one()
        assert second_snapshot == first_snapshot
    finally:
        engine.dispose()


def test_init_db_deletes_mixed_legacy_and_canonical_capability_storage(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE skills (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    tool_definitions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE capabilities (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    tool_grants JSONB NOT NULL DEFAULT '[]'::jsonb,
                    tool_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO skills (key, version, status, name, tool_definitions) "
                "VALUES ('legacy_capability', 1, 'published', 'Legacy', '[]'::jsonb)"
            )
            connection.exec_driver_sql(
                "INSERT INTO capabilities (key, version, status, name, tool_grants) "
                "VALUES ('canonical_capability', 1, 'published', 'Canonical', '[]'::jsonb)"
            )

        init_db(database_url)

        with engine.connect() as connection:
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            capability_columns = {
                column["name"] for column in inspector.get_columns("capabilities")
            }
            capability_count = connection.execute(
                text("SELECT COUNT(*) FROM capabilities")
            ).scalar_one()

        assert "skills" not in table_names
        assert "tool_keys" in capability_columns
        assert "tool_grants" not in capability_columns
        assert "tool_definitions" not in capability_columns
        assert capability_count == 0
    finally:
        engine.dispose()


def test_init_db_adds_nullable_run_graph_metadata_columns(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE run_agent_invocations DROP COLUMN graph_metadata"
            )
            connection.exec_driver_sql("ALTER TABLE run_steps DROP COLUMN graph_metadata")

        init_db(database_url)

        inspector = inspect(engine)
        run_step_columns = {column["name"]: column for column in inspector.get_columns("run_steps")}
        invocation_columns = {
            column["name"]: column for column in inspector.get_columns("run_agent_invocations")
        }
        assert run_step_columns["graph_metadata"]["nullable"] is True
        assert invocation_columns["graph_metadata"]["nullable"] is True
    finally:
        engine.dispose()


def test_init_db_repairs_run_lifecycle_columns_and_status_constraint(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="lifecycle_package",
                workflow_key="lifecycle_workflow",
            )
            succeeded_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "status, input, started_at, finished_at, created_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, 'succeeded', '{}'::jsonb, "
                    "'2026-04-19T10:00:00Z', '2026-04-19T10:02:00Z', "
                    "'2026-04-19T09:59:00Z') RETURNING id"
                ),
                package,
            ).scalar_one()
            running_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "status, input, started_at, created_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, 'running', '{}'::jsonb, "
                    "'2026-04-19T11:00:00Z', '2026-04-19T10:59:00Z') RETURNING id"
                ),
                package,
            ).scalar_one()
            connection.exec_driver_sql("ALTER TABLE runs DROP CONSTRAINT ck_runs_status")
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT ck_runs_status "
                "CHECK (status IN ('running', 'succeeded', 'failed'))"
            )
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN status SET DEFAULT 'running'")
            connection.exec_driver_sql("ALTER TABLE runs DROP COLUMN queued_at")
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN started_at SET DEFAULT NOW()")
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN started_at SET NOT NULL")

        init_db(database_url)

        inspector = inspect(engine)
        run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
        run_status_sql = next(
            constraint["sqltext"]
            for constraint in inspector.get_check_constraints("runs")
            if constraint.get("name") == "ck_runs_status"
        )
        with engine.begin() as connection:
            preserved_rows = connection.execute(
                text(
                    "SELECT id, status, queued_at IS NOT NULL, started_at IS NOT NULL, "
                    "finished_at IS NOT NULL FROM runs ORDER BY id"
                )
            ).all()
            queued_insert_status = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "input"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, '{}'::jsonb"
                    ") RETURNING status"
                ),
                package,
            ).scalar_one()

        assert run_columns["queued_at"]["nullable"] is False
        assert run_columns["started_at"]["nullable"] is True
        assert all(
            status in run_status_sql for status in ("queued", "running", "succeeded", "failed")
        )
        assert preserved_rows == [
            (succeeded_run_id, "succeeded", True, True, True),
            (running_run_id, "failed", True, True, True),
        ]
        assert queued_insert_status == "queued"
    finally:
        engine.dispose()


def test_init_db_running_run_recovery_marks_new_platform_rows_terminal(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        queued_run_id: int
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="recovery_package",
                workflow_key="recovery_workflow",
            )
            running_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "status, input"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, 'running', '{}'::jsonb"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            failed_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "status, input, error"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, 'failed', '{}'::jsonb, 'existing failure'"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            queued_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, "
                    "workflow_package_workflow_key, "
                    "status, input, started_at, finished_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, "
                    ":workflow_key, 'queued', '{}'::jsonb, NULL, NULL"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            step_rows = connection.execute(
                text(
                    "INSERT INTO run_steps (run_id, step_index, status, origin, persisted_at) "
                    "VALUES "
                    "(:running_run_id, 1, 'succeeded', 'planned', NOW()), "
                    "(:running_run_id, 2, 'running', 'planned', NULL), "
                    "(:running_run_id, 3, 'pending', 'planned', NULL), "
                    "(:failed_run_id, 1, 'pending', 'planned', NULL) "
                    "RETURNING id, run_id, step_index"
                ),
                {"failed_run_id": failed_run_id, "running_run_id": running_run_id},
            ).all()
            step_id_by_identity = {(row.run_id, row.step_index): row.id for row in step_rows}
            connection.execute(
                text(
                    "INSERT INTO run_agent_invocations ("
                    "run_step_id, run_id, step_index, slot, position, agent_id, agent_key, "
                    "agent_version, output_schema_id, output_schema_version, status, "
                    "resolved_input, output, output_origin, persisted_at"
                    ") VALUES "
                    "(:succeeded_step_id, :running_run_id, 1, 'review', 0, 1, 'agent_a', "
                    "1, 1, 1, 'succeeded', '{}'::jsonb, '{\"ok\": true}'::jsonb, "
                    "'executed', NOW()), "
                    "(:running_step_id, :running_run_id, 2, 'review', 0, 1, 'agent_a', "
                    "1, 1, 1, 'running', '{}'::jsonb, NULL, NULL, NULL), "
                    "(:pending_step_id, :running_run_id, 3, 'review', 0, 1, 'agent_a', "
                    "1, 1, 1, 'pending', '{}'::jsonb, NULL, NULL, NULL), "
                    "(:failed_pending_step_id, :failed_run_id, 1, 'review', 0, 1, 'agent_a', "
                    "1, 1, 1, 'pending', '{}'::jsonb, NULL, NULL, NULL)"
                ),
                {
                    "failed_pending_step_id": step_id_by_identity[(failed_run_id, 1)],
                    "failed_run_id": failed_run_id,
                    "pending_step_id": step_id_by_identity[(running_run_id, 3)],
                    "running_run_id": running_run_id,
                    "running_step_id": step_id_by_identity[(running_run_id, 2)],
                    "succeeded_step_id": step_id_by_identity[(running_run_id, 1)],
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            repaired_run = connection.execute(
                text("SELECT status, error, finished_at IS NOT NULL FROM runs WHERE id = :run_id"),
                {"run_id": running_run_id},
            ).one()
            queued_run = connection.execute(
                text(
                    "SELECT status, started_at IS NULL, finished_at IS NULL "
                    "FROM runs WHERE id = :run_id"
                ),
                {"run_id": queued_run_id},
            ).one()
            repaired_steps = connection.execute(
                text(
                    "SELECT step_index, status, error, persisted_at IS NOT NULL, "
                    "finished_at IS NOT NULL FROM run_steps "
                    "WHERE run_id IN (:running_run_id, :failed_run_id) "
                    "ORDER BY run_id, step_index"
                ),
                {"failed_run_id": failed_run_id, "running_run_id": running_run_id},
            ).all()
            repaired_invocations = connection.execute(
                text(
                    "SELECT step_index, status, error_code, error_message, "
                    "persisted_at IS NOT NULL, finished_at IS NOT NULL "
                    "FROM run_agent_invocations "
                    "WHERE run_id IN (:running_run_id, :failed_run_id) "
                    "ORDER BY run_id, step_index"
                ),
                {"failed_run_id": failed_run_id, "running_run_id": running_run_id},
            ).all()

        assert repaired_run == ("failed", _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE, True)
        assert queued_run == ("queued", True, True)
        assert repaired_steps == [
            (1, "succeeded", None, True, False),
            (2, "failed", _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE, False, True),
            (3, "skipped", _AGENT_PLATFORM_PENDING_SKIP_MESSAGE, False, True),
            (1, "skipped", _AGENT_PLATFORM_PENDING_SKIP_MESSAGE, False, True),
        ]
        assert repaired_invocations == [
            (1, "succeeded", None, None, True, False),
            (
                2,
                "failed",
                "startup_recovery",
                _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE,
                False,
                True,
            ),
            (
                3,
                "skipped",
                "startup_recovery",
                _AGENT_PLATFORM_PENDING_SKIP_MESSAGE,
                False,
                True,
            ),
            (
                1,
                "skipped",
                "startup_recovery",
                _AGENT_PLATFORM_PENDING_SKIP_MESSAGE,
                False,
                True,
            ),
        ]
    finally:
        engine.dispose()


def test_init_db_hard_cutover_deletes_runtime_rows_and_preserves_config_product_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            retired_portfolio_id = _seed_stock_analysis_upgrade_rows(connection)
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD COLUMN per_step_outputs JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
            connection.exec_driver_sql(
                "INSERT INTO runs ("
                "target_kind, target_id, target_key, target_version, status, input, "
                "per_step_outputs"
                ") VALUES ('workflow', 99, 'legacy_runtime', 1, 'succeeded', "
                "'{}'::jsonb, '{}'::jsonb)"
            )

        init_db(database_url)

        with engine.connect() as connection:
            first_snapshot = _stock_analysis_sanitation_snapshot(
                connection,
                retired_portfolio_id=retired_portfolio_id,
            )

        assert first_snapshot == {
            "output_schema_keys": [],
            "capability_keys": [],
            "mcp_server_keys": [],
            "model_connection_keys": ["upgrade_test_connection"],
            "agent_keys": [],
            "workflow_keys": [],
            "template_names": sorted([_LIVE_TEMPLATE_NAME, *STARTER_TEMPLATE_NAMES]),
            "report_slugs": sorted([*RETIRED_STOCK_ANALYSIS_REPORT_SLUGS, _LIVE_REPORT_SLUG]),
            "portfolio_slugs": sorted([STARTER_PORTFOLIO_SLUG, _LIVE_PORTFOLIO_SLUG]),
            "retired_balance_count": 1,
            "retired_position_count": 1,
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
        _assert_runtime_execution_table_shape(engine)

        with engine.begin() as connection:
            next_output_schema_id = connection.execute(
                text(
                    "INSERT INTO output_schemas ("
                    "key, version, status, kind, name, description, json_schema, registry_refs"
                    ") VALUES ("
                    "'post_cutover_schema', 1, 'draft', 'standalone', 'Post Cutover', '', "
                    "'{\"type\": \"object\"}'::jsonb, '[]'::jsonb"
                    ") RETURNING id"
                )
            ).scalar_one()
            next_agent_id = connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model_connection_id, "
                    "model_connection_snapshot, model, system_prompt, input_schema, "
                    "output_schema_id, output_schema_version, capabilities, mcp_servers"
                    ") VALUES ("
                    "'post_cutover_agent', 1, 'draft', 'Post Cutover Agent', '', 1, "
                    "'{}'::jsonb, 'openai:gpt-5.4-mini', 'Prompt', '{}'::jsonb, "
                    ":output_schema_id, 1, '[]'::jsonb, '[]'::jsonb"
                    ") RETURNING id"
                ),
                {"output_schema_id": next_output_schema_id},
            ).scalar_one()
            next_workflow_id = connection.execute(
                text(
                    "INSERT INTO workflows ("
                    "key, version, status, name, description, input_schema, steps, output_spec"
                    ") VALUES ("
                    "'post_cutover_workflow', 1, 'draft', 'Post Cutover Workflow', '', "
                    "'{}'::jsonb, '[]'::jsonb, '{}'::jsonb"
                    ") RETURNING id"
                )
            ).scalar_one()
            next_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, status, input"
                    ") VALUES ("
                    "'workflow', :workflow_id, 'post_cutover_workflow', 1, "
                    "'succeeded', '{}'::jsonb"
                    ") RETURNING id"
                ),
                {"workflow_id": next_workflow_id},
            ).scalar_one()
            next_capability_id = connection.execute(
                text(
                    "INSERT INTO capabilities ("
                    "key, version, status, name, tool_keys, created_at, updated_at"
                    ") VALUES ("
                    "'post_cutover_capability', 1, 'draft', 'Post Cutover', '[]'::jsonb, "
                    "NOW(), NOW()"
                    ") RETURNING id"
                )
            ).scalar_one()
            next_mcp_server_id = connection.execute(
                text(
                    "INSERT INTO mcp_servers ("
                    "key, version, status, config, created_at, updated_at"
                    ") VALUES ('post_cutover_mcp', 1, 'draft', '{}'::jsonb, NOW(), NOW()) "
                    "RETURNING id"
                )
            ).scalar_one()
            next_model_connection_id = connection.execute(
                text(
                    "INSERT INTO model_connections ("
                    "key, status, name, description, base_url, model_id, reasoning_effort, "
                    "api_style, timeout_seconds, secret_payload, created_at, updated_at"
                    ") VALUES ("
                    "'post_cutover_model', 'active', 'Post Cutover Model', '', "
                    "'https://api.openai.com/v1', 'openai:gpt-5.4-mini', 'medium', "
                    "'responses', 60, '{}'::jsonb, NOW(), NOW()"
                    ") RETURNING id"
                )
            ).scalar_one()

        assert (
            next_output_schema_id,
            next_agent_id,
            next_workflow_id,
            next_run_id,
        ) == (1, 1, 1, 1)
        assert (next_capability_id, next_mcp_server_id, next_model_connection_id) == (3, 3, 2)
    finally:
        engine.dispose()


def test_workflow_package_clean_break_removes_legacy_authoring_rows_preserves_model_connections(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO model_connections (
                        key, status, name, description, base_url, model_id, reasoning_effort,
                        api_style, timeout_seconds, secret_payload, created_at, updated_at
                    ) VALUES (
                        'clean_break_model', 'active', 'Clean Break Model', '',
                        'https://api.openai.com/v1', 'openai:gpt-5.4-mini', 'medium',
                        'responses', 60, '{}'::jsonb, NOW(), NOW()
                    )
                    """
                )
            )
            stale_capability_id = connection.execute(
                text(
                    """
                    INSERT INTO capabilities (
                        key, version, status, name, description, tool_keys, created_at, updated_at
                    ) VALUES (
                        :key, 1, 'draft', :name, :description, CAST(:tool_keys AS jsonb),
                        NOW(), NOW()
                    ) RETURNING id
                    """
                ),
                {
                    "description": "Custom-key stale tool key deleted during startup.",
                    "key": _CUSTOM_STALE_SKILL_KEY,
                    "name": "Stock Analysis Workspace Verify",
                    "tool_keys": json.dumps(
                        ["signaldeck.reports.lookup", "signaldeck.stale.lookup"]
                    ),
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO output_schemas (
                        key, version, status, kind, name, description, json_schema,
                        registry_refs, created_at, updated_at
                    ) VALUES (
                        'stale_output_schema', 1, 'draft', 'standalone', 'Stale Output', '',
                        '{"type": "object"}'::jsonb, '[]'::jsonb, NOW(), NOW()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO mcp_servers (key, version, status, config, created_at, updated_at)
                    VALUES ('stale_mcp_server', 1, 'draft', '{}'::jsonb, NOW(), NOW())
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflows (
                        key, version, status, name, input_schema, steps, output_spec
                    )
                    VALUES (
                        'stale_workflow', 1, 'draft', 'Stale Workflow', '{}'::jsonb,
                        '[]'::jsonb, '{}'::jsonb
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO agents (
                        key, version, status, name, description, model_connection_id,
                        model_connection_snapshot, model, system_prompt, input_schema,
                        output_schema_id, output_schema_version, capabilities, mcp_servers
                    ) VALUES (
                        :key, 1, 'draft', :name, '', 1, '{}'::jsonb, 'openai:gpt-5.4-mini',
                        'Prompt', '{}'::jsonb, 1, 1, CAST(:capabilities AS jsonb), '[]'::jsonb
                    )
                    """
                ),
                {
                    "capabilities": json.dumps(
                        [
                            {
                                "capabilityId": stale_capability_id,
                                "capabilityKey": _CUSTOM_STALE_SKILL_KEY,
                                "capabilityVersion": 1,
                            }
                        ]
                    ),
                    "key": "stale_capability_agent",
                    "name": "Stale Capability Agent",
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            first_snapshot = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM capabilities), "
                    "(SELECT COUNT(*) FROM agents), "
                    "(SELECT COUNT(*) FROM workflows), "
                    "(SELECT COUNT(*) FROM mcp_servers), "
                    "(SELECT COUNT(*) FROM output_schemas), "
                    "(SELECT COUNT(*) FROM model_connections WHERE key = 'clean_break_model')"
                )
            ).one()

        assert first_snapshot == (0, 0, 0, 0, 0, 1)

        init_db(database_url)

        with engine.connect() as connection:
            second_snapshot = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM capabilities), "
                    "(SELECT COUNT(*) FROM agents), "
                    "(SELECT COUNT(*) FROM workflows), "
                    "(SELECT COUNT(*) FROM mcp_servers), "
                    "(SELECT COUNT(*) FROM output_schemas), "
                    "(SELECT COUNT(*) FROM model_connections WHERE key = 'clean_break_model')"
                )
            ).one()

        assert second_snapshot == first_snapshot
    finally:
        engine.dispose()


def test_init_db_hard_cutover_recreates_legacy_runs_and_partial_runtime_tables(
    database_url: str,
) -> None:
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
                    CONSTRAINT ck_runs_total_tokens_non_negative CHECK (total_tokens >= 0)
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
                "CREATE TABLE run_steps ("
                "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
                "run_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending'"
                ")"
            )
            connection.exec_driver_sql(
                "CREATE TABLE run_agent_invocations ("
                "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
                "run_step_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending'"
                ")"
            )
            legacy_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "workflow_id, workflow_key, workflow_version, target_kind, target_id, "
                    "target_key, target_version, input, per_step_outputs, final_output, status, "
                    "total_tokens, trace_id"
                    ") VALUES ("
                    "7, 'market_review', 3, 'agent', 9, 'different_target', 4, "
                    "'{}'::jsonb, '{}'::jsonb, '{\"headline\":\"Buy\"}'::jsonb, "
                    "'succeeded', 321, 'trace-legacy-run'"
                    ") RETURNING id"
                )
            ).scalar_one()
            legacy_step_id = connection.execute(
                text(
                    "INSERT INTO run_steps (run_id, status) "
                    "VALUES (:run_id, 'running') RETURNING id"
                ),
                {"run_id": legacy_run_id},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO run_agent_invocations (run_step_id, status) "
                    "VALUES (:run_step_id, 'running')"
                ),
                {"run_step_id": legacy_step_id},
            )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            runtime_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM runs), "
                    "(SELECT COUNT(*) FROM run_steps), "
                    "(SELECT COUNT(*) FROM run_agent_invocations)"
                )
            ).one()

        assert runtime_counts == (0, 0, 0)
        _assert_runtime_execution_table_shape(engine)
    finally:
        engine.dispose()


def test_init_db_fresh_schema_makes_agent_model_connection_id_non_null(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert agent_columns["model_connection_id"]["nullable"] is False
        assert agent_columns["model_connection_snapshot"]["nullable"] is False
    finally:
        engine.dispose()


def test_init_db_fresh_schema_has_flexible_model_connection_reasoning_effort(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        model_connection_columns = {
            column["name"]: column for column in inspect(engine).get_columns("model_connections")
        }
        assert {"organization", "project"}.isdisjoint(model_connection_columns)
        assert set(_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS).isdisjoint(
            model_connection_columns
        )
        reasoning_effort_column = model_connection_columns["reasoning_effort"]

        assert reasoning_effort_column["nullable"] is True
        assert getattr(reasoning_effort_column["type"], "length", None) == 128
        assert "medium" in str(reasoning_effort_column.get("default"))
        _assert_flexible_model_connection_reasoning_effort_check(engine)
        _assert_model_connection_reasoning_effort_direct_sql_contract(
            engine,
            key_prefix="fresh_reasoning_effort",
        )
    finally:
        engine.dispose()


def test_init_db_drops_legacy_model_connection_secret_metadata_columns(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    marker_column, suffix_column = _LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE model_connections ADD COLUMN {marker_column} BOOLEAN DEFAULT TRUE"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE model_connections ADD COLUMN {suffix_column} VARCHAR(4)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN organization VARCHAR(200)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN project VARCHAR(200)"
            )
            connection.execute(
                text(
                    f"""
                    INSERT INTO model_connections (
                        key, status, name, description, base_url, organization, project,
                        model_id, reasoning_effort, api_style, timeout_seconds, secret_payload,
                        {marker_column}, {suffix_column}, created_at, updated_at
                    ) VALUES (
                        :key, 'active', :name, '', 'https://api.openai.com/v1', NULL, NULL,
                        :model_id, 'medium', 'responses', 60, CAST(:secret_payload AS jsonb),
                        TRUE, '1234', NOW(), NOW()
                    )
                    """
                ),
                {
                    "key": "legacy_secret_metadata_connection",
                    "model_id": "openai:gpt-5.4-mini",
                    "name": "Legacy Secret Metadata Connection",
                    "secret_payload": json.dumps({"apiKey": "sk-forward-repair-1234"}),
                },
            )

        init_db(database_url)
        init_db(database_url)

        model_connection_columns = {
            column["name"]: column for column in inspect(engine).get_columns("model_connections")
        }
        with engine.connect() as connection:
            secret_payload = connection.execute(
                text(
                    "SELECT secret_payload FROM model_connections "
                    "WHERE key = 'legacy_secret_metadata_connection'"
                )
            ).scalar_one()

        retired_columns = {
            *_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS,
            "organization",
            "project",
        }
        assert retired_columns.isdisjoint(model_connection_columns)
        assert secret_payload == {"apiKey": "sk-forward-repair-1234"}
    finally:
        engine.dispose()


def test_init_db_backfills_model_connection_keys_deterministically(database_url: str) -> None:
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
                    organization VARCHAR(200),
                    project VARCHAR(200),
                    model_id VARCHAR(200) NOT NULL,
                    reasoning_effort VARCHAR(20) NOT NULL DEFAULT 'medium',
                    timeout_seconds INTEGER NOT NULL DEFAULT 60,
                    secret_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    last_tested_at TIMESTAMPTZ,
                    last_test_ok BOOLEAN,
                    last_test_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO model_connections ("
                    "status, name, description, base_url, organization, project, model_id, "
                    "reasoning_effort, timeout_seconds, secret_payload, "
                    "created_at, updated_at"
                    ") VALUES ("
                    "'active', :name, '', 'https://api.openai.com/v1', NULL, NULL, :model_id, "
                    "'medium', 60, '{}'::jsonb, NOW(), NOW()"
                    ")"
                ),
                [
                    {"name": "Primary OpenAI", "model_id": "gpt-5.4-mini"},
                    {"name": "Primary OpenAI", "model_id": "gpt-5.4"},
                    {"name": "!!!", "model_id": "openai:gpt-4.1"},
                    {"name": "2026 Default", "model_id": "gpt-5.4"},
                ],
            )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id, key, api_style FROM model_connections ORDER BY id ASC")
            ).all()

        model_connection_columns = {
            column["name"]: column for column in inspect(engine).get_columns("model_connections")
        }
        unique_constraints = {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints("model_connections")
        }
        model_connection_indexes = {
            index["name"] for index in inspect(engine).get_indexes("model_connections")
        }
        model_connection_check_constraints = {
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints("model_connections")
        }

        assert rows == [
            (1, "primary_openai", "responses"),
            (2, "primary_openai_2", "responses"),
            (3, "openai_gpt_4_1", "responses"),
            (4, "model_connection_2026_default", "responses"),
        ]
        assert model_connection_columns["key"]["nullable"] is False
        assert model_connection_columns["api_style"]["nullable"] is False
        assert {"organization", "project"}.isdisjoint(model_connection_columns)
        assert set(_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS).isdisjoint(
            model_connection_columns
        )
        assert "ck_model_connections_api_style" in model_connection_check_constraints
        assert "uq_model_connections_key" in unique_constraints
        assert "ix_model_connections_key" in model_connection_indexes
    finally:
        engine.dispose()


def test_init_db_repairs_legacy_enum_only_model_connection_reasoning_effort(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE model_connections (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    base_url VARCHAR(500) NOT NULL,
                    organization VARCHAR(200),
                    project VARCHAR(200),
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
                    CONSTRAINT ck_model_connections_reasoning_effort CHECK (
                        reasoning_effort IN ('low', 'medium', 'high')
                    ),
                    CONSTRAINT ck_model_connections_api_style CHECK (
                        api_style IN ('responses', 'chat_completions')
                    ),
                    CONSTRAINT uq_model_connections_key UNIQUE (key)
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO model_connections ("
                    "key, status, name, description, base_url, organization, project, "
                    "model_id, reasoning_effort, api_style, timeout_seconds, secret_payload, "
                    "created_at, updated_at"
                    ") VALUES ("
                    ":key, 'active', :name, '', 'https://api.openai.com/v1', NULL, NULL, "
                    ":model_id, :reasoning_effort, 'responses', 60, '{}'::jsonb, "
                    "NOW(), NOW()"
                    ")"
                ),
                [
                    {
                        "key": "legacy_low",
                        "model_id": "openai:gpt-5.4-mini-low",
                        "name": "Legacy Low",
                        "reasoning_effort": "low",
                    },
                    {
                        "key": "legacy_medium",
                        "model_id": "openai:gpt-5.4-mini-medium",
                        "name": "Legacy Medium",
                        "reasoning_effort": "medium",
                    },
                    {
                        "key": "legacy_high",
                        "model_id": "openai:gpt-5.4-mini-high",
                        "name": "Legacy High",
                        "reasoning_effort": "high",
                    },
                ],
            )

        init_db(database_url)
        init_db(database_url)

        model_connection_columns = {
            column["name"]: column for column in inspect(engine).get_columns("model_connections")
        }
        with engine.connect() as connection:
            preserved_rows = connection.execute(
                text(
                    "SELECT key, reasoning_effort FROM model_connections "
                    "WHERE key LIKE 'legacy_%' ORDER BY key ASC"
                )
            ).all()

        assert {"organization", "project"}.isdisjoint(model_connection_columns)
        assert set(_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS).isdisjoint(
            model_connection_columns
        )
        reasoning_effort_column = model_connection_columns["reasoning_effort"]
        assert reasoning_effort_column["nullable"] is True
        assert getattr(reasoning_effort_column["type"], "length", None) == 128
        assert preserved_rows == [
            ("legacy_high", "high"),
            ("legacy_low", "low"),
            ("legacy_medium", "medium"),
        ]
        _assert_flexible_model_connection_reasoning_effort_check(engine)
        _assert_model_connection_reasoning_effort_direct_sql_contract(
            engine,
            key_prefix="legacy_reasoning_effort",
        )
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_migrates_agent_memory_reports_to_agent_source(
    session_factory,
) -> None:
    matching_slug = "legacy_agent_memory_external"
    weekly_slug = "legacy_weekly_external"
    malformed_slug = "legacy_agent_memory_malformed"
    uploaded_slug = "legacy_agent_memory_uploaded"
    compiled_slug = "legacy_agent_memory_compiled"
    slugs = (matching_slug, weekly_slug, malformed_slug, uploaded_slug, compiled_slug)
    weekly_metadata: dict[str, object] = {
        "analysis": {"reviewType": "weekly_review", "versionGroup": "weekly_review/v1"},
        "tags": ["external"],
    }
    malformed_metadata = _agent_memory_report_metadata(agentVersion="v7")
    uploaded_metadata = _agent_memory_report_metadata(runId=5252, agentKey="uploaded_agent")
    compiled_metadata = _agent_memory_report_metadata(runId=6262, agentKey="compiled_agent")

    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            _insert_report_upgrade_row(
                connection,
                slug=matching_slug,
                source="external",
                metadata=_agent_memory_report_metadata(),
            )
            _insert_report_upgrade_row(
                connection,
                slug=weekly_slug,
                source="external",
                metadata=weekly_metadata,
            )
            _insert_report_upgrade_row(
                connection,
                slug=malformed_slug,
                source="external",
                metadata=malformed_metadata,
            )
            _insert_report_upgrade_row(
                connection,
                slug=uploaded_slug,
                source="uploaded",
                metadata=uploaded_metadata,
            )
            _insert_report_upgrade_row(
                connection,
                slug=compiled_slug,
                source="compiled",
                metadata=compiled_metadata,
            )

    upgrade_legacy_schema(engine)

    rows = _report_upgrade_rows_by_slug(engine, slugs)
    matching_metadata = cast(dict[str, object], rows[matching_slug]["metadata"])

    assert rows[matching_slug]["source"] == "agent"
    assert matching_metadata["createdBy"] == {
        "type": "agent",
        "runId": 4242,
        "agentKey": "portfolio_manager",
        "agentVersion": 7,
        "agentName": "Portfolio Manager",
        "workflowKey": "memory_workflow",
        "workflowVersion": 2,
        "stepId": "write_memory",
        "slot": "decision",
        "traceId": "trace-123",
    }
    assert matching_metadata["analysis"] == _agent_memory_report_metadata()["analysis"]
    assert rows[weekly_slug] == {"source": "external", "metadata": weekly_metadata}
    assert rows[malformed_slug] == {"source": "external", "metadata": malformed_metadata}
    assert rows[uploaded_slug] == {"source": "uploaded", "metadata": uploaded_metadata}
    assert rows[compiled_slug] == {"source": "compiled", "metadata": compiled_metadata}


def test_upgrade_legacy_schema_agent_memory_source_repair_is_idempotent(session_factory) -> None:
    slug = "legacy_agent_memory_idempotent"

    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            _insert_report_upgrade_row(
                connection,
                slug=slug,
                source="external",
                metadata=_agent_memory_report_metadata(),
            )

    upgrade_legacy_schema(engine)
    first_rows = _report_upgrade_rows_by_slug(engine, (slug,))
    upgrade_legacy_schema(engine)
    second_rows = _report_upgrade_rows_by_slug(engine, (slug,))

    assert first_rows == second_rows
    assert first_rows[slug]["source"] == "agent"
    assert cast(dict[str, object], first_rows[slug]["metadata"])["createdBy"] == {
        "type": "agent",
        "runId": 4242,
        "agentKey": "portfolio_manager",
        "agentVersion": 7,
        "agentName": "Portfolio Manager",
        "workflowKey": "memory_workflow",
        "workflowVersion": 2,
        "stepId": "write_memory",
        "slot": "decision",
        "traceId": "trace-123",
    }


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


def test_init_db_hard_cutover_deletes_legacy_agent_rows_when_stale_runtime_schema_exists(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)
    removed_archive_status = "arch" + "ived"

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"""
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
                        status IN ('draft', 'published', 'deprecated', '{removed_archive_status}')
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
                    ":key, 1, 'published', :name, '', :model, 'Analyze the ticker.', "
                    "'{\"type\":\"object\"}'::jsonb, 1, 1, '[]'::jsonb, '[]'::jsonb, 0"
                    ")"
                ),
                [
                    {"key": "research_agent_alpha", "model": "openai:gpt-5.4-mini", "name": "A"},
                    {"key": "research_agent_beta", "model": "openai:gpt-5.4-mini", "name": "B"},
                    {"key": "research_agent_gamma", "model": "openai:gpt-5.4", "name": "C"},
                ],
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE runs (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    target_kind VARCHAR(20) NOT NULL,
                    target_id INTEGER NOT NULL,
                    target_key VARCHAR(120) NOT NULL,
                    target_version INTEGER NOT NULL,
                    input JSONB NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    per_step_outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO runs (
                    target_kind, target_id, target_key, target_version, input, status,
                    per_step_outputs
                ) VALUES (
                    'agent', 1, 'research_agent_alpha', 1, '{}'::jsonb, 'succeeded', '{}'::jsonb
                )
                """
            )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            agent_count = connection.execute(text("SELECT COUNT(*) FROM agents")).scalar_one()
            model_connection_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections")
            ).scalar_one()

        repaired_agent_columns = {
            column["name"]: column for column in inspect(engine).get_columns("agents")
        }
        assert agent_count == 0
        assert model_connection_count == 0
        assert repaired_agent_columns["model_connection_id"]["nullable"] is False
        assert repaired_agent_columns["model_connection_snapshot"]["nullable"] is False
        assert {"skills", "temperature", "max_tool_rounds", "streaming"}.isdisjoint(
            repaired_agent_columns
        )
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
            connection.exec_driver_sql(
                """
                INSERT INTO output_schemas (
                    key, version, status, kind, name, description, json_schema, registry_refs,
                    created_at, updated_at
                ) VALUES (
                    'repair_schema', 1, 'published', 'standalone', 'Repair Schema', '',
                    '{"type":"object"}'::jsonb, '[]'::jsonb, NOW(), NOW()
                )
                """
            )
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model_connection_id, model, "
                    "system_prompt, input_schema, output_schema_id, "
                    "output_schema_version, capabilities, "
                    "mcp_servers, budget_usd"
                    ") VALUES ("
                    ":key, :version, :status, :name, :description, NULL, :model, "
                    ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, "
                    ":output_schema_version, CAST(:capabilities AS jsonb), "
                    "CAST(:mcp_servers AS jsonb), "
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
                    "capabilities": "[]",
                    "mcp_servers": "[]",
                    "budget_usd": 0,
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            clean_break_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM agents WHERE key = :agent_key), "
                    "(SELECT COUNT(*) FROM model_connections WHERE model_id = :model_id)"
                ),
                {
                    "agent_key": "repair_nullable_agent",
                    "model_id": "openai:gpt-5.4-mini",
                },
            ).one()

        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert clean_break_counts == (0, 0)
        assert agent_columns["model_connection_id"]["nullable"] is False
        assert agent_columns["model_connection_snapshot"]["nullable"] is False
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_rehardens_nullable_model_connection_column_when_already_linked(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO output_schemas (
                    key, version, status, kind, name, description, json_schema, registry_refs,
                    created_at, updated_at
                ) VALUES (
                    'prelinked_schema', 1, 'published', 'standalone', 'Prelinked Schema', '',
                    '{"type":"object"}'::jsonb, '[]'::jsonb, NOW(), NOW()
                )
                """
            )
            linked_model_connection_id = connection.execute(
                text(
                    "INSERT INTO model_connections ("
                    "key, status, name, description, base_url, model_id, reasoning_effort, "
                    "api_style, timeout_seconds, secret_payload, created_at, updated_at"
                    ") VALUES ("
                    ":key, 'active', :name, '', 'https://api.openai.com/v1', :model_id, "
                    "'medium', 'chat_completions', 60, '{}'::jsonb, NOW(), NOW()"
                    ") RETURNING id"
                ),
                {
                    "key": "prelinked_connection",
                    "name": "prelinked-connection",
                    "model_id": "openai:gpt-5.4-mini",
                },
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO agents ("
                    "key, version, status, name, description, model_connection_id, model, "
                    "system_prompt, input_schema, output_schema_id, "
                    "output_schema_version, capabilities, "
                    "mcp_servers, budget_usd, model_connection_snapshot"
                    ") VALUES ("
                    ":key, :version, :status, :name, :description, :model_connection_id, :model, "
                    ":system_prompt, CAST(:input_schema AS jsonb), :output_schema_id, "
                    ":output_schema_version, CAST(:capabilities AS jsonb), "
                    "CAST(:mcp_servers AS jsonb), "
                    ":budget_usd, CAST(:model_connection_snapshot AS jsonb)"
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
                    "capabilities": "[]",
                    "mcp_servers": "[]",
                    "budget_usd": 0,
                    "model_connection_snapshot": json.dumps(
                        {
                            "base_url": "https://api.openai.com/v1",
                            "model_id": "openai:gpt-5.4-mini",
                            "reasoning_effort": "medium",
                            "api_style": "chat_completions",
                            "timeout_seconds": 60,
                        }
                    ),
                },
            )
            connection.exec_driver_sql(
                "ALTER TABLE agents ALTER COLUMN model_connection_id DROP NOT NULL"
            )

        init_db(database_url)

        with engine.connect() as connection:
            clean_break_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM agents WHERE key = :agent_key), "
                    "(SELECT COUNT(*) AS row_count FROM model_connections "
                    "WHERE id = :connection_id), "
                    "(SELECT MIN(api_style) FROM model_connections WHERE id = :connection_id)"
                ),
                {
                    "agent_key": "already_linked_agent",
                    "connection_id": linked_model_connection_id,
                },
            ).one()

        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        assert clean_break_counts == (0, 1, "chat_completions")
        assert agent_columns["model_connection_id"]["nullable"] is False
        assert agent_columns["model_connection_snapshot"]["nullable"] is False
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_backfills_snapshot_reasoning_effort_null_and_custom(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            null_connection_id = _insert_model_connection_reasoning_effort_row(
                connection,
                key="snapshot_null_connection",
                reasoning_effort=None,
            )
            custom_connection_id = _insert_model_connection_reasoning_effort_row(
                connection,
                key="snapshot_custom_connection",
                reasoning_effort="XHigh",
            )
            missing_field_connection_id = _insert_model_connection_reasoning_effort_row(
                connection,
                key="snapshot_missing_field_connection",
                reasoning_effort="custom-exact",
                api_style="chat_completions",
            )
            _insert_agent_model_connection_snapshot_row(
                connection,
                key="snapshot_null_agent",
                model_connection_id=null_connection_id,
                model_id="openai:snapshot_null_connection",
                model_connection_snapshot={},
            )
            _insert_agent_model_connection_snapshot_row(
                connection,
                key="snapshot_custom_agent",
                model_connection_id=custom_connection_id,
                model_id="openai:snapshot_custom_connection",
                model_connection_snapshot={
                    "base_url": "https://api.openai.com/v1",
                    "model_id": "openai:snapshot_custom_connection",
                    "reasoning_effort": "   ",
                    "api_style": "responses",
                    "timeout_seconds": 60,
                },
            )
            _insert_agent_model_connection_snapshot_row(
                connection,
                key="snapshot_missing_reasoning_agent",
                model_connection_id=missing_field_connection_id,
                model_id="openai:snapshot_missing_field_connection",
                model_connection_snapshot={
                    "base_url": "https://api.openai.com/v1",
                    "model_id": "openai:snapshot_missing_field_connection",
                    "api_style": "responses",
                    "timeout_seconds": 60,
                },
            )

        init_db(database_url)

        with engine.connect() as connection:
            clean_break_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM agents WHERE key LIKE 'snapshot_%_agent'), "
                    "(SELECT COUNT(*) FROM model_connections "
                    "WHERE key LIKE 'snapshot_%_connection')"
                )
            ).one()

        assert clean_break_counts == (0, 3)
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_deletes_wrapped_mcp_authoring_rows(session_factory) -> None:
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
        stored_count = session.query(McpServer).filter_by(key="market_data", version=1).count()
        assert stored_count == 0


def test_upgrade_legacy_schema_deletes_mismatched_wrapped_mcp_authoring_rows(
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
            stored_count = connection.execute(
                text("SELECT COUNT(*) FROM mcp_servers WHERE key = :key AND version = :version"),
                {"key": "market_data", "version": 1},
            ).scalar_one()

        assert stored_count == 0
    finally:
        engine.dispose()


def test_init_db_creates_extension_state_table_and_default_row(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        columns = {column["name"]: column for column in inspector.get_columns("extension_states")}
        indexes = {index["name"] for index in inspector.get_indexes("extension_states")}
        unique_constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("extension_states")
        }
        check_constraints = {
            constraint["name"] for constraint in inspector.get_check_constraints("extension_states")
        }
        primary_key = inspector.get_pk_constraint("extension_states")

        assert "extension_states" in table_names
        assert set(columns) == {"extension_key", "enabled"}
        assert primary_key["constrained_columns"] == ["extension_key"]
        assert columns["extension_key"]["nullable"] is False
        assert columns["enabled"]["nullable"] is False
        assert "ix_extension_states_extension_key" not in indexes
        assert "ix_extension_states_enabled" not in indexes
        assert "uq_extension_states_extension_key" not in unique_constraints
        assert "ck_extension_states_version_positive" not in check_constraints

        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT extension_key, enabled
                    FROM extension_states
                    WHERE extension_key = :extension_key
                    """
                    ),
                    {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY},
                )
                .mappings()
                .one()
            )

        assert row["extension_key"] == FINANCE_WORKSPACE_EXTENSION_KEY
        assert row["enabled"] is True
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_extension_state_is_idempotent_and_preserves_toggle(
    session_factory,
) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS "extension_states" CASCADE')
            connection.exec_driver_sql(
                """
                CREATE TABLE extension_states (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    extension_key VARCHAR(120) NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    enabled_at TIMESTAMPTZ,
                    disabled_at TIMESTAMPTZ,
                    disabled_reason TEXT,
                    state_version INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT ck_extension_states_version_positive CHECK (state_version > 0),
                    CONSTRAINT uq_extension_states_extension_key UNIQUE (extension_key)
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_extension_states_extension_key ON extension_states (extension_key)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_extension_states_enabled ON extension_states (enabled)"
            )
            connection.execute(
                text(
                    """
                    INSERT INTO extension_states (
                        extension_key, enabled, disabled_at, disabled_reason,
                        state_version, created_at, updated_at
                    ) VALUES (
                        :extension_key, FALSE, NOW(), 'maintenance', 7, NOW(), NOW()
                    )
                    """
                ),
                {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY},
            )

    upgrade_legacy_schema(engine)
    upgrade_legacy_schema(engine)

    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("extension_states")}
    indexes = {index["name"] for index in inspector.get_indexes("extension_states")}
    unique_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("extension_states")
    }
    check_constraints = {
        constraint["name"] for constraint in inspector.get_check_constraints("extension_states")
    }

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """
                SELECT extension_key, enabled
                FROM extension_states
                ORDER BY extension_key ASC
                """
                )
            )
            .mappings()
            .all()
        )

    assert set(columns) == {"extension_key", "enabled"}
    assert "ix_extension_states_extension_key" not in indexes
    assert "ix_extension_states_enabled" not in indexes
    assert "uq_extension_states_extension_key" not in unique_constraints
    assert "ck_extension_states_version_positive" not in check_constraints
    assert rows == [
        {
            "extension_key": FINANCE_WORKSPACE_EXTENSION_KEY,
            "enabled": False,
        }
    ]


def test_upgrade_legacy_schema_extension_state_deduplicates_legacy_rows(
    session_factory,
) -> None:
    with session_factory() as session:
        engine = session.get_bind()
        with engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS "extension_states" CASCADE')
            connection.exec_driver_sql(
                """
                CREATE TABLE extension_states (
                    id INTEGER,
                    extension_key VARCHAR(120),
                    enabled BOOLEAN,
                    state_version INTEGER,
                    created_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ
                )
                """
            )
            connection.execute(
                text(
                    """
                    INSERT INTO extension_states (
                        id, extension_key, enabled, state_version, created_at, updated_at
                    ) VALUES
                        (1, :extension_key, TRUE, 2, '2026-01-01', '2026-01-04'),
                        (2, :extension_key, FALSE, 7, '2026-01-02', '2026-01-02'),
                        (3, :extension_key, TRUE, 7, '2026-01-03', '2026-01-03')
                    """
                ),
                {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY},
            )

    upgrade_legacy_schema(engine)

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """
                    SELECT extension_key, enabled
                    FROM extension_states
                    ORDER BY extension_key ASC
                    """
                )
            )
            .mappings()
            .all()
        )

    assert rows == [
        {
            "extension_key": FINANCE_WORKSPACE_EXTENSION_KEY,
            "enabled": True,
        }
    ]


def test_upgrade_legacy_schema_adds_run_extension_dependencies_column(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE runs DROP COLUMN extension_dependencies")
        upgrade_legacy_schema(engine)

        inspector = inspect(engine)
        run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
        assert "extension_dependencies" in run_columns
        assert "extension_snapshots" not in run_columns
        assert run_columns["extension_dependencies"]["nullable"] is False

        with engine.begin() as connection:
            value = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version, input, status
                    ) VALUES (
                        'workflowPackage', 1, 'upgrade_package', 1, '{}'::jsonb, 'queued'
                    ) RETURNING extension_dependencies
                    """
                )
            ).scalar_one()
        assert value == []
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_normalizes_run_extension_snapshot_jsonb(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    legacy_snapshots = [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "label": "Finance Workspace",
            "enabled": True,
            "defaultEnabled": True,
            "stateVersion": 7,
            "phase": "active",
            "versioningRule": "bundled",
            "enabledAt": "2026-05-16T09:00:00Z",
            "disabledAt": None,
            "disabledReason": None,
            "surfaces": ["tool.signaldeck.market_data.quote_lookup", 100],
            "fields": ["spec.capabilityProfiles.quote_tools.toolKeys[0]", None],
        },
        {
            "extensionKey": "custom.extension",
            "label": "Legacy Extension",
            "enabled": False,
            "surfaces": "not-an-array",
            "fields": None,
        },
        {"label": "missing key", "surfaces": ["tool.invalid"]},
    ]

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE runs RENAME COLUMN extension_dependencies TO extension_snapshots"
            )
            package_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_packages (key, name, description, status, draft_source)
                    VALUES ('legacy_snapshot_package', 'Legacy Snapshot Package', '', 'active', '')
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
                        :package_id, 1, 'apiVersion: signaldeck.workflowPackage/v1',
                        'legacyhash', '{}'::jsonb, '{"agents": []}'::jsonb,
                        'compiledhash', '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"package_id": package_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    UPDATE workflow_packages
                    SET latest_version_id = :version_id
                    WHERE id = :package_id
                    """
                ),
                {"package_id": package_id, "version_id": version_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key, workflow_package_version_id,
                        workflow_package_version, workflow_package_manifest_hash,
                        workflow_package_compiled_hash, workflow_package_workflow_key,
                        extension_snapshots, input, status
                    ) VALUES (
                        'workflowPackage', :package_id, 'legacy_snapshot_package', 1,
                        :package_id, 'legacy_snapshot_package', :version_id,
                        1, 'legacyhash', 'compiledhash',
                        'advisory_research', CAST(:snapshots AS JSONB),
                        '{}'::jsonb, 'queued'
                    )
                    """
                ),
                {
                    "package_id": package_id,
                    "version_id": version_id,
                    "snapshots": json.dumps(legacy_snapshots),
                },
            )

        upgrade_legacy_schema(engine)

        inspector = inspect(engine)
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        assert "extension_dependencies" in run_columns
        assert "extension_snapshots" not in run_columns

        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT
                        extension_dependencies,
                        workflow_package_manifest_hash,
                        workflow_package_compiled_hash,
                        launch_snapshot
                    FROM runs
                    WHERE target_key = 'legacy_snapshot_package'
                    """
                    )
                )
                .mappings()
                .one()
            )

        assert row["workflow_package_manifest_hash"] == "legacyhash"
        assert row["workflow_package_compiled_hash"] == "compiledhash"
        assert row["launch_snapshot"]["workflowKey"] == "advisory_research"
        assert row["launch_snapshot"]["parameters"] == {}
        assert row["extension_dependencies"] == [
            {
                "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
                "surfaces": ["tool.signaldeck.market_data.quote_lookup"],
                "fields": ["spec.capabilityProfiles.quote_tools.toolKeys[0]"],
            },
            {"extensionKey": "custom.extension", "surfaces": [], "fields": []},
        ]
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_backfills_package_run_before_clean_break_cleanup(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="cleanup_order_package",
                workflow_key="cleanup_order_workflow",
            )
            preserved_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, workflow_package_version_id, "
                    "workflow_package_version, workflow_package_manifest_hash, "
                    "workflow_package_compiled_hash, workflow_package_workflow_key, "
                    "input, status"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :version, "
                    ":package_id, :package_key, :version_id, :version, "
                    ":manifest_hash, :compiled_hash, :workflow_key, "
                    "'{\"ticker\": \"MSFT\"}'::jsonb, 'succeeded'"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, input, status"
                    ") VALUES ("
                    "'workflow', 42, 'cleanup_order_legacy_workflow', 1, "
                    "'{}'::jsonb, 'succeeded'"
                    ")"
                )
            )

        upgrade_legacy_schema(engine)

        with engine.connect() as connection:
            rows = (
                connection.execute(
                    text("SELECT id, target_key, launch_snapshot " "FROM runs ORDER BY id")
                )
                .mappings()
                .all()
            )

        assert [row["id"] for row in rows] == [preserved_run_id]
        assert rows[0]["target_key"] == "cleanup_order_package"
        assert rows[0]["launch_snapshot"] == {
            "workflowKey": "cleanup_order_workflow",
            "workflowName": "cleanup_order_workflow",
            "workflowDescription": "",
            "inputSchema": {},
            "parameters": {"ticker": "MSFT"},
            "localResourceRefs": {
                "agents": [],
                "outputSchemas": [],
                "capabilityProfiles": [],
                "mcpServers": [],
                "workflows": ["cleanup_order_workflow"],
            },
            "resolvedModelConnections": [],
            "preflightSummary": None,
            "workflowPackageId": package["package_id"],
            "workflowPackageKey": "cleanup_order_package",
            "workflowPackageVersionId": package["version_id"],
            "workflowPackageVersion": 1,
            "workflowPackageManifestHash": package["manifest_hash"],
            "workflowPackageCompiledHash": package["compiled_hash"],
        }
    finally:
        engine.dispose()
