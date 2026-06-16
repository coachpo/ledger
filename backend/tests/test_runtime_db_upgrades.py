# ruff: noqa: E501
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import init_db
from app.db.upgrades import upgrade_legacy_schema
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.report import REPORT_SOURCE_CHECK_CONSTRAINT
from app.services.workflow_package_service import WorkflowPackageService

AGENT_PLATFORM_TABLE_NAMES = {
    "model_connections",
    "run_agent_invocations",
    "run_forks",
    "run_operation_invocations",
    "run_steps",
    "runs",
    "run_workflow_package_snapshots",
    "workflow_packages",
    "workflow_package_runtime_input_entries",
    "workflow_package_secret_bindings",
}
OLD_MEMORY_TABLE_NAMES = {
    "agent_memory_entries",
    "agent_memory_revisions",
    "run_memory_events",
}
LEGACY_MEMORY_TABLE_NAMES = {
    "legacy_agent_memory_entries",
    "legacy_agent_memory_revisions",
    "legacy_run_memory_events",
}
WORKFLOW_MEMORY_TABLE_NAMES = {
    "workflow_memory_audit_events",
    "workflow_memory_consolidation_runs",
    "workflow_memory_decisions",
    "workflow_memory_items",
    "workflow_memory_proposals",
    "workflow_memory_quarantine",
    "workflow_memory_revisions",
    "workflow_checkpoints",
}
REMOVED_CORE_MEMORY_TABLE_NAMES = {"agent_memory_chunks", "agent_memory_embeddings"}
SCHEDULE_TABLE_NAMES = {
    "workflow_package_schedules",
    "workflow_package_schedule_fires",
}
RETIRED_GLOBAL_AUTHORING_TABLE_NAMES = {
    "agents",
    "workflows",
    "capabilities",
    "mcp_servers",
    "output_schemas",
    "workflow_agent_refs",
    "agent_capability_refs",
    "agent_mcp_server_refs",
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
LIVE_AGENT_PLATFORM_TABLE_NAMES = AGENT_PLATFORM_TABLE_NAMES
LIVE_WORKFLOW_MEMORY_TABLE_NAMES = WORKFLOW_MEMORY_TABLE_NAMES
LIVE_SCHEDULE_TABLE_NAMES = SCHEDULE_TABLE_NAMES
REMOVED_RUN_PROVENANCE_COLUMNS = {
    "workflow_package_version_id",
    "workflow_package_version",
    "workflow_package_manifest_hash",
    "workflow_package_compiled_hash",
    "launch_snapshot",
}
_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE = (
    "Run marked as failed during startup recovery because the previous process exited while "
    "it was still running."
)
_AGENT_PLATFORM_PENDING_SKIP_MESSAGE = (
    "Runtime row skipped during startup recovery because the parent run failed before it started."
)
_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS = (
    "_".join(("has", "api", "key")),
    "_".join(("api", "key", "last4")),
)
_RUN_HEADER_COLUMNS = {
    "id",
    "target_kind",
    "target_id",
    "target_key",
    "target_version",
    "workflow_package_id",
    "workflow_package_key",
    "workflow_package_workflow_key",
    "schedule_id",
    "schedule_fire_id",
    "scheduled_for",
    "schedule_reason",
    "schedule_provenance",
    "extension_dependencies",
    "input",
    "status",
    "execution_scope_key",
    "concurrency_policy",
    "lease_owner",
    "lease_expires_at",
    "heartbeat_at",
    "attempt_count",
    "last_claimed_at",
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
_SCHEDULE_COLUMNS = {
    "id",
    "package_id",
    "workflow_key",
    "name",
    "description",
    "status",
    "timezone",
    "recurrence",
    "starts_at",
    "ends_at",
    "next_fire_at",
    "overlap_policy",
    "misfire_policy",
    "misfire_grace_seconds",
    "input_template",
    "template_vars",
    "created_at",
    "updated_at",
}
_SCHEDULE_FIRE_COLUMNS = {
    "id",
    "schedule_id",
    "fire_key",
    "reason",
    "status",
    "scheduled_for",
    "scheduled_local_date",
    "scheduled_local_time",
    "scheduled_local_datetime",
    "materialized_at",
    "rendered_parameters",
    "skip_reason",
    "error_code",
    "error_message",
    "created_at",
    "updated_at",
}
_RUN_SNAPSHOT_COLUMNS = {
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
}
_RUNTIME_INPUT_REGISTRY_COLUMNS = {
    "id",
    "package_id",
    "workflow_key",
    "slot",
    "name",
    "payload",
    "source_kind",
    "manifest_hash",
    "compiled_hash",
    "schema_fingerprint",
    "input_schema_snapshot",
    "source_run_id",
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
_RUN_FORK_COLUMNS = {
    "run_id",
    "source_run_id",
    "lineage_root_run_id",
    "source_invocation_id",
    "source_step_index",
    "resume_step_index",
    "invocation_input",
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
_DIGITAL_ORACLE_PRESET_KEY = "digital_oracle_researcher"
_TRADINGAGENTS_MODEL_CONNECTION_KEY = "tradingagents_primary_model"
_TRADINGAGENTS_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_DIGITAL_ORACLE_FIXTURE_PATH = Path(__file__).parents[2] / "demo" / "digital_oracle_researcher.yaml"
_DIGITAL_ORACLE_DRAFT_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_packages"
    / "digital_oracle_researcher.draft.yaml"
)
_TRADINGAGENTS_PRESET_SQL_PATH = (
    Path(__file__).parents[1] / "app" / "db" / "tradingagents_advisory_research.sql"
)
_DIGITAL_ORACLE_PRESET_SQL_PATH = (
    Path(__file__).parents[1] / "app" / "db" / "digital_oracle_researcher.sql"
)
_DIGITAL_ORACLE_PRESET_EXTENSION_DEPENDENCIES = [
    {
        "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
        "fields": [
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[0]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[2]",
        ],
        "surfaces": [
            "runtime.tool.signaldeck.digital_oracle.market_sentiment.lookup",
            "runtime.tool.signaldeck.digital_oracle.prediction_markets.lookup",
            "runtime.tool.signaldeck.digital_oracle.sec_filings.lookup",
            "tool.signaldeck.digital_oracle.market_sentiment.lookup",
            "tool.signaldeck.digital_oracle.prediction_markets.lookup",
            "tool.signaldeck.digital_oracle.sec_filings.lookup",
        ],
    },
    {
        "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
        "fields": [
            "spec.capabilityProfiles.finance_price_history_tools.toolKeys[0]",
            "spec.capabilityProfiles.finance_price_history_tools.toolKeys[1]",
            "spec.mcpServers.exa.toolKeys[0]",
        ],
        "surfaces": [
            "mcp.packagePrivate.web_search_exa",
            "provider.fallbackQuote",
            "provider.quote",
            "provider.socialSentiment",
            "runtime.tool.signaldeck.finance.market_data.history_lookup",
            "runtime.tool.signaldeck.finance.market_data.ohlcv_lookup",
            "tool.signaldeck.finance.market_data.history_lookup",
            "tool.signaldeck.finance.market_data.ohlcv_lookup",
        ],
    },
]


def _compile_fixture_artifacts(engine: Engine, manifest_source: str) -> dict[str, object]:
    test_session_factory: sessionmaker[Session] = sessionmaker(bind=engine, future=True)
    with test_session_factory() as session:
        return WorkflowPackageService(session, test_session_factory)._prepare_manifest(
            manifest_source
        )


_TRADINGAGENTS_LAUNCH_METADATA_BY_WORKFLOW_KEY = {
    "advisory_research": (
        "Advisory Research",
        "TradingAgents advisory research inputs",
    ),
    "market_research": (
        "Market Research",
        "TradingAgents market research inputs",
    ),
    "news_research": (
        "News Research",
        "TradingAgents news research inputs",
    ),
    "fundamentals_research": (
        "Fundamentals Research",
        "TradingAgents fundamentals research inputs",
    ),
}


def _insert_representable_workflow_package(
    connection: Connection,
    *,
    key: str,
    workflow_key: str = "upgrade_workflow",
) -> dict[str, object]:
    manifest_hash = "a" * 64
    compiled_hash = "b" * 64
    package_definition: dict[str, object] = {
        "metadata": {"key": key, "name": key.replace("_", " ").title()},
        "spec": {"workflows": [{"key": workflow_key}]},
    }
    compiled_plan: dict[str, object] = {
        "packageKey": key,
        "agents": [],
        "outputSchemas": [],
        "capabilityProfiles": [],
        "mcpServers": [],
        "workflows": [
            {
                "key": workflow_key,
                "name": workflow_key,
                "description": "",
                "inputSchema": {},
            }
        ],
    }
    package_id = cast(
        int,
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
                    :compiled_hash, '[]'::jsonb
                ) RETURNING id
                """
            ),
            {
                "compiled_hash": compiled_hash,
                "compiled_plan": json.dumps(compiled_plan, sort_keys=True),
                "key": key,
                "manifest_hash": manifest_hash,
                "manifest_source": "manifest",
                "name": key.replace("_", " ").title(),
                "package_definition": json.dumps(package_definition, sort_keys=True),
            },
        ).scalar_one(),
    )
    return {
        "package_id": package_id,
        "package_key": key,
        "target_version": 1,
        "manifest_hash": manifest_hash,
        "compiled_hash": compiled_hash,
        "manifest_source": "manifest",
        "package_definition": package_definition,
        "compiled_plan": compiled_plan,
        "extension_dependencies": [],
        "workflow_key": workflow_key,
        "workflow_name": workflow_key,
    }


def _insert_run_workflow_package_snapshot(
    connection: Connection,
    *,
    run_id: int,
    package: dict[str, object],
    parameters: dict[str, object] | None = None,
    extension_dependencies: list[dict[str, object]] | None = None,
) -> None:
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
                :run_id, :package_id, :package_key, :package_name, '', 'active',
                :workflow_key, :workflow_name, '', :manifest_hash, :compiled_hash,
                :manifest_source, CAST(:package_definition AS jsonb),
                CAST(:compiled_plan AS jsonb), CAST(:extension_dependencies AS jsonb),
                CAST(:local_resource_refs AS jsonb), '{}'::jsonb,
                CAST(:launch_parameters AS jsonb), '[]'::jsonb, '{}'::jsonb, NOW(), NOW()
            )
            """
        ),
        {
            "compiled_hash": package["compiled_hash"],
            "compiled_plan": json.dumps(package["compiled_plan"], sort_keys=True),
            "extension_dependencies": json.dumps(
                (
                    extension_dependencies
                    if extension_dependencies is not None
                    else package["extension_dependencies"]
                ),
                sort_keys=True,
            ),
            "launch_parameters": json.dumps(parameters or {}, sort_keys=True),
            "local_resource_refs": json.dumps(
                {
                    "agents": [],
                    "outputSchemas": [],
                    "capabilityProfiles": [],
                    "mcpServers": [],
                    "workflows": [package["workflow_key"]],
                },
                sort_keys=True,
            ),
            "manifest_hash": package["manifest_hash"],
            "manifest_source": package["manifest_source"],
            "package_definition": json.dumps(
                package["package_definition"],
                sort_keys=True,
            ),
            "package_id": package["package_id"],
            "package_key": package["package_key"],
            "package_name": str(package["package_key"]).replace("_", " ").title(),
            "run_id": run_id,
            "workflow_key": package["workflow_key"],
            "workflow_name": package["workflow_name"],
        },
    )


def _assert_tradingagents_preset_launchable(
    engine: Engine,
    *,
    package_id: int,
    workflow_key: str,
    expected_name: str,
    expected_input_schema_title: str,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO model_connections (
                    key, status, name, description, base_url, model_id,
                    reasoning_effort, protocol_profile, timeout_seconds, secret_payload,
                    created_at, updated_at
                ) VALUES (
                    :key, 'active', 'TradingAgents Primary Model', '', :base_url,
                    :model_id, 'medium', 'openai_responses', 60,
                    '{"apiKey":"sk-tradingagents-upgrade-test"}'::jsonb, NOW(), NOW()
                )
                ON CONFLICT (key) DO UPDATE SET
                    status = EXCLUDED.status,
                    name = EXCLUDED.name,
                    base_url = EXCLUDED.base_url,
                    model_id = EXCLUDED.model_id,
                    secret_payload = EXCLUDED.secret_payload,
                    updated_at = NOW()
                """
            ),
            {
                "base_url": "https://api.openai.com/v1",
                "key": _TRADINGAGENTS_MODEL_CONNECTION_KEY,
                "model_id": "openai:gpt-5.4-mini",
            },
        )

    test_session_factory: sessionmaker[Session] = sessionmaker(bind=engine, future=True)
    with test_session_factory() as session:
        launch = WorkflowPackageService(session, test_session_factory).get_launch(
            package_id,
            workflow_key=workflow_key,
        )

    assert launch.package_key == _TRADINGAGENTS_PRESET_KEY
    assert launch.workflow_key == workflow_key
    assert launch.name == expected_name
    assert cast(dict[str, object], launch.input_schema)["title"] == expected_input_schema_title
    assert launch.ready is True
    assert launch.blocking_errors == []


def _tradingagents_preset_schedule_rows(connection: Connection) -> list[Mapping[str, object]]:
    return cast(
        list[Mapping[str, object]],
        connection.execute(
            text(
                """
                SELECT
                    schedule.id,
                    schedule.package_id,
                    schedule.workflow_key,
                    schedule.name,
                    schedule.description,
                    schedule.status,
                    schedule.timezone,
                    schedule.recurrence,
                    schedule.next_fire_at,
                    schedule.overlap_policy,
                    schedule.misfire_policy,
                    schedule.misfire_grace_seconds,
                    schedule.input_template,
                    schedule.template_vars
                FROM workflow_package_schedules AS schedule
                JOIN workflow_packages AS package
                  ON package.id = schedule.package_id
                WHERE package.key = :package_key
                ORDER BY schedule.workflow_key ASC, schedule.id ASC
                """
            ),
            {"package_key": _TRADINGAGENTS_PRESET_KEY},
        )
        .mappings()
        .all(),
    )


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


def _assert_report_source_constraint(engine: Engine) -> None:
    constraints = {
        constraint["name"] for constraint in inspect(engine).get_check_constraints("reports")
    }
    assert REPORT_SOURCE_CHECK_CONSTRAINT in constraints


def _assert_invalid_report_source_rejected(engine: Engine, *, slug: str) -> None:
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            _ = connection.execute(
                text(
                    """
                    INSERT INTO reports (name, slug, source, content, metadata)
                    VALUES (:name, :slug, 'wire', '# Invalid', '{}'::jsonb)
                    """
                ),
                {"name": slug.replace("_", " ").title(), "slug": slug},
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


def _assert_schedule_table_shape(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert LIVE_SCHEDULE_TABLE_NAMES <= table_names

    schedule_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_package_schedules")
    }
    fire_columns = {
        column["name"]: column
        for column in inspector.get_columns("workflow_package_schedule_fires")
    }
    run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
    schedule_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_package_schedules")
    }
    fire_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_package_schedule_fires")
    }
    run_indexes = {index["name"] for index in inspector.get_indexes("runs")}
    schedule_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("workflow_package_schedules")
        if constraint.get("name")
    }
    fire_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("workflow_package_schedule_fires")
        if constraint.get("name")
    }
    run_checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("runs")
        if constraint.get("name")
    }
    fire_unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("workflow_package_schedule_fires")
    }
    schedule_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("workflow_package_schedules")
    }
    fire_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("workflow_package_schedule_fires")
    }
    run_foreign_keys = {
        _foreign_key_signature(foreign_key) for foreign_key in inspector.get_foreign_keys("runs")
    }

    assert set(schedule_columns) == _SCHEDULE_COLUMNS
    assert "archived_at" not in schedule_columns
    assert schedule_columns["package_id"]["nullable"] is False
    assert schedule_columns["workflow_key"]["nullable"] is False
    assert schedule_columns["timezone"]["nullable"] is False
    assert schedule_columns["recurrence"]["nullable"] is False
    assert schedule_columns["starts_at"]["nullable"] is True
    assert schedule_columns["ends_at"]["nullable"] is True
    assert schedule_columns["next_fire_at"]["nullable"] is True
    assert {
        "ix_workflow_package_schedules_package",
        "ix_workflow_package_schedules_package_workflow",
        "ix_workflow_package_schedules_status_next_fire",
        "ix_workflow_package_schedules_next_fire",
    } <= schedule_indexes
    assert all(
        value in schedule_checks["ck_workflow_package_schedules_status"]
        for value in ("enabled", "paused")
    )
    assert "archived" not in schedule_checks["ck_workflow_package_schedules_status"]
    assert all(
        value in schedule_checks["ck_workflow_package_schedules_overlap_policy"]
        for value in ("skip", "queue")
    )
    assert all(
        value in schedule_checks["ck_workflow_package_schedules_misfire_policy"]
        for value in ("skip", "catchUpOne")
    )
    assert (
        "misfire_grace_seconds"
        in schedule_checks["ck_workflow_package_schedules_misfire_grace_non_negative"]
    )
    assert (("package_id",), "workflow_packages", "CASCADE") in schedule_foreign_keys

    assert set(fire_columns) == _SCHEDULE_FIRE_COLUMNS
    assert fire_columns["schedule_id"]["nullable"] is False
    assert fire_columns["fire_key"]["nullable"] is False
    assert fire_columns["scheduled_for"]["nullable"] is False
    assert fire_columns["materialized_at"]["nullable"] is True
    assert {
        "ix_workflow_package_schedule_fires_schedule",
        "ix_workflow_package_schedule_fires_schedule_status",
        "ix_workflow_package_schedule_fires_scheduled_for",
        "ix_workflow_package_schedule_fires_status",
    } <= fire_indexes
    assert all(
        value in fire_checks["ck_workflow_package_schedule_fires_status"]
        for value in ("pending", "queued", "skipped", "failed")
    )
    assert all(
        value in fire_checks["ck_workflow_package_schedule_fires_reason"]
        for value in ("scheduled", "manual")
    )
    assert fire_unique_constraints["uq_workflow_package_schedule_fires_schedule_fire_key"] == (
        "schedule_id",
        "fire_key",
    )
    assert (("schedule_id",), "workflow_package_schedules", "CASCADE") in fire_foreign_keys
    assert not any(foreign_key[1] == "runs" for foreign_key in fire_foreign_keys)

    assert run_columns["schedule_id"]["nullable"] is True
    assert run_columns["schedule_fire_id"]["nullable"] is True
    assert run_columns["scheduled_for"]["nullable"] is True
    assert run_columns["schedule_reason"]["nullable"] is True
    assert run_columns["schedule_provenance"]["nullable"] is True
    assert {
        "ix_runs_schedule",
        "ix_runs_schedule_status",
        "ix_runs_schedule_fire",
        "ix_runs_scheduled_for",
        "uq_runs_schedule_fire",
    } <= run_indexes
    assert all(value in run_checks["ck_runs_schedule_reason"] for value in ("scheduled", "manual"))
    assert (("schedule_id",), "workflow_package_schedules", "SET NULL") in run_foreign_keys
    assert (
        ("schedule_fire_id",),
        "workflow_package_schedule_fires",
        "SET NULL",
    ) in run_foreign_keys
    with engine.connect() as connection:
        schedule_fire_index_sql = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'runs' AND indexname = 'uq_runs_schedule_fire'"
            )
        ).scalar_one()
    assert "WHERE" in schedule_fire_index_sql
    assert "schedule_fire_id IS NOT NULL" in schedule_fire_index_sql


def _assert_workflow_memory_table_shape(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert LIVE_WORKFLOW_MEMORY_TABLE_NAMES <= table_names
    assert OLD_MEMORY_TABLE_NAMES.isdisjoint(table_names)
    assert REMOVED_CORE_MEMORY_TABLE_NAMES.isdisjoint(table_names)

    item_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_items")
    }
    proposal_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_proposals")
    }
    decision_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_decisions")
    }
    audit_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_audit_events")
    }
    revision_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_revisions")
    }
    quarantine_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_memory_quarantine")
    }
    consolidation_columns = {
        column["name"]: column
        for column in inspector.get_columns("workflow_memory_consolidation_runs")
    }
    checkpoint_columns = {
        column["name"]: column for column in inspector.get_columns("workflow_checkpoints")
    }

    assert {
        "id",
        "memory_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "namespace",
        "kind",
        "content_json",
        "summary",
        "provenance_json",
        "policy_status",
        "lifecycle_status",
        "valid_from",
        "expires_at",
        "superseded_by_id",
        "deleted_at",
        "proposal_id",
        "decision_id",
        "run_id",
        "invocation_id",
        "created_at",
        "updated_at",
    } <= set(item_columns)
    assert item_columns["policy_status"]["nullable"] is False
    assert item_columns["lifecycle_status"]["nullable"] is False
    assert {"commit_status", "archived", "accepted", "visible_to_workflow"}.isdisjoint(item_columns)

    assert {
        "id",
        "proposal_id",
        "run_id",
        "invocation_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "namespace",
        "kind",
        "content_json",
        "reason",
        "source_output_path",
        "detectors_json",
        "status",
        "created_at",
        "updated_at",
    } <= set(proposal_columns)
    assert proposal_columns["content_json"]["nullable"] is False
    assert {"accepted", "commit_status"}.isdisjoint(proposal_columns)

    assert {
        "id",
        "decision_id",
        "proposal_id",
        "decision",
        "reason_code",
        "reason",
        "policy_snapshot_json",
        "decided_by",
        "created_at",
    } <= set(decision_columns)
    assert decision_columns["proposal_id"]["nullable"] is False
    assert decision_columns["policy_snapshot_json"]["nullable"] is False

    assert {
        "id",
        "event_type",
        "target_type",
        "target_id",
        "run_id",
        "invocation_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "event_json",
        "created_at",
    } <= set(audit_columns)

    assert {
        "id",
        "memory_item_id",
        "revision_id",
        "version",
        "content_json",
        "summary",
        "provenance_json",
        "supersedes_revision_id",
        "created_at",
    } <= set(revision_columns)
    assert revision_columns["memory_item_id"]["nullable"] is False

    assert {
        "id",
        "memory_item_id",
        "proposal_id",
        "run_id",
        "invocation_id",
        "reason_code",
        "reason",
        "detectors_json",
        "resolved_at",
        "created_at",
    } <= set(quarantine_columns)
    assert quarantine_columns["detectors_json"]["nullable"] is False

    assert {
        "id",
        "consolidation_id",
        "package_key",
        "workflow_key",
        "namespace",
        "status",
        "started_at",
        "finished_at",
        "source_memory_ids_json",
        "output_memory_ids_json",
        "stats_json",
        "created_at",
    } <= set(consolidation_columns)

    assert {
        "id",
        "checkpoint_id",
        "run_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "invocation_id",
        "checkpoint_type",
        "sequence",
        "state_json",
        "retention",
        "metadata_json",
        "created_at",
    } <= set(checkpoint_columns)
    assert "state" not in checkpoint_columns
    assert checkpoint_columns["state_json"]["nullable"] is False

    unique_constraints_by_table = {
        table_name: {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table_name)
            if constraint.get("name")
        }
        for table_name in LIVE_WORKFLOW_MEMORY_TABLE_NAMES
    }
    assert (
        "uq_workflow_memory_items_memory_id" in unique_constraints_by_table["workflow_memory_items"]
    )
    assert (
        "uq_workflow_memory_proposals_proposal_id"
        in unique_constraints_by_table["workflow_memory_proposals"]
    )
    assert (
        "uq_workflow_memory_decisions_decision_id"
        in unique_constraints_by_table["workflow_memory_decisions"]
    )
    assert (
        "uq_workflow_memory_revisions_revision_id"
        in unique_constraints_by_table["workflow_memory_revisions"]
    )
    assert (
        "uq_workflow_memory_consolidation_runs_consolidation_id"
        in unique_constraints_by_table["workflow_memory_consolidation_runs"]
    )
    assert (
        "uq_workflow_checkpoints_checkpoint_id"
        in unique_constraints_by_table["workflow_checkpoints"]
    )

    item_indexes = {index["name"] for index in inspector.get_indexes("workflow_memory_items")}
    checkpoint_indexes = {index["name"] for index in inspector.get_indexes("workflow_checkpoints")}
    assert "ix_workflow_memory_items_retrieval_scope" in item_indexes
    assert "ix_workflow_memory_items_run_invocation" in item_indexes
    assert "ix_workflow_checkpoints_scope_run_sequence" in checkpoint_indexes
    assert "ix_workflow_checkpoints_run_invocation" in checkpoint_indexes

    item_foreign_keys = {
        _foreign_key_signature(cast(dict[str, object], cast(object, foreign_key)))
        for foreign_key in inspector.get_foreign_keys("workflow_memory_items")
    }
    decision_foreign_keys = {
        _foreign_key_signature(cast(dict[str, object], cast(object, foreign_key)))
        for foreign_key in inspector.get_foreign_keys("workflow_memory_decisions")
    }
    assert (("superseded_by_id",), "workflow_memory_items", "SET NULL") in item_foreign_keys
    assert (("proposal_id",), "workflow_memory_proposals", "SET NULL") in item_foreign_keys
    assert (("decision_id",), "workflow_memory_decisions", "SET NULL") in item_foreign_keys
    assert (("proposal_id",), "workflow_memory_proposals", "CASCADE") in decision_foreign_keys


def _assert_core_memory_table_shape(engine: Engine) -> None:
    _assert_workflow_memory_table_shape(engine)


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
    protocol_profile: str = "openai_responses",
) -> int:
    model_connection_id = cast(
        int,
        connection.execute(
            text(
                """
                INSERT INTO model_connections (
                    key, status, name, description, base_url, model_id, reasoning_effort,
                    protocol_profile, timeout_seconds, secret_payload, created_at, updated_at
                ) VALUES (
                    :key, 'active', :name, '', 'https://api.openai.com/v1', :model_id,
                    :reasoning_effort, :protocol_profile, 60, '{}'::jsonb, NOW(), NOW()
                ) RETURNING id
                """
            ),
            {
                "key": key,
                "model_id": f"openai:{key}",
                "name": key.replace("_", " ").title(),
                "protocol_profile": protocol_profile,
                "reasoning_effort": reasoning_effort,
            },
        ).scalar_one(),
    )
    return model_connection_id


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
    snapshot_columns = {
        column["name"]: column for column in inspector.get_columns("run_workflow_package_snapshots")
    }
    run_step_columns = {column["name"]: column for column in inspector.get_columns("run_steps")}
    invocation_columns = {
        column["name"]: column for column in inspector.get_columns("run_agent_invocations")
    }
    fork_columns = {column["name"]: column for column in inspector.get_columns("run_forks")}
    operation_columns = {
        column["name"]: column for column in inspector.get_columns("run_operation_invocations")
    }
    run_indexes = {index["name"] for index in inspector.get_indexes("runs")}
    snapshot_indexes = {
        index["name"] for index in inspector.get_indexes("run_workflow_package_snapshots")
    }
    run_step_indexes = {index["name"] for index in inspector.get_indexes("run_steps")}
    invocation_indexes = {index["name"] for index in inspector.get_indexes("run_agent_invocations")}
    fork_indexes = {index["name"] for index in inspector.get_indexes("run_forks")}
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
    with engine.connect() as connection:
        serial_scope_index_sql = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'runs' "
                "AND indexname = 'uq_runs_running_serial_execution_scope'"
            )
        ).scalar_one()
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
    fork_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("run_forks")
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
    snapshot_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_workflow_package_snapshots")
    }
    run_step_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_steps")
    }
    invocation_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_agent_invocations")
    }
    fork_foreign_keys = {
        _foreign_key_signature(foreign_key)
        for foreign_key in inspector.get_foreign_keys("run_forks")
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
        *REMOVED_RUN_PROVENANCE_COLUMNS,
        *_RUN_COST_COLUMNS,
    }.isdisjoint(run_columns)
    assert run_columns["schedule_id"]["nullable"] is True
    assert run_columns["schedule_fire_id"]["nullable"] is True
    assert run_columns["scheduled_for"]["nullable"] is True
    assert run_columns["schedule_reason"]["nullable"] is True
    assert run_columns["schedule_provenance"]["nullable"] is True
    assert run_columns["source_run_id"]["nullable"] is True
    assert run_columns["lineage_root_run_id"]["nullable"] is True
    assert run_columns["resume_step_index"]["nullable"] is False
    assert run_columns["extension_dependencies"]["nullable"] is False
    assert run_columns["queued_at"]["nullable"] is False
    assert run_columns["started_at"]["nullable"] is True
    assert run_columns["execution_scope_key"]["nullable"] is True
    assert run_columns["concurrency_policy"]["nullable"] is False
    assert run_columns["attempt_count"]["nullable"] is False
    assert all(status in run_status_sql for status in ("queued", "running", "succeeded", "failed"))
    normalized_serial_scope_index_sql = serial_scope_index_sql.lower()
    assert "where" in normalized_serial_scope_index_sql
    assert "status" in normalized_serial_scope_index_sql
    assert "running" in normalized_serial_scope_index_sql
    assert "concurrency_policy" in normalized_serial_scope_index_sql
    assert "serial" in normalized_serial_scope_index_sql
    assert {
        "ix_runs_status",
        "ix_runs_queue_claim",
        "ix_runs_target",
        "ix_runs_target_key",
        "ix_runs_source_run",
        "ix_runs_lineage_root",
        "ix_runs_execution_scope_status",
        "uq_runs_running_serial_execution_scope",
        "ix_runs_workflow_package",
        "ix_runs_workflow_package_key",
        "ix_runs_workflow_package_workflow_key",
        "ix_runs_schedule",
        "ix_runs_schedule_status",
        "ix_runs_schedule_fire",
        "ix_runs_scheduled_for",
        "uq_runs_schedule_fire",
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
        "ck_runs_concurrency_policy",
        "ck_runs_attempt_count_non_negative",
        "ck_runs_schedule_reason",
    } <= run_checks
    assert set(_RUN_COST_CHECKS).isdisjoint(run_checks)
    assert (("source_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("lineage_root_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("workflow_package_id",), "workflow_packages", "CASCADE") in run_foreign_keys
    assert "agent_id" not in run_columns
    assert "workflow_id" not in run_columns
    assert (("schedule_id",), "workflow_package_schedules", "SET NULL") in run_foreign_keys
    assert (
        ("schedule_fire_id",),
        "workflow_package_schedule_fires",
        "SET NULL",
    ) in run_foreign_keys
    assert not any(
        foreign_key[0]
        for foreign_key in run_foreign_keys
        if set(foreign_key[0]) & REMOVED_RUN_PROVENANCE_COLUMNS
    )

    assert set(snapshot_columns) == _RUN_SNAPSHOT_COLUMNS
    assert snapshot_columns["run_id"]["nullable"] is False
    assert snapshot_columns["workflow_package_id"]["nullable"] is False
    assert snapshot_columns["workflow_package_key"]["nullable"] is False
    assert snapshot_columns["manifest_source"]["nullable"] is False
    assert snapshot_columns["package_definition"]["nullable"] is False
    assert {
        "ix_run_workflow_package_snapshots_package_key",
        "ix_run_workflow_package_snapshots_workflow_key",
        "ix_run_workflow_package_snapshots_manifest_hash",
        "ix_run_workflow_package_snapshots_compiled_hash",
        "ix_run_workflow_package_snapshots_compiled_plan_gin",
        "ix_run_workflow_package_snapshots_model_connections_gin",
    } <= snapshot_indexes
    assert snapshot_foreign_keys == {(("run_id",), "runs", "CASCADE")}

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

    assert _RUN_FORK_COLUMNS <= set(fork_columns)
    assert fork_columns["run_id"]["nullable"] is False
    assert fork_columns["source_run_id"]["nullable"] is True
    assert fork_columns["lineage_root_run_id"]["nullable"] is True
    assert fork_columns["source_invocation_id"]["nullable"] is True
    assert fork_columns["source_step_index"]["nullable"] is False
    assert fork_columns["resume_step_index"]["nullable"] is False
    assert fork_columns["invocation_input"]["nullable"] is False
    assert {
        "ix_run_forks_source_run",
        "ix_run_forks_lineage_root",
        "ix_run_forks_source_invocation",
    } <= fork_indexes
    assert {
        "ck_run_forks_source_step_index_positive",
        "ck_run_forks_resume_step_index_positive",
    } <= fork_checks
    assert (("run_id",), "runs", "CASCADE") in fork_foreign_keys
    assert (("source_run_id",), "runs", "SET NULL") in fork_foreign_keys
    assert (("lineage_root_run_id",), "runs", "SET NULL") in fork_foreign_keys
    assert (
        ("source_invocation_id",),
        "run_agent_invocations",
        "SET NULL",
    ) in fork_foreign_keys

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


def test_s13_current_contract_bootstrap_excludes_retired_global_authoring_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        run_columns = {column["name"] for column in inspector.get_columns("runs")}

        assert LIVE_AGENT_PLATFORM_TABLE_NAMES <= table_names
        assert LIVE_WORKFLOW_MEMORY_TABLE_NAMES <= table_names
        assert OLD_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        assert LIVE_SCHEDULE_TABLE_NAMES <= table_names
        assert RETIRED_GLOBAL_AUTHORING_TABLE_NAMES.isdisjoint(table_names)
        assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(table_names)
        assert REMOVED_RUN_PROVENANCE_COLUMNS.isdisjoint(run_columns)
    finally:
        engine.dispose()


def test_s13_retired_global_authoring_tables_are_drop_only_upgrade_targets() -> None:
    upgrades_source = (Path(__file__).parents[1] / "app" / "db" / "upgrades.py").read_text()

    for table_name in RETIRED_GLOBAL_AUTHORING_TABLE_NAMES | {"skills"}:
        assert not re.search(rf"\bUPDATE\s+{table_name}\b", upgrades_source, re.I)
        assert not re.search(rf"\bINSERT\s+INTO\s+{table_name}\b", upgrades_source, re.I)
        assert not re.search(rf"\bALTER\s+TABLE\s+{table_name}\b", upgrades_source, re.I)
        assert not re.search(
            rf"\bSELECT\b[^;]*\bFROM\s+{table_name}\b", upgrades_source, re.I | re.S
        )

    assert "model_connection_snapshot" not in upgrades_source
    assert "UPDATE run_workflow_package_snapshots" in upgrades_source
    assert "DELETE FROM model_connections" in upgrades_source


def test_init_db_creates_current_runtime_tables_and_drops_legacy_backend_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        table_names = set(inspect(engine).get_table_names())
        assert LIVE_AGENT_PLATFORM_TABLE_NAMES <= table_names
        assert RETIRED_GLOBAL_AUTHORING_TABLE_NAMES.isdisjoint(table_names)
        assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(table_names)
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


def test_run_schedule_provenance_column_and_set_null_fks(
    database_url: str,
) -> None:
    init_db(database_url)
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_schedule_table_shape(engine)
        _assert_runtime_execution_table_shape(engine)
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="schedule_creation_package",
                workflow_key="schedule_creation_workflow",
            )
            schedule_defaults = (
                connection.execute(
                    text(
                        """
                    INSERT INTO workflow_package_schedules (
                        package_id, workflow_key, name, timezone, recurrence,
                        input_template, template_vars
                    ) VALUES (
                        :package_id, :workflow_key, 'Daily research', 'UTC', '{}'::jsonb,
                        '{}'::jsonb, '{}'::jsonb
                    ) RETURNING id, status, overlap_policy, misfire_policy, misfire_grace_seconds
                    """
                    ),
                    package,
                )
                .mappings()
                .one()
            )
            schedule_id = schedule_defaults["id"]
            assert schedule_defaults["status"] == "enabled"
            assert schedule_defaults["overlap_policy"] == "skip"
            assert schedule_defaults["misfire_policy"] == "catchUpOne"
            assert schedule_defaults["misfire_grace_seconds"] == 86400
            fire_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_schedule_fires (
                        schedule_id, fire_key, reason, status, scheduled_for,
                        materialized_at, rendered_parameters
                    ) VALUES (
                        :schedule_id, 'daily-2026-06-01', 'scheduled', 'queued',
                        '2026-06-01T13:00:00Z', NOW(), '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                {"schedule_id": schedule_id},
            ).scalar_one()
            fire_defaults = (
                connection.execute(
                    text(
                        """
                    INSERT INTO workflow_package_schedule_fires (
                        schedule_id, fire_key, scheduled_for
                    ) VALUES (
                        :schedule_id, 'daily-defaults-2026-06-02',
                        '2026-06-02T13:00:00Z'
                    ) RETURNING reason, status, rendered_parameters
                    """
                    ),
                    {"schedule_id": schedule_id},
                )
                .mappings()
                .one()
            )
            assert fire_defaults["reason"] == "scheduled"
            assert fire_defaults["status"] == "pending"
            assert fire_defaults["rendered_parameters"] == {}
            schedule_provenance = {
                "scheduleId": schedule_id,
                "scheduleFireId": fire_id,
                "scheduleName": "Daily research",
                "packageId": package["package_id"],
                "packageKey": package["package_key"],
                "workflowKey": package["workflow_key"],
                "timezone": "UTC",
                "recurrence": {},
                "fireKey": "daily-2026-06-01",
                "reason": "scheduled",
                "scheduledFor": "2026-06-01T13:00:00Z",
                "scheduledLocalDate": None,
                "scheduledLocalTime": None,
                "scheduledLocalDateTime": None,
                "materializedAt": None,
                "scheduleDeletedAt": None,
            }
            connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, schedule_id, schedule_fire_id,
                        scheduled_for, schedule_reason, schedule_provenance, status, input
                    ) VALUES (
                        'workflowPackage', :package_id, :package_key, 1,
                        :package_id, :package_key, :workflow_key, :schedule_id,
                        :schedule_fire_id, '2026-06-01T13:00:00Z', 'scheduled',
                        CAST(:schedule_provenance AS jsonb), 'queued', '{}'::jsonb
                    )
                    """
                ),
                {
                    **package,
                    "schedule_id": schedule_id,
                    "schedule_fire_id": fire_id,
                    "schedule_provenance": json.dumps(schedule_provenance),
                },
            )
            stored_schedule_provenance = connection.execute(
                text(
                    "SELECT schedule_provenance FROM runs WHERE schedule_fire_id = :schedule_fire_id"
                ),
                {"schedule_fire_id": fire_id},
            ).scalar_one()
            assert stored_schedule_provenance == schedule_provenance

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_package_schedule_fires (
                            schedule_id, fire_key, scheduled_for
                        ) VALUES (
                            :schedule_id, 'daily-2026-06-01', '2026-06-01T13:00:00Z'
                        )
                        """
                    ),
                    {"schedule_id": schedule_id},
                )
    finally:
        engine.dispose()


def test_init_db_schedule_repair_restores_missing_tables_columns_and_indexes(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TABLE IF EXISTS workflow_package_schedule_fires CASCADE"
            )
            connection.exec_driver_sql("DROP TABLE IF EXISTS workflow_package_schedules CASCADE")
            for index_name in (
                "ix_runs_schedule",
                "ix_runs_schedule_status",
                "ix_runs_schedule_fire",
                "ix_runs_scheduled_for",
                "uq_runs_schedule_fire",
            ):
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
            for column_name in (
                "schedule_id",
                "schedule_fire_id",
                "scheduled_for",
                "schedule_reason",
                "schedule_provenance",
            ):
                connection.exec_driver_sql(
                    f"ALTER TABLE runs DROP COLUMN IF EXISTS {column_name} CASCADE"
                )
            connection.exec_driver_sql(
                """
                CREATE TABLE workflow_package_schedules (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    package_id INTEGER NOT NULL,
                    workflow_key VARCHAR(120) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    timezone VARCHAR(120) NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE workflow_package_schedule_fires (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    schedule_id INTEGER NOT NULL,
                    fire_key VARCHAR(255) NOT NULL,
                    scheduled_for TIMESTAMPTZ NOT NULL
                )
                """
            )

        init_db(database_url)
        init_db(database_url)
        _assert_schedule_table_shape(engine)
        _assert_runtime_execution_table_shape(engine)
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="schedule_repair_package",
                workflow_key="schedule_repair_workflow",
            )
            repaired_schedule = (
                connection.execute(
                    text(
                        """
                    INSERT INTO workflow_package_schedules (
                        package_id, workflow_key, name, timezone
                    ) VALUES (
                        :package_id, :workflow_key, 'Repair schedule', 'UTC'
                    ) RETURNING id, status, recurrence, overlap_policy, misfire_policy,
                        misfire_grace_seconds, input_template, template_vars
                    """
                    ),
                    package,
                )
                .mappings()
                .one()
            )
            repaired_fire = (
                connection.execute(
                    text(
                        """
                    INSERT INTO workflow_package_schedule_fires (
                        schedule_id, fire_key, scheduled_for
                    ) VALUES (
                        :schedule_id, 'repair-defaults-2026-06-01',
                        '2026-06-01T13:00:00Z'
                    ) RETURNING reason, status, rendered_parameters
                    """
                    ),
                    {"schedule_id": repaired_schedule["id"]},
                )
                .mappings()
                .one()
            )
            assert repaired_schedule["status"] == "enabled"
            assert repaired_schedule["recurrence"] == {}
            assert repaired_schedule["overlap_policy"] == "skip"
            assert repaired_schedule["misfire_policy"] == "catchUpOne"
            assert repaired_schedule["misfire_grace_seconds"] == 86400
            assert repaired_schedule["input_template"] == {}
            assert repaired_schedule["template_vars"] == {}
            assert repaired_fire["reason"] == "scheduled"
            assert repaired_fire["status"] == "pending"
            assert repaired_fire["rendered_parameters"] == {}
    finally:
        engine.dispose()


def test_init_db_archived_schedule_repair_retains_direct_runs_and_stamps_scheduleDeletedAt(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    archived_report_slug = "agent_memory_archived_schedule_cleanup_run"

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TABLE IF EXISTS workflow_package_schedule_fires CASCADE"
            )
            connection.exec_driver_sql("DROP TABLE IF EXISTS workflow_package_schedules CASCADE")
            for index_name in (
                "ix_runs_schedule",
                "ix_runs_schedule_status",
                "ix_runs_schedule_fire",
                "ix_runs_scheduled_for",
                "uq_runs_schedule_fire",
            ):
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
            for column_name in (
                "schedule_id",
                "schedule_fire_id",
                "scheduled_for",
                "schedule_reason",
                "schedule_provenance",
            ):
                connection.exec_driver_sql(
                    f"ALTER TABLE runs DROP COLUMN IF EXISTS {column_name} CASCADE"
                )
            connection.exec_driver_sql(
                """
                CREATE TABLE workflow_package_schedules (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    package_id INTEGER NOT NULL,
                    workflow_key VARCHAR(120) NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                    timezone VARCHAR(120) NOT NULL,
                    next_fire_at TIMESTAMPTZ,
                    archived_at TIMESTAMPTZ,
                    CONSTRAINT ck_workflow_package_schedules_status CHECK (
                        status IN ('enabled', 'paused', 'archived')
                    ),
                    CONSTRAINT fk_workflow_package_schedules_package_id
                        FOREIGN KEY (package_id)
                        REFERENCES workflow_packages(id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE workflow_package_schedule_fires (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    schedule_id INTEGER NOT NULL,
                    fire_key VARCHAR(255) NOT NULL,
                    reason VARCHAR(20) NOT NULL DEFAULT 'scheduled',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    scheduled_for TIMESTAMPTZ NOT NULL,
                    rendered_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                    CONSTRAINT uq_workflow_package_schedule_fires_schedule_fire_key
                        UNIQUE (schedule_id, fire_key),
                    CONSTRAINT ck_workflow_package_schedule_fires_status CHECK (
                        status IN ('pending', 'queued', 'skipped', 'failed')
                    ),
                    CONSTRAINT ck_workflow_package_schedule_fires_reason CHECK (
                        reason IN ('scheduled', 'manual')
                    ),
                    CONSTRAINT fk_workflow_package_schedule_fires_schedule_id
                        FOREIGN KEY (schedule_id)
                        REFERENCES workflow_package_schedules(id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN schedule_id INTEGER")
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN schedule_fire_id INTEGER")
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN scheduled_for TIMESTAMPTZ")
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN schedule_reason VARCHAR(20)")
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT fk_runs_schedule_id "
                "FOREIGN KEY (schedule_id) "
                "REFERENCES workflow_package_schedules(id) ON DELETE SET NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT fk_runs_schedule_fire_id "
                "FOREIGN KEY (schedule_fire_id) "
                "REFERENCES workflow_package_schedule_fires(id) ON DELETE SET NULL"
            )
            package = _insert_representable_workflow_package(
                connection,
                key="schedule_archive_cleanup_package",
                workflow_key="schedule_archive_cleanup_workflow",
            )
            archived_schedule_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_package_schedules (
                            package_id, workflow_key, name, status, timezone, next_fire_at,
                            archived_at
                        ) VALUES (
                            :package_id, :workflow_key, 'Archived cleanup schedule', 'archived',
                            'UTC', '2026-05-31T13:00:00Z', '2026-05-31T13:30:00Z'
                        ) RETURNING id
                        """
                    ),
                    package,
                ).scalar_one()
            )
            archived_fire_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_package_schedule_fires (
                            schedule_id, fire_key, reason, status, scheduled_for,
                            rendered_parameters
                        ) VALUES (
                            :schedule_id, 'archived-cleanup-fire', 'scheduled', 'queued',
                            '2026-05-31T13:00:00Z', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {"schedule_id": archived_schedule_id},
                ).scalar_one()
            )
            archived_run_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, schedule_id, schedule_fire_id,
                            scheduled_for, schedule_reason, status, input
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, :schedule_id,
                            :schedule_fire_id, '2026-05-31T13:00:00Z', 'scheduled',
                            'succeeded', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {
                        **package,
                        "schedule_fire_id": archived_fire_id,
                        "schedule_id": archived_schedule_id,
                    },
                ).scalar_one()
            )
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=archived_run_id,
                package=package,
            )
            _insert_report_upgrade_row(
                connection,
                slug=archived_report_slug,
                source="agent",
                metadata=_agent_memory_report_metadata(runId=archived_run_id),
            )

        init_db(database_url)

        with engine.connect() as connection:
            archived_row = (
                connection.execute(
                    text(
                        """
                    SELECT schedule_id, schedule_fire_id, scheduled_for, schedule_reason,
                           schedule_provenance
                    FROM runs
                    WHERE id = :run_id
                    """
                    ),
                    {"run_id": archived_run_id},
                )
                .mappings()
                .one()
            )
            stored_schedule_provenance = cast(
                dict[str, object],
                archived_row["schedule_provenance"],
            )
            deleted_at = cast(str | None, stored_schedule_provenance["scheduleDeletedAt"])

        init_db(database_url)

        with engine.connect() as connection:
            archived_counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM workflow_package_schedules WHERE id = :schedule_id),
                        (SELECT COUNT(*) FROM workflow_package_schedule_fires WHERE id = :fire_id),
                        (SELECT COUNT(*) FROM runs WHERE id = :run_id),
                        (SELECT COUNT(*) FROM reports WHERE slug = :report_slug)
                    """
                ),
                {
                    "fire_id": archived_fire_id,
                    "report_slug": archived_report_slug,
                    "run_id": archived_run_id,
                    "schedule_id": archived_schedule_id,
                },
            ).one()
            persisted_deleted_at = connection.execute(
                text(
                    "SELECT schedule_provenance ->> 'scheduleDeletedAt' FROM runs WHERE id = :run_id"
                ),
                {"run_id": archived_run_id},
            ).scalar_one()

        assert deleted_at is not None
        assert archived_row["schedule_id"] is None
        assert archived_row["schedule_fire_id"] is None
        assert archived_row["scheduled_for"] == datetime(2026, 5, 31, 13, 0, tzinfo=UTC)
        assert archived_row["schedule_reason"] == "scheduled"
        assert stored_schedule_provenance == {
            "scheduleId": archived_schedule_id,
            "scheduleFireId": archived_fire_id,
            "scheduleName": "Archived cleanup schedule",
            "packageId": package["package_id"],
            "packageKey": package["package_key"],
            "workflowKey": package["workflow_key"],
            "timezone": "UTC",
            "recurrence": {},
            "fireKey": "archived-cleanup-fire",
            "reason": "scheduled",
            "scheduledFor": "2026-05-31T13:00:00Z",
            "scheduledLocalDate": None,
            "scheduledLocalTime": None,
            "scheduledLocalDateTime": None,
            "materializedAt": None,
            "scheduleDeletedAt": deleted_at,
        }
        assert persisted_deleted_at == deleted_at
        assert archived_counts == (0, 0, 1, 1)
    finally:
        engine.dispose()


def test_init_db_orphaned_schedule_repair_backfills_safe_provenance_and_leaves_fully_orphaned_rows_null(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS fk_runs_schedule_id"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_schedule_id_fkey"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS fk_runs_schedule_fire_id"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_schedule_fire_id_fkey"
            )
            package = _insert_representable_workflow_package(
                connection,
                key="orphaned_schedule_repair_package",
                workflow_key="orphaned_schedule_repair_workflow",
            )
            schedule_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_package_schedules (
                            package_id, workflow_key, name, timezone, recurrence,
                            input_template, template_vars
                        ) VALUES (
                            :package_id, :workflow_key, 'Repair schedule', 'UTC',
                            CAST(:recurrence AS jsonb), '{}'::jsonb, '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {**package, "recurrence": json.dumps({"type": "daily"}, sort_keys=True)},
                ).scalar_one()
            )
            fire_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_package_schedule_fires (
                            schedule_id, fire_key, reason, status, scheduled_for,
                            scheduled_local_date, scheduled_local_time,
                            scheduled_local_datetime, materialized_at, rendered_parameters
                        ) VALUES (
                            :schedule_id, 'repair-live-fire', 'manual', 'queued',
                            '2026-06-01T14:00:00Z', '2026-06-01', '14:00:00',
                            '2026-06-01T14:00:00', '2026-06-01T13:59:00Z', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {"schedule_id": schedule_id},
                ).scalar_one()
            )
            schedule_only_run_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, schedule_id, schedule_fire_id,
                            scheduled_for, schedule_reason, status, input
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, :schedule_id,
                            :schedule_fire_id, '2026-06-01T13:00:00Z', 'scheduled',
                            'queued', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {
                        **package,
                        "schedule_id": schedule_id,
                        "schedule_fire_id": fire_id + 1000,
                    },
                ).scalar_one()
            )
            fire_resolved_run_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, schedule_id, schedule_fire_id,
                            scheduled_for, schedule_reason, status, input
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, :schedule_id,
                            :schedule_fire_id, '2026-06-01T14:00:00Z', 'manual',
                            'queued', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {
                        **package,
                        "schedule_id": schedule_id + 1000,
                        "schedule_fire_id": fire_id,
                    },
                ).scalar_one()
            )
            fully_orphaned_run_id = int(
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, schedule_id, schedule_fire_id,
                            scheduled_for, schedule_reason, status, input
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, :schedule_id,
                            :schedule_fire_id, '2026-06-01T15:00:00Z', 'scheduled',
                            'queued', '{}'::jsonb
                        ) RETURNING id
                        """
                    ),
                    {
                        **package,
                        "schedule_id": schedule_id + 2000,
                        "schedule_fire_id": fire_id + 2000,
                    },
                ).scalar_one()
            )
            for run_id in (
                schedule_only_run_id,
                fire_resolved_run_id,
                fully_orphaned_run_id,
            ):
                _insert_run_workflow_package_snapshot(
                    connection,
                    run_id=run_id,
                    package=package,
                )

        init_db(database_url)
        init_db(database_url)

        with engine.connect() as connection:
            repaired_rows = cast(
                list[Mapping[str, object]],
                connection.execute(
                    text(
                        """
                        SELECT id, schedule_id, schedule_fire_id, schedule_provenance
                        FROM runs
                        WHERE id IN :run_ids
                        ORDER BY id
                        """
                    ).bindparams(bindparam("run_ids", expanding=True)),
                    {
                        "run_ids": [
                            schedule_only_run_id,
                            fire_resolved_run_id,
                            fully_orphaned_run_id,
                        ]
                    },
                )
                .mappings()
                .all(),
            )

        repaired_rows_by_id = {cast(int, row["id"]): row for row in repaired_rows}
        assert repaired_rows_by_id[schedule_only_run_id]["schedule_id"] == schedule_id
        assert repaired_rows_by_id[schedule_only_run_id]["schedule_fire_id"] is None
        assert repaired_rows_by_id[schedule_only_run_id]["schedule_provenance"] == {
            "scheduleId": schedule_id,
            "scheduleFireId": None,
            "scheduleName": "Repair schedule",
            "packageId": package["package_id"],
            "packageKey": package["package_key"],
            "workflowKey": package["workflow_key"],
            "timezone": "UTC",
            "recurrence": {"type": "daily"},
            "fireKey": None,
            "reason": "scheduled",
            "scheduledFor": "2026-06-01T13:00:00Z",
            "scheduledLocalDate": None,
            "scheduledLocalTime": None,
            "scheduledLocalDateTime": None,
            "materializedAt": None,
            "scheduleDeletedAt": None,
        }
        assert repaired_rows_by_id[fire_resolved_run_id]["schedule_id"] is None
        assert repaired_rows_by_id[fire_resolved_run_id]["schedule_fire_id"] == fire_id
        assert repaired_rows_by_id[fire_resolved_run_id]["schedule_provenance"] == {
            "scheduleId": schedule_id,
            "scheduleFireId": fire_id,
            "scheduleName": "Repair schedule",
            "packageId": package["package_id"],
            "packageKey": package["package_key"],
            "workflowKey": package["workflow_key"],
            "timezone": "UTC",
            "recurrence": {"type": "daily"},
            "fireKey": "repair-live-fire",
            "reason": "manual",
            "scheduledFor": "2026-06-01T14:00:00Z",
            "scheduledLocalDate": "2026-06-01",
            "scheduledLocalTime": "14:00:00",
            "scheduledLocalDateTime": "2026-06-01T14:00:00",
            "materializedAt": "2026-06-01T13:59:00Z",
            "scheduleDeletedAt": None,
        }
        assert repaired_rows_by_id[fully_orphaned_run_id]["schedule_id"] is None
        assert repaired_rows_by_id[fully_orphaned_run_id]["schedule_fire_id"] is None
        assert repaired_rows_by_id[fully_orphaned_run_id]["schedule_provenance"] is None
    finally:
        engine.dispose()


def test_upgrade_creates_run_forks_without_backfilling_legacy_lineage(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS "run_forks"')
            package = _insert_representable_workflow_package(
                connection,
                key="fork_upgrade_package",
            )
            source_run_id = cast(
                int,
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, extension_dependencies,
                            input, status, resume_step_index
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, '[]'::jsonb,
                            CAST(:input AS jsonb), 'succeeded', 1
                        ) RETURNING id
                        """
                    ),
                    {
                        "input": json.dumps({"ticker": "NVDA"}, sort_keys=True),
                        "package_id": package["package_id"],
                        "package_key": package["package_key"],
                        "workflow_key": package["workflow_key"],
                    },
                ).scalar_one(),
            )
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=source_run_id,
                package=package,
                parameters={"ticker": "NVDA"},
            )
            legacy_run_id = cast(
                int,
                connection.execute(
                    text(
                        """
                        INSERT INTO runs (
                            target_kind, target_id, target_key, target_version,
                            workflow_package_id, workflow_package_key,
                            workflow_package_workflow_key, extension_dependencies,
                            input, status, source_run_id, lineage_root_run_id,
                            forked_from_step_index, resume_step_index
                        ) VALUES (
                            'workflowPackage', :package_id, :package_key, 1,
                            :package_id, :package_key, :workflow_key, '[]'::jsonb,
                            CAST(:input AS jsonb), 'succeeded', :source_run_id,
                            :source_run_id, 2, 2
                        ) RETURNING id
                        """
                    ),
                    {
                        "input": json.dumps({"ticker": "NVDA"}, sort_keys=True),
                        "package_id": package["package_id"],
                        "package_key": package["package_key"],
                        "source_run_id": source_run_id,
                        "workflow_key": package["workflow_key"],
                    },
                ).scalar_one(),
            )
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=legacy_run_id,
                package=package,
                parameters={"ticker": "NVDA"},
            )

        upgrade_legacy_schema(engine)
        _assert_runtime_execution_table_shape(engine)
        with engine.connect() as connection:
            fork_count = connection.execute(text("SELECT COUNT(*) FROM run_forks")).scalar_one()
            legacy_lineage = connection.execute(
                text(
                    """
                    SELECT source_run_id, lineage_root_run_id,
                           forked_from_step_index, resume_step_index
                    FROM runs
                    WHERE id = :legacy_run_id
                    """
                ),
                {"legacy_run_id": legacy_run_id},
            ).one()

        assert fork_count == 0
        assert tuple(legacy_lineage) == (source_run_id, source_run_id, 2, 2)
    finally:
        engine.dispose()


def test_init_db_creates_workflow_memory_tables_idempotently(database_url: str) -> None:
    init_db(database_url)
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        _assert_workflow_memory_table_shape(engine)
        with engine.begin() as connection:
            item_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_items (
                        memory_id, package_key, workflow_key, agent_key, step_id, namespace,
                        kind, content_json, summary, provenance_json, policy_status,
                        lifecycle_status
                    ) VALUES (
                        'workflow-memory-upgrade-1', 'package-a', 'workflow-a', 'agent-a',
                        'step-a', 'research', 'fact', '{"value":"alpha"}'::jsonb,
                        'Workflow memory summary', '{}'::jsonb, 'committed', 'active'
                    ) RETURNING id
                    """
                )
            ).scalar_one()
            proposal_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_proposals (
                        proposal_id, package_key, workflow_key, agent_key, step_id, namespace,
                        kind, content_json, detectors_json, status
                    ) VALUES (
                        'workflow-proposal-upgrade-1', 'package-a', 'workflow-a', 'agent-a',
                        'step-a', 'research', 'fact', '{"value":"alpha"}'::jsonb,
                        '{}'::jsonb, 'committed'
                    ) RETURNING id
                    """
                )
            ).scalar_one()
            decision_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_decisions (
                        decision_id, proposal_id, decision, reason_code, policy_snapshot_json,
                        decided_by
                    ) VALUES (
                        'workflow-decision-upgrade-1', :proposal_id, 'commit', 'policy_match',
                        '{}'::jsonb, 'policy'
                    ) RETURNING id
                    """
                ),
                {"proposal_id": proposal_id},
            ).scalar_one()
            connection.execute(
                text(
                    """
                    UPDATE workflow_memory_items
                    SET proposal_id = :proposal_id, decision_id = :decision_id
                    WHERE id = :item_id
                    """
                ),
                {"decision_id": decision_id, "item_id": item_id, "proposal_id": proposal_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_revisions (
                        memory_item_id, revision_id, version, content_json, summary,
                        provenance_json
                    ) VALUES (
                        :item_id, 'workflow-memory-upgrade-1:rev-1', 1,
                        '{"value":"alpha"}'::jsonb, 'Workflow memory summary', '{}'::jsonb
                    )
                    """
                ),
                {"item_id": item_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_quarantine (
                        memory_item_id, reason_code, detectors_json
                    ) VALUES (:item_id, 'policy_review', '{}'::jsonb)
                    """
                ),
                {"item_id": item_id},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_audit_events (
                        event_type, target_type, target_id, package_key, workflow_key, event_json
                    ) VALUES (
                        'created', 'memory_item', 'workflow-memory-upgrade-1', 'package-a',
                        'workflow-a', '{}'::jsonb
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_consolidation_runs (
                        consolidation_id, package_key, workflow_key, namespace, status,
                        started_at, source_memory_ids_json, output_memory_ids_json, stats_json
                    ) VALUES (
                        'consolidation-upgrade-1', 'package-a', 'workflow-a', 'research',
                        'succeeded', NOW(), '[]'::jsonb, '[]'::jsonb, '{}'::jsonb
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_checkpoints (
                        checkpoint_id, run_id, package_key, workflow_key, checkpoint_type,
                        sequence, state_json, retention, metadata_json
                    ) VALUES (
                        'checkpoint-upgrade-1', 1, 'package-a', 'workflow-a', 'resume', 1,
                        CAST(:state_json AS jsonb), 'latest', '{}'::jsonb
                    )
                    """
                ),
                {"state_json": json.dumps({"cursor": "step-a"}, sort_keys=True)},
            )

        init_db(database_url)
        _assert_workflow_memory_table_shape(engine)
        with engine.connect() as connection:
            counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM workflow_memory_items),
                        (SELECT COUNT(*) FROM workflow_memory_proposals),
                        (SELECT COUNT(*) FROM workflow_memory_decisions),
                        (SELECT COUNT(*) FROM workflow_memory_audit_events),
                        (SELECT COUNT(*) FROM workflow_memory_revisions),
                        (SELECT COUNT(*) FROM workflow_memory_quarantine),
                        (SELECT COUNT(*) FROM workflow_memory_consolidation_runs),
                        (SELECT COUNT(*) FROM workflow_checkpoints)
                    """
                )
            ).one()

        assert counts == (1, 1, 1, 1, 1, 1, 1, 1)
    finally:
        engine.dispose()


def test_init_db_drops_empty_old_memory_tables_deterministically(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE agent_memory_entries (id INTEGER)")
            connection.exec_driver_sql("CREATE TABLE agent_memory_revisions (id INTEGER)")
            connection.exec_driver_sql("CREATE TABLE run_memory_events (id INTEGER)")

        init_db(database_url)
        init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert OLD_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        assert LEGACY_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        _assert_workflow_memory_table_shape(engine)
    finally:
        engine.dispose()


def test_init_db_renames_non_empty_old_memory_tables_to_legacy_names(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE agent_memory_entries (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    memory_id VARCHAR(160) NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE agent_memory_revisions (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    memory_entry_id INTEGER REFERENCES agent_memory_entries(id),
                    revision_id VARCHAR(160) NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE run_memory_events (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    memory_entry_id INTEGER REFERENCES agent_memory_entries(id),
                    memory_id VARCHAR(160)
                )
                """
            )
            entry_id = connection.execute(
                text(
                    "INSERT INTO agent_memory_entries (memory_id) "
                    "VALUES ('old-memory-1') RETURNING id"
                )
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO agent_memory_revisions (memory_entry_id, revision_id) "
                    "VALUES (:entry_id, 'old-memory-1:rev-1')"
                ),
                {"entry_id": entry_id},
            )
            connection.execute(
                text(
                    "INSERT INTO run_memory_events (memory_entry_id, memory_id) "
                    "VALUES (:entry_id, 'old-memory-1')"
                ),
                {"entry_id": entry_id},
            )

        init_db(database_url)
        init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert OLD_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        assert LEGACY_MEMORY_TABLE_NAMES <= table_names
        _assert_workflow_memory_table_shape(engine)
        with engine.connect() as connection:
            counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM legacy_agent_memory_entries),
                        (SELECT COUNT(*) FROM legacy_agent_memory_revisions),
                        (SELECT COUNT(*) FROM legacy_run_memory_events)
                    """
                )
            ).one()
            legacy_event = connection.execute(
                text("SELECT memory_id FROM legacy_run_memory_events")
            ).scalar_one()

        assert counts == (1, 1, 1)
        assert legacy_event == "old-memory-1"
    finally:
        engine.dispose()


def test_init_db_drops_removed_memory_chunk_and_embedding_tables(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE agent_memory_chunks (id INTEGER)")
            connection.exec_driver_sql("CREATE TABLE agent_memory_embeddings (id INTEGER)")

        init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert REMOVED_CORE_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        _assert_workflow_memory_table_shape(engine)
    finally:
        engine.dispose()


def retired_init_db_maps_legacy_status_to_workflow_visibility(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    legacy_statuses = ("approved", "pending", "archived")
    content_hashes = ("a" * 64, "b" * 64, "c" * 64)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_revisions DROP COLUMN visible_to_workflow CASCADE"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_entries DROP COLUMN visible_to_workflow CASCADE"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_entries ADD COLUMN status VARCHAR(20) "
                "NOT NULL DEFAULT 'pending'"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_revisions ADD COLUMN status VARCHAR(20) "
                "NOT NULL DEFAULT 'pending'"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_entries ADD CONSTRAINT ck_agent_memory_entries_status "
                "CHECK (status IN ('pending', 'approved', 'archived'))"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_revisions ADD CONSTRAINT ck_agent_memory_revisions_status "
                "CHECK (status IN ('pending', 'approved', 'archived'))"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_agent_memory_entries_scope_status_kind "
                "ON agent_memory_entries (scope_type, scope_key, status, kind)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_agent_memory_entries_status_kind "
                "ON agent_memory_entries (status, kind)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_agent_memory_entries_status_updated_at_id "
                "ON agent_memory_entries (status, updated_at, id)"
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version, input, status
                    ) VALUES (
                        'workflowPackage', 1, 'legacy_memory_status_package', 1,
                        '{}'::jsonb, 'succeeded'
                    )
                    RETURNING id
                    """
                )
            ).scalar_one()
            for index, (legacy_status, content_hash) in enumerate(
                zip(legacy_statuses, content_hashes, strict=True),
                start=1,
            ):
                memory_entry_id = connection.execute(
                    text(
                        """
                        INSERT INTO agent_memory_entries (
                            memory_id, scope_type, scope_key, kind, status, summary,
                            content_hash, source_run_id, source_agent_key,
                            source_agent_version, source_step_id, source_slot
                        ) VALUES (
                            :memory_id, 'run', :scope_key, 'decision', :status,
                            :summary, :content_hash, :run_id, 'research_agent', 1,
                            :source_step_id, 'decision'
                        ) RETURNING id
                        """
                    ),
                    {
                        "content_hash": content_hash,
                        "memory_id": f"memory-status-{legacy_status}",
                        "run_id": run_id,
                        "scope_key": str(run_id),
                        "source_step_id": f"write_memory_{index}",
                        "status": legacy_status,
                        "summary": f"{legacy_status} memory summary",
                    },
                ).scalar_one()
                connection.execute(
                    text(
                        """
                        INSERT INTO agent_memory_revisions (
                            memory_entry_id, revision_id, version, status, summary, content,
                            content_hash, source_run_id, source_agent_key, source_step_id,
                            source_slot
                        ) VALUES (
                            :memory_entry_id, :revision_id, 1, :status, :summary,
                            :content, :content_hash, :run_id, 'research_agent',
                            :source_step_id, 'decision'
                        )
                        """
                    ),
                    {
                        "content": f"{legacy_status} memory content.",
                        "content_hash": content_hash,
                        "memory_entry_id": memory_entry_id,
                        "revision_id": f"memory-status-{legacy_status}:rev-1",
                        "run_id": run_id,
                        "source_step_id": f"write_memory_{index}",
                        "status": legacy_status,
                        "summary": f"{legacy_status} memory summary",
                    },
                )

        init_db(database_url)
        _assert_core_memory_table_shape(engine)

        with engine.connect() as connection:
            entry_visibility = connection.execute(
                text(
                    """
                    SELECT memory_id, visible_to_workflow
                    FROM agent_memory_entries
                    WHERE memory_id LIKE 'memory-status-%'
                    ORDER BY memory_id ASC
                    """
                )
            ).all()
            revision_visibility = connection.execute(
                text(
                    """
                    SELECT revision_id, visible_to_workflow
                    FROM agent_memory_revisions
                    WHERE revision_id LIKE 'memory-status-%'
                    ORDER BY revision_id ASC
                    """
                )
            ).all()

        assert entry_visibility == [
            ("memory-status-approved", True),
            ("memory-status-archived", False),
            ("memory-status-pending", False),
        ]
        assert revision_visibility == [
            ("memory-status-approved:rev-1", True),
            ("memory-status-archived:rev-1", False),
            ("memory-status-pending:rev-1", False),
        ]
    finally:
        engine.dispose()


def retired_init_db_normalizes_legacy_status_event_types(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE run_memory_events "
                "DROP CONSTRAINT IF EXISTS ck_run_memory_events_event_type"
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version, input, status
                    ) VALUES (
                        'workflowPackage', 1, 'legacy_memory_event_package', 1,
                        '{}'::jsonb, 'succeeded'
                    )
                    RETURNING id
                    """
                )
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO run_memory_events (run_id, event_type, status_snapshot)
                    VALUES (
                        :run_id, 'operator_status_changed',
                        jsonb_build_object('visibleToWorkflow', TRUE)
                    )
                    """
                ),
                {"run_id": run_id},
            )

        init_db(database_url)
        _assert_core_memory_table_shape(engine)
        with engine.connect() as connection:
            event_types = (
                connection.execute(text("SELECT event_type FROM run_memory_events ORDER BY id"))
                .scalars()
                .all()
            )

        assert event_types == ["operator_visibility_changed"]
    finally:
        engine.dispose()


def retired_init_db_drops_obsolete_core_attributes(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_entries "
                "ADD COLUMN attributes JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_revisions "
                "ADD COLUMN attributes JSONB NOT NULL DEFAULT '{}'::jsonb"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_entries "
                "ADD CONSTRAINT ck_agent_memory_entries_attributes "
                "CHECK (jsonb_typeof(attributes) = 'object')"
            )
            connection.exec_driver_sql(
                "ALTER TABLE agent_memory_revisions "
                "ADD CONSTRAINT ck_agent_memory_revisions_attributes "
                "CHECK (jsonb_typeof(attributes) = 'object')"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_agent_memory_entries_attributes_gin "
                "ON agent_memory_entries USING gin (attributes jsonb_path_ops)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX ix_agent_memory_revisions_attributes_gin "
                "ON agent_memory_revisions USING gin (attributes jsonb_path_ops)"
            )

        init_db(database_url)
        _assert_core_memory_table_shape(engine)
    finally:
        engine.dispose()


def retired_init_db_creates_core_tables_idempotently(database_url: str) -> None:
    init_db(database_url)
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    first_content_hash = "a" * 64
    second_content_hash = "b" * 64

    try:
        _assert_core_memory_table_shape(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                ALTER TABLE agent_memory_revisions
                ADD CONSTRAINT uq_agent_memory_revisions_entry_content_hash
                UNIQUE (memory_entry_id, content_hash)
                """
            )
        init_db(database_url)
        _assert_core_memory_table_shape(engine)

        with engine.begin() as connection:
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version, input, status
                    ) VALUES (
                        'workflowPackage', 1, 'memory_package', 1, '{}'::jsonb, 'succeeded'
                    )
                    RETURNING id
                    """
                )
            ).scalar_one()
            memory_entry_id = connection.execute(
                text(
                    """
                    INSERT INTO agent_memory_entries (
                        memory_id, scope_type, scope_key, kind, visible_to_workflow, summary,
                        content_hash, source_run_id, source_agent_key, source_agent_version,
                        source_step_id, source_slot
                    ) VALUES (
                        'memory-core-1', 'run', :scope_key, 'decision', FALSE,
                        'Memory summary', :content_hash, :run_id, 'research_agent', 1,
                        'write_memory', 'decision'
                    ) RETURNING id
                    """
                ),
                {
                    "content_hash": first_content_hash,
                    "run_id": run_id,
                    "scope_key": str(run_id),
                },
            ).scalar_one()

            revision_id = connection.execute(
                text(
                    """
                    INSERT INTO agent_memory_revisions (
                        memory_entry_id, revision_id, version, visible_to_workflow, summary,
                        content, content_hash, source_run_id, source_agent_key, source_step_id,
                        source_slot
                    ) VALUES (
                        :memory_entry_id, 'memory-core-1:rev-1', 1, FALSE,
                        'Memory summary', 'Canonical memory content.', :content_hash, :run_id,
                        'research_agent', 'write_memory', 'decision'
                    ) RETURNING id
                    """
                ),
                {
                    "content_hash": first_content_hash,
                    "memory_entry_id": memory_entry_id,
                    "run_id": run_id,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """
                    INSERT INTO agent_memory_revisions (
                        memory_entry_id, revision_id, version, visible_to_workflow, summary,
                        content, content_hash, source_run_id, source_agent_key, source_step_id,
                        source_slot
                    ) VALUES
                        (
                            :memory_entry_id, 'memory-core-1:rev-2', 2, FALSE,
                            'Updated memory summary', 'Canonical memory content B.',
                            :second_content_hash, :run_id, 'research_agent', 'write_memory',
                            'decision'
                        ),
                        (
                            :memory_entry_id, 'memory-core-1:rev-3', 3, FALSE,
                            'Memory summary restored', 'Canonical memory content.',
                            :first_content_hash, :run_id, 'research_agent', 'write_memory',
                            'decision'
                        )
                    """
                ),
                {
                    "first_content_hash": first_content_hash,
                    "memory_entry_id": memory_entry_id,
                    "run_id": run_id,
                    "second_content_hash": second_content_hash,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO run_memory_events (
                        run_id, event_type, memory_entry_id, memory_revision_id, memory_id,
                        revision_id, retrieval_mode, result_snapshot, status_snapshot
                    ) VALUES (
                        :run_id, 'written', :memory_entry_id, :revision_id, 'memory-core-1',
                        'memory-core-1:rev-1', 'write', '{"action":"created"}'::jsonb,
                        '{"status":"pending"}'::jsonb
                    )
                    """
                ),
                {
                    "memory_entry_id": memory_entry_id,
                    "revision_id": revision_id,
                    "run_id": run_id,
                },
            )

        with engine.connect() as connection:
            counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM agent_memory_entries),
                        (SELECT COUNT(*) FROM agent_memory_revisions),
                        (SELECT COUNT(*) FROM run_memory_events)
                    """
                )
            ).one()
        assert counts == (1, 3, 1)
        with engine.connect() as connection:
            revision_hashes = connection.execute(
                text(
                    """
                    SELECT version, content_hash
                    FROM agent_memory_revisions
                    WHERE memory_entry_id = :memory_entry_id
                    ORDER BY version ASC
                    """
                ),
                {"memory_entry_id": memory_entry_id},
            ).all()
        assert revision_hashes == [
            (1, first_content_hash),
            (2, second_content_hash),
            (3, first_content_hash),
        ]
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO agent_memory_entries (
                            memory_id, scope_type, scope_key, kind, visible_to_workflow, summary,
                            content_hash, source_run_id, source_agent_key, source_agent_version,
                            source_step_id, source_slot
                        ) VALUES (
                            'memory-core-duplicate', 'run', :scope_key, 'decision', FALSE,
                            'Duplicate memory summary', :content_hash, :run_id,
                            'research_agent', 1, 'write_memory', 'decision'
                        )
                        """
                    ),
                    {
                        "content_hash": first_content_hash,
                        "run_id": run_id,
                        "scope_key": str(run_id),
                    },
                )

        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM agent_memory_entries WHERE id = :memory_entry_id"),
                {"memory_entry_id": memory_entry_id},
            )
            cascade_counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM agent_memory_entries),
                        (SELECT COUNT(*) FROM agent_memory_revisions),
                        (SELECT COUNT(*) FROM run_memory_events)
                    """
                )
            ).one()
            event_snapshot = connection.execute(
                text(
                    """
                    SELECT memory_entry_id, memory_revision_id, memory_id, revision_id
                    FROM run_memory_events
                    WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).one()

        assert cascade_counts == (0, 0, 1)
        assert event_snapshot == (None, None, "memory-core-1", "memory-core-1:rev-1")
    finally:
        engine.dispose()


def test_init_db_repairs_jsonb_and_text_indexes_on_existing_persistence_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)
    index_names = (
        "ix_run_workflow_package_snapshots_compiled_plan_gin",
        "ix_run_workflow_package_snapshots_model_connections_gin",
    )

    try:
        with engine.begin() as connection:
            for index_name in index_names:
                connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

        init_db(database_url)
        _assert_core_memory_table_shape(engine)
        _assert_runtime_execution_table_shape(engine)

        with engine.connect() as connection:
            index_definitions = {
                str(row.indexname): str(row.indexdef)
                for row in connection.execute(
                    text(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE indexname IN :index_names
                        """
                    ).bindparams(bindparam("index_names", expanding=True)),
                    {"index_names": index_names},
                )
            }

        assert set(index_definitions) == set(index_names)
        assert (
            "jsonb_path_ops"
            in index_definitions["ix_run_workflow_package_snapshots_compiled_plan_gin"]
        )
        assert (
            "jsonb_path_ops"
            in index_definitions["ix_run_workflow_package_snapshots_model_connections_gin"]
        )
    finally:
        engine.dispose()


def retired_init_db_drops_removed_chunk_and_embedding_tables(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE agent_memory_chunks (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    memory_entry_id INTEGER,
                    memory_revision_id INTEGER
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE agent_memory_embeddings (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    memory_chunk_id INTEGER REFERENCES agent_memory_chunks(id) ON DELETE CASCADE
                )
                """
            )

        init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert REMOVED_CORE_MEMORY_TABLE_NAMES.isdisjoint(table_names)
        _assert_core_memory_table_shape(engine)
    finally:
        engine.dispose()


def retired_init_db_ignores_legacy_report_backed_rows(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    legacy_slug = "legacy_agent_memory_historical"
    normal_slug = "ordinary_external_report"

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE reports (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    slug VARCHAR(200) NOT NULL,
                    source VARCHAR(20) NOT NULL DEFAULT 'compiled',
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_reports_name UNIQUE (name),
                    CONSTRAINT uq_reports_slug UNIQUE (slug)
                )
                """
            )
            _insert_report_upgrade_row(
                connection,
                slug=legacy_slug,
                source="agent",
                metadata=_agent_memory_report_metadata(),
            )
            _insert_report_upgrade_row(
                connection,
                slug=normal_slug,
                source="external",
                metadata={"analysis": {"reviewType": "weekly_review"}},
            )

        init_db(database_url)
        init_db(database_url)

        _assert_core_memory_table_shape(engine)
        rows = _report_upgrade_rows_by_slug(engine, (legacy_slug, normal_slug))
        with engine.connect() as connection:
            memory_counts = connection.execute(
                text(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM agent_memory_entries),
                        (SELECT COUNT(*) FROM agent_memory_revisions),
                        (SELECT COUNT(*) FROM run_memory_events)
                    """
                )
            ).one()

        assert memory_counts == (0, 0, 0)
        assert rows[legacy_slug]["source"] == "agent"
        assert rows[legacy_slug]["metadata"] == _agent_memory_report_metadata()
        assert rows[normal_slug] == {
            "source": "external",
            "metadata": {"analysis": {"reviewType": "weekly_review"}},
        }
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


def _recreate_legacy_owner_scoped_runtime_input_registry_table(
    connection: Connection,
) -> None:
    connection.exec_driver_sql("DROP TABLE IF EXISTS workflow_package_runtime_input_entries")
    connection.exec_driver_sql(
        """
        CREATE TABLE workflow_package_runtime_input_entries (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            package_id INTEGER NOT NULL,
            workflow_key VARCHAR(120) NOT NULL,
            owner_type VARCHAR(40) NOT NULL,
            owner_id VARCHAR(120) NOT NULL,
            slot VARCHAR(20) NOT NULL,
            name VARCHAR(200),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_kind VARCHAR(40) NOT NULL,
            manifest_hash VARCHAR(64) NOT NULL,
            compiled_hash VARCHAR(64) NOT NULL,
            schema_fingerprint VARCHAR(64) NOT NULL,
            input_schema_snapshot JSONB,
            source_run_id INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_workflow_package_runtime_input_entries_slot CHECK (
                slot IN ('history', 'personal')
            ),
            CONSTRAINT ck_workflow_package_runtime_input_entries_name_personal_only CHECK (
                slot = 'personal' OR name IS NULL
            ),
            CONSTRAINT fk_workflow_package_runtime_input_entries_package_id
                FOREIGN KEY (package_id) REFERENCES workflow_packages(id) ON DELETE CASCADE,
            CONSTRAINT fk_workflow_package_runtime_input_entries_source_run_id
                FOREIGN KEY (source_run_id) REFERENCES runs(id) ON DELETE SET NULL
        )
        """
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_workflow_package_runtime_input_entries_package "
        "ON workflow_package_runtime_input_entries (package_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_workflow_package_runtime_input_entries_scope_slot_created "
        "ON workflow_package_runtime_input_entries "
        "(package_id, workflow_key, owner_type, owner_id, slot, created_at, id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_workflow_package_runtime_input_entries_scope_slot_updated "
        "ON workflow_package_runtime_input_entries "
        "(package_id, workflow_key, owner_type, owner_id, slot, updated_at, id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX ix_workflow_package_runtime_input_entries_source_run "
        "ON workflow_package_runtime_input_entries (source_run_id)"
    )


def _insert_legacy_owner_scoped_runtime_input_entry(
    connection: Connection,
    *,
    package: Mapping[str, object],
    owner_type: str,
    owner_id: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO workflow_package_runtime_input_entries (
                package_id, workflow_key, owner_type, owner_id, slot, name, payload,
                source_kind, manifest_hash, compiled_hash, schema_fingerprint,
                input_schema_snapshot, source_run_id
            ) VALUES (
                :package_id, :workflow_key, :owner_type, :owner_id, 'personal',
                'Default review', '{"ticker":"MSFT"}'::jsonb, 'manual', :manifest_hash,
                :compiled_hash, :schema_fingerprint, '{"type":"object"}'::jsonb, NULL
            )
            """
        ),
        {
            "compiled_hash": package["compiled_hash"],
            "manifest_hash": package["manifest_hash"],
            "owner_id": owner_id,
            "owner_type": owner_type,
            "package_id": package["package_id"],
            "schema_fingerprint": "c" * 64,
            "workflow_key": package["workflow_key"],
        },
    )


def test_runtime_input_owner_cutoff_valid_legacy_scope_converts_to_preset(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="runtime_input_owner_cutoff_valid",
                workflow_key="daily_review",
            )
            _recreate_legacy_owner_scoped_runtime_input_registry_table(connection)
            _insert_legacy_owner_scoped_runtime_input_entry(
                connection,
                package=package,
                owner_type="local_user",
                owner_id="default",
            )

        init_db(database_url)

        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("workflow_package_runtime_input_entries")
        }
        check_constraints = {
            constraint["name"]: constraint["sqltext"]
            for constraint in inspector.get_check_constraints(
                "workflow_package_runtime_input_entries"
            )
            if constraint.get("name")
        }
        index_columns = {
            index["name"]: tuple(index["column_names"])
            for index in inspector.get_indexes("workflow_package_runtime_input_entries")
        }
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT slot, name, payload
                    FROM workflow_package_runtime_input_entries
                    WHERE package_id = :package_id
                    """
                ),
                {"package_id": package["package_id"]},
            ).one()
            index_definitions = {
                str(index_name): str(index_definition).lower()
                for index_name, index_definition in connection.execute(
                    text(
                        """
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE tablename = 'workflow_package_runtime_input_entries'
                        """
                    )
                )
            }

        assert set(columns) == _RUNTIME_INPUT_REGISTRY_COLUMNS
        assert row == ("preset", "Default review", {"ticker": "MSFT"})
        slot_constraint_sql = check_constraints["ck_workflow_package_runtime_input_entries_slot"]
        assert "preset" in slot_constraint_sql
        assert "history" in slot_constraint_sql
        assert "personal" not in slot_constraint_sql
        assert index_columns["ix_workflow_package_runtime_input_entries_scope_slot_created"] == (
            "package_id",
            "workflow_key",
            "slot",
            "created_at",
            "id",
        )
        assert index_columns["ix_workflow_package_runtime_input_entries_scope_slot_updated"] == (
            "package_id",
            "workflow_key",
            "slot",
            "updated_at",
            "id",
        )
        assert all("owner_type" not in definition for definition in index_definitions.values())
        assert all("owner_id" not in definition for definition in index_definitions.values())
    finally:
        engine.dispose()


def test_runtime_input_owner_cutoff_invalid_legacy_scope_hard_fails(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="runtime_input_owner_cutoff_invalid",
                workflow_key="daily_review",
            )
            _recreate_legacy_owner_scoped_runtime_input_registry_table(connection)
            _insert_legacy_owner_scoped_runtime_input_entry(
                connection,
                package=package,
                owner_type="local_user",
                owner_id="unexpected",
            )

        with pytest.raises(RuntimeError) as error:
            init_db(database_url)

        message = str(error.value)
        assert "workflow_package_runtime_input_entries" in message
        assert "invalid owner scope" in message
        with engine.connect() as connection:
            invalid_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_runtime_input_entries
                    WHERE owner_type = 'local_user'
                      AND owner_id = 'unexpected'
                    """
                )
            ).scalar_one()
        assert invalid_count == 1
    finally:
        engine.dispose()


def test_init_db_creates_runtime_input_registry_table_and_cascades(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("workflow_package_runtime_input_entries")
        }
        indexes = {
            index["name"]
            for index in inspector.get_indexes("workflow_package_runtime_input_entries")
        }
        check_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints(
                "workflow_package_runtime_input_entries"
            )
        }
        foreign_keys = {
            _foreign_key_signature(cast(dict[str, object], cast(object, foreign_key)))
            for foreign_key in inspector.get_foreign_keys("workflow_package_runtime_input_entries")
        }

        assert set(columns) == _RUNTIME_INPUT_REGISTRY_COLUMNS
        assert columns["package_id"]["nullable"] is False
        assert columns["workflow_key"]["nullable"] is False
        assert columns["slot"]["nullable"] is False
        assert columns["name"]["nullable"] is True
        assert columns["payload"]["nullable"] is False
        assert columns["source_kind"]["nullable"] is False
        assert columns["manifest_hash"]["nullable"] is False
        assert columns["compiled_hash"]["nullable"] is False
        assert columns["schema_fingerprint"]["nullable"] is False
        assert columns["input_schema_snapshot"]["nullable"] is True
        assert columns["source_run_id"]["nullable"] is True
        assert {
            "ix_workflow_package_runtime_input_entries_package",
            "ix_workflow_package_runtime_input_entries_scope_slot_created",
            "ix_workflow_package_runtime_input_entries_scope_slot_updated",
            "ix_workflow_package_runtime_input_entries_source_run",
        } <= indexes
        assert {
            "ck_workflow_package_runtime_input_entries_slot",
            "ck_workflow_package_runtime_input_entries_name_preset_only",
        } <= check_constraints
        assert (("package_id",), "workflow_packages", "CASCADE") in foreign_keys
        assert (("source_run_id",), "runs", "SET NULL") in foreign_keys

        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="runtime_input_registry_scope",
                workflow_key="daily_review",
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, extension_dependencies,
                        input, status
                    ) VALUES (
                        'workflowPackage', :package_id, :package_key,
                        :target_version, :package_id, :package_key, :workflow_key,
                        '[]'::jsonb, '{}'::jsonb, 'succeeded'
                    ) RETURNING id
                    """
                ),
                {
                    "package_id": package["package_id"],
                    "package_key": package["package_key"],
                    "target_version": package["target_version"],
                    "workflow_key": package["workflow_key"],
                },
            ).scalar_one()
            base_params = {
                "package_id": package["package_id"],
                "workflow_key": package["workflow_key"],
                "manifest_hash": package["manifest_hash"],
                "compiled_hash": package["compiled_hash"],
                "schema_fingerprint": "c" * 64,
                "input_schema_snapshot": json.dumps({"type": "object"}, sort_keys=True),
            }
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_runtime_input_entries (
                        package_id, workflow_key, slot, name, payload, source_kind,
                        manifest_hash, compiled_hash, schema_fingerprint,
                        input_schema_snapshot, source_run_id
                    ) VALUES (
                        :package_id, :workflow_key, 'preset', 'Default review',
                        CAST(:preset_payload AS jsonb), 'manual', :manifest_hash,
                        :compiled_hash, :schema_fingerprint,
                        CAST(:input_schema_snapshot AS jsonb), NULL
                    )
                    """
                ),
                {
                    **base_params,
                    "preset_payload": json.dumps({"ticker": "MSFT"}, sort_keys=True),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO workflow_package_runtime_input_entries (
                        package_id, workflow_key, slot, name, payload, source_kind,
                        manifest_hash, compiled_hash, schema_fingerprint,
                        input_schema_snapshot, source_run_id
                    ) VALUES (
                        :package_id, :workflow_key, 'history', NULL,
                        CAST(:history_payload AS jsonb), 'launch', :manifest_hash,
                        :compiled_hash, :schema_fingerprint,
                        CAST(:input_schema_snapshot AS jsonb), :run_id
                    )
                    """
                ),
                {
                    **base_params,
                    "history_payload": json.dumps({"ticker": "AAPL"}, sort_keys=True),
                    "run_id": run_id,
                },
            )
            entry_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_runtime_input_entries
                    WHERE package_id = :package_id
                    """
                ),
                {"package_id": package["package_id"]},
            ).scalar_one()
            connection.execute(text("DELETE FROM runs WHERE id = :run_id"), {"run_id": run_id})
            source_run_null_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_runtime_input_entries
                    WHERE package_id = :package_id
                      AND slot = 'history'
                      AND source_run_id IS NULL
                    """
                ),
                {"package_id": package["package_id"]},
            ).scalar_one()
            connection.execute(
                text("DELETE FROM workflow_packages WHERE id = :package_id"),
                {"package_id": package["package_id"]},
            )
            remaining_count = connection.execute(
                text("SELECT COUNT(*) FROM workflow_package_runtime_input_entries")
            ).scalar_one()

        assert entry_count == 2
        assert source_run_null_count == 1
        assert remaining_count == 0
    finally:
        engine.dispose()


def test_runtime_input_registry_upgrade_does_not_backfill_from_run_snapshots(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="runtime_input_no_backfill",
                workflow_key="daily_review",
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, extension_dependencies,
                        input, status
                    ) VALUES (
                        'workflowPackage', :package_id, :package_key, :target_version,
                        :package_id, :package_key, :workflow_key,
                        '[]'::jsonb, '{"ticker": "AAPL"}'::jsonb, 'succeeded'
                    ) RETURNING id
                    """
                ),
                {
                    "package_id": package["package_id"],
                    "package_key": package["package_key"],
                    "target_version": package["target_version"],
                    "workflow_key": package["workflow_key"],
                },
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=cast(int, run_id),
                package=package,
                parameters={"ticker": "AAPL"},
            )

        init_db(database_url)

        with engine.connect() as connection:
            registry_count = connection.execute(
                text("SELECT COUNT(*) FROM workflow_package_runtime_input_entries")
            ).scalar_one()
            snapshot_parameters = connection.execute(
                text(
                    """
                    SELECT launch_parameters
                    FROM run_workflow_package_snapshots
                    WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).scalar_one()

        assert registry_count == 0
        assert snapshot_parameters == {"ticker": "AAPL"}
    finally:
        engine.dispose()


def test_init_db_seeds_tradingagents_advisory_preset_without_secret_state(
    database_url: str,
) -> None:
    fixture_source = _TRADINGAGENTS_FIXTURE_PATH.read_text(encoding="utf-8")
    preset_sql = _TRADINGAGENTS_PRESET_SQL_PATH.read_text(encoding="utf-8")
    assert "INSERT INTO workflow_packages" in preset_sql
    assert "ON CONFLICT (key) DO UPDATE" in preset_sql
    assert "WHERE NOT EXISTS" not in preset_sql
    assert "INSERT INTO workflow_package_versions" not in preset_sql
    assert "latest_version_id" not in preset_sql
    assert "draft_source" not in preset_sql
    removed_validation_column = "_".join(("validation", "summary"))
    assert removed_validation_column not in preset_sql
    assert "INSERT INTO model_connections" not in preset_sql
    assert "workflow_package_secret_bindings (" not in preset_sql
    assert "INSERT INTO runs" not in preset_sql

    init_db(database_url)
    engine = create_engine(database_url, future=True)
    fixture_compiled = _compile_fixture_artifacts(engine, fixture_source)
    expected_package_definition = cast(dict[str, object], fixture_compiled["packageDefinition"])
    expected_compiled_plan = cast(dict[str, object], fixture_compiled["compiledPlan"])
    expected_extension_dependencies = cast(
        list[dict[str, object]], fixture_compiled["extensionDependencies"]
    )

    try:
        with engine.connect() as connection:
            table_names = set(inspect(connection).get_table_names())
            assert "workflow_package_versions" not in table_names
            assert "workflow_package_version_model_connections" not in table_names
            row = (
                connection.execute(
                    text(
                        """
                    SELECT
                        package.id AS package_id,
                        package.key,
                        package.name,
                        package.description,
                        package.manifest_source,
                        package.manifest_hash,
                        package.package_definition,
                        package.compiled_plan,
                        package.compiled_hash,
                        package.extension_dependencies
                    FROM workflow_packages AS package
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
            run_count = connection.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()

        assert package_count == 2
        assert row["key"] == _TRADINGAGENTS_PRESET_KEY
        assert row["name"] == "TradingAgents Advisory Research"
        assert (
            row["description"]
            == cast(dict[str, object], expected_package_definition["metadata"])["description"]
        )
        assert row["manifest_source"] == fixture_source
        assert row["manifest_hash"] == fixture_compiled["manifestHash"]
        assert row["compiled_hash"] == fixture_compiled["compiledHash"]
        assert row["package_definition"] == expected_package_definition
        assert row["compiled_plan"] == expected_compiled_plan
        assert row["extension_dependencies"] == expected_extension_dependencies

        serialized_preset = (
            fixture_source
            + json.dumps(row["package_definition"], sort_keys=True)
            + json.dumps(row["compiled_plan"], sort_keys=True)
        )
        removed_budget_field = "budget" + "Usd"
        for forbidden_value in (
            removed_budget_field,
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
        assert run_count == 0

        package_id = int(row["package_id"])
        for workflow_key in (
            "advisory_research",
            "market_research",
            "news_research",
            "fundamentals_research",
        ):
            expected_name, expected_input_schema_title = (
                _TRADINGAGENTS_LAUNCH_METADATA_BY_WORKFLOW_KEY[workflow_key]
            )
            _assert_tradingagents_preset_launchable(
                engine,
                package_id=package_id,
                workflow_key=workflow_key,
                expected_name=expected_name,
                expected_input_schema_title=expected_input_schema_title,
            )

        upgrade_legacy_schema(engine)
        with engine.connect() as connection:
            idempotent_row = (
                connection.execute(
                    text(
                        """
                    SELECT package.id AS package_id
                    FROM workflow_packages AS package
                    WHERE package.key = :package_key
                    """
                    ),
                    {"package_key": _TRADINGAGENTS_PRESET_KEY},
                )
                .mappings()
                .one()
            )
        assert idempotent_row["package_id"] == package_id
    finally:
        engine.dispose()


def test_init_db_seeds_digital_oracle_preset_without_secret_state(database_url: str) -> None:
    fixture_source = _DIGITAL_ORACLE_FIXTURE_PATH.read_text(encoding="utf-8")
    draft_fixture_source = _DIGITAL_ORACLE_DRAFT_FIXTURE_PATH.read_text(encoding="utf-8")
    preset_sql = _DIGITAL_ORACLE_PRESET_SQL_PATH.read_text(encoding="utf-8")
    assert "finance-owned" not in fixture_source
    assert "finance-owned" not in draft_fixture_source
    assert "INSERT INTO workflow_packages" in preset_sql
    assert "ON CONFLICT (key) DO UPDATE" in preset_sql
    assert "INSERT INTO model_connections" not in preset_sql
    assert "workflow_package_secret_bindings (" not in preset_sql
    assert "INSERT INTO runs" not in preset_sql

    init_db(database_url)
    engine = create_engine(database_url, future=True)
    fixture_compiled = _compile_fixture_artifacts(engine, fixture_source)
    expected_package_definition = cast(dict[str, object], fixture_compiled["packageDefinition"])
    expected_compiled_plan = cast(dict[str, object], fixture_compiled["compiledPlan"])
    expected_extension_dependencies = cast(
        list[dict[str, object]], fixture_compiled["extensionDependencies"]
    )

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
                        package.manifest_source,
                        package.manifest_hash,
                        package.package_definition,
                        package.compiled_plan,
                        package.compiled_hash,
                        package.extension_dependencies
                    FROM workflow_packages AS package
                    WHERE package.key = :package_key
                    """
                    ),
                    {"package_key": _DIGITAL_ORACLE_PRESET_KEY},
                )
                .mappings()
                .one()
            )
            model_connection_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections")
            ).scalar_one()
            non_empty_model_secret_count = connection.execute(
                text("SELECT COUNT(*) FROM model_connections WHERE secret_payload <> '{}'::jsonb")
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
            schedule_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM workflow_package_schedules
                    WHERE package_id = :package_id
                    """
                ),
                {"package_id": row["package_id"]},
            ).scalar_one()
            run_count = connection.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()

        assert row["key"] == _DIGITAL_ORACLE_PRESET_KEY
        assert row["name"] == "Digital Oracle Researcher"
        assert (
            row["description"]
            == cast(dict[str, object], expected_package_definition["metadata"])["description"]
        )
        assert row["manifest_source"] == fixture_source
        assert row["manifest_hash"] == fixture_compiled["manifestHash"]
        assert row["compiled_hash"] == fixture_compiled["compiledHash"]
        assert row["package_definition"] == expected_package_definition
        assert row["compiled_plan"] == expected_compiled_plan
        assert row["extension_dependencies"] == expected_extension_dependencies
        assert expected_extension_dependencies == _DIGITAL_ORACLE_PRESET_EXTENSION_DEPENDENCIES

        serialized_preset = (
            fixture_source
            + json.dumps(row["package_definition"], sort_keys=True)
            + json.dumps(row["compiled_plan"], sort_keys=True)
        )
        for forbidden_value in (
            "finance-owned",
            "encrypted",
            "requiredBindings",
            "secretPayload",
            "secretRefs",
        ):
            assert forbidden_value not in serialized_preset
        assert re.search(r"\bsk-[A-Za-z0-9_-]{16,}", serialized_preset) is None
        assert model_connection_count == 0
        assert non_empty_model_secret_count == 0
        assert secret_binding_count == 0
        assert schedule_count == 0
        assert run_count == 0
    finally:
        engine.dispose()


def test_init_db_does_not_seed_tradingagents_preset_schedules(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            first_rows = _tradingagents_preset_schedule_rows(connection)
        assert first_rows == []

        init_db(database_url)

        with engine.connect() as connection:
            second_rows = _tradingagents_preset_schedule_rows(connection)
        assert second_rows == []
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
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, "
                    "input, status, total_tokens, inherited_tokens, executed_tokens, "
                    f"{run_cost_columns_sql}"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, "
                    "'{}'::jsonb, 'succeeded', 17, 5, 12, "
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
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(run_id),
                package=package,
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS ck_runs_target_kind"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT ck_runs_target_kind "
                "CHECK (target_kind IN ('agent', 'workflow', 'workflowPackage'))"
            )
            legacy_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, input, status, "
                    "total_tokens, inherited_tokens, executed_tokens, "
                    f"{run_cost_columns_sql}"
                    ") VALUES ("
                    "'workflow', 42, 'legacy_cost_workflow', 1, '{}'::jsonb, 'succeeded', "
                    "31, 11, 20, "
                    f"{run_cost_placeholders_sql}"
                    ") RETURNING id"
                ),
                {
                    f"run_legacy_amount_{index}": index + 1
                    for index, _ in enumerate(_RUN_COST_COLUMNS)
                },
            ).scalar_one()
            _insert_report_upgrade_row(
                connection,
                slug="legacy_cost_agent_memory_report",
                source="agent",
                metadata=_agent_memory_report_metadata(runId=int(legacy_run_id)),
            )
            _insert_report_upgrade_row(
                connection,
                slug="legacy_cost_external_agent_memory_report",
                source="external",
                metadata=_agent_memory_report_metadata(runId=int(legacy_run_id)),
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
                    "(SELECT COUNT(*) FROM run_workflow_package_snapshots), "
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
            legacy_report_counts = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM reports WHERE slug = 'legacy_cost_agent_memory_report'), "
                    "(SELECT COUNT(*) FROM reports WHERE slug = 'legacy_cost_external_agent_memory_report')"
                )
            ).one()

        assert runtime_counts == (1, 1, 1, 1)
        assert preserved_run == ("cost_package", "succeeded", 17)
        assert preserved_invocation == ("legacy_cost_agent", "succeeded", 19)
        assert legacy_report_counts == (0, 0)
        assert set(_RUN_COST_COLUMNS).isdisjoint(run_columns)
        assert _INVOCATION_COST_COLUMN not in invocation_columns
        assert set(_RUN_COST_CHECKS).isdisjoint(run_constraints)
        assert _INVOCATION_COST_CHECK not in invocation_constraints
    finally:
        engine.dispose()


def test_init_db_repairs_reports_columns_before_non_package_run_report_cleanup(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS ck_runs_target_kind"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT ck_runs_target_kind "
                "CHECK (target_kind IN ('agent', 'workflow', 'workflowPackage'))"
            )
            legacy_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, status, input"
                    ") VALUES ('workflow', 99, 'legacy_report_cleanup_workflow', 1, "
                    "'succeeded', '{}'::jsonb) RETURNING id"
                )
            ).scalar_one()
            _insert_report_upgrade_row(
                connection,
                slug="legacy_report_cleanup_agent_memory_report",
                source="external",
                metadata=_agent_memory_report_metadata(runId=int(legacy_run_id)),
            )
            connection.exec_driver_sql("ALTER TABLE reports DROP COLUMN metadata CASCADE")
            connection.exec_driver_sql("ALTER TABLE reports DROP COLUMN source CASCADE")

        init_db(database_url)

        inspector = inspect(engine)
        report_columns = {column["name"] for column in inspector.get_columns("reports")}
        assert {"source", "metadata"} <= report_columns
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
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, "
                    "status, input, started_at, finished_at, created_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, 'succeeded', '{}'::jsonb, "
                    "'2026-04-19T10:00:00Z', '2026-04-19T10:02:00Z', "
                    "'2026-04-19T09:59:00Z') RETURNING id"
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(succeeded_run_id),
                package=package,
            )
            running_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, "
                    "status, input, started_at, created_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, 'running', '{}'::jsonb, "
                    "'2026-04-19T11:00:00Z', '2026-04-19T10:59:00Z') RETURNING id"
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(running_run_id),
                package=package,
            )
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
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, input"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, '{}'::jsonb"
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


def test_init_db_repairs_run_scheduler_metadata_columns_and_indexes(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            package = _insert_representable_workflow_package(
                connection,
                key="scheduler_repair_package",
                workflow_key="scheduler_repair_workflow",
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, status, input
                    ) VALUES (
                        'workflowPackage', :package_id, :package_key, :target_version,
                        :package_id, :package_key, :workflow_key, 'queued', '{}'::jsonb
                    ) RETURNING id
                    """
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(run_id),
                package=package,
            )
            connection.exec_driver_sql(
                "DROP INDEX IF EXISTS uq_runs_running_serial_execution_scope"
            )
            for column_name in (
                "execution_scope_key",
                "concurrency_policy",
                "lease_owner",
                "lease_expires_at",
                "heartbeat_at",
                "attempt_count",
                "last_claimed_at",
            ):
                connection.exec_driver_sql(
                    f"ALTER TABLE runs DROP COLUMN IF EXISTS {column_name} CASCADE"
                )

        init_db(database_url)
        _assert_runtime_execution_table_shape(engine)
        with engine.connect() as connection:
            scheduler_row = connection.execute(
                text(
                    """
                    SELECT execution_scope_key, concurrency_policy, attempt_count,
                           lease_owner, lease_expires_at, heartbeat_at, last_claimed_at
                    FROM runs
                    WHERE id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).one()

        assert tuple(scheduler_row) == (
            "package:scheduler_repair_package",
            "serial",
            0,
            None,
            None,
            None,
            None,
        )
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
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, status, input"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, 'running', '{}'::jsonb"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(running_run_id),
                package=package,
            )
            failed_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, status, input, error"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, 'failed', "
                    "'{}'::jsonb, 'existing failure'"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(failed_run_id),
                package=package,
            )
            queued_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, status, input, started_at, finished_at"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, 'queued', "
                    "'{}'::jsonb, NULL, NULL"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(queued_run_id),
                package=package,
            )
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
                        model_id, reasoning_effort, protocol_profile, timeout_seconds, secret_payload,
                        {marker_column}, {suffix_column}, created_at, updated_at
                    ) VALUES (
                        :key, 'active', :name, '', 'https://api.openai.com/v1', NULL, NULL,
                        :model_id, 'medium', 'openai_responses', 60, CAST(:secret_payload AS jsonb),
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
                text("SELECT id, key, protocol_profile FROM model_connections ORDER BY id ASC")
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
            (1, "primary_openai", "openai_responses"),
            (2, "primary_openai_2", "openai_responses"),
            (3, "openai_gpt_4_1", "openai_responses"),
            (4, "model_connection_2026_default", "openai_responses"),
        ]
        assert model_connection_columns["key"]["nullable"] is False
        assert model_connection_columns["protocol_profile"]["nullable"] is False
        assert "api_style" not in model_connection_columns
        assert {"organization", "project"}.isdisjoint(model_connection_columns)
        assert set(_LEGACY_MODEL_CONNECTION_SECRET_METADATA_COLUMNS).isdisjoint(
            model_connection_columns
        )
        assert "ck_model_connections_protocol_profile" in model_connection_check_constraints
        assert "ck_model_connections_api_style" not in model_connection_check_constraints
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


def test_init_db_refuses_existing_reports_with_unknown_source(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE reports (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    slug VARCHAR(200) NOT NULL,
                    source VARCHAR(20) NOT NULL DEFAULT 'compiled',
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_reports_name UNIQUE (name),
                    CONSTRAINT uq_reports_slug UNIQUE (slug)
                )
                """
            )
            _insert_report_upgrade_row(
                connection,
                slug="unknown_source_report",
                source="wire",
                metadata={"tags": ["invalid"]},
            )

        with pytest.raises(RuntimeError) as error:
            init_db(database_url)

        message = str(error.value)
        assert "reports.source contains unsupported values: wire (1 rows)" in message
        assert "Expected one of: compiled, uploaded, external, agent" in message
        assert "without an explicit repair" in message
        with engine.connect() as connection:
            invalid_count = connection.execute(
                text("SELECT COUNT(*) FROM reports WHERE source = 'wire'")
            ).scalar_one()
        assert invalid_count == 1
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
    _assert_report_source_constraint(engine)
    _assert_invalid_report_source_rejected(engine, slug="invalid_after_agent_source_repair")


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
            {"extension_key": DIGITAL_ORACLE_EXTENSION_KEY, "enabled": True},
            {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY, "enabled": True},
        ]
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
        {"extension_key": DIGITAL_ORACLE_EXTENSION_KEY, "enabled": True},
        {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY, "enabled": False},
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
        {"extension_key": DIGITAL_ORACLE_EXTENSION_KEY, "enabled": True},
        {"extension_key": FINANCE_WORKSPACE_EXTENSION_KEY, "enabled": True},
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
            "surfaces": [
                "tool.signaldeck.finance.market_data.quote_lookup",
                "runtime.tool.signaldeck.finance.market_data.quote_lookup",
                100,
            ],
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
            package = _insert_representable_workflow_package(
                connection,
                key="legacy_snapshot_package",
                workflow_key="advisory_research",
            )
            run_id = connection.execute(
                text(
                    """
                    INSERT INTO runs (
                        target_kind, target_id, target_key, target_version,
                        workflow_package_id, workflow_package_key,
                        workflow_package_workflow_key, extension_snapshots, input, status
                    ) VALUES (
                        'workflowPackage', :package_id, :package_key, :target_version,
                        :package_id, :package_key, :workflow_key,
                        CAST(:snapshots AS JSONB), '{}'::jsonb, 'queued'
                    ) RETURNING id
                    """
                ),
                {**package, "snapshots": json.dumps(legacy_snapshots)},
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(run_id),
                package=package,
            )

        upgrade_legacy_schema(engine)

        inspector = inspect(engine)
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        assert "extension_dependencies" in run_columns
        assert "extension_snapshots" not in run_columns
        assert REMOVED_RUN_PROVENANCE_COLUMNS.isdisjoint(run_columns)

        with engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                    SELECT extension_dependencies
                    FROM runs
                    WHERE target_key = 'legacy_snapshot_package'
                    """
                    )
                )
                .mappings()
                .one()
            )

        assert row["extension_dependencies"] == [
            {
                "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
                "surfaces": [
                    "tool.signaldeck.finance.market_data.quote_lookup",
                    "runtime.tool.signaldeck.finance.market_data.quote_lookup",
                ],
                "fields": ["spec.capabilityProfiles.quote_tools.toolKeys[0]"],
            },
            {"extensionKey": "custom.extension", "surfaces": [], "fields": []},
        ]
    finally:
        engine.dispose()


def test_upgrade_legacy_schema_purges_pre_cutover_package_runs_snapshots_and_memory_reports(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS db_upgrade_markers")
            package = _insert_representable_workflow_package(
                connection,
                key="cleanup_order_package",
                workflow_key="cleanup_order_workflow",
            )
            snapshot_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, input, status"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, "
                    "CAST(:input_payload AS jsonb), 'succeeded'"
                    ") RETURNING id"
                ),
                {**package, "input_payload": json.dumps({"ticker": "MSFT"})},
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(snapshot_run_id),
                package=package,
                parameters={"ticker": "MSFT"},
            )
            stale_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, input, status"
                    ") VALUES ("
                    "'workflowPackage', :package_id, 'stale_without_snapshot', "
                    ":target_version, :package_id, 'stale_without_snapshot', "
                    ":workflow_key, '{}'::jsonb, 'succeeded'"
                    ") RETURNING id"
                ),
                package,
            ).scalar_one()
            for run_id, slug in (
                (snapshot_run_id, "agent_memory_pre_cutover_snapshot_run"),
                (stale_run_id, "agent_memory_pre_cutover_stale_run"),
            ):
                _insert_report_upgrade_row(
                    connection,
                    slug=slug,
                    source="agent",
                    metadata={"analysis": {"reviewType": "agent_memory", "runId": int(run_id)}},
                )

        upgrade_legacy_schema(engine)

        with engine.connect() as connection:
            package_run_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM runs
                    WHERE target_kind = 'workflowPackage'
                       OR workflow_package_id IS NOT NULL
                       OR workflow_package_key IS NOT NULL
                    """
                )
            ).scalar_one()
            snapshot_count = connection.execute(
                text("SELECT COUNT(*) FROM run_workflow_package_snapshots")
            ).scalar_one()
            memory_report_count = connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM reports
                    WHERE slug IN (
                        'agent_memory_pre_cutover_snapshot_run',
                        'agent_memory_pre_cutover_stale_run'
                    )
                    """
                )
            ).scalar_one()
            marker_count = connection.execute(
                text("SELECT COUNT(*) FROM db_upgrade_markers")
            ).scalar_one()

        assert package_run_count == 0
        assert snapshot_count == 0
        assert memory_report_count == 0
        assert marker_count == 1

        with engine.begin() as connection:
            post_cutover_run_id = connection.execute(
                text(
                    "INSERT INTO runs ("
                    "target_kind, target_id, target_key, target_version, "
                    "workflow_package_id, workflow_package_key, "
                    "workflow_package_workflow_key, input, status"
                    ") VALUES ("
                    "'workflowPackage', :package_id, :package_key, :target_version, "
                    ":package_id, :package_key, :workflow_key, "
                    "CAST(:input_payload AS jsonb), 'succeeded'"
                    ") RETURNING id"
                ),
                {**package, "input_payload": json.dumps({"ticker": "AAPL"})},
            ).scalar_one()
            _insert_run_workflow_package_snapshot(
                connection,
                run_id=int(post_cutover_run_id),
                package=package,
                parameters={"ticker": "AAPL"},
            )
            _insert_report_upgrade_row(
                connection,
                slug="agent_memory_post_cutover_run",
                source="agent",
                metadata={
                    "analysis": {
                        "reviewType": "agent_memory",
                        "runId": int(post_cutover_run_id),
                    }
                },
            )

        upgrade_legacy_schema(engine)

        with engine.connect() as connection:
            surviving_row = (
                connection.execute(
                    text(
                        """
                        SELECT run.id, snapshot.launch_parameters
                        FROM runs AS run
                        JOIN run_workflow_package_snapshots AS snapshot
                          ON snapshot.run_id = run.id
                        WHERE run.id = :run_id
                        """
                    ),
                    {"run_id": post_cutover_run_id},
                )
                .mappings()
                .one()
            )
            surviving_memory_count = connection.execute(
                text("SELECT COUNT(*) FROM reports WHERE slug = 'agent_memory_post_cutover_run'")
            ).scalar_one()

        assert surviving_row["launch_parameters"] == {"ticker": "AAPL"}
        assert surviving_memory_count == 1
    finally:
        engine.dispose()
