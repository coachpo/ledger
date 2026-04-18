from __future__ import annotations

import re
from importlib import import_module

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.validation import validate_supported_database_engine
from app.services.runtime_seed_catalog import (
    SEEDED_AGENT_SPECS,
    SEEDED_BUILTIN_SPECS,
    SEEDED_CAPABILITY_BUNDLE_SPECS,
    SEEDED_CONNECTOR_SPECS,
    SEEDED_TOOL_SPECS,
)

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
_SEEDED_RUNTIME_VERSION = 1
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
)

_LEGACY_SEEDED_AGENT_INSTRUCTION_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "decision_writer": (
        "Render the final backtest analysis report and translate reviewed "
        "analyses into Ledger trade decisions.",
    ),
}

_SEEDED_AGENT_INSTRUCTION_BY_KEY: dict[str, str] = {
    agent.key: agent.system_prompt for agent in SEEDED_AGENT_SPECS
}

_LEGACY_SEEDED_PERSONA_DESCRIPTION_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "builtin:librarian": ("Research and retrieve supporting context for a backtest analysis.",),
    "builtin:explore": (
        "Inspect the current backtest state and summarize relevant findings.",
        "Inspect the current backtest context and summarize relevant findings.",
    ),
}

_SEEDED_BUILTIN_DESCRIPTION_BY_KEY: dict[str, str] = {
    builtin.canonical_target_id: builtin.description for builtin in SEEDED_BUILTIN_SPECS
}

_LEGACY_SEEDED_CAPABILITY_DESCRIPTION_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "ledger.report_lookup": (
        "Read report content by exact slug.",
        "Read frozen report content by slug.",
    ),
    "ledger.orchestration_catalog_lookup": (
        "Read orchestration catalog data.",
        "Read frozen orchestration catalog data.",
    ),
    "ledger.cycle_context_lookup": (
        "Read prepared cycle context artifacts.",
        "Read frozen cycle context artifacts.",
        "Read prepared cycle prompt and runtime artifacts from the historical "
        "simulation execution path.",
    ),
    "builtin.librarian_context": ("Seed-owned bundle ref for backtest research context lookups.",),
    "builtin.explore_context": (
        "Seed-owned bundle ref for backtest-oriented cycle context lookups.",
    ),
    "ledger.mcp.market_data": (
        "Phase-3 placeholder for a backtest-owned market-data MCP connector.",
        "Read trusted market data connector output.",
    ),
    "ledger.mcp.company_filings": (
        "Phase-3 placeholder for a backtest-owned filings MCP connector.",
        "Read trusted company filings connector output.",
    ),
}

_SEEDED_CAPABILITY_DESCRIPTION_BY_KEY: dict[str, str] = {
    **{tool.tool_id: tool.description for tool in SEEDED_TOOL_SPECS},
    **{bundle.bundle_key: bundle.description for bundle in SEEDED_CAPABILITY_BUNDLE_SPECS},
    **{connector.connector_id: connector.description for connector in SEEDED_CONNECTOR_SPECS},
}


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


def _upgrade_runtime_seed_description_compatibility(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as connection:
        if "agent_specs" in table_names:
            for (
                key,
                legacy_instructions,
            ) in _LEGACY_SEEDED_AGENT_INSTRUCTION_COMPATIBILITY.items():
                expected_instruction = _SEEDED_AGENT_INSTRUCTION_BY_KEY[key]
                for legacy_instruction in legacy_instructions:
                    connection.execute(
                        text(
                            """
                            UPDATE agent_specs
                            SET instructions = :expected_instruction
                            WHERE key = :key
                              AND version = :version
                              AND origin = 'seeded'
                              AND instructions = :legacy_instruction
                            """
                        ),
                        {
                            "key": key,
                            "version": _SEEDED_RUNTIME_VERSION,
                            "expected_instruction": expected_instruction,
                            "legacy_instruction": legacy_instruction,
                        },
                    )

        if "persona_profiles" in table_names:
            for (
                key,
                legacy_descriptions,
            ) in _LEGACY_SEEDED_PERSONA_DESCRIPTION_COMPATIBILITY.items():
                expected_description = _SEEDED_BUILTIN_DESCRIPTION_BY_KEY[key]
                for legacy_description in legacy_descriptions:
                    connection.execute(
                        text(
                            """
                            UPDATE persona_profiles
                            SET system_prompt_fragment = :expected_description
                            WHERE key = :key
                              AND version = :version
                              AND origin = 'seeded'
                              AND system_prompt_fragment = :legacy_description
                            """
                        ),
                        {
                            "key": key,
                            "version": _SEEDED_RUNTIME_VERSION,
                            "expected_description": expected_description,
                            "legacy_description": legacy_description,
                        },
                    )

        if "capability_registry_entries" in table_names:
            for (
                key,
                legacy_descriptions,
            ) in _LEGACY_SEEDED_CAPABILITY_DESCRIPTION_COMPATIBILITY.items():
                expected_description = _SEEDED_CAPABILITY_DESCRIPTION_BY_KEY[key]
                for legacy_description in legacy_descriptions:
                    connection.execute(
                        text(
                            """
                            UPDATE capability_registry_entries
                            SET description = :expected_description
                            WHERE key = :key
                              AND version = :version
                              AND origin = 'seeded'
                              AND description = :legacy_description
                            """
                        ),
                        {
                            "key": key,
                            "version": _SEEDED_RUNTIME_VERSION,
                            "expected_description": expected_description,
                            "legacy_description": legacy_description,
                        },
                    )


def _ensure_runtime_v2_tables(engine: Engine, table_names: set[str]) -> None:
    for table_name, module_path, model_name in _RUNTIME_V2_TABLE_SPECS:
        if table_name in table_names:
            continue
        model = getattr(import_module(module_path), model_name)
        model.__table__.create(engine, checkfirst=True)
        table_names.add(table_name)


def _archive_legacy_seeded_workflow_specs(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "workflow_specs" not in table_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE workflow_specs
                SET status = 'ARCHIVED'
                WHERE origin = 'seeded'
                  AND status <> 'ARCHIVED'
                """
            )
        )


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

    _ensure_runtime_v2_tables(engine, table_names)
    _archive_legacy_seeded_workflow_specs(engine)
    _upgrade_persona_profiles_table(engine)
    _upgrade_runtime_seed_description_compatibility(engine)

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
