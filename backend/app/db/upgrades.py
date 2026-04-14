from __future__ import annotations

import json
import re
from importlib import import_module
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.validation import validate_supported_database_engine

_OBSOLETE_TABLES = (
    "stock_analysis_versions",
    "stock_analysis_responses",
    "stock_analysis_requests",
    "stock_analysis_runs",
    "stock_analysis_conversations",
    "portfolio_stock_analysis_settings",
    "prompt_templates",
    "user_snippets",
    "llm_configs",
)
_LEGACY_SLUG_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_LEGACY_SLUG_DUPLICATE_UNDERSCORES_RE = re.compile(r"_+")
_BACKTEST_SNAPSHOT_EXECUTION_MODE_DEFAULT = "structured_output"
_BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT = "not_required"
_RUNTIME_V2_TABLE_SPECS = (
    ("agent_specs", "app.models.agent_spec", "AgentSpec"),
    ("workflow_specs", "app.models.workflow_spec", "WorkflowSpec"),
    ("persona_profiles", "app.models.persona_profile", "PersonaProfile"),
    (
        "capability_registry_entries",
        "app.models.capability_registry_entry",
        "CapabilityRegistryEntry",
    ),
    ("runtime_runs", "app.models.runtime_run", "RuntimeRun"),
    ("runtime_trace_events", "app.models.runtime_trace_event", "RuntimeTraceEvent"),
    ("runtime_approvals", "app.models.runtime_approval", "RuntimeApproval"),
    ("runtime_checkpoints", "app.models.runtime_checkpoint", "RuntimeCheckpoint"),
    ("runtime_run_artifacts", "app.models.runtime_run_artifact", "RuntimeRunArtifact"),
    (
        "persona_projection_events",
        "app.models.persona_projection_event",
        "PersonaProjectionEvent",
    ),
    ("runtime_control_flags", "app.models.runtime_control_flag", "RuntimeControlFlag"),
    (
        "runtime_flag_change_events",
        "app.models.runtime_flag_change_event",
        "RuntimeFlagChangeEvent",
    ),
)


def normalize_legacy_portfolio_slug(name: str) -> str:
    normalized = _LEGACY_SLUG_INVALID_CHARS_RE.sub("_", name.strip().lower())
    normalized = _LEGACY_SLUG_DUPLICATE_UNDERSCORES_RE.sub("_", normalized).strip("_")
    if not normalized:
        normalized = "portfolio"
    if not normalized[0].isalpha():
        normalized = f"portfolio_{normalized}"
    return normalized


def build_unique_legacy_portfolio_slug(base_slug: str, used_slugs: set[str]) -> str:
    suffix = ""
    sequence = 2

    while True:
        max_base_length = 100 - len(suffix)
        trimmed_base = base_slug[:max_base_length].rstrip("_")
        if not trimmed_base:
            trimmed_base = "portfolio"[:max_base_length].rstrip("_") or "p"

        candidate = f"{trimmed_base}{suffix}"
        if candidate not in used_slugs:
            used_slugs.add(candidate)
            return candidate

        suffix = f"_{sequence}"
        sequence += 1


def _normalize_legacy_snapshot_version(value: object) -> int:
    if isinstance(value, int):
        return value if value > 0 else 1

    digits = re.sub(r"\D", "", str(value or "").strip())
    if not digits:
        return 1
    normalized = int(digits)
    return normalized if normalized > 0 else 1


def _ensure_json_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_legacy_snapshot_execution_mode(value: object) -> str:
    normalized = str(value or "").strip()
    return normalized or _BACKTEST_SNAPSHOT_EXECUTION_MODE_DEFAULT


def _normalize_legacy_snapshot_approval_trace(value: object) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or _BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT
    return _BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT


def _migrate_legacy_builtin_versions(snapshot_payload: dict[str, Any]) -> list[dict[str, Any]]:
    explicit_versions = snapshot_payload.get("resolved_builtin_versions")
    if isinstance(explicit_versions, list):
        return explicit_versions

    migrated: list[dict[str, Any]] = []
    for item in _ensure_json_list(snapshot_payload.get("built_in_revisions")):
        if not isinstance(item, str):
            continue
        canonical_target_id = item if item.startswith("builtin:") else f"builtin:{item}"
        migrated.append(
            {
                "canonical_target_id": canonical_target_id,
                "handle": canonical_target_id.split(":", 1)[1],
                "revision": 1,
            }
        )
    return migrated


def _migrate_legacy_version_entries(
    value: object,
    *,
    id_field: str,
) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []

    migrated: list[dict[str, Any]] = []
    for canonical_target_id, version in sorted(value.items(), key=lambda item: str(item[0])):
        migrated.append(
            {
                "canonical_target_id": str(canonical_target_id),
                id_field: None,
                "version": _normalize_legacy_snapshot_version(version),
            }
        )
    return migrated


def _upgrade_backtest_orchestration_snapshots(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {
        column["name"] for column in inspector.get_columns("backtest_orchestration_snapshots")
    }

    required_columns = {
        "prompt_report_slug": "VARCHAR(200)",
        "orchestration_pattern_key": "VARCHAR(120)",
        "pattern_policy_version": "INTEGER",
        "entry_prompt_hash": "VARCHAR(64)",
        "full_user_prompt_hash": "VARCHAR(64)",
        "execution_mode": (f"VARCHAR(40) DEFAULT '{_BACKTEST_SNAPSHOT_EXECUTION_MODE_DEFAULT}'"),
        "resolved_mentions": "JSONB DEFAULT '[]'::jsonb",
        "mentioned_target_outputs": "JSONB DEFAULT '[]'::jsonb",
        "resolved_builtin_versions": "JSONB DEFAULT '[]'::jsonb",
        "resolved_role_versions": "JSONB DEFAULT '[]'::jsonb",
        "resolved_character_versions": "JSONB DEFAULT '[]'::jsonb",
        "resolved_bundle_versions": "JSONB DEFAULT '[]'::jsonb",
        "resolved_tool_versions": "JSONB DEFAULT '[]'::jsonb",
        "resolved_connector_versions": "JSONB DEFAULT '[]'::jsonb",
        "tool_call_trace": "JSONB DEFAULT '[]'::jsonb",
        "approval_trace": (
            f"JSONB DEFAULT '\"{_BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT}\"'::jsonb"
        ),
    }

    with engine.begin() as connection:
        for column_name, column_ddl in required_columns.items():
            if column_name not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE backtest_orchestration_snapshots ADD COLUMN {column_name} "
                    f"{column_ddl}"
                )

    if "snapshot" in columns:
        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, snapshot FROM backtest_orchestration_snapshots ORDER BY id")
            ).mappings()
            for row in rows:
                snapshot_payload = row["snapshot"] if isinstance(row["snapshot"], dict) else {}
                connection.execute(
                    text(
                        """
                        UPDATE backtest_orchestration_snapshots
                        SET prompt_report_slug = :prompt_report_slug,
                            orchestration_pattern_key = :orchestration_pattern_key,
                            pattern_policy_version = :pattern_policy_version,
                            entry_prompt_hash = :entry_prompt_hash,
                            full_user_prompt_hash = :full_user_prompt_hash,
                            execution_mode = :execution_mode,
                            resolved_mentions = CAST(:resolved_mentions AS JSONB),
                            mentioned_target_outputs = CAST(:mentioned_target_outputs AS JSONB),
                            resolved_builtin_versions = CAST(:resolved_builtin_versions AS JSONB),
                            resolved_role_versions = CAST(:resolved_role_versions AS JSONB),
                            resolved_character_versions =
                                CAST(:resolved_character_versions AS JSONB),
                            resolved_bundle_versions =
                                CAST(:resolved_bundle_versions AS JSONB),
                            resolved_tool_versions = CAST(:resolved_tool_versions AS JSONB),
                            resolved_connector_versions =
                                CAST(:resolved_connector_versions AS JSONB),
                            tool_call_trace = CAST(:tool_call_trace AS JSONB),
                            approval_trace = CAST(:approval_trace AS JSONB)
                        WHERE id = :snapshot_id
                        """
                    ),
                    {
                        "snapshot_id": row["id"],
                        "prompt_report_slug": str(snapshot_payload.get("prompt_report_slug") or ""),
                        "orchestration_pattern_key": str(
                            snapshot_payload.get("orchestration_pattern_key")
                            or "seeded_internal_backtest_v1"
                        ),
                        "pattern_policy_version": _normalize_legacy_snapshot_version(
                            snapshot_payload.get("pattern_policy_version")
                        ),
                        "entry_prompt_hash": str(snapshot_payload.get("entry_prompt_hash") or ""),
                        "full_user_prompt_hash": str(
                            snapshot_payload.get("full_user_prompt_hash") or ""
                        ),
                        "execution_mode": _normalize_legacy_snapshot_execution_mode(
                            snapshot_payload.get("execution_mode")
                        ),
                        "resolved_mentions": json.dumps(
                            _ensure_json_list(snapshot_payload.get("resolved_mentions"))
                        ),
                        "mentioned_target_outputs": json.dumps(
                            _ensure_json_list(snapshot_payload.get("mentioned_target_outputs"))
                        ),
                        "resolved_builtin_versions": json.dumps(
                            _migrate_legacy_builtin_versions(snapshot_payload)
                        ),
                        "resolved_role_versions": json.dumps(
                            _migrate_legacy_version_entries(
                                snapshot_payload.get("resolved_role_versions"),
                                id_field="role_id",
                            )
                        ),
                        "resolved_character_versions": json.dumps(
                            _migrate_legacy_version_entries(
                                snapshot_payload.get("resolved_character_versions"),
                                id_field="character_id",
                            )
                        ),
                        "resolved_bundle_versions": json.dumps(
                            _ensure_json_list(snapshot_payload.get("resolved_bundle_versions"))
                        ),
                        "resolved_tool_versions": json.dumps(
                            _ensure_json_list(snapshot_payload.get("resolved_tool_versions"))
                        ),
                        "resolved_connector_versions": json.dumps(
                            _ensure_json_list(snapshot_payload.get("resolved_connector_versions"))
                        ),
                        "tool_call_trace": json.dumps(
                            _ensure_json_list(snapshot_payload.get("tool_call_trace"))
                        ),
                        "approval_trace": json.dumps(
                            _normalize_legacy_snapshot_approval_trace(
                                snapshot_payload.get("approval_trace")
                            )
                        ),
                    },
                )

            # Keep legacy snapshot columns in place during the rollback window.
            # The explicit columns become the active compatibility surface, but
            # destructive cleanup must wait until rollback compatibility is removed.

    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            UPDATE backtest_orchestration_snapshots
            SET prompt_report_slug = COALESCE(prompt_report_slug, ''),
                orchestration_pattern_key = COALESCE(
                    orchestration_pattern_key,
                    'seeded_internal_backtest_v1'
                ),
                pattern_policy_version = COALESCE(pattern_policy_version, 1),
                entry_prompt_hash = COALESCE(entry_prompt_hash, ''),
                full_user_prompt_hash = COALESCE(full_user_prompt_hash, ''),
                execution_mode = COALESCE(
                    execution_mode,
                    '{_BACKTEST_SNAPSHOT_EXECUTION_MODE_DEFAULT}'
                ),
                resolved_mentions = COALESCE(resolved_mentions, '[]'::jsonb),
                mentioned_target_outputs = COALESCE(mentioned_target_outputs, '[]'::jsonb),
                resolved_builtin_versions = COALESCE(resolved_builtin_versions, '[]'::jsonb),
                resolved_role_versions = COALESCE(resolved_role_versions, '[]'::jsonb),
                resolved_character_versions = COALESCE(resolved_character_versions, '[]'::jsonb),
                resolved_bundle_versions = COALESCE(resolved_bundle_versions, '[]'::jsonb),
                resolved_tool_versions = COALESCE(resolved_tool_versions, '[]'::jsonb),
                resolved_connector_versions = COALESCE(
                    resolved_connector_versions,
                    '[]'::jsonb
                ),
                tool_call_trace = COALESCE(tool_call_trace, '[]'::jsonb),
                approval_trace = COALESCE(
                    approval_trace,
                    '"{_BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT}"'::jsonb
                )
            """
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN prompt_report_slug SET DEFAULT ''"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN orchestration_pattern_key SET DEFAULT "
            "'seeded_internal_backtest_v1'"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN pattern_policy_version SET DEFAULT 1"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN execution_mode SET DEFAULT "
            f"'{_BACKTEST_SNAPSHOT_EXECUTION_MODE_DEFAULT}'"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_mentions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN mentioned_target_outputs SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_builtin_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_role_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_character_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_bundle_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_tool_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_connector_versions SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN tool_call_trace SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN approval_trace SET DEFAULT "
            f"'\"{_BACKTEST_SNAPSHOT_APPROVAL_TRACE_DEFAULT}\"'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN prompt_report_slug SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN orchestration_pattern_key SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN pattern_policy_version SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots ALTER COLUMN execution_mode SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN entry_prompt_hash SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN full_user_prompt_hash SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_mentions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN mentioned_target_outputs SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_builtin_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_role_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_character_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_bundle_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_tool_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots "
            "ALTER COLUMN resolved_connector_versions SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots ALTER COLUMN tool_call_trace SET NOT NULL"
        )
        connection.exec_driver_sql(
            "ALTER TABLE backtest_orchestration_snapshots ALTER COLUMN approval_trace SET NOT NULL"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_backtest_orchestration_snapshots_backtest_id "
            "ON backtest_orchestration_snapshots (backtest_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_backtest_orchestration_snapshots_cycle_date "
            "ON backtest_orchestration_snapshots (cycle_date)"
        )

    unique_constraints = {
        constraint["name"]
        for constraint in inspect(engine).get_unique_constraints("backtest_orchestration_snapshots")
    }
    if "uq_backtest_orchestration_snapshots_cycle" not in unique_constraints:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE backtest_orchestration_snapshots "
                "ADD CONSTRAINT uq_backtest_orchestration_snapshots_cycle "
                "UNIQUE (backtest_id, cycle_date)"
            )


def _ensure_runtime_v2_tables(engine: Engine, table_names: set[str]) -> None:
    for table_name, module_path, model_name in _RUNTIME_V2_TABLE_SPECS:
        if table_name in table_names:
            continue
        model = getattr(import_module(module_path), model_name)
        model.__table__.create(engine, checkfirst=True)
        table_names.add(table_name)


def _upgrade_persona_profiles_table(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "persona_profiles" not in table_names:
        return

    persona_columns = {column["name"] for column in inspector.get_columns("persona_profiles")}
    persona_check_constraints = {
        constraint.get("name") for constraint in inspector.get_check_constraints("persona_profiles")
    }

    with engine.begin() as connection:
        if "legacy_entity_type" not in persona_columns:
            connection.exec_driver_sql(
                "ALTER TABLE persona_profiles ADD COLUMN legacy_entity_type VARCHAR(20)"
            )
        if "legacy_entity_key" not in persona_columns:
            connection.exec_driver_sql(
                "ALTER TABLE persona_profiles ADD COLUMN legacy_entity_key VARCHAR(120)"
            )

    if "ck_persona_profiles_legacy_entity_type" not in persona_check_constraints:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE persona_profiles ADD CONSTRAINT "
                "ck_persona_profiles_legacy_entity_type "
                "CHECK (legacy_entity_type IS NULL OR legacy_entity_type IN ('role', 'character'))"
            )

    if "ck_persona_profiles_legacy_entity_pair" not in persona_check_constraints:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE persona_profiles ADD CONSTRAINT "
                "ck_persona_profiles_legacy_entity_pair "
                "CHECK ((legacy_entity_type IS NULL AND legacy_entity_key IS NULL) OR "
                "(legacy_entity_type IS NOT NULL AND legacy_entity_key IS NOT NULL))"
            )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_persona_profiles_legacy_entity "
            "ON persona_profiles (legacy_entity_type, legacy_entity_key)"
        )


def upgrade_legacy_schema(engine: Engine) -> None:
    validate_supported_database_engine(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "backtest_orchestration_snapshots" not in table_names:
        BacktestOrchestrationSnapshot = import_module(
            "app.models.backtest_orchestration_snapshot"
        ).BacktestOrchestrationSnapshot
        BacktestOrchestrationSnapshot.__table__.create(engine, checkfirst=True)
        table_names.add("backtest_orchestration_snapshots")

    if "backtest_orchestration_snapshots" in table_names:
        _upgrade_backtest_orchestration_snapshots(engine)

    _ensure_runtime_v2_tables(engine, table_names)
    _upgrade_persona_profiles_table(engine)

    if "portfolios" in table_names:
        portfolio_columns = {column["name"] for column in inspector.get_columns("portfolios")}
        if "slug" not in portfolio_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE portfolios ADD COLUMN slug VARCHAR(100)")
                legacy_portfolios = connection.exec_driver_sql(
                    "SELECT id, name FROM portfolios ORDER BY id"
                ).all()
                used_slugs: set[str] = set()
                for portfolio_id, name in legacy_portfolios:
                    connection.execute(
                        text("UPDATE portfolios SET slug = :slug WHERE id = :portfolio_id"),
                        {
                            "slug": build_unique_legacy_portfolio_slug(
                                normalize_legacy_portfolio_slug(name), used_slugs
                            ),
                            "portfolio_id": portfolio_id,
                        },
                    )
                connection.exec_driver_sql("ALTER TABLE portfolios ALTER COLUMN slug SET NOT NULL")
                connection.exec_driver_sql(
                    "ALTER TABLE portfolios ADD CONSTRAINT uq_portfolios_slug UNIQUE (slug)"
                )

    if "balances" in table_names:
        balance_columns = {column["name"] for column in inspector.get_columns("balances")}
        if "operation_type" not in balance_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE balances ADD COLUMN operation_type VARCHAR")
                connection.exec_driver_sql(
                    "UPDATE balances SET operation_type = 'DEPOSIT' WHERE operation_type IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE balances ALTER COLUMN operation_type SET NOT NULL"
                )

    if "trading_operations" in table_names:
        trading_operation_columns = {
            column["name"] for column in inspector.get_columns("trading_operations")
        }
        if "backtest_id" not in trading_operation_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE trading_operations "
                    "ADD COLUMN backtest_id INTEGER REFERENCES backtests(id) ON DELETE CASCADE"
                )

    if "backtests" in table_names:
        backtest_columns = {column["name"] for column in inspector.get_columns("backtests")}
        backtest_indexes = {index["name"] for index in inspector.get_indexes("backtests")}
        if "orchestration_pattern_key" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN orchestration_pattern_key "
                    "VARCHAR(120) DEFAULT 'seeded_internal_backtest_v1'"
                )
                connection.exec_driver_sql(
                    "UPDATE backtests "
                    "SET orchestration_pattern_key = 'seeded_internal_backtest_v1' "
                    "WHERE orchestration_pattern_key IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ALTER COLUMN orchestration_pattern_key SET NOT NULL"
                )
        if "launch_mode" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN launch_mode VARCHAR(30)"
                )
        if "workflow_spec_key" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN workflow_spec_key VARCHAR(120)"
                )
        if "workflow_spec_version" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN workflow_spec_version INTEGER"
                )
        if "execution_owner" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN execution_owner VARCHAR(20)"
                )
        if "current_run_id" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN current_run_id "
                    "INTEGER REFERENCES runtime_runs(id) ON DELETE SET NULL"
                )
        if "last_completed_run_id" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN last_completed_run_id "
                    "INTEGER REFERENCES runtime_runs(id) ON DELETE SET NULL"
                )
        if "launch_mode_classified_at" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN launch_mode_classified_at TIMESTAMPTZ"
                )
        if "launch_mode_classified_by" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN launch_mode_classified_by VARCHAR(120)"
                )
        if "launch_mode_classification_note" not in backtest_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE backtests ADD COLUMN launch_mode_classification_note TEXT"
                )
        if "ix_backtests_execution_owner" not in backtest_indexes:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE INDEX ix_backtests_execution_owner ON backtests (execution_owner)"
                )
        if "ix_backtests_current_run_id" not in backtest_indexes:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE INDEX ix_backtests_current_run_id ON backtests (current_run_id)"
                )
        if "ix_backtests_last_completed_run_id" not in backtest_indexes:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "CREATE INDEX ix_backtests_last_completed_run_id "
                    "ON backtests (last_completed_run_id)"
                )

    if "reports" in table_names:
        report_columns = {column["name"] for column in inspector.get_columns("reports")}
        if "slug" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE reports ADD COLUMN slug VARCHAR(200)")
                connection.exec_driver_sql("UPDATE reports SET slug = name WHERE slug IS NULL")
                connection.exec_driver_sql("ALTER TABLE reports ALTER COLUMN slug SET NOT NULL")
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD CONSTRAINT uq_reports_slug UNIQUE (slug)"
                )
        if "source" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD COLUMN source VARCHAR(20) DEFAULT 'compiled' NOT NULL"
                )
        if "metadata" not in report_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE reports ADD COLUMN metadata JSONB DEFAULT '{}' NOT NULL"
                )

    if "market_quotes" in table_names:
        market_quote_columns = {column["name"] for column in inspector.get_columns("market_quotes")}
        if "name" not in market_quote_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE market_quotes ADD COLUMN name VARCHAR(255)")

    if "orchestration_roles" not in table_names:
        OrchestrationRole = import_module("app.models.orchestration_role").OrchestrationRole
        OrchestrationRole.__table__.create(engine, checkfirst=True)
        table_names.add("orchestration_roles")

    if "orchestration_roles" in table_names:
        role_columns = {
            column["name"] for column in inspect(engine).get_columns("orchestration_roles")
        }
        role_unique_constraints = {
            constraint.get("name")
            for constraint in inspect(engine).get_unique_constraints("orchestration_roles")
        }
        if "version" not in role_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ADD COLUMN version INTEGER"
                )
                connection.exec_driver_sql(
                    "UPDATE orchestration_roles SET version = 1 WHERE version IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ALTER COLUMN version SET DEFAULT 1"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ALTER COLUMN version SET NOT NULL"
                )
        if "capability_bundle_keys" not in role_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ADD COLUMN capability_bundle_keys "
                    "JSONB DEFAULT '[]'::jsonb"
                )
                connection.exec_driver_sql(
                    "UPDATE orchestration_roles SET capability_bundle_keys = '[]'::jsonb "
                    "WHERE capability_bundle_keys IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ALTER COLUMN capability_bundle_keys "
                    "SET NOT NULL"
                )
        if "uq_orchestration_roles_name" not in role_unique_constraints:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_roles ADD CONSTRAINT "
                    "uq_orchestration_roles_name UNIQUE (name)"
                )

    if "orchestration_characters" not in table_names:
        OrchestrationCharacter = import_module(
            "app.models.orchestration_character"
        ).OrchestrationCharacter
        OrchestrationCharacter.__table__.create(engine, checkfirst=True)
        table_names.add("orchestration_characters")

    if "orchestration_characters" in table_names:
        character_columns = {
            column["name"] for column in inspect(engine).get_columns("orchestration_characters")
        }
        if "version" not in character_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_characters ADD COLUMN version INTEGER"
                )
                connection.exec_driver_sql(
                    "UPDATE orchestration_characters SET version = 1 WHERE version IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_characters ALTER COLUMN version SET DEFAULT 1"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_characters ALTER COLUMN version SET NOT NULL"
                )
        if "capability_bundle_keys" not in character_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_characters ADD COLUMN capability_bundle_keys "
                    "JSONB DEFAULT '[]'::jsonb"
                )
                connection.exec_driver_sql(
                    "UPDATE orchestration_characters SET capability_bundle_keys = '[]'::jsonb "
                    "WHERE capability_bundle_keys IS NULL"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE orchestration_characters ALTER COLUMN capability_bundle_keys "
                    "SET NOT NULL"
                )

    # Intentionally retain legacy optional tables during the rollback window.
    # Startup upgrades stay additive/non-destructive until compatibility removal is approved.
