# ruff: noqa: E501
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import init_db
from app.db.upgrades import apply_startup_schema_repairs
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
SCHEDULE_TABLE_NAMES = {
    "workflow_package_schedules",
    "workflow_package_schedule_fires",
}
LIVE_AGENT_PLATFORM_TABLE_NAMES = AGENT_PLATFORM_TABLE_NAMES
LIVE_WORKFLOW_MEMORY_TABLE_NAMES = WORKFLOW_MEMORY_TABLE_NAMES
LIVE_SCHEDULE_TABLE_NAMES = SCHEDULE_TABLE_NAMES
_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE = (
    "Run marked as failed during startup recovery because the previous process exited while "
    "it was still running."
)
_AGENT_PLATFORM_PENDING_SKIP_MESSAGE = (
    "Runtime row skipped during startup recovery because the parent run failed before it started."
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
_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_DIGITAL_ORACLE_PRESET_KEY = "digital_oracle_researcher"
_TRADINGAGENTS_MACRO_PRESET_KEY = "tradingagents_advisory_research_macro"
_TRADINGAGENTS_MIXED_SIGNALS_PRESET_KEY = "tradingagents_advisory_research_mixed_signals"
_TRADINGAGENTS_MODEL_CONNECTION_KEY = "tradingagents_primary_model"
_TRADINGAGENTS_FIXTURE_PATH = (
    Path(__file__).parents[2] / "demo" / "tradingagents_advisory_research.yaml"
)
_DIGITAL_ORACLE_FIXTURE_PATH = Path(__file__).parents[2] / "demo" / "digital_oracle_researcher.yaml"
_TRADINGAGENTS_MACRO_FIXTURE_PATH = (
    Path(__file__).parents[2] / "demo" / "tradingagents_advisory_research_macro.yaml"
)
_TRADINGAGENTS_MIXED_SIGNALS_FIXTURE_PATH = (
    Path(__file__).parents[2] / "demo" / "tradingagents_advisory_research_mixed_signals.yaml"
)
_EXPECTED_PRESET_HASHES = {
    _DIGITAL_ORACLE_PRESET_KEY: (
        "9cdde0eaf311164747948b386c9901cd3a70c0ef981c8296e616c52e212ac0c4",
        "1a997fe3f393bdef1db33473c7241683ecbba6e5f266b3bc1b1960c4e5ba5ea4",
    ),
    _TRADINGAGENTS_MACRO_PRESET_KEY: (
        "09c79f75209be49c4745b548129df309c039d84894e3dc80e27d21eeae6812de",
        "43cf2f6e2890e15ab1d943636d08471d9013aa1c8435cacea496da930ff50865",
    ),
    _TRADINGAGENTS_MIXED_SIGNALS_PRESET_KEY: (
        "6b5e54a5bd3fc62d99aa6bec8d0be839f548d232e3e610535da3bc0d083ba92f",
        "59010485fc6eac23f94bb75777ae3fb3b920b5879738007f0dfd7ad58daa16fd",
    ),
}
_DIGITAL_ORACLE_PRESET_EXTENSION_DEPENDENCIES = [
    {
        "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
        "fields": [
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[0]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[1]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[2]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[3]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[4]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[5]",
            "spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[6]",
        ],
        "surfaces": [
            "runtime.tool.signaldeck.digital_oracle.cftc_positioning.lookup",
            "runtime.tool.signaldeck.digital_oracle.crypto_derivatives.lookup",
            "runtime.tool.signaldeck.digital_oracle.macro_rates.lookup",
            "runtime.tool.signaldeck.digital_oracle.market_sentiment.lookup",
            "runtime.tool.signaldeck.digital_oracle.options.lookup",
            "runtime.tool.signaldeck.digital_oracle.prediction_markets.lookup",
            "runtime.tool.signaldeck.digital_oracle.sec_filings.lookup",
            "tool.signaldeck.digital_oracle.cftc_positioning.lookup",
            "tool.signaldeck.digital_oracle.crypto_derivatives.lookup",
            "tool.signaldeck.digital_oracle.macro_rates.lookup",
            "tool.signaldeck.digital_oracle.market_sentiment.lookup",
            "tool.signaldeck.digital_oracle.options.lookup",
            "tool.signaldeck.digital_oracle.prediction_markets.lookup",
            "tool.signaldeck.digital_oracle.sec_filings.lookup",
        ],
    }
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
                    key, name, description, base_url, model_id,
                    reasoning_effort, protocol_profile, timeout_seconds, secret_payload,
                    created_at, updated_at
                ) VALUES (
                    :key, 'TradingAgents Primary Model', '', :base_url,
                    :model_id, 'medium', 'openai_responses', 60,
                    '{"apiKey":"sk-tradingagents-upgrade-test"}'::jsonb, NOW(), NOW()
                )
                ON CONFLICT (key) DO UPDATE SET
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
        "owner_type",
        "owner_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "namespace",
        "kind",
        "content_fingerprint",
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
    assert item_columns["content_fingerprint"]["nullable"] is False
    assert item_columns["owner_type"]["nullable"] is False
    assert item_columns["owner_id"]["nullable"] is False
    assert {
        "id",
        "proposal_id",
        "owner_type",
        "owner_id",
        "run_id",
        "invocation_id",
        "package_key",
        "workflow_key",
        "agent_key",
        "step_id",
        "namespace",
        "kind",
        "content_fingerprint",
        "idempotency_key",
        "content_json",
        "reason",
        "source_output_path",
        "detectors_json",
        "status",
        "created_at",
        "updated_at",
    } <= set(proposal_columns)
    assert proposal_columns["content_json"]["nullable"] is False
    assert proposal_columns["content_fingerprint"]["nullable"] is False
    assert proposal_columns["idempotency_key"]["nullable"] is False
    assert proposal_columns["owner_type"]["nullable"] is False
    assert proposal_columns["owner_id"]["nullable"] is False
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
        "owner_type",
        "owner_id",
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
    assert audit_columns["owner_type"]["nullable"] is False
    assert audit_columns["owner_id"]["nullable"] is False

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
        "owner_type",
        "owner_id",
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
    assert quarantine_columns["owner_type"]["nullable"] is False
    assert quarantine_columns["owner_id"]["nullable"] is False

    assert {
        "id",
        "consolidation_id",
        "owner_type",
        "owner_id",
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
    assert consolidation_columns["owner_type"]["nullable"] is False
    assert consolidation_columns["owner_id"]["nullable"] is False

    assert {
        "id",
        "checkpoint_id",
        "owner_type",
        "owner_id",
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
    assert checkpoint_columns["state_json"]["nullable"] is False
    assert checkpoint_columns["owner_type"]["nullable"] is False
    assert checkpoint_columns["owner_id"]["nullable"] is False

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
        "uq_workflow_memory_items_proposal_id"
        in unique_constraints_by_table["workflow_memory_items"]
    )
    assert (
        "uq_workflow_memory_proposals_proposal_id"
        in unique_constraints_by_table["workflow_memory_proposals"]
    )
    assert (
        "uq_workflow_memory_proposals_owner_idempotency_key"
        in unique_constraints_by_table["workflow_memory_proposals"]
    )
    proposal_unique_columns = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("workflow_memory_proposals")
        if constraint.get("name")
    }
    assert proposal_unique_columns["uq_workflow_memory_proposals_owner_idempotency_key"] == (
        "owner_type",
        "owner_id",
        "idempotency_key",
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
    proposal_indexes = {
        index["name"] for index in inspector.get_indexes("workflow_memory_proposals")
    }
    checkpoint_indexes = {index["name"] for index in inspector.get_indexes("workflow_checkpoints")}
    assert "ix_workflow_memory_items_retrieval_scope" in item_indexes
    assert "ix_workflow_memory_items_owner_run_invocation" in item_indexes
    assert "ix_workflow_memory_items_content_fingerprint" in item_indexes
    assert "ix_workflow_memory_proposals_scope" in proposal_indexes
    assert "ix_workflow_memory_proposals_owner_run_invocation" in proposal_indexes
    assert "ix_workflow_memory_proposals_content_fingerprint" in proposal_indexes
    assert "ix_workflow_checkpoints_scope_run_sequence" in checkpoint_indexes
    assert "ix_workflow_checkpoints_owner_run_invocation" in checkpoint_indexes

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
                    key, name, description, base_url, model_id, reasoning_effort,
                    protocol_profile, timeout_seconds, secret_payload, created_at, updated_at
                ) VALUES (
                    :key, :name, '', 'https://api.openai.com/v1', :model_id,
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
    assert (("source_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("lineage_root_run_id",), "runs", "SET NULL") in run_foreign_keys
    assert (("workflow_package_id",), "workflow_packages", "CASCADE") in run_foreign_keys
    assert (("schedule_id",), "workflow_package_schedules", "SET NULL") in run_foreign_keys
    assert (
        ("schedule_fire_id",),
        "workflow_package_schedule_fires",
        "SET NULL",
    ) in run_foreign_keys
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


def test_init_db_creates_current_runtime_tables(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        table_names = set(inspect(engine).get_table_names())
        assert LIVE_AGENT_PLATFORM_TABLE_NAMES <= table_names
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
                        kind, content_fingerprint, content_json, summary, provenance_json,
                        policy_status, lifecycle_status
                    ) VALUES (
                        'workflow-memory-upgrade-1', 'package-a', 'workflow-a', 'agent-a',
                        'step-a', 'research', 'fact',
                        '1111111111111111111111111111111111111111111111111111111111111111',
                        '{"value":"alpha"}'::jsonb, 'Workflow memory summary', '{}'::jsonb,
                        'committed', 'active'
                    ) RETURNING id
                    """
                )
            ).scalar_one()
            proposal_id = connection.execute(
                text(
                    """
                    INSERT INTO workflow_memory_proposals (
                        proposal_id, package_key, workflow_key, agent_key, step_id, namespace,
                        kind, content_fingerprint, idempotency_key, content_json, detectors_json,
                        status
                    ) VALUES (
                        'workflow-proposal-upgrade-1', 'package-a', 'workflow-a', 'agent-a',
                        'step-a', 'research', 'fact',
                        '1111111111111111111111111111111111111111111111111111111111111111',
                        '2222222222222222222222222222222222222222222222222222222222222222',
                        '{"value":"alpha"}'::jsonb, '{}'::jsonb, 'committed'
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


def test_init_db_scopes_proposal_idempotency_keys_by_owner(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        duplicate_key = "8" * 64
        with engine.begin() as connection:
            for owner_id in ("default", "other"):
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_memory_proposals (
                            proposal_id, owner_type, owner_id, package_key, workflow_key,
                            agent_key, step_id, namespace, kind, content_fingerprint,
                            idempotency_key, content_json, detectors_json, status
                        ) VALUES (
                            :proposal_id, 'local_user', :owner_id, 'package-a', 'workflow-a',
                            'agent-a', 'step-a', 'research', 'fact', :fingerprint,
                            :idempotency_key, '{"value":"owner"}'::jsonb, '{}'::jsonb,
                            'proposed'
                        )
                        """
                    ),
                    {
                        "fingerprint": "7" * 64,
                        "idempotency_key": duplicate_key,
                        "owner_id": owner_id,
                        "proposal_id": f"owner-idempotency-{owner_id}",
                    },
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO workflow_memory_proposals (
                            proposal_id, owner_type, owner_id, package_key, workflow_key,
                            agent_key, step_id, namespace, kind, content_fingerprint,
                            idempotency_key, content_json, detectors_json, status
                        ) VALUES (
                            'owner-idempotency-default-duplicate', 'local_user', 'default',
                            'package-a', 'workflow-a', 'agent-a', 'step-a', 'research', 'fact',
                            :fingerprint, :idempotency_key, '{"value":"owner"}'::jsonb,
                            '{}'::jsonb, 'proposed'
                        )
                        """
                    ),
                    {"fingerprint": "9" * 64, "idempotency_key": duplicate_key},
                )
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


def test_init_db_seeds_tradingagents_advisory_preset_without_secret_state(
    database_url: str,
) -> None:
    fixture_source = _TRADINGAGENTS_FIXTURE_PATH.read_text(encoding="utf-8")

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

        assert package_count == 4
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

        apply_startup_schema_repairs(engine)
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
        assert (row["manifest_hash"], row["compiled_hash"]) == _EXPECTED_PRESET_HASHES[
            _DIGITAL_ORACLE_PRESET_KEY
        ]
        assert row["package_definition"] == expected_package_definition
        assert row["compiled_plan"] == expected_compiled_plan
        assert row["extension_dependencies"] == expected_extension_dependencies
        assert expected_extension_dependencies[:1] == _DIGITAL_ORACLE_PRESET_EXTENSION_DEPENDENCIES
        assert {dependency["extensionKey"] for dependency in expected_extension_dependencies} == {
            DIGITAL_ORACLE_EXTENSION_KEY,
            FINANCE_WORKSPACE_EXTENSION_KEY,
        }

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


def test_init_db_seeds_macro_and_mixed_signal_presets_with_expected_boundaries(
    database_url: str,
) -> None:
    preset_expectations = {
        _TRADINGAGENTS_MACRO_PRESET_KEY: (
            _TRADINGAGENTS_MACRO_FIXTURE_PATH,
            {FINANCE_WORKSPACE_EXTENSION_KEY},
            set(),
        ),
        _TRADINGAGENTS_MIXED_SIGNALS_PRESET_KEY: (
            _TRADINGAGENTS_MIXED_SIGNALS_FIXTURE_PATH,
            {FINANCE_WORKSPACE_EXTENSION_KEY, DIGITAL_ORACLE_EXTENSION_KEY},
            {
                "signaldeck.digital_oracle.macro_rates.lookup",
                "signaldeck.digital_oracle.prediction_markets.lookup",
            },
        ),
    }

    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        for package_key, (
            fixture_path,
            expected_extension_keys,
            expected_digital_tool_keys,
        ) in preset_expectations.items():
            fixture_source = fixture_path.read_text(encoding="utf-8")
            fixture_compiled = _compile_fixture_artifacts(engine, fixture_source)
            expected_package_definition = cast(
                dict[str, object], fixture_compiled["packageDefinition"]
            )
            expected_compiled_plan = cast(dict[str, object], fixture_compiled["compiledPlan"])
            expected_extension_dependencies = cast(
                list[dict[str, object]], fixture_compiled["extensionDependencies"]
            )

            with engine.connect() as connection:
                row = (
                    connection.execute(
                        text(
                            """
                        SELECT
                            package.id AS package_id,
                            package.key,
                            package.name,
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
                        {"package_key": package_key},
                    )
                    .mappings()
                    .one()
                )
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

            assert row["key"] == package_key
            assert row["manifest_source"] == fixture_source
            assert row["manifest_hash"] == fixture_compiled["manifestHash"]
            assert row["compiled_hash"] == fixture_compiled["compiledHash"]
            assert (row["manifest_hash"], row["compiled_hash"]) == _EXPECTED_PRESET_HASHES[
                package_key
            ]
            assert row["package_definition"] == expected_package_definition
            assert row["compiled_plan"] == expected_compiled_plan
            assert row["extension_dependencies"] == expected_extension_dependencies
            assert {
                dependency["extensionKey"] for dependency in expected_extension_dependencies
            } == expected_extension_keys

            serialized_preset = (
                fixture_source
                + json.dumps(row["package_definition"], sort_keys=True)
                + json.dumps(row["compiled_plan"], sort_keys=True)
            )
            assert "mcp.packagePrivate.web_search_exa" in json.dumps(
                expected_extension_dependencies,
                sort_keys=True,
            )
            assert {
                tool_key
                for tool_key in (
                    "signaldeck.digital_oracle.macro_rates.lookup",
                    "signaldeck.digital_oracle.prediction_markets.lookup",
                    "signaldeck.digital_oracle.sec_filings.lookup",
                    "signaldeck.digital_oracle.market_sentiment.lookup",
                )
                if tool_key in serialized_preset
            } == expected_digital_tool_keys
            assert secret_binding_count == 0
            assert run_count == 0
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


def test_init_db_fresh_schema_has_flexible_model_connection_reasoning_effort(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        model_connection_columns = {
            column["name"]: column for column in inspect(engine).get_columns("model_connections")
        }
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


def test_init_db_creates_extension_state_table_and_default_row(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        columns = {column["name"]: column for column in inspector.get_columns("extension_states")}
        primary_key = inspector.get_pk_constraint("extension_states")

        assert "extension_states" in table_names
        assert set(columns) == {"extension_key", "enabled"}
        assert primary_key["constrained_columns"] == ["extension_key"]
        assert columns["extension_key"]["nullable"] is False
        assert columns["enabled"]["nullable"] is False

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


def test_startup_schema_repairs_add_run_extension_dependencies_column(
    database_url: str,
) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE runs DROP COLUMN extension_dependencies")
        apply_startup_schema_repairs(engine)

        inspector = inspect(engine)
        run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
        assert "extension_dependencies" in run_columns
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
