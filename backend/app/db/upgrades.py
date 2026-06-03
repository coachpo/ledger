# ruff: noqa: E501
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from pydantic import ValidationError
from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.agents.tool_catalog.server_declared import SERVER_DECLARED_TOOL_REGISTRY
from app.core.formatting import to_utc, utcnow
from app.db.validation import validate_supported_database_engine
from app.extensions.registry import get_bundled_extension_registry
from app.models.agent import (
    AGENT_MANIFEST_API_VERSION,
    AGENT_MANIFEST_COMPILER_VERSION,
    TEMPORARY_AGENT_MANIFEST_HASH,
    TEMPORARY_AGENT_MANIFEST_SOURCE,
)
from app.models.workflow import TEMPORARY_WORKFLOW_MANIFEST_SOURCE, WORKFLOW_MANIFEST_API_VERSION
from app.schemas.workflow_package_manifest import WorkflowPackageManifest

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
_LEGACY_BACKEND_TABLES = (
    "runtime_trace_events",
    "runtime_approvals",
    "runtime_checkpoints",
    "runtime_run_artifacts",
    "runtime_runs",
    "persona_projection_events",
    "capability_registry_entries",
    "persona_profiles",
    "workflow_specs",
    "agent_specs",
    "orchestration_characters",
    "orchestration_roles",
)
_LEGACY_SLUG_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_LEGACY_SLUG_DUPLICATE_UNDERSCORES_RE = re.compile(r"_+")
_MODEL_CONNECTION_KEY_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_]+")
_MODEL_CONNECTION_KEY_DUPLICATE_UNDERSCORES_RE = re.compile(r"_+")
_MODEL_CONNECTION_KEY_MAX_LENGTH = 120
_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE = (
    "Run marked as failed during startup recovery because the previous process exited while "
    "it was still running."
)
_AGENT_PLATFORM_PENDING_SKIP_MESSAGE = (
    "Runtime row skipped during startup recovery because the parent run failed before it started."
)
_MODEL_CONNECTION_PLACEHOLDER_BASE_URL = "https://api.openai.com/v1"
_MODEL_CONNECTION_PLACEHOLDER_REASONING_EFFORT = "medium"
_MODEL_CONNECTION_PLACEHOLDER_TIMEOUT_SECONDS = 60
_MODEL_CONNECTION_KIND_CHECK = (
    "ck_model_connections_connection_kind"  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
)
_MODEL_CONNECTION_REASONING_EFFORT_CHECK = "ck_model_connections_reasoning_effort"
_MODEL_CONNECTION_REASONING_EFFORT_CHECK_SQL = (
    "reasoning_effort IS NULL OR (length(btrim(reasoning_effort)) BETWEEN 1 AND 128)"
)
_MODEL_CONNECTION_DEFAULT_PROTOCOL_PROFILE = "openai_responses"
_MODEL_CONNECTION_ALLOWED_PROTOCOL_PROFILES = (
    "openai_chat_completions",
    _MODEL_CONNECTION_DEFAULT_PROTOCOL_PROFILE,
)
_MODEL_CONNECTION_LEGACY_API_STYLE_TO_PROTOCOL_PROFILE = {
    "chat_completions": "openai_chat_completions",
    "responses": _MODEL_CONNECTION_DEFAULT_PROTOCOL_PROFILE,
}
_MODEL_CONNECTION_PROTOCOL_PROFILE_TO_LEGACY_API_STYLE = {
    value: key for key, value in _MODEL_CONNECTION_LEGACY_API_STYLE_TO_PROTOCOL_PROFILE.items()
}
_MODEL_CONNECTION_PROTOCOL_PROFILE_CHECK = "ck_model_connections_protocol_profile"
_MODEL_CONNECTION_CAPABILITY_STATUS_CHECK = "ck_model_connections_capability_statuses"
_MODEL_CONNECTION_CAPABILITY_STATUS_JSONPATH = (
    '$.*.status ? (!(@ == "supported" || @ == "unsupported" '
    '|| @ == "unknown" || @ == "notApplicable"))'
)
_MODEL_CONNECTION_OUTPUT_STRATEGY_POLICY_CHECK = "ck_model_connections_output_strategy_policy"
_MODEL_CONNECTION_PARALLEL_TOOL_CALLS_POLICY_CHECK = (
    "ck_model_connections_parallel_tool_calls_policy"
)
_MODEL_CONNECTION_REASONING_POLICY_CHECK = "ck_model_connections_reasoning_policy"
_MODEL_CONNECTION_STREAMING_POLICY_CHECK = "ck_model_connections_streaming_policy"
_MODEL_CONNECTION_PROBE_CACHE_TTL_CHECK = "ck_model_connections_probe_cache_ttl_positive"
_MODEL_CONNECTION_ALLOWED_OUTPUT_STRATEGY_POLICIES = (
    "require_strict_schema",
    "prefer_strict_schema",
    "allow_json_object_validation",
    "allow_plain_text",
)
_MODEL_CONNECTION_ALLOWED_TOOL_POLICIES = ("allow", "serialize", "forbid")
_MODEL_CONNECTION_ALLOWED_BINARY_POLICIES = ("allow", "forbid")
_MODEL_CONNECTION_DEFAULT_OUTPUT_STRATEGY_POLICY = "prefer_strict_schema"
_MODEL_CONNECTION_DEFAULT_PARALLEL_TOOL_CALLS_POLICY = "serialize"
_MODEL_CONNECTION_DEFAULT_REASONING_POLICY = "allow"
_MODEL_CONNECTION_DEFAULT_STREAMING_POLICY = "allow"
_MODEL_CONNECTION_DEFAULT_PROBE_CACHE_TTL_SECONDS = 900
_MODEL_CONNECTION_DEFAULT_CAPABILITIES = {
    "textGeneration": {"status": "supported", "detail": None, "lastProbedAt": None},
    "chatCompletions": {"status": "notApplicable", "detail": None, "lastProbedAt": None},
    "responsesApi": {"status": "supported", "detail": None, "lastProbedAt": None},
    "streaming": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "nativeToolCalls": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "parallelToolCalls": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "jsonObjectOutput": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "strictJsonSchemaOutput": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "reasoningHints": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "usageReporting": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "systemMessages": {"status": "unknown", "detail": None, "lastProbedAt": None},
}
_MODEL_CONNECTION_STALE_SECRET_METADATA_COLUMNS = (
    "_".join(("has", "api", "key")),
    "_".join(("api", "key", "last4")),
)
_EXTENSION_STATE_CANONICAL_TABLE = "_extension_states_canonical"
_EXTENSION_STATE_PRIMARY_KEY = "pk_extension_states_extension_key"
_EXTENSION_STATE_TEMP_PRIMARY_KEY = "pk_extension_states_canonical_extension_key"
_EXTENSION_STATE_CREATE_TABLE_SQL = f"""
    CREATE TABLE IF NOT EXISTS extension_states (
        extension_key VARCHAR(120) NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT {_EXTENSION_STATE_PRIMARY_KEY} PRIMARY KEY (extension_key)
    )
    """
_EXTENSION_STATE_CREATE_CANONICAL_TABLE_SQL = f"""
    CREATE TABLE "{_EXTENSION_STATE_CANONICAL_TABLE}" (
        extension_key VARCHAR(120) NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT {_EXTENSION_STATE_TEMP_PRIMARY_KEY} PRIMARY KEY (extension_key)
    )
    """
_PRESET_PACKAGE_SQL_FILE = "".join(("trading", "agents", "_", "advisory", "_", "research", ".sql"))
_PRESET_PACKAGE_KEY = _PRESET_PACKAGE_SQL_FILE.removesuffix(".sql")
_PRESET_PACKAGE_MANIFEST_HASH = "3d05ed8a6533618b6a955dc0ac368c3dd229d8ecb002667f5b887ece4f4081f1"
_PRESET_PACKAGE_COMPILED_HASH = "a62916f90c24b61c419d05dbfe8b22274cafdfd0ebff52493509140b25468936"
_PRESET_PACKAGE_SCHEDULE_RECURRENCE = {"type": "interval", "every": 2, "unit": "minutes"}
_PRESET_PACKAGE_SCHEDULE_DEFAULTS = {
    "timezone": "UTC",
    "overlap_policy": "skip",
    "misfire_policy": "catchUpOne",
    "misfire_grace_seconds": 86400,
}
_PRESET_PACKAGE_SCHEDULE_SPECS = (
    {
        "workflow_key": "advisory_research",
        "name": "TradingAgents Advisory Research · 2m",
        "input_template": {
            "ticker": "SPY",
            "asOfDate": "{{fire.scheduledLocalDate}}",
            "horizonDays": 30,
            "portfolioId": "",
            "outputLanguage": "English",
            "benchmarkSymbol": "SPY",
            "maxRiskDebateRounds": 2,
            "maxInvestmentDebateRounds": 2,
        },
    },
    {
        "workflow_key": "market_research",
        "name": "TradingAgents Market Research · 2m",
        "input_template": {
            "ticker": "SPY",
            "asOfDate": "{{fire.scheduledLocalDate}}",
            "horizonDays": 30,
            "outputLanguage": "English",
            "benchmarkSymbol": "SPY",
        },
    },
    {
        "workflow_key": "news_research",
        "name": "TradingAgents News Research · 2m",
        "input_template": {
            "ticker": "SPY",
            "asOfDate": "{{fire.scheduledLocalDate}}",
            "horizonDays": 30,
            "outputLanguage": "English",
        },
    },
    {
        "workflow_key": "fundamentals_research",
        "name": "TradingAgents Fundamentals Research · 2m",
        "input_template": {
            "ticker": "SPY",
            "asOfDate": "{{fire.scheduledLocalDate}}",
            "horizonDays": 30,
            "outputLanguage": "English",
        },
    },
)
_DB_UPGRADE_MARKER_TABLE = "db_upgrade_markers"
_WORKFLOW_PACKAGE_STARTUP_CUTOVER_MARKER_KEY = "workflow_package_artifact_cutover_v1"


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL = (
    _sql_string_literal(json.dumps(_MODEL_CONNECTION_DEFAULT_CAPABILITIES, sort_keys=True))
    + "::jsonb"
)
_WORKFLOW_MANIFEST_API_VERSION_SQL = _sql_string_literal(WORKFLOW_MANIFEST_API_VERSION)
_TEMPORARY_WORKFLOW_MANIFEST_SOURCE_SQL = _sql_string_literal(TEMPORARY_WORKFLOW_MANIFEST_SOURCE)
_AGENT_MANIFEST_API_VERSION_SQL = _sql_string_literal(AGENT_MANIFEST_API_VERSION)
_TEMPORARY_AGENT_MANIFEST_SOURCE_SQL = _sql_string_literal(TEMPORARY_AGENT_MANIFEST_SOURCE)
_TEMPORARY_AGENT_MANIFEST_HASH_SQL = _sql_string_literal(TEMPORARY_AGENT_MANIFEST_HASH)
_AGENT_MANIFEST_COMPILER_VERSION_SQL = _sql_string_literal(AGENT_MANIFEST_COMPILER_VERSION)
_AGENT_PLATFORM_TABLE_STATEMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "output_schemas",
        (
            """
            CREATE TABLE IF NOT EXISTS output_schemas (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                kind VARCHAR(20) NOT NULL DEFAULT 'standalone',
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                json_schema JSONB NOT NULL,
                registry_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_output_schemas_status CHECK (
                    status IN ('draft', 'published', 'deprecated')
                ),
                CONSTRAINT ck_output_schemas_kind CHECK (kind IN ('standalone', 'shared')),
                CONSTRAINT ck_output_schemas_version_positive CHECK (version > 0),
                CONSTRAINT uq_output_schemas_key_version UNIQUE (key, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_output_schemas_key ON output_schemas (key)",
            "CREATE INDEX IF NOT EXISTS ix_output_schemas_status ON output_schemas (status)",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_output_schemas_published_key "
                "ON output_schemas (key) WHERE status = 'published'"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_output_schemas_draft_key "
                "ON output_schemas (key) WHERE status = 'draft'"
            ),
        ),
    ),
    (
        "capabilities",
        (
            """
            CREATE TABLE IF NOT EXISTS capabilities (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tool_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_capabilities_status CHECK (
                    status IN ('draft', 'published', 'deprecated')
                ),
                CONSTRAINT ck_capabilities_version_positive CHECK (version > 0),
                CONSTRAINT uq_capabilities_key_version UNIQUE (key, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_capabilities_key ON capabilities (key)",
            "CREATE INDEX IF NOT EXISTS ix_capabilities_status ON capabilities (status)",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_capabilities_published_key "
                "ON capabilities (key) WHERE status = 'published'"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_capabilities_draft_key "
                "ON capabilities (key) WHERE status = 'draft'"
            ),
        ),
    ),
    (
        "mcp_servers",
        (
            """
            CREATE TABLE IF NOT EXISTS mcp_servers (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                config JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_mcp_servers_status CHECK (
                    status IN ('draft', 'published', 'deprecated')
                ),
                CONSTRAINT ck_mcp_servers_version_positive CHECK (version > 0),
                CONSTRAINT uq_mcp_servers_key_version UNIQUE (key, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_mcp_servers_key ON mcp_servers (key)",
            "CREATE INDEX IF NOT EXISTS ix_mcp_servers_status ON mcp_servers (status)",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_servers_published_key "
                "ON mcp_servers (key) WHERE status = 'published'"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_servers_draft_key "
                "ON mcp_servers (key) WHERE status = 'draft'"
            ),
        ),
    ),
    (
        "model_connections",
        (
            f"""
            CREATE TABLE IF NOT EXISTS model_connections (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                base_url VARCHAR(500) NOT NULL,
                model_id VARCHAR(200) NOT NULL,
                reasoning_effort VARCHAR(128) DEFAULT 'medium',
                protocol_profile VARCHAR(40) NOT NULL DEFAULT 'openai_responses',
                capabilities JSONB NOT NULL DEFAULT {_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL},
                output_strategy_policy VARCHAR(40) NOT NULL DEFAULT 'prefer_strict_schema',
                parallel_tool_calls_policy VARCHAR(20) NOT NULL DEFAULT 'serialize',
                reasoning_policy VARCHAR(20) NOT NULL DEFAULT 'allow',
                streaming_policy VARCHAR(20) NOT NULL DEFAULT 'allow',
                last_probed_at TIMESTAMPTZ,
                probe_cache_ttl_seconds INTEGER NOT NULL DEFAULT 900,
                timeout_seconds INTEGER NOT NULL DEFAULT 60,
                secret_payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                last_tested_at TIMESTAMPTZ,
                last_test_ok BOOLEAN,
                last_test_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_model_connections_status CHECK (
                    status IN ('active')
                ),
                CONSTRAINT ck_model_connections_reasoning_effort CHECK (
                    reasoning_effort IS NULL
                    OR (length(btrim(reasoning_effort)) BETWEEN 1 AND 128)
                ),
                CONSTRAINT ck_model_connections_protocol_profile CHECK (
                    protocol_profile IN ('openai_chat_completions', 'openai_responses')
                ),
                CONSTRAINT ck_model_connections_capability_statuses CHECK (
                    jsonb_typeof(capabilities) = 'object'
                    AND NOT jsonb_path_exists(
                        capabilities,
                        {_MODEL_CONNECTION_CAPABILITY_STATUS_JSONPATH!r}
                    )
                ),
                CONSTRAINT ck_model_connections_output_strategy_policy CHECK (
                    output_strategy_policy IN (
                        'require_strict_schema',
                        'prefer_strict_schema',
                        'allow_json_object_validation',
                        'allow_plain_text'
                    )
                ),
                CONSTRAINT ck_model_connections_parallel_tool_calls_policy CHECK (
                    parallel_tool_calls_policy IN ('allow', 'serialize', 'forbid')
                ),
                CONSTRAINT ck_model_connections_reasoning_policy CHECK (
                    reasoning_policy IN ('allow', 'forbid')
                ),
                CONSTRAINT ck_model_connections_streaming_policy CHECK (
                    streaming_policy IN ('allow', 'forbid')
                ),
                CONSTRAINT ck_model_connections_probe_cache_ttl_positive CHECK (
                    probe_cache_ttl_seconds > 0
                ),
                CONSTRAINT ck_model_connections_timeout_seconds_positive CHECK (
                    timeout_seconds > 0
                ),
                CONSTRAINT uq_model_connections_key UNIQUE (key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_model_connections_status ON model_connections (status)",
            (
                "CREATE INDEX IF NOT EXISTS ix_model_connections_model_id "
                "ON model_connections (model_id)"
            ),
        ),
    ),
    (
        "agents",
        (
            """
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                manifest_api_version VARCHAR(80) NOT NULL DEFAULT 'signaldeck.agent/v1',
                manifest_source TEXT NOT NULL DEFAULT $$apiVersion: signaldeck.agent/v1
kind: Agent
metadata:
  source: legacy-payload-placeholder
$$,
                manifest_hash VARCHAR(64) NOT NULL DEFAULT
                    '1051cbdb8f6e2f18cca4b4d4fbfee4a66406f500ce80662ad736a01868602948',
                compiler_version VARCHAR(80) NOT NULL DEFAULT 'agent-manifest-compiler/v1',
                model_connection_id INTEGER,
                model_connection_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
                model VARCHAR(200) NOT NULL,
                system_prompt TEXT NOT NULL,
                input_schema JSONB NOT NULL,
                output_schema_id INTEGER NOT NULL,
                output_schema_version INTEGER NOT NULL,
                capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
                mcp_servers JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_agents_status CHECK (
                    status IN ('draft', 'published', 'deprecated')
                ),
                CONSTRAINT ck_agents_version_positive CHECK (version > 0),
                CONSTRAINT ck_agents_output_schema_version_positive CHECK (
                    output_schema_version > 0
                ),
                CONSTRAINT uq_agents_key_version UNIQUE (key, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_agents_key ON agents (key)",
            "CREATE INDEX IF NOT EXISTS ix_agents_status ON agents (status)",
            (
                "CREATE INDEX IF NOT EXISTS ix_agents_output_schema "
                "ON agents (output_schema_id, output_schema_version)"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_published_key "
                "ON agents (key) WHERE status = 'published'"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_draft_key "
                "ON agents (key) WHERE status = 'draft'"
            ),
        ),
    ),
    (
        "workflows",
        (
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                key VARCHAR(120) NOT NULL,
                version INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                name VARCHAR(200) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                manifest_api_version VARCHAR(80) NOT NULL DEFAULT 'signaldeck.workflow/v1',
                manifest_source TEXT NOT NULL DEFAULT $$apiVersion: signaldeck.workflow/v1
kind: Workflow
metadata:
  source: legacy-payload-placeholder
$$,
                input_schema JSONB NOT NULL,
                steps JSONB NOT NULL,
                output_spec JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_workflows_status CHECK (
                    status IN ('draft', 'published', 'deprecated')
                ),
                CONSTRAINT ck_workflows_version_positive CHECK (version > 0),
                CONSTRAINT uq_workflows_key_version UNIQUE (key, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_workflows_key ON workflows (key)",
            "CREATE INDEX IF NOT EXISTS ix_workflows_status ON workflows (status)",
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_published_key "
                "ON workflows (key) WHERE status = 'published'"
            ),
            (
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflows_draft_key "
                "ON workflows (key) WHERE status = 'draft'"
            ),
        ),
    ),
    (
        "runs",
        (
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                target_kind VARCHAR(20) NOT NULL,
                target_id INTEGER NOT NULL,
                target_key VARCHAR(120) NOT NULL,
                target_version INTEGER NOT NULL,
                workflow_package_id INTEGER,
                workflow_package_key VARCHAR(120),
                workflow_package_workflow_key VARCHAR(120),
                extension_dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
                input JSONB NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'queued',
                execution_scope_key VARCHAR(255),
                concurrency_policy VARCHAR(20) NOT NULL DEFAULT 'serial',
                lease_owner VARCHAR(255),
                lease_expires_at TIMESTAMPTZ,
                heartbeat_at TIMESTAMPTZ,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_claimed_at TIMESTAMPTZ,
                source_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                lineage_root_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                forked_from_step_index INTEGER,
                resume_step_index INTEGER NOT NULL DEFAULT 1,
                final_output JSONB,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                inherited_tokens INTEGER NOT NULL DEFAULT 0,
                executed_tokens INTEGER NOT NULL DEFAULT 0,
                trace_id VARCHAR(255),
                error TEXT,
                queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_runs_target_kind CHECK (
                    target_kind IN ('agent', 'workflow', 'workflowPackage')
                ),
                CONSTRAINT ck_runs_status CHECK (
                    status IN ('queued', 'running', 'succeeded', 'failed')
                ),
                CONSTRAINT ck_runs_target_version_positive CHECK (target_version > 0),
                CONSTRAINT ck_runs_resume_step_index_positive CHECK (resume_step_index > 0),
                CONSTRAINT ck_runs_forked_from_step_index_positive CHECK (
                    forked_from_step_index IS NULL OR forked_from_step_index > 0
                ),
                CONSTRAINT ck_runs_total_tokens_non_negative CHECK (total_tokens >= 0),
                CONSTRAINT ck_runs_inherited_tokens_non_negative CHECK (inherited_tokens >= 0),
                CONSTRAINT ck_runs_executed_tokens_non_negative CHECK (executed_tokens >= 0),
                CONSTRAINT ck_runs_concurrency_policy CHECK (
                    concurrency_policy IN ('serial', 'parallel')
                ),
                CONSTRAINT ck_runs_attempt_count_non_negative CHECK (attempt_count >= 0)
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_runs_status ON runs (status)",
            (
                "CREATE INDEX IF NOT EXISTS ix_runs_target "
                "ON runs (target_kind, target_id, target_version)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_runs_target_key "
                "ON runs (target_kind, target_key, target_version)"
            ),
            "CREATE INDEX IF NOT EXISTS ix_runs_source_run ON runs (source_run_id)",
            "CREATE INDEX IF NOT EXISTS ix_runs_lineage_root ON runs (lineage_root_run_id)",
            ("CREATE INDEX IF NOT EXISTS ix_runs_workflow_package ON runs (workflow_package_id)"),
            (
                "CREATE INDEX IF NOT EXISTS ix_runs_workflow_package_key "
                "ON runs (workflow_package_key)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_runs_workflow_package_workflow_key "
                "ON runs (workflow_package_workflow_key)"
            ),
        ),
    ),
    (
        "run_workflow_package_snapshots",
        (
            """
            CREATE TABLE IF NOT EXISTS run_workflow_package_snapshots (
                run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                workflow_package_id INTEGER NOT NULL,
                workflow_package_key VARCHAR(120) NOT NULL,
                workflow_package_name VARCHAR(200) NOT NULL,
                workflow_package_description TEXT NOT NULL DEFAULT '',
                workflow_package_status VARCHAR(20),
                workflow_key VARCHAR(120) NOT NULL,
                workflow_name VARCHAR(200) NOT NULL,
                workflow_description TEXT NOT NULL DEFAULT '',
                manifest_hash VARCHAR(64) NOT NULL,
                compiled_hash VARCHAR(64) NOT NULL,
                manifest_source TEXT NOT NULL,
                package_definition JSONB NOT NULL,
                compiled_plan JSONB NOT NULL,
                extension_dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
                local_resource_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
                input_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
                launch_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                resolved_model_connections JSONB NOT NULL DEFAULT '[]'::jsonb,
                preflight_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS ix_run_workflow_package_snapshots_package_key "
                "ON run_workflow_package_snapshots (workflow_package_key)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_workflow_package_snapshots_workflow_key "
                "ON run_workflow_package_snapshots (workflow_key)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_workflow_package_snapshots_manifest_hash "
                "ON run_workflow_package_snapshots (manifest_hash)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_workflow_package_snapshots_compiled_hash "
                "ON run_workflow_package_snapshots (compiled_hash)"
            ),
        ),
    ),
    (
        "run_steps",
        (
            """
            CREATE TABLE IF NOT EXISTS run_steps (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                origin VARCHAR(20) NOT NULL DEFAULT 'planned',
                source_run_step_id INTEGER REFERENCES run_steps(id) ON DELETE SET NULL,
                source_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                source_step_index INTEGER,
                graph_metadata JSONB,
                error TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                persisted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_run_steps_run_step_index UNIQUE (run_id, step_index),
                CONSTRAINT ck_run_steps_step_index_positive CHECK (step_index > 0),
                CONSTRAINT ck_run_steps_status CHECK (
                    status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')
                ),
                CONSTRAINT ck_run_steps_origin CHECK (origin IN ('planned', 'copied')),
                CONSTRAINT ck_run_steps_source_step_index_positive CHECK (
                    source_step_index IS NULL OR source_step_index > 0
                )
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS ix_run_steps_run_step_index "
                "ON run_steps (run_id, step_index)"
            ),
            ("CREATE INDEX IF NOT EXISTS ix_run_steps_run_status ON run_steps (run_id, status)"),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_steps_source_run_step "
                "ON run_steps (source_run_step_id)"
            ),
        ),
    ),
    (
        "run_agent_invocations",
        (
            """
            CREATE TABLE IF NOT EXISTS run_agent_invocations (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                run_step_id INTEGER NOT NULL REFERENCES run_steps(id) ON DELETE CASCADE,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                slot VARCHAR(120) NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                agent_id INTEGER NOT NULL,
                agent_key VARCHAR(120) NOT NULL,
                agent_version INTEGER NOT NULL,
                output_schema_id INTEGER NOT NULL,
                output_schema_version INTEGER NOT NULL,
                input_mode VARCHAR(20) NOT NULL DEFAULT 'wired',
                wiring JSONB NOT NULL DEFAULT '{}'::jsonb,
                graph_metadata JSONB,
                optional BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                resolved_input JSONB NOT NULL DEFAULT '{}'::jsonb,
                resolved_input_origin VARCHAR(20) NOT NULL DEFAULT 'derived',
                output JSONB,
                output_origin VARCHAR(20),
                error_code VARCHAR(120),
                error_message TEXT,
                error_details JSONB NOT NULL DEFAULT '[]'::jsonb,
                tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER,
                trace_span_id VARCHAR(255),
                source_invocation_id INTEGER REFERENCES run_agent_invocations(id)
                    ON DELETE SET NULL,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                persisted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_run_agent_invocations_step_slot UNIQUE (run_step_id, slot),
                CONSTRAINT ck_run_agent_invocations_step_index_positive CHECK (step_index > 0),
                CONSTRAINT ck_run_agent_invocations_position_non_negative CHECK (position >= 0),
                CONSTRAINT ck_run_agent_invocations_agent_id_positive CHECK (agent_id > 0),
                CONSTRAINT ck_run_agent_invocations_agent_version_positive CHECK (
                    agent_version > 0
                ),
                CONSTRAINT ck_run_agent_invocations_output_schema_id_positive CHECK (
                    output_schema_id > 0
                ),
                CONSTRAINT ck_run_agent_invocations_output_schema_version_positive CHECK (
                    output_schema_version > 0
                ),
                CONSTRAINT ck_run_agent_invocations_input_mode CHECK (
                    input_mode IN ('passthrough', 'wired')
                ),
                CONSTRAINT ck_run_agent_invocations_status CHECK (
                    status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')
                ),
                CONSTRAINT ck_run_agent_invocations_resolved_input_origin CHECK (
                    resolved_input_origin IN ('derived', 'edited', 'copied', 'passthrough')
                ),
                CONSTRAINT ck_run_agent_invocations_output_origin CHECK (
                    output_origin IS NULL OR output_origin IN ('executed', 'edited', 'copied')
                ),
                CONSTRAINT ck_run_agent_invocations_tokens_non_negative CHECK (tokens >= 0),
                CONSTRAINT ck_run_agent_invocations_duration_non_negative CHECK (
                    duration_ms IS NULL OR duration_ms >= 0
                )
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS ix_run_agent_invocations_run_step_index "
                "ON run_agent_invocations (run_id, step_index)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_agent_invocations_run_status "
                "ON run_agent_invocations (run_id, status)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_agent_invocations_agent_version "
                "ON run_agent_invocations (agent_key, agent_version)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_agent_invocations_source_invocation "
                "ON run_agent_invocations (source_invocation_id)"
            ),
        ),
    ),
    (
        "run_forks",
        (
            """
            CREATE TABLE IF NOT EXISTS run_forks (
                run_id INTEGER PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
                source_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                lineage_root_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                source_invocation_id INTEGER REFERENCES run_agent_invocations(id)
                    ON DELETE SET NULL,
                source_step_index INTEGER NOT NULL,
                resume_step_index INTEGER NOT NULL,
                invocation_input JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT ck_run_forks_source_step_index_positive CHECK (
                    source_step_index > 0
                ),
                CONSTRAINT ck_run_forks_resume_step_index_positive CHECK (
                    resume_step_index > 0
                )
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_run_forks_source_run ON run_forks (source_run_id)",
            (
                "CREATE INDEX IF NOT EXISTS ix_run_forks_lineage_root "
                "ON run_forks (lineage_root_run_id)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_forks_source_invocation "
                "ON run_forks (source_invocation_id)"
            ),
        ),
    ),
    (
        "run_operation_invocations",
        (
            """
            CREATE TABLE IF NOT EXISTS run_operation_invocations (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                run_step_id INTEGER NOT NULL REFERENCES run_steps(id) ON DELETE CASCADE,
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                step_index INTEGER NOT NULL,
                slot VARCHAR(120) NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                operation_key VARCHAR(120) NOT NULL,
                operation_kind VARCHAR(40) NOT NULL,
                output_schema_id INTEGER NOT NULL,
                output_schema_version INTEGER NOT NULL,
                method VARCHAR(20),
                timeout_seconds INTEGER,
                request_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                response_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                graph_metadata JSONB,
                optional BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                output JSONB,
                output_origin VARCHAR(20),
                error_code VARCHAR(120),
                error_message TEXT,
                error_details JSONB NOT NULL DEFAULT '[]'::jsonb,
                duration_ms INTEGER,
                trace_span_id VARCHAR(255),
                source_operation_invocation_id INTEGER REFERENCES run_operation_invocations(id)
                    ON DELETE SET NULL,
                source_run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
                source_run_step_id INTEGER REFERENCES run_steps(id) ON DELETE SET NULL,
                source_step_index INTEGER,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                persisted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_run_operation_invocations_step_slot UNIQUE (run_step_id, slot),
                CONSTRAINT ck_run_operation_invocations_step_index_positive CHECK (step_index > 0),
                CONSTRAINT ck_run_operation_invocations_position_non_negative CHECK (position >= 0),
                CONSTRAINT ck_run_operation_invocations_operation_kind CHECK (
                    operation_kind IN ('http')
                ),
                CONSTRAINT ck_run_operation_invocations_status CHECK (
                    status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')
                ),
                CONSTRAINT ck_run_operation_invocations_output_schema_id_positive CHECK (
                    output_schema_id > 0
                ),
                CONSTRAINT ck_run_operation_invocations_output_schema_version_positive CHECK (
                    output_schema_version > 0
                ),
                CONSTRAINT ck_run_operation_invocations_source_step_index_positive CHECK (
                    source_step_index IS NULL OR source_step_index > 0
                ),
                CONSTRAINT ck_run_operation_invocations_output_origin CHECK (
                    output_origin IS NULL OR output_origin IN ('executed', 'edited', 'copied')
                ),
                CONSTRAINT ck_run_operation_invocations_duration_non_negative CHECK (
                    duration_ms IS NULL OR duration_ms >= 0
                ),
                CONSTRAINT ck_run_operation_invocations_timeout_positive CHECK (
                    timeout_seconds IS NULL OR timeout_seconds > 0
                )
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_run_step_index "
                "ON run_operation_invocations (run_id, step_index)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_run_status "
                "ON run_operation_invocations (run_id, status)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_operation_key "
                "ON run_operation_invocations (operation_key)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_source_operation "
                "ON run_operation_invocations (source_operation_invocation_id)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_source_run "
                "ON run_operation_invocations (source_run_id)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS ix_run_operation_invocations_source_run_step "
                "ON run_operation_invocations (source_run_step_id)"
            ),
        ),
    ),
)

_WORKFLOW_PACKAGE_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS workflow_packages (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        key VARCHAR(120) NOT NULL,
        name VARCHAR(200) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        manifest_source TEXT NOT NULL,
        manifest_hash VARCHAR(64) NOT NULL,
        package_definition JSONB NOT NULL,
        compiled_plan JSONB NOT NULL,
        compiled_hash VARCHAR(64) NOT NULL,
        extension_dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_package_secret_bindings (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        package_id INTEGER NOT NULL REFERENCES workflow_packages(id) ON DELETE CASCADE,
        key VARCHAR(120) NOT NULL,
        secret_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_workflow_package_secret_bindings_package_key UNIQUE (package_id, key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_packages_key ON workflow_packages (key)",
    ("CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_packages_key ON workflow_packages (key)"),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_packages_manifest_hash "
        "ON workflow_packages (manifest_hash)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_packages_compiled_hash "
        "ON workflow_packages (compiled_hash)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_secret_bindings_package "
        "ON workflow_package_secret_bindings (package_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_secret_bindings_key "
        "ON workflow_package_secret_bindings (key)"
    ),
)
_RUNTIME_INPUT_REGISTRY_TABLE_NAME = "workflow_package_runtime_input_entries"
_RUNTIME_INPUT_REGISTRY_PACKAGE_FK = "fk_workflow_package_runtime_input_entries_package_id"
_RUNTIME_INPUT_REGISTRY_SOURCE_RUN_FK = "fk_workflow_package_runtime_input_entries_source_run_id"
_RUNTIME_INPUT_REGISTRY_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS workflow_package_runtime_input_entries (
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
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_runtime_input_entries_package "
        "ON workflow_package_runtime_input_entries (package_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_runtime_input_entries_scope_slot_created "
        "ON workflow_package_runtime_input_entries "
        "(package_id, workflow_key, owner_type, owner_id, slot, created_at, id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_runtime_input_entries_scope_slot_updated "
        "ON workflow_package_runtime_input_entries "
        "(package_id, workflow_key, owner_type, owner_id, slot, updated_at, id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_runtime_input_entries_source_run "
        "ON workflow_package_runtime_input_entries (source_run_id)"
    ),
)
_WORKFLOW_PACKAGE_SCHEDULE_TABLE_NAMES = {
    "workflow_package_schedules",
    "workflow_package_schedule_fires",
}
_WORKFLOW_PACKAGE_SCHEDULE_COLUMNS: dict[str, str] = {
    "package_id": "INTEGER NOT NULL",
    "workflow_key": "VARCHAR(120) NOT NULL",
    "name": "VARCHAR(200) NOT NULL",
    "description": "TEXT",
    "status": "VARCHAR(20) NOT NULL DEFAULT 'enabled'",
    "timezone": "VARCHAR(120) NOT NULL",
    "recurrence": "JSONB NOT NULL DEFAULT '{}'::jsonb",
    "starts_at": "TIMESTAMPTZ",
    "ends_at": "TIMESTAMPTZ",
    "next_fire_at": "TIMESTAMPTZ",
    "overlap_policy": "VARCHAR(20) NOT NULL DEFAULT 'skip'",
    "misfire_policy": "VARCHAR(20) NOT NULL DEFAULT 'catchUpOne'",
    "misfire_grace_seconds": "INTEGER NOT NULL DEFAULT 86400",
    "input_template": "JSONB NOT NULL DEFAULT '{}'::jsonb",
    "template_vars": "JSONB NOT NULL DEFAULT '{}'::jsonb",
    "created_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
}
_WORKFLOW_PACKAGE_SCHEDULE_FIRE_COLUMNS: dict[str, str] = {
    "schedule_id": "INTEGER NOT NULL",
    "fire_key": "VARCHAR(255) NOT NULL",
    "reason": "VARCHAR(20) NOT NULL DEFAULT 'scheduled'",
    "status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
    "scheduled_for": "TIMESTAMPTZ NOT NULL",
    "scheduled_local_date": "VARCHAR(10)",
    "scheduled_local_time": "VARCHAR(8)",
    "scheduled_local_datetime": "VARCHAR(32)",
    "materialized_at": "TIMESTAMPTZ",
    "rendered_parameters": "JSONB NOT NULL DEFAULT '{}'::jsonb",
    "skip_reason": "VARCHAR(120)",
    "error_code": "VARCHAR(120)",
    "error_message": "TEXT",
    "created_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "updated_at": "TIMESTAMPTZ NOT NULL DEFAULT NOW()",
}
_RUN_SCHEDULE_PROVENANCE_COLUMNS: dict[str, str] = {
    "schedule_id": "INTEGER",
    "schedule_fire_id": "INTEGER",
    "scheduled_for": "TIMESTAMPTZ",
    "schedule_reason": "VARCHAR(20)",
    "schedule_provenance": "JSONB",
}
_WORKFLOW_PACKAGE_SCHEDULE_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS workflow_package_schedules (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        package_id INTEGER NOT NULL,
        workflow_key VARCHAR(120) NOT NULL,
        name VARCHAR(200) NOT NULL,
        description TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'enabled',
        timezone VARCHAR(120) NOT NULL,
        recurrence JSONB NOT NULL DEFAULT '{}'::jsonb,
        starts_at TIMESTAMPTZ,
        ends_at TIMESTAMPTZ,
        next_fire_at TIMESTAMPTZ,
        overlap_policy VARCHAR(20) NOT NULL DEFAULT 'skip',
        misfire_policy VARCHAR(20) NOT NULL DEFAULT 'catchUpOne',
        misfire_grace_seconds INTEGER NOT NULL DEFAULT 86400,
        input_template JSONB NOT NULL DEFAULT '{}'::jsonb,
        template_vars JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_workflow_package_schedules_status CHECK (
            status IN ('enabled', 'paused')
        ),
        CONSTRAINT ck_workflow_package_schedules_overlap_policy CHECK (
            overlap_policy IN ('skip', 'queue')
        ),
        CONSTRAINT ck_workflow_package_schedules_misfire_policy CHECK (
            misfire_policy IN ('skip', 'catchUpOne')
        ),
        CONSTRAINT ck_workflow_package_schedules_misfire_grace_non_negative CHECK (
            misfire_grace_seconds >= 0
        ),
        CONSTRAINT fk_workflow_package_schedules_package_id
            FOREIGN KEY (package_id) REFERENCES workflow_packages(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workflow_package_schedule_fires (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        schedule_id INTEGER NOT NULL,
        fire_key VARCHAR(255) NOT NULL,
        reason VARCHAR(20) NOT NULL DEFAULT 'scheduled',
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        scheduled_for TIMESTAMPTZ NOT NULL,
        scheduled_local_date VARCHAR(10),
        scheduled_local_time VARCHAR(8),
        scheduled_local_datetime VARCHAR(32),
        materialized_at TIMESTAMPTZ,
        rendered_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
        skip_reason VARCHAR(120),
        error_code VARCHAR(120),
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_workflow_package_schedule_fires_schedule_fire_key
            UNIQUE (schedule_id, fire_key),
        CONSTRAINT ck_workflow_package_schedule_fires_status CHECK (
            status IN ('pending', 'queued', 'skipped', 'failed')
        ),
        CONSTRAINT ck_workflow_package_schedule_fires_reason CHECK (
            reason IN ('scheduled', 'manual')
        ),
        CONSTRAINT fk_workflow_package_schedule_fires_schedule_id
            FOREIGN KEY (schedule_id) REFERENCES workflow_package_schedules(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedules_package ON workflow_package_schedules (package_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedules_package_workflow "
        "ON workflow_package_schedules (package_id, workflow_key)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedules_status_next_fire "
        "ON workflow_package_schedules (status, next_fire_at, id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedules_next_fire ON workflow_package_schedules (next_fire_at)",
    "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedule_fires_schedule ON workflow_package_schedule_fires (schedule_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedule_fires_schedule_status "
        "ON workflow_package_schedule_fires (schedule_id, status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedule_fires_scheduled_for "
        "ON workflow_package_schedule_fires (scheduled_for)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_workflow_package_schedule_fires_status ON workflow_package_schedule_fires (status)",
)
_WORKFLOW_PACKAGE_SCHEDULE_CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "workflow_package_schedules",
        "ck_workflow_package_schedules_status",
        "status IN ('enabled', 'paused')",
    ),
    (
        "workflow_package_schedules",
        "ck_workflow_package_schedules_overlap_policy",
        "overlap_policy IN ('skip', 'queue')",
    ),
    (
        "workflow_package_schedules",
        "ck_workflow_package_schedules_misfire_policy",
        "misfire_policy IN ('skip', 'catchUpOne')",
    ),
    (
        "workflow_package_schedules",
        "ck_workflow_package_schedules_misfire_grace_non_negative",
        "misfire_grace_seconds >= 0",
    ),
    (
        "workflow_package_schedule_fires",
        "ck_workflow_package_schedule_fires_status",
        "status IN ('pending', 'queued', 'skipped', 'failed')",
    ),
    (
        "workflow_package_schedule_fires",
        "ck_workflow_package_schedule_fires_reason",
        "reason IN ('scheduled', 'manual')",
    ),
)
_RUN_SCHEDULE_PROVENANCE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_runs_schedule ON runs (schedule_id)",
    "CREATE INDEX IF NOT EXISTS ix_runs_schedule_status ON runs (schedule_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_runs_schedule_fire ON runs (schedule_fire_id)",
    "CREATE INDEX IF NOT EXISTS ix_runs_scheduled_for ON runs (scheduled_for)",
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_schedule_fire "
        "ON runs (schedule_fire_id) WHERE schedule_fire_id IS NOT NULL"
    ),
)
_RUN_WORKFLOW_PACKAGE_PROVENANCE_COLUMNS: dict[str, str] = {
    "workflow_package_id": "INTEGER",
    "workflow_package_key": "VARCHAR(120)",
    "workflow_package_workflow_key": "VARCHAR(120)",
    "extension_dependencies": "JSONB NOT NULL DEFAULT '[]'::jsonb",
}
_RUN_WORKFLOW_PACKAGE_REMOVED_PROVENANCE_COLUMNS = (
    "workflow_package_" + "version_id",
    "workflow_package_" + "version",
    "workflow_package_manifest_hash",
    "workflow_package_compiled_hash",
    "workflow_package_hash",
    "launch_snapshot",
)
_RUN_WORKFLOW_PACKAGE_PROVENANCE_INDEXES: tuple[str, ...] = (
    ("CREATE INDEX IF NOT EXISTS ix_runs_workflow_package ON runs (workflow_package_id)"),
    ("CREATE INDEX IF NOT EXISTS ix_runs_workflow_package_key ON runs (workflow_package_key)"),
    (
        "CREATE INDEX IF NOT EXISTS ix_runs_workflow_package_workflow_key "
        "ON runs (workflow_package_workflow_key)"
    ),
)
_RUN_SCHEDULER_METADATA_COLUMNS: dict[str, str] = {
    "execution_scope_key": "VARCHAR(255)",
    "concurrency_policy": "VARCHAR(20) NOT NULL DEFAULT 'serial'",
    "lease_owner": "VARCHAR(255)",
    "lease_expires_at": "TIMESTAMPTZ",
    "heartbeat_at": "TIMESTAMPTZ",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "last_claimed_at": "TIMESTAMPTZ",
}
_RUN_SCHEDULER_NON_UNIQUE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_runs_queue_claim ON runs (status, queued_at, id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_runs_execution_scope_status "
        "ON runs (execution_scope_key, status)"
    ),
)
_RUN_SCHEDULER_SERIAL_INDEX = "uq_runs_running_serial_execution_scope"
_RUN_SCHEDULER_SERIAL_INDEX_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {_RUN_SCHEDULER_SERIAL_INDEX} "
    "ON runs (execution_scope_key) "
    "WHERE status = 'running' AND concurrency_policy = 'serial' "
    "AND execution_scope_key IS NOT NULL"
)
_RUN_TARGET_REFERENCE_COLUMNS: dict[str, str] = {
    "agent_id": "INTEGER",
    "workflow_id": "INTEGER",
}
_PLATFORM_REFERENCE_TABLE_NAMES = {
    "workflow_agent_refs",
    "agent_capability_refs",
    "agent_mcp_server_refs",
}
_PLATFORM_REFERENCE_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS workflow_agent_refs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
        agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE RESTRICT,
        CONSTRAINT uq_workflow_agent_refs_workflow_agent UNIQUE (workflow_id, agent_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_capability_refs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        capability_id INTEGER NOT NULL REFERENCES capabilities(id) ON DELETE RESTRICT,
        capability_key VARCHAR(120) NOT NULL,
        CONSTRAINT uq_agent_capability_refs_agent_capability UNIQUE (agent_id, capability_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_mcp_server_refs (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        mcp_server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE RESTRICT,
        mcp_server_key VARCHAR(120) NOT NULL,
        CONSTRAINT uq_agent_mcp_server_refs_agent_server UNIQUE (agent_id, mcp_server_id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_workflow_agent_refs_workflow "
        "ON workflow_agent_refs (workflow_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_workflow_agent_refs_agent ON workflow_agent_refs (agent_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_capability_refs_agent ON agent_capability_refs (agent_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_capability_refs_capability "
        "ON agent_capability_refs (capability_id)"
    ),
    "CREATE INDEX IF NOT EXISTS ix_agent_mcp_server_refs_agent ON agent_mcp_server_refs (agent_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_mcp_server_refs_server "
        "ON agent_mcp_server_refs (mcp_server_id)"
    ),
)

_CORE_MEMORY_TABLE_NAMES = {
    "agent_memory_entries",
    "agent_memory_revisions",
    "agent_memory_chunks",
    "run_memory_events",
}
_CORE_MEMORY_PGVECTOR_TABLE_NAMES = {"agent_memory_embeddings"}
_CORE_MEMORY_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS agent_memory_entries (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        memory_id VARCHAR(160) NOT NULL,
        scope_type VARCHAR(40) NOT NULL,
        scope_key VARCHAR(160) NOT NULL,
        kind VARCHAR(80) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        summary TEXT NOT NULL,
        subject_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
        content_hash VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(160),
        created_by_type VARCHAR(40) NOT NULL DEFAULT 'agent',
        source_run_id INTEGER NOT NULL,
        source_agent_key VARCHAR(120) NOT NULL,
        source_agent_version INTEGER NOT NULL,
        source_agent_name VARCHAR(160),
        source_workflow_key VARCHAR(120),
        source_workflow_version INTEGER,
        source_step_id VARCHAR(120),
        source_slot VARCHAR(120),
        source_trace_id VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_agent_memory_entries_memory_id UNIQUE (memory_id),
        CONSTRAINT ck_agent_memory_entries_scope_type CHECK (
            scope_type IN ('workspace', 'package', 'workflow', 'run', 'agent', 'namespace')
        ),
        CONSTRAINT ck_agent_memory_entries_status CHECK (
            status IN ('pending', 'resolved', 'expired')
        ),
        CONSTRAINT ck_agent_memory_entries_content_hash CHECK (
            content_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_entries_subject_refs CHECK (
            jsonb_typeof(subject_refs) = 'array'
        ),
        CONSTRAINT ck_agent_memory_entries_attributes CHECK (
            jsonb_typeof(attributes) = 'object'
        ),
        CONSTRAINT ck_agent_memory_entries_source_run_id_positive CHECK (source_run_id > 0),
        CONSTRAINT ck_agent_memory_entries_source_agent_version_positive CHECK (
            source_agent_version > 0
        ),
        CONSTRAINT ck_agent_memory_entries_source_workflow_version_positive CHECK (
            source_workflow_version IS NULL OR source_workflow_version > 0
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_memory_revisions (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        memory_entry_id INTEGER NOT NULL REFERENCES agent_memory_entries(id) ON DELETE CASCADE,
        revision_id VARCHAR(160) NOT NULL,
        version INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        revision_action VARCHAR(20) NOT NULL DEFAULT 'created',
        summary TEXT NOT NULL,
        content TEXT NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        subject_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
        supersedes_revision_id VARCHAR(160),
        source_run_id INTEGER NOT NULL,
        source_agent_key VARCHAR(120) NOT NULL,
        source_step_id VARCHAR(120),
        source_slot VARCHAR(120),
        trace_span_id VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_agent_memory_revisions_revision_id UNIQUE (revision_id),
        CONSTRAINT uq_agent_memory_revisions_entry_version UNIQUE (memory_entry_id, version),
        CONSTRAINT ck_agent_memory_revisions_version_positive CHECK (version > 0),
        CONSTRAINT ck_agent_memory_revisions_status CHECK (
            status IN ('pending', 'resolved', 'expired')
        ),
        CONSTRAINT ck_agent_memory_revisions_action CHECK (
            revision_action IN ('created', 'reused', 'superseded')
        ),
        CONSTRAINT ck_agent_memory_revisions_content_hash CHECK (
            content_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_revisions_subject_refs CHECK (
            jsonb_typeof(subject_refs) = 'array'
        ),
        CONSTRAINT ck_agent_memory_revisions_attributes CHECK (
            jsonb_typeof(attributes) = 'object'
        ),
        CONSTRAINT ck_agent_memory_revisions_source_run_id_positive CHECK (source_run_id > 0)
    )
    """,
    (
        "ALTER TABLE agent_memory_revisions DROP CONSTRAINT IF EXISTS "
        "uq_agent_memory_revisions_entry_content_hash"
    ),
    """
    CREATE TABLE IF NOT EXISTS agent_memory_chunks (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        memory_entry_id INTEGER NOT NULL REFERENCES agent_memory_entries(id) ON DELETE CASCADE,
        memory_revision_id INTEGER NOT NULL REFERENCES agent_memory_revisions(id) ON DELETE CASCADE,
        memory_id VARCHAR(160) NOT NULL,
        revision_id VARCHAR(160) NOT NULL,
        chunk_id VARCHAR(200) NOT NULL,
        chunk_index INTEGER NOT NULL,
        chunking_version VARCHAR(80) NOT NULL,
        content TEXT NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        source_content_hash VARCHAR(64) NOT NULL,
        token_count INTEGER,
        attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_agent_memory_chunks_chunk_id UNIQUE (chunk_id),
        CONSTRAINT uq_agent_memory_chunks_revision_index UNIQUE (
            memory_revision_id, chunk_index
        ),
        CONSTRAINT ck_agent_memory_chunks_chunk_index_non_negative CHECK (chunk_index >= 0),
        CONSTRAINT ck_agent_memory_chunks_token_count_non_negative CHECK (
            token_count IS NULL OR token_count >= 0
        ),
        CONSTRAINT ck_agent_memory_chunks_content_hash CHECK (
            content_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_chunks_source_content_hash CHECK (
            source_content_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_chunks_attributes CHECK (jsonb_typeof(attributes) = 'object')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_memory_events (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        run_step_id INTEGER REFERENCES run_steps(id) ON DELETE SET NULL,
        run_agent_invocation_id INTEGER REFERENCES run_agent_invocations(id) ON DELETE SET NULL,
        run_operation_invocation_id INTEGER
            REFERENCES run_operation_invocations(id) ON DELETE SET NULL,
        step_id VARCHAR(120),
        invocation_id VARCHAR(160),
        event_type VARCHAR(20) NOT NULL,
        memory_entry_id INTEGER REFERENCES agent_memory_entries(id) ON DELETE SET NULL,
        memory_revision_id INTEGER REFERENCES agent_memory_revisions(id) ON DELETE SET NULL,
        memory_id VARCHAR(160),
        revision_id VARCHAR(160),
        retrieval_mode VARCHAR(40),
        filters JSONB NOT NULL DEFAULT '{}'::jsonb,
        budget JSONB NOT NULL DEFAULT '{}'::jsonb,
        excerpt TEXT,
        injected_text TEXT,
        result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        status_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        trace_span_id VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_run_memory_events_event_type CHECK (
            event_type IN (
                'retrieved', 'injected', 'written', 'reused',
                'superseded', 'reviewed', 'failed'
            )
        ),
        CONSTRAINT ck_run_memory_events_filters CHECK (jsonb_typeof(filters) = 'object'),
        CONSTRAINT ck_run_memory_events_budget CHECK (jsonb_typeof(budget) = 'object'),
        CONSTRAINT ck_run_memory_events_result_snapshot CHECK (
            jsonb_typeof(result_snapshot) = 'object'
        ),
        CONSTRAINT ck_run_memory_events_status_snapshot CHECK (
            jsonb_typeof(status_snapshot) = 'object'
        )
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_entries_scope "
        "ON agent_memory_entries (scope_type, scope_key)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_entries_scope_status_kind "
        "ON agent_memory_entries (scope_type, scope_key, status, kind)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_entries_status_kind "
        "ON agent_memory_entries (status, kind)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_entries_content_hash "
        "ON agent_memory_entries (content_hash)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_entries_source "
        "ON agent_memory_entries (source_run_id, source_agent_key)"
    ),
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_entries_idempotency_key "
        "ON agent_memory_entries (idempotency_key) WHERE idempotency_key IS NOT NULL"
    ),
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_entries_idempotency_fallback "
        "ON agent_memory_entries (scope_type, scope_key, kind, content_hash, source_run_id, "
        "source_agent_key, COALESCE(source_step_id, ''), COALESCE(source_slot, '')) "
        "WHERE idempotency_key IS NULL"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_revisions_entry "
        "ON agent_memory_revisions (memory_entry_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_revisions_content_hash "
        "ON agent_memory_revisions (content_hash)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_revisions_created_at "
        "ON agent_memory_revisions (created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_revisions_supersedes "
        "ON agent_memory_revisions (supersedes_revision_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_entry "
        "ON agent_memory_chunks (memory_entry_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_revision "
        "ON agent_memory_chunks (memory_revision_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_memory_id "
        "ON agent_memory_chunks (memory_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_revision_id "
        "ON agent_memory_chunks (revision_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_content_hash "
        "ON agent_memory_chunks (content_hash)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_chunks_chunking_version "
        "ON agent_memory_chunks (chunking_version)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_run_created_at "
        "ON run_memory_events (run_id, created_at, id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_run_type_created_at "
        "ON run_memory_events (run_id, event_type, created_at)"
    ),
    ("CREATE INDEX IF NOT EXISTS ix_run_memory_events_run_step ON run_memory_events (run_step_id)"),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_agent_invocation "
        "ON run_memory_events (run_agent_invocation_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_operation_invocation "
        "ON run_memory_events (run_operation_invocation_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_memory_entry "
        "ON run_memory_events (memory_entry_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_memory_revision "
        "ON run_memory_events (memory_revision_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_run_memory_events_trace_span "
        "ON run_memory_events (trace_span_id)"
    ),
)
_CORE_MEMORY_PGVECTOR_TABLE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS agent_memory_embeddings (
        id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        memory_chunk_id INTEGER NOT NULL REFERENCES agent_memory_chunks(id) ON DELETE CASCADE,
        memory_entry_id INTEGER NOT NULL REFERENCES agent_memory_entries(id) ON DELETE CASCADE,
        memory_revision_id INTEGER NOT NULL REFERENCES agent_memory_revisions(id) ON DELETE CASCADE,
        memory_id VARCHAR(160) NOT NULL,
        revision_id VARCHAR(160) NOT NULL,
        chunk_id VARCHAR(200) NOT NULL,
        embedding_provider VARCHAR(80),
        embedding_model VARCHAR(200) NOT NULL,
        embedding_dimensions INTEGER NOT NULL,
        embedding VECTOR,
        content_hash VARCHAR(64) NOT NULL,
        chunking_version VARCHAR(80) NOT NULL,
        embedding_config_hash VARCHAR(64),
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        error_message TEXT,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        embedded_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_agent_memory_embeddings_status CHECK (
            status IN ('pending', 'ready', 'stale', 'failed')
        ),
        CONSTRAINT ck_agent_memory_embeddings_dimensions_positive CHECK (
            embedding_dimensions > 0
        ),
        CONSTRAINT ck_agent_memory_embeddings_content_hash CHECK (
            content_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_embeddings_config_hash CHECK (
            embedding_config_hash IS NULL OR embedding_config_hash ~ '^[a-f0-9]{64}$'
        ),
        CONSTRAINT ck_agent_memory_embeddings_ready_has_vector CHECK (
            status <> 'ready' OR embedding IS NOT NULL
        ),
        CONSTRAINT ck_agent_memory_embeddings_metadata CHECK (jsonb_typeof(metadata) = 'object')
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_chunk "
        "ON agent_memory_embeddings (memory_chunk_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_entry "
        "ON agent_memory_embeddings (memory_entry_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_revision "
        "ON agent_memory_embeddings (memory_revision_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_status "
        "ON agent_memory_embeddings (status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_model_status "
        "ON agent_memory_embeddings (embedding_model, status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_embeddings_provenance "
        "ON agent_memory_embeddings "
        "(embedding_model, embedding_dimensions, chunking_version, content_hash)"
    ),
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_embeddings_chunk_provenance "
        "ON agent_memory_embeddings ("
        "memory_chunk_id, COALESCE(embedding_provider, ''), embedding_model, "
        "embedding_dimensions, chunking_version, content_hash, "
        "COALESCE(embedding_config_hash, '')"
        ")"
    ),
)

_RUNTIME_HARD_CUTOVER_DROP_ORDER = (
    "run_forks",
    "run_operation_invocations",
    "run_agent_invocations",
    "run_steps",
    "run_workflow_package_snapshots",
    "runs",
    "agents",
    "workflows",
    "output_schemas",
)
_RUNTIME_HARD_CUTOVER_CREATE_ORDER = (
    "output_schemas",
    "agents",
    "workflows",
    "runs",
    "run_workflow_package_snapshots",
    "run_steps",
    "run_agent_invocations",
    "run_forks",
    "run_operation_invocations",
)
_GLOBAL_AUTHORING_TABLES = (
    "agents",
    "workflows",
    "capabilities",
    "mcp_servers",
    "output_schemas",
)
_REPRESENTABLE_PACKAGE_RUN_SQL = """
run.target_kind = 'workflowPackage'
AND run.workflow_package_id IS NOT NULL
AND run.workflow_package_key IS NOT NULL
AND run.workflow_package_workflow_key IS NOT NULL
AND EXISTS (
    SELECT 1
    FROM run_workflow_package_snapshots AS snapshot
    WHERE snapshot.run_id = run.id
      AND snapshot.workflow_package_id = run.workflow_package_id
      AND snapshot.workflow_package_key = run.workflow_package_key
      AND snapshot.workflow_key = run.workflow_package_workflow_key
)
"""
_GLOBAL_AUTHORING_CLEANUP_REQUIRED_PACKAGE_TABLES = frozenset(
    {"workflow_packages", "run_workflow_package_snapshots"}
)
_GLOBAL_AUTHORING_CLEANUP_REQUIRED_RUN_COLUMNS = frozenset(
    {
        "target_kind",
        "workflow_package_id",
        "workflow_package_key",
        "workflow_package_workflow_key",
    }
)
_RUNTIME_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "output_schemas": frozenset(
        {
            "id",
            "key",
            "version",
            "status",
            "kind",
            "name",
            "description",
            "json_schema",
            "registry_refs",
            "created_at",
            "updated_at",
        }
    ),
    "agents": frozenset(
        {
            "id",
            "key",
            "version",
            "status",
            "name",
            "description",
            "manifest_api_version",
            "manifest_source",
            "manifest_hash",
            "compiler_version",
            "model_connection_id",
            "model_connection_snapshot",
            "model",
            "system_prompt",
            "input_schema",
            "output_schema_id",
            "output_schema_version",
            "capabilities",
            "mcp_servers",
            "created_at",
            "updated_at",
        }
    ),
    "workflows": frozenset(
        {
            "id",
            "key",
            "version",
            "status",
            "name",
            "description",
            "manifest_api_version",
            "manifest_source",
            "input_schema",
            "steps",
            "output_spec",
            "created_at",
            "updated_at",
        }
    ),
    "runs": frozenset(
        {
            "id",
            "agent_id",
            "workflow_id",
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
    ),
    "run_workflow_package_snapshots": frozenset(
        {
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
    ),
    "run_steps": frozenset(
        {
            "id",
            "run_id",
            "step_index",
            "status",
            "origin",
            "source_run_step_id",
            "source_run_id",
            "source_step_index",
            "error",
            "started_at",
            "finished_at",
            "persisted_at",
            "created_at",
            "updated_at",
        }
    ),
    "run_agent_invocations": frozenset(
        {
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
    ),
    "run_forks": frozenset(
        {
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
    ),
    "run_operation_invocations": frozenset(
        {
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
    ),
}
_RUNTIME_REPAIRABLE_RUN_COLUMNS = frozenset(
    {"queued_at", *_RUN_SCHEDULER_METADATA_COLUMNS.keys(), *_RUN_SCHEDULE_PROVENANCE_COLUMNS.keys()}
)
_RUNTIME_CUTOVER_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    table_name: (
        _RUNTIME_REQUIRED_COLUMNS[table_name] - _RUNTIME_REPAIRABLE_RUN_COLUMNS
        if table_name == "runs"
        else _RUNTIME_REQUIRED_COLUMNS[table_name]
    )
    for table_name in (
        "runs",
        "run_workflow_package_snapshots",
        "run_steps",
        "run_agent_invocations",
        "run_forks",
        "run_operation_invocations",
    )
}
_RUNTIME_LEGACY_COLUMNS: dict[str, frozenset[str]] = {
    "runs": frozenset({"workflow_key", "workflow_version", "per_step_outputs"}),
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


def normalize_legacy_model_connection_key(
    *,
    name: str | None,
    model_id: str | None,
) -> str:
    for raw_value in (name, model_id, "model_connection"):
        if raw_value is None:
            continue
        normalized = _MODEL_CONNECTION_KEY_INVALID_CHARS_RE.sub(
            "_",
            str(raw_value).strip().lower(),
        )
        normalized = _MODEL_CONNECTION_KEY_DUPLICATE_UNDERSCORES_RE.sub(
            "_",
            normalized,
        ).strip("_")
        if normalized:
            break
    else:
        normalized = "model_connection"

    if not normalized[0].isalpha():
        normalized = f"model_connection_{normalized}"
    return normalized[:_MODEL_CONNECTION_KEY_MAX_LENGTH].rstrip("_") or "model_connection"


def build_unique_model_connection_key(base_key: str, used_keys: set[str]) -> str:
    suffix = ""
    sequence = 2

    while True:
        max_base_length = _MODEL_CONNECTION_KEY_MAX_LENGTH - len(suffix)
        trimmed_base = base_key[:max_base_length].rstrip("_")
        if not trimmed_base:
            trimmed_base = "model_connection"[:max_base_length].rstrip("_") or "m"

        candidate = f"{trimmed_base}{suffix}"
        if candidate not in used_keys:
            used_keys.add(candidate)
            return candidate

        suffix = f"_{sequence}"
        sequence += 1


def _refresh_table_names(engine: Engine, table_names: set[str]) -> None:
    table_names.clear()
    table_names.update(inspect(engine).get_table_names())


def _constraint_exists(engine: Engine, table_name: str, constraint_name: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.execute(
                text(
                    """
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = CAST(:table_name AS regclass)
                      AND conname = :constraint_name
                    """
                ),
                {"constraint_name": constraint_name, "table_name": table_name},
            ).scalar_one_or_none()
        )


def _drop_constraint_if_exists(
    connection: Connection,
    table_name: str,
    constraint_name: str,
) -> None:
    connection.exec_driver_sql(
        f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
    )


def _ensure_hard_delete_lifecycle_schema(engine: Engine, table_names: set[str]) -> None:
    removed_status = "arch" + "ived"
    removed_archive_index = "_".join(("ix", "workflow", "packages", removed_status, "at"))
    removed_archive_columns = tuple(
        "_".join((removed_status, suffix)) for suffix in ("at", "by", "reason")
    )
    lifecycle_checks = {
        "agents": ("ck_agents_status", "status IN ('draft', 'published', 'deprecated')"),
        "workflows": ("ck_workflows_status", "status IN ('draft', 'published', 'deprecated')"),
        "capabilities": (
            "ck_capabilities_status",
            "status IN ('draft', 'published', 'deprecated')",
        ),
        "mcp_servers": (
            "ck_mcp_servers_status",
            "status IN ('draft', 'published', 'deprecated')",
        ),
        "output_schemas": (
            "ck_output_schemas_status",
            "status IN ('draft', 'published', 'deprecated')",
        ),
        "model_connections": ("ck_model_connections_status", "status IN ('active')"),
    }
    with engine.begin() as connection:
        for table_name, (constraint_name, constraint_sql) in lifecycle_checks.items():
            if table_name in table_names:
                connection.exec_driver_sql(
                    f"DELETE FROM {table_name} WHERE status = '{removed_status}'"
                )
                _drop_constraint_if_exists(connection, table_name, constraint_name)
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} "
                    f"CHECK ({constraint_sql})"
                )
        if "workflow_packages" in table_names:
            workflow_package_columns = {
                column["name"] for column in inspect(engine).get_columns("workflow_packages")
            }
            archived_at_column = removed_archive_columns[0]
            if archived_at_column in workflow_package_columns:
                connection.exec_driver_sql(
                    f"DELETE FROM workflow_packages WHERE {archived_at_column} IS NOT NULL"
                )
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {removed_archive_index}")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_workflow_packages_deleted_at")
            connection.exec_driver_sql("DROP INDEX IF EXISTS uq_workflow_packages_active_key")
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_packages_key "
                "ON workflow_packages (key)"
            )
            for column_name in (
                *removed_archive_columns,
                "deleted_at",
                "deleted_by",
                "deleted_reason",
            ):
                connection.exec_driver_sql(
                    f"ALTER TABLE workflow_packages DROP COLUMN IF EXISTS {column_name}"
                )


def _cutover_capability_storage(engine: Engine, table_names: set[str]) -> None:
    legacy_storage_detected = _legacy_capability_storage_detected(engine, table_names)
    _drop_legacy_capability_tables(engine, table_names)
    _ensure_capability_tool_keys_column(engine, table_names)
    _ensure_agent_capabilities_column(engine, table_names)

    if legacy_storage_detected:
        _delete_all_capabilities_and_clear_agent_refs(engine, table_names)
    else:
        _delete_capabilities_with_stale_tool_keys(engine, table_names)
    _refresh_table_names(engine, table_names)


def _legacy_capability_storage_detected(engine: Engine, table_names: set[str]) -> bool:
    if {"skills", "capability_registry_entries"} & table_names:
        return True

    inspector = inspect(engine)
    if "capabilities" in table_names:
        capability_columns = {column["name"] for column in inspector.get_columns("capabilities")}
        if {"tool_grants", "tool_definitions"} & capability_columns:
            return True
    if "agents" in table_names:
        agent_columns = {column["name"] for column in inspector.get_columns("agents")}
        if "skills" in agent_columns:
            return True
    return False


def _drop_legacy_capability_tables(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        for table_name in ("capability_registry_entries", "skills"):
            _ = connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            table_names.discard(table_name)


def _ensure_capability_tool_keys_column(engine: Engine, table_names: set[str]) -> None:
    if "capabilities" not in table_names:
        return

    capability_columns = {column["name"] for column in inspect(engine).get_columns("capabilities")}
    with engine.begin() as connection:
        if "tool_keys" not in capability_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE capabilities ADD COLUMN tool_keys JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        _ = connection.exec_driver_sql(
            " ".join(
                (
                    "UPDATE capabilities SET tool_keys = '[]'::jsonb",
                    "WHERE tool_keys IS NULL OR jsonb_typeof(tool_keys) <> 'array'",
                )
            )
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE capabilities ALTER COLUMN tool_keys SET DEFAULT '[]'::jsonb"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE capabilities ALTER COLUMN tool_keys SET NOT NULL"
        )
        _ = connection.exec_driver_sql("ALTER TABLE capabilities DROP COLUMN IF EXISTS tool_grants")
        _ = connection.exec_driver_sql(
            "ALTER TABLE capabilities DROP COLUMN IF EXISTS tool_definitions"
        )


def _ensure_agent_capabilities_column(engine: Engine, table_names: set[str]) -> None:
    if "agents" not in table_names:
        return

    agent_columns = {column["name"] for column in inspect(engine).get_columns("agents")}
    with engine.begin() as connection:
        if "capabilities" not in agent_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE agents ADD COLUMN capabilities JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        _ = connection.exec_driver_sql(
            "UPDATE agents SET capabilities = '[]'::jsonb WHERE capabilities IS NULL"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE agents ALTER COLUMN capabilities SET DEFAULT '[]'::jsonb"
        )
        _ = connection.exec_driver_sql("ALTER TABLE agents ALTER COLUMN capabilities SET NOT NULL")
        _ = connection.exec_driver_sql("ALTER TABLE agents DROP COLUMN IF EXISTS skills")


def _delete_all_capabilities_and_clear_agent_refs(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        if "agents" in table_names:
            _ = connection.exec_driver_sql("UPDATE agents SET capabilities = '[]'::jsonb")
        if "capabilities" in table_names:
            _ = connection.exec_driver_sql("DELETE FROM capabilities")


def _delete_capabilities_with_stale_tool_keys(engine: Engine, table_names: set[str]) -> None:
    if "capabilities" not in table_names:
        return

    known_tool_keys = sorted(SERVER_DECLARED_TOOL_REGISTRY)
    with engine.begin() as connection:
        stale_count = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM capabilities AS capability
                    WHERE EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(capability.tool_keys) AS tool_key(value)
                        WHERE jsonb_typeof(tool_key.value) <> 'string'
                           OR tool_key.value #>> '{}' <> ALL(:known_tool_keys)
                    )
                    """
                ),
                {"known_tool_keys": known_tool_keys},
            ).scalar_one()
        )
        if not stale_count:
            return
        if "agents" in table_names:
            _ = connection.exec_driver_sql("UPDATE agents SET capabilities = '[]'::jsonb")
        _ = connection.execute(
            text(
                """
                DELETE FROM capabilities AS capability
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(capability.tool_keys) AS tool_key(value)
                    WHERE jsonb_typeof(tool_key.value) <> 'string'
                       OR tool_key.value #>> '{}' <> ALL(:known_tool_keys)
                )
                """
            ),
            {"known_tool_keys": known_tool_keys},
        )


def _extension_state_order_terms(column_names: set[str]) -> str:
    state_version_order = (
        "state_version DESC NULLS LAST" if "state_version" in column_names else "0 DESC"
    )
    updated_at_order = "updated_at DESC NULLS LAST" if "updated_at" in column_names else "NULL DESC"
    created_at_order = "created_at DESC NULLS LAST" if "created_at" in column_names else "NULL DESC"
    id_order = "id DESC NULLS LAST" if "id" in column_names else "0 DESC"
    return ", ".join(
        (
            state_version_order,
            updated_at_order,
            created_at_order,
            id_order,
            "COALESCE(enabled, TRUE) ASC",
            "extension_key ASC",
        )
    )


def _normalize_existing_extension_state_table(
    connection: Connection,
    column_names: set[str],
) -> None:
    _ = connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{_EXTENSION_STATE_CANONICAL_TABLE}"')
    _ = connection.exec_driver_sql(_EXTENSION_STATE_CREATE_CANONICAL_TABLE_SQL)

    if {"extension_key", "enabled"} <= column_names:
        order_terms = _extension_state_order_terms(column_names)
        _ = connection.exec_driver_sql(
            f"""
            INSERT INTO "{_EXTENSION_STATE_CANONICAL_TABLE}" (extension_key, enabled)
            SELECT extension_key, enabled
            FROM (
                SELECT
                    extension_key,
                    COALESCE(enabled, TRUE) AS enabled,
                    ROW_NUMBER() OVER (
                        PARTITION BY extension_key
                        ORDER BY {order_terms}
                    ) AS row_priority
                FROM extension_states
                WHERE extension_key IS NOT NULL
                  AND btrim(extension_key) <> ''
            ) AS ranked_states
            WHERE row_priority = 1
            """
        )

    _ = connection.exec_driver_sql('DROP TABLE IF EXISTS "extension_states" CASCADE')
    _ = connection.exec_driver_sql(
        f'ALTER TABLE "{_EXTENSION_STATE_CANONICAL_TABLE}" RENAME TO extension_states'
    )
    _ = connection.exec_driver_sql(
        f'ALTER TABLE extension_states RENAME CONSTRAINT "{_EXTENSION_STATE_TEMP_PRIMARY_KEY}" '
        f'TO "{_EXTENSION_STATE_PRIMARY_KEY}"'
    )


def _ensure_extension_state_table(engine: Engine, table_names: set[str]) -> None:
    column_names: set[str] = set()
    if "extension_states" in table_names:
        column_names = {
            str(column["name"]) for column in inspect(engine).get_columns("extension_states")
        }
    with engine.begin() as connection:
        if "extension_states" in table_names:
            _normalize_existing_extension_state_table(connection, column_names)
        else:
            _ = connection.exec_driver_sql(_EXTENSION_STATE_CREATE_TABLE_SQL)

        for extension in get_bundled_extension_registry().list_extensions():
            _ = connection.execute(
                text(
                    """
                    INSERT INTO extension_states (extension_key, enabled)
                    VALUES (:extension_key, :enabled)
                    ON CONFLICT (extension_key) DO NOTHING
                    """
                ),
                {"extension_key": extension.key, "enabled": extension.default_enabled},
            )
    table_names.add("extension_states")


def _ensure_workflow_package_tables(engine: Engine, table_names: set[str]) -> None:
    table_statements = _WORKFLOW_PACKAGE_TABLE_STATEMENTS[:2]
    index_statements = _WORKFLOW_PACKAGE_TABLE_STATEMENTS[2:]
    with engine.begin() as connection:
        for statement in table_statements:
            connection.exec_driver_sql(statement)
    table_names.update(
        {
            "workflow_packages",
            "workflow_package_secret_bindings",
        }
    )
    _drop_removed_package_history_schema(engine, table_names)
    _ensure_workflow_package_current_artifact_columns(engine, table_names)
    with engine.begin() as connection:
        for statement in index_statements:
            connection.exec_driver_sql(statement)


def _ensure_runtime_input_registry_table(engine: Engine, table_names: set[str]) -> None:
    required_parents = {"workflow_packages", "runs"}
    if not required_parents <= table_names:
        return

    with engine.begin() as connection:
        for statement in _RUNTIME_INPUT_REGISTRY_TABLE_STATEMENTS:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "DELETE FROM workflow_package_runtime_input_entries AS entry "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM workflow_packages AS pkg "
            "WHERE pkg.id = entry.package_id"
            ")"
        )
        connection.exec_driver_sql(
            "UPDATE workflow_package_runtime_input_entries AS entry "
            "SET source_run_id = NULL "
            "WHERE source_run_id IS NOT NULL "
            "AND NOT EXISTS ("
            "SELECT 1 FROM runs AS run WHERE run.id = entry.source_run_id"
            ")"
        )
        for constraint_name in (
            _RUNTIME_INPUT_REGISTRY_PACKAGE_FK,
            "workflow_package_runtime_input_entries_package_id_fkey",
        ):
            _drop_constraint_if_exists(
                connection,
                _RUNTIME_INPUT_REGISTRY_TABLE_NAME,
                constraint_name,
            )
        connection.exec_driver_sql(
            "ALTER TABLE workflow_package_runtime_input_entries "
            f"ADD CONSTRAINT {_RUNTIME_INPUT_REGISTRY_PACKAGE_FK} "
            "FOREIGN KEY (package_id) "
            "REFERENCES workflow_packages(id) ON DELETE CASCADE"
        )
        for constraint_name in (
            _RUNTIME_INPUT_REGISTRY_SOURCE_RUN_FK,
            "workflow_package_runtime_input_entries_source_run_id_fkey",
        ):
            _drop_constraint_if_exists(
                connection,
                _RUNTIME_INPUT_REGISTRY_TABLE_NAME,
                constraint_name,
            )
        connection.exec_driver_sql(
            "ALTER TABLE workflow_package_runtime_input_entries "
            f"ADD CONSTRAINT {_RUNTIME_INPUT_REGISTRY_SOURCE_RUN_FK} "
            "FOREIGN KEY (source_run_id) "
            "REFERENCES runs(id) ON DELETE SET NULL"
        )
    table_names.add(_RUNTIME_INPUT_REGISTRY_TABLE_NAME)


def _schedule_provenance_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return to_utc(value).isoformat().replace("+00:00", "Z")


def _load_rows_by_id(
    connection: Connection,
    *,
    table_name: str,
    columns: tuple[str, ...],
    ids: set[int],
) -> dict[int, Mapping[str, object]]:
    if not ids:
        return {}

    rows = cast(
        list[Mapping[str, object]],
        connection.execute(
            text(
                f"SELECT {', '.join(columns)} FROM {table_name} WHERE id IN :ids ORDER BY id"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": sorted(ids)},
        )
        .mappings()
        .all(),
    )
    return {cast(int, row["id"]): row for row in rows}


def _load_run_schedule_contexts(connection: Connection) -> list[dict[str, object]]:
    run_rows = cast(
        list[Mapping[str, object]],
        connection.execute(
            text(
                """
                SELECT id, schedule_id, schedule_fire_id, schedule_reason,
                       scheduled_for, schedule_provenance
                FROM runs
                WHERE schedule_id IS NOT NULL OR schedule_fire_id IS NOT NULL
                ORDER BY id
                """
            )
        )
        .mappings()
        .all(),
    )
    fire_rows = _load_rows_by_id(
        connection,
        table_name="workflow_package_schedule_fires",
        columns=(
            "id",
            "schedule_id",
            "fire_key",
            "reason",
            "scheduled_for",
            "scheduled_local_date",
            "scheduled_local_time",
            "scheduled_local_datetime",
            "materialized_at",
        ),
        ids={
            cast(int, row["schedule_fire_id"])
            for row in run_rows
            if row["schedule_fire_id"] is not None
        },
    )
    schedule_ids = {
        cast(int, row["schedule_id"]) for row in run_rows if row["schedule_id"] is not None
    }
    schedule_ids.update(
        cast(int, row["schedule_id"])
        for row in fire_rows.values()
        if row["schedule_id"] is not None
    )
    schedule_rows = _load_rows_by_id(
        connection,
        table_name="workflow_package_schedules",
        columns=("id", "package_id", "workflow_key", "name", "timezone", "recurrence"),
        ids=schedule_ids,
    )
    package_rows = _load_rows_by_id(
        connection,
        table_name="workflow_packages",
        columns=("id", "key"),
        ids={
            cast(int, row["package_id"])
            for row in schedule_rows.values()
            if row["package_id"] is not None
        },
    )

    contexts: list[dict[str, object]] = []
    for run_row in run_rows:
        fire_row = None
        if run_row["schedule_fire_id"] is not None:
            fire_row = fire_rows.get(cast(int, run_row["schedule_fire_id"]))

        schedule_row = None
        if run_row["schedule_id"] is not None:
            schedule_row = schedule_rows.get(cast(int, run_row["schedule_id"]))
        if schedule_row is None and fire_row is not None and fire_row["schedule_id"] is not None:
            schedule_row = schedule_rows.get(cast(int, fire_row["schedule_id"]))

        package_row = None
        if schedule_row is not None and schedule_row["package_id"] is not None:
            package_row = package_rows.get(cast(int, schedule_row["package_id"]))

        contexts.append(
            {
                "run": run_row,
                "fire": fire_row,
                "schedule": schedule_row,
                "package": package_row,
            }
        )
    return contexts


def _build_run_schedule_provenance(
    *,
    run_row: Mapping[str, object],
    fire_row: Mapping[str, object] | None,
    schedule_row: Mapping[str, object] | None,
    package_row: Mapping[str, object] | None,
    schedule_deleted_at: str | None = None,
) -> dict[str, object] | None:
    existing_provenance = (
        cast(Mapping[str, object], _jsonb_payload(run_row["schedule_provenance"]))
        if run_row["schedule_provenance"] is not None
        else None
    )
    if schedule_row is None and fire_row is None:
        return None

    deleted_at_value = (
        cast(str | None, existing_provenance.get("scheduleDeletedAt"))
        if existing_provenance is not None
        else None
    )
    if deleted_at_value is None:
        deleted_at_value = schedule_deleted_at

    scheduled_for = run_row["scheduled_for"]
    reason = run_row["schedule_reason"]
    if fire_row is not None:
        if fire_row["scheduled_for"] is not None:
            scheduled_for = fire_row["scheduled_for"]
        if fire_row["reason"] is not None:
            reason = fire_row["reason"]

    schedule_id = None
    if schedule_row is not None:
        schedule_id = schedule_row["id"]
    elif fire_row is not None:
        schedule_id = fire_row["schedule_id"]

    recurrence = None
    if schedule_row is not None and schedule_row["recurrence"] is not None:
        recurrence = _jsonb_payload(schedule_row["recurrence"])

    return {
        "scheduleId": schedule_id,
        "scheduleFireId": fire_row["id"] if fire_row is not None else None,
        "scheduleName": schedule_row["name"] if schedule_row is not None else None,
        "packageId": schedule_row["package_id"] if schedule_row is not None else None,
        "packageKey": package_row["key"] if package_row is not None else None,
        "workflowKey": schedule_row["workflow_key"] if schedule_row is not None else None,
        "timezone": schedule_row["timezone"] if schedule_row is not None else None,
        "recurrence": recurrence,
        "fireKey": fire_row["fire_key"] if fire_row is not None else None,
        "reason": reason,
        "scheduledFor": _schedule_provenance_timestamp(cast(datetime | None, scheduled_for)),
        "scheduledLocalDate": (fire_row["scheduled_local_date"] if fire_row is not None else None),
        "scheduledLocalTime": (fire_row["scheduled_local_time"] if fire_row is not None else None),
        "scheduledLocalDateTime": (
            fire_row["scheduled_local_datetime"] if fire_row is not None else None
        ),
        "materializedAt": _schedule_provenance_timestamp(
            cast(datetime | None, fire_row["materialized_at"]) if fire_row is not None else None
        ),
        "scheduleDeletedAt": deleted_at_value,
    }


def _backfill_run_schedule_provenance(connection: Connection) -> None:
    for context in _load_run_schedule_contexts(connection):
        run_row = cast(Mapping[str, object], context["run"])
        fire_row = cast(Mapping[str, object] | None, context["fire"])
        schedule_row = cast(Mapping[str, object] | None, context["schedule"])
        package_row = cast(Mapping[str, object] | None, context["package"])

        schedule_provenance = _build_run_schedule_provenance(
            run_row=run_row,
            fire_row=fire_row,
            schedule_row=schedule_row,
            package_row=package_row,
        )
        if schedule_provenance is None:
            continue
        if _jsonb_payload(run_row["schedule_provenance"]) == schedule_provenance:
            continue

        connection.execute(
            text(
                """
                UPDATE runs
                SET schedule_provenance = CAST(:schedule_provenance AS jsonb)
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_row["id"],
                "schedule_provenance": json.dumps(schedule_provenance, sort_keys=True),
            },
        )


def _null_unresolved_run_schedule_refs(connection: Connection) -> None:
    connection.exec_driver_sql(
        "UPDATE runs SET schedule_id = NULL "
        "WHERE schedule_id IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM workflow_package_schedules AS schedule "
        "WHERE schedule.id = runs.schedule_id"
        ")"
    )
    connection.exec_driver_sql(
        "UPDATE runs SET schedule_fire_id = NULL "
        "WHERE schedule_fire_id IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM workflow_package_schedule_fires AS fire "
        "WHERE fire.id = runs.schedule_fire_id"
        ")"
    )


def _delete_legacy_workflow_package_schedules_with_run_retention(
    connection: Connection,
    schedule_columns: set[str],
) -> None:
    delete_predicates = [
        "NOT EXISTS ("
        "SELECT 1 FROM workflow_packages AS package "
        "WHERE package.id = schedule.package_id"
        ")"
    ]
    archived_predicates = ["schedule.status = 'archived'"]
    if "archived_at" in schedule_columns:
        archived_predicates.append("schedule.archived_at IS NOT NULL")
    delete_predicates.append(f"({' OR '.join(archived_predicates)})")
    schedule_ids = cast(
        list[int],
        connection.execute(
            text(
                f"""
                SELECT schedule.id
                FROM workflow_package_schedules AS schedule
                WHERE {' OR '.join(delete_predicates)}
                ORDER BY schedule.id
                """
            )
        )
        .scalars()
        .all(),
    )
    if not schedule_ids:
        return

    deleted_at = _schedule_provenance_timestamp(utcnow())
    delete_schedule_id_set = set(schedule_ids)
    for context in _load_run_schedule_contexts(connection):
        run_row = cast(Mapping[str, object], context["run"])
        fire_row = cast(Mapping[str, object] | None, context["fire"])
        schedule_row = cast(Mapping[str, object] | None, context["schedule"])
        package_row = cast(Mapping[str, object] | None, context["package"])

        effective_schedule_id = None
        if schedule_row is not None:
            effective_schedule_id = cast(int, schedule_row["id"])
        elif fire_row is not None and fire_row["schedule_id"] is not None:
            effective_schedule_id = cast(int, fire_row["schedule_id"])
        if effective_schedule_id not in delete_schedule_id_set:
            continue

        schedule_provenance = _build_run_schedule_provenance(
            run_row=run_row,
            fire_row=fire_row,
            schedule_row=schedule_row,
            package_row=package_row,
            schedule_deleted_at=deleted_at,
        )
        if schedule_provenance is None:
            continue

        connection.execute(
            text(
                """
                UPDATE runs
                SET schedule_id = NULL,
                    schedule_fire_id = NULL,
                    schedule_provenance = CAST(:schedule_provenance AS jsonb)
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_row["id"],
                "schedule_provenance": json.dumps(schedule_provenance, sort_keys=True),
            },
        )

    connection.execute(
        text(
            """
            DELETE FROM workflow_package_schedules
            WHERE id IN :schedule_ids
            """
        ).bindparams(bindparam("schedule_ids", expanding=True)),
        {"schedule_ids": schedule_ids},
    )


def _ensure_workflow_package_schedule_tables(engine: Engine, table_names: set[str]) -> None:
    if not {"workflow_packages", "runs"} <= table_names:
        return

    table_statements = _WORKFLOW_PACKAGE_SCHEDULE_TABLE_STATEMENTS[:2]
    index_statements = _WORKFLOW_PACKAGE_SCHEDULE_TABLE_STATEMENTS[2:]
    with engine.begin() as connection:
        for statement in table_statements:
            connection.exec_driver_sql(statement)
    table_names.update(_WORKFLOW_PACKAGE_SCHEDULE_TABLE_NAMES)

    inspector = inspect(engine)
    schedule_columns = {
        column["name"] for column in inspector.get_columns("workflow_package_schedules")
    }
    fire_columns = {
        column["name"] for column in inspector.get_columns("workflow_package_schedule_fires")
    }
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    fire_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("workflow_package_schedule_fires")
        if constraint.get("name")
    }

    with engine.begin() as connection:
        for column_name, column_type in _WORKFLOW_PACKAGE_SCHEDULE_COLUMNS.items():
            if column_name not in schedule_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE workflow_package_schedules ADD COLUMN {column_name} {column_type}"
                )
                schedule_columns.add(column_name)
        for column_name, column_type in _WORKFLOW_PACKAGE_SCHEDULE_FIRE_COLUMNS.items():
            if column_name not in fire_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE workflow_package_schedule_fires "
                    f"ADD COLUMN {column_name} {column_type}"
                )
                fire_columns.add(column_name)
        for column_name, column_type in _RUN_SCHEDULE_PROVENANCE_COLUMNS.items():
            if column_name not in run_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD COLUMN {column_name} {column_type}"
                )
                run_columns.add(column_name)

    with engine.begin() as connection:
        _backfill_run_schedule_provenance(connection)
        _null_unresolved_run_schedule_refs(connection)
        connection.exec_driver_sql(
            "UPDATE runs SET schedule_reason = NULL "
            "WHERE schedule_reason IS NOT NULL "
            "AND schedule_reason NOT IN ('scheduled', 'manual')"
        )

        _drop_constraint_if_exists(connection, "runs", "ck_runs_schedule_reason")
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT ck_runs_schedule_reason "
            "CHECK (schedule_reason IS NULL OR schedule_reason IN ('scheduled', 'manual'))"
        )
        for constraint_name in ("fk_runs_schedule_id", "runs_schedule_id_fkey"):
            _drop_constraint_if_exists(connection, "runs", constraint_name)
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT fk_runs_schedule_id "
            "FOREIGN KEY (schedule_id) "
            "REFERENCES workflow_package_schedules(id) ON DELETE SET NULL"
        )
        for constraint_name in ("fk_runs_schedule_fire_id", "runs_schedule_fire_id_fkey"):
            _drop_constraint_if_exists(connection, "runs", constraint_name)
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT fk_runs_schedule_fire_id "
            "FOREIGN KEY (schedule_fire_id) "
            "REFERENCES workflow_package_schedule_fires(id) ON DELETE SET NULL"
        )

        _delete_legacy_workflow_package_schedules_with_run_retention(
            connection,
            schedule_columns,
        )
        if "archived_at" in schedule_columns:
            connection.exec_driver_sql(
                "ALTER TABLE workflow_package_schedules DROP COLUMN IF EXISTS archived_at"
            )
            schedule_columns.discard("archived_at")

        connection.exec_driver_sql(
            "DELETE FROM workflow_package_schedule_fires AS fire "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM workflow_package_schedules AS schedule "
            "WHERE schedule.id = fire.schedule_id"
            ")"
        )
        _null_unresolved_run_schedule_refs(connection)

        for table_name, constraint_name, constraint_sql in _WORKFLOW_PACKAGE_SCHEDULE_CHECKS:
            _drop_constraint_if_exists(connection, table_name, constraint_name)
            connection.exec_driver_sql(
                f"ALTER TABLE {table_name} ADD CONSTRAINT {constraint_name} CHECK ({constraint_sql})"
            )
        if "uq_workflow_package_schedule_fires_schedule_fire_key" not in fire_unique_constraints:
            connection.exec_driver_sql(
                "ALTER TABLE workflow_package_schedule_fires "
                "ADD CONSTRAINT uq_workflow_package_schedule_fires_schedule_fire_key "
                "UNIQUE (schedule_id, fire_key)"
            )
        for constraint_name in (
            "fk_workflow_package_schedules_package_id",
            "workflow_package_schedules_package_id_fkey",
        ):
            _drop_constraint_if_exists(connection, "workflow_package_schedules", constraint_name)
        connection.exec_driver_sql(
            "ALTER TABLE workflow_package_schedules "
            "ADD CONSTRAINT fk_workflow_package_schedules_package_id "
            "FOREIGN KEY (package_id) REFERENCES workflow_packages(id) ON DELETE CASCADE"
        )
        for constraint_name in (
            "fk_workflow_package_schedule_fires_schedule_id",
            "workflow_package_schedule_fires_schedule_id_fkey",
        ):
            _drop_constraint_if_exists(
                connection,
                "workflow_package_schedule_fires",
                constraint_name,
            )
        connection.exec_driver_sql(
            "ALTER TABLE workflow_package_schedule_fires "
            "ADD CONSTRAINT fk_workflow_package_schedule_fires_schedule_id "
            "FOREIGN KEY (schedule_id) "
            "REFERENCES workflow_package_schedules(id) ON DELETE CASCADE"
        )
        for statement in (*index_statements, *_RUN_SCHEDULE_PROVENANCE_INDEXES):
            connection.exec_driver_sql(statement)


def _drop_removed_package_history_schema(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        if "workflow_packages" in table_names:
            for constraint_name in (
                "fk_workflow_packages_" + "latest_" + "version_" + "id",
                "workflow_packages_" + "latest_" + "version_" + "id_fkey",
            ):
                _drop_constraint_if_exists(connection, "workflow_packages", constraint_name)
            removed_pointer_column = "latest_" + "version_" + "id"
            connection.exec_driver_sql(
                "ALTER TABLE workflow_packages "
                f"DROP COLUMN IF EXISTS {removed_pointer_column} CASCADE"
            )
            connection.exec_driver_sql(
                "ALTER TABLE workflow_packages DROP COLUMN IF EXISTS draft_source CASCADE"
            )
        for table_name in (
            "workflow_package_" + "version_model_connections",
            "workflow_package_" + "versions",
        ):
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            table_names.discard(table_name)


def _ensure_workflow_package_current_artifact_columns(
    engine: Engine,
    table_names: set[str],
) -> None:
    if "workflow_packages" not in table_names:
        return

    package_columns = {
        column["name"] for column in inspect(engine).get_columns("workflow_packages")
    }
    column_definitions = {
        "manifest_source": "TEXT",
        "manifest_hash": "VARCHAR(64)",
        "package_definition": "JSONB",
        "compiled_plan": "JSONB",
        "compiled_hash": "VARCHAR(64)",
        "extension_dependencies": "JSONB DEFAULT '[]'::jsonb",
    }
    removed_state_columns = {
        "_".join(("last", "launched", "at")),
        "_".join(("validation", "summary")),
    }
    obsolete_columns = removed_state_columns & package_columns
    required_artifact_columns = {
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
    }

    with engine.begin() as connection:
        if obsolete_columns:
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_workflow_packages_last_launched_at")
        for column_name in sorted(obsolete_columns):
            connection.exec_driver_sql(
                f"ALTER TABLE workflow_packages DROP COLUMN IF EXISTS {column_name}"
            )
            package_columns.discard(column_name)
        if "status" in package_columns:
            _drop_constraint_if_exists(
                connection,
                "workflow_packages",
                "ck_workflow_packages_status",
            )
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_workflow_packages_status")
            connection.exec_driver_sql(
                "ALTER TABLE workflow_packages DROP COLUMN IF EXISTS status CASCADE"
            )
            package_columns.discard("status")
        connection.exec_driver_sql("DROP INDEX IF EXISTS uq_workflow_packages_active_key")
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_packages_key ON workflow_packages (key)"
        )
        for column_name, column_type in column_definitions.items():
            if column_name not in package_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE workflow_packages ADD COLUMN {column_name} {column_type}"
                )
                package_columns.add(column_name)
        connection.exec_driver_sql(
            """
            DELETE FROM workflow_packages
            WHERE manifest_source IS NULL
               OR manifest_hash IS NULL
               OR package_definition IS NULL
               OR compiled_plan IS NULL
               OR compiled_hash IS NULL
            """
        )
        connection.exec_driver_sql(
            "UPDATE workflow_packages SET extension_dependencies = '[]'::jsonb "
            "WHERE extension_dependencies IS NULL "
            "OR jsonb_typeof(extension_dependencies) <> 'array'"
        )
        for column_name in sorted(required_artifact_columns):
            connection.exec_driver_sql(
                f"ALTER TABLE workflow_packages ALTER COLUMN {column_name} SET NOT NULL"
            )
        connection.exec_driver_sql(
            "ALTER TABLE workflow_packages ALTER COLUMN extension_dependencies "
            "SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE workflow_packages ALTER COLUMN extension_dependencies SET NOT NULL"
        )


def _preset_package_sql_path() -> Path:
    return Path(__file__).with_name(_PRESET_PACKAGE_SQL_FILE)


def _ensure_db_upgrade_marker_table(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {_DB_UPGRADE_MARKER_TABLE} (
                key VARCHAR(120) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    table_names.add(_DB_UPGRADE_MARKER_TABLE)


def _upgrade_marker_applied(connection: Connection, marker_key: str) -> bool:
    return bool(
        connection.execute(
            text(f"SELECT 1 FROM {_DB_UPGRADE_MARKER_TABLE} WHERE key = :marker_key"),
            {"marker_key": marker_key},
        ).scalar_one_or_none()
    )


def _mark_upgrade_applied(connection: Connection, marker_key: str) -> None:
    connection.execute(
        text(
            f"""
            INSERT INTO {_DB_UPGRADE_MARKER_TABLE} (key)
            VALUES (:marker_key)
            ON CONFLICT (key) DO NOTHING
            """
        ),
        {"marker_key": marker_key},
    )


def _ensure_report_agent_memory_cleanup_columns(engine: Engine, table_names: set[str]) -> None:
    if "reports" not in table_names:
        return

    report_columns = {column["name"] for column in inspect(engine).get_columns("reports")}
    with engine.begin() as connection:
        if "source" not in report_columns:
            connection.exec_driver_sql(
                "ALTER TABLE reports ADD COLUMN source VARCHAR(20) DEFAULT 'compiled' NOT NULL"
            )
        if "metadata" not in report_columns:
            connection.exec_driver_sql(
                "ALTER TABLE reports ADD COLUMN metadata JSONB DEFAULT '{}' NOT NULL"
            )


def _workflow_package_run_artifact_filter_sql(
    *,
    run_columns: set[str],
    table_names: set[str],
) -> str:
    filters: list[str] = []
    if "target_kind" in run_columns:
        filters.append("run.target_kind = 'workflowPackage'")
    if "workflow_package_id" in run_columns:
        filters.append("run.workflow_package_id IS NOT NULL")
    if "workflow_package_key" in run_columns:
        filters.append("run.workflow_package_key IS NOT NULL")
    if "run_workflow_package_snapshots" in table_names:
        filters.append(
            "EXISTS ("
            "SELECT 1 FROM run_workflow_package_snapshots AS snapshot "
            "WHERE snapshot.run_id = run.id"
            ")"
        )
    if not filters:
        return "FALSE"
    return " OR ".join(f"({filter_sql})" for filter_sql in filters)


def _purge_workflow_package_run_artifacts(
    connection: Connection,
    *,
    table_names: set[str],
    run_columns: set[str],
) -> None:
    run_filter_sql = _workflow_package_run_artifact_filter_sql(
        run_columns=run_columns,
        table_names=table_names,
    )
    if run_filter_sql == "FALSE":
        return

    connection.exec_driver_sql("DROP TABLE IF EXISTS workflow_package_cutover_run_ids")
    connection.exec_driver_sql(
        f"""
        CREATE TEMPORARY TABLE workflow_package_cutover_run_ids ON COMMIT DROP AS
        SELECT DISTINCT run.id
        FROM runs AS run
        WHERE {run_filter_sql}
        """
    )
    stale_run_count = connection.exec_driver_sql(
        "SELECT COUNT(*) FROM workflow_package_cutover_run_ids"
    ).scalar_one()
    if not stale_run_count:
        connection.exec_driver_sql("DROP TABLE workflow_package_cutover_run_ids")
        return

    if "reports" in table_names:
        connection.exec_driver_sql(
            """
            DELETE FROM reports AS report
            USING workflow_package_cutover_run_ids AS stale_run
            WHERE report.source = 'agent'
              AND jsonb_typeof(report.metadata) = 'object'
              AND jsonb_typeof(report.metadata -> 'analysis') = 'object'
              AND report.metadata -> 'analysis' ->> 'reviewType' = 'agent_memory'
              AND (report.metadata -> 'analysis' ->> 'runId') ~ '^[0-9]+$'
              AND (report.metadata -> 'analysis' ->> 'runId')::integer = stale_run.id
            """
        )

    for table_name in (
        "run_operation_invocations",
        "run_agent_invocations",
        "run_steps",
        "run_workflow_package_snapshots",
    ):
        if table_name in table_names:
            connection.exec_driver_sql(
                f"""
                DELETE FROM {table_name}
                WHERE run_id IN (SELECT id FROM workflow_package_cutover_run_ids)
                """
            )

    connection.exec_driver_sql(
        """
        DELETE FROM runs
        WHERE id IN (SELECT id FROM workflow_package_cutover_run_ids)
        """
    )
    connection.exec_driver_sql("DROP TABLE workflow_package_cutover_run_ids")


def _jsonb_payload(value: object) -> object:
    if isinstance(value, str):
        return cast(object, json.loads(value))
    return value


def _browser_proven_package_preset_needs_reseed(connection: Connection) -> bool:
    row = (
        connection.execute(
            text(
                """
                SELECT manifest_source, manifest_hash, package_definition,
                       compiled_plan, compiled_hash
                FROM workflow_packages
                WHERE key = :package_key
                """
            ),
            {"package_key": _PRESET_PACKAGE_KEY},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return True

    if (
        row["manifest_hash"] != _PRESET_PACKAGE_MANIFEST_HASH
        or row["compiled_hash"] != _PRESET_PACKAGE_COMPILED_HASH
    ):
        return True

    try:
        package_definition = _jsonb_payload(row["package_definition"])
        compiled_plan = _jsonb_payload(row["compiled_plan"])
        WorkflowPackageManifest.model_validate(package_definition)
    except (TypeError, ValueError, ValidationError):
        return True

    serialized_preset = (
        str(row["manifest_source"])
        + json.dumps(package_definition, sort_keys=True)
        + json.dumps(compiled_plan, sort_keys=True)
    )
    removed_budget_field = "budget" + "Usd"
    return removed_budget_field in serialized_preset


def _insert_browser_proven_package_preset(connection: Connection, preset_sql_path: Path) -> None:
    connection.exec_driver_sql(preset_sql_path.read_text(encoding="utf-8"))


def _browser_proven_package_preset_schedule_definitions(
    package_definition: object,
    compiled_plan: object,
) -> tuple[dict[str, object], ...]:
    workflow_descriptions: dict[str, str | None] = {}

    def _collect_descriptions(payload: object) -> None:
        if not isinstance(payload, Mapping):
            return
        spec = payload.get("spec")
        if isinstance(spec, Mapping):
            workflows = spec.get("workflows")
            if isinstance(workflows, list):
                for workflow in workflows:
                    if not isinstance(workflow, Mapping) or workflow.get("key") is None:
                        continue
                    workflow_descriptions[str(workflow["key"])] = cast(
                        str | None,
                        workflow.get("description"),
                    )
        workflows = payload.get("workflows")
        if isinstance(workflows, list):
            for workflow in workflows:
                if not isinstance(workflow, Mapping) or workflow.get("key") is None:
                    continue
                workflow_descriptions.setdefault(
                    str(workflow["key"]),
                    cast(str | None, workflow.get("description")),
                )

    _collect_descriptions(package_definition)
    _collect_descriptions(compiled_plan)

    return tuple(
        {
            "workflow_key": spec["workflow_key"],
            "name": spec["name"],
            "description": workflow_descriptions.get(str(spec["workflow_key"])),
            "timezone": _PRESET_PACKAGE_SCHEDULE_DEFAULTS["timezone"],
            "recurrence": _PRESET_PACKAGE_SCHEDULE_RECURRENCE,
            "overlap_policy": _PRESET_PACKAGE_SCHEDULE_DEFAULTS["overlap_policy"],
            "misfire_policy": _PRESET_PACKAGE_SCHEDULE_DEFAULTS["misfire_policy"],
            "misfire_grace_seconds": _PRESET_PACKAGE_SCHEDULE_DEFAULTS["misfire_grace_seconds"],
            "input_template": spec["input_template"],
            "template_vars": {},
        }
        for spec in _PRESET_PACKAGE_SCHEDULE_SPECS
    )


def _browser_proven_package_preset_schedule_next_fire_at(
    *,
    created_at: datetime,
    starts_at: datetime | None,
    ends_at: datetime | None,
    reference_now: datetime,
) -> datetime | None:
    delta = timedelta(minutes=2)
    now = to_utc(reference_now)
    compare_at = to_utc(starts_at) if starts_at is not None and to_utc(starts_at) > now else now
    first = to_utc(starts_at or created_at) + delta
    candidate = first
    if first < compare_at:
        candidate = first + (delta * (int((compare_at - first) // delta) + 1))
    if ends_at is not None and candidate > to_utc(ends_at):
        return None
    return candidate


def _ensure_browser_proven_package_preset_schedules(connection: Connection) -> None:
    preset_row = (
        connection.execute(
            text(
                """
                SELECT id, package_definition, compiled_plan
                FROM workflow_packages
                WHERE key = :package_key
                """
            ),
            {"package_key": _PRESET_PACKAGE_KEY},
        )
        .mappings()
        .one_or_none()
    )
    if preset_row is None:
        return

    schedule_specs = _browser_proven_package_preset_schedule_definitions(
        _jsonb_payload(preset_row["package_definition"]),
        _jsonb_payload(preset_row["compiled_plan"]),
    )
    schedule_names = [str(spec["name"]) for spec in schedule_specs]
    existing_rows = (
        connection.execute(
            text(
                """
                SELECT id, name, status, created_at, starts_at, ends_at, next_fire_at
                FROM workflow_package_schedules
                WHERE package_id = :package_id
                  AND name IN :schedule_names
                ORDER BY name ASC,
                    CASE WHEN status = 'paused' THEN 0 ELSE 1 END ASC,
                    id ASC
                """
            ).bindparams(bindparam("schedule_names", expanding=True)),
            {
                "package_id": preset_row["id"],
                "schedule_names": schedule_names,
            },
        )
        .mappings()
        .all()
    )
    rows_by_name: dict[str, list[Mapping[str, object]]] = {}
    for row in existing_rows:
        rows_by_name.setdefault(str(row["name"]), []).append(cast(Mapping[str, object], row))

    seeded_at = utcnow()
    insert_statement = text(
        """
        INSERT INTO workflow_package_schedules (
            package_id, workflow_key, name, description, status, timezone,
            recurrence, starts_at, ends_at, next_fire_at, overlap_policy,
            misfire_policy, misfire_grace_seconds, input_template,
            template_vars, created_at, updated_at
        ) VALUES (
            :package_id, :workflow_key, :name, :description, :status, :timezone,
            CAST(:recurrence AS jsonb), NULL, NULL, :next_fire_at,
            :overlap_policy, :misfire_policy, :misfire_grace_seconds,
            CAST(:input_template AS jsonb), CAST(:template_vars AS jsonb),
            :created_at, :updated_at
        )
        """
    )
    update_statement = text(
        """
        UPDATE workflow_package_schedules
        SET workflow_key = :workflow_key,
            name = :name,
            description = :description,
            status = :status,
            timezone = :timezone,
            recurrence = CAST(:recurrence AS jsonb),
            next_fire_at = :next_fire_at,
            overlap_policy = :overlap_policy,
            misfire_policy = :misfire_policy,
            misfire_grace_seconds = :misfire_grace_seconds,
            input_template = CAST(:input_template AS jsonb),
            template_vars = CAST(:template_vars AS jsonb),
            updated_at = :updated_at
        WHERE id = :schedule_id
        """
    )

    for spec in schedule_specs:
        matching_rows = rows_by_name.get(str(spec["name"]), [])
        if matching_rows:
            matching_row = matching_rows[0]
            next_fire_at = cast(datetime | None, matching_row["next_fire_at"])
            if next_fire_at is None or to_utc(next_fire_at) > seeded_at:
                next_fire_at = _browser_proven_package_preset_schedule_next_fire_at(
                    created_at=cast(datetime, matching_row["created_at"]),
                    starts_at=cast(datetime | None, matching_row["starts_at"]),
                    ends_at=cast(datetime | None, matching_row["ends_at"]),
                    reference_now=seeded_at,
                )
            connection.execute(
                update_statement,
                {
                    "schedule_id": matching_row["id"],
                    "workflow_key": spec["workflow_key"],
                    "name": spec["name"],
                    "description": spec["description"],
                    "status": "paused" if str(matching_row["status"]) == "paused" else "enabled",
                    "timezone": spec["timezone"],
                    "recurrence": json.dumps(spec["recurrence"], sort_keys=True),
                    "next_fire_at": next_fire_at,
                    "overlap_policy": spec["overlap_policy"],
                    "misfire_policy": spec["misfire_policy"],
                    "misfire_grace_seconds": spec["misfire_grace_seconds"],
                    "input_template": json.dumps(spec["input_template"], sort_keys=True),
                    "template_vars": json.dumps(spec["template_vars"], sort_keys=True),
                    "updated_at": seeded_at,
                },
            )
            continue

        connection.execute(
            insert_statement,
            {
                "package_id": preset_row["id"],
                "workflow_key": spec["workflow_key"],
                "name": spec["name"],
                "description": spec["description"],
                "status": "enabled",
                "timezone": spec["timezone"],
                "recurrence": json.dumps(spec["recurrence"], sort_keys=True),
                "next_fire_at": _browser_proven_package_preset_schedule_next_fire_at(
                    created_at=seeded_at,
                    starts_at=None,
                    ends_at=None,
                    reference_now=seeded_at,
                ),
                "overlap_policy": spec["overlap_policy"],
                "misfire_policy": spec["misfire_policy"],
                "misfire_grace_seconds": spec["misfire_grace_seconds"],
                "input_template": json.dumps(spec["input_template"], sort_keys=True),
                "template_vars": json.dumps(spec["template_vars"], sort_keys=True),
                "created_at": seeded_at,
                "updated_at": seeded_at,
            },
        )


def _ensure_browser_proven_package_preset(engine: Engine, table_names: set[str]) -> None:
    if "workflow_packages" not in table_names:
        return

    preset_sql_path = _preset_package_sql_path()
    if not preset_sql_path.exists():
        return

    _ensure_db_upgrade_marker_table(engine, table_names)
    _ensure_report_agent_memory_cleanup_columns(engine, table_names)
    _repair_legacy_agent_memory_report_sources(engine, table_names)
    run_columns = set()
    if "runs" in table_names:
        run_columns = {column["name"] for column in inspect(engine).get_columns("runs")}

    with engine.begin() as connection:
        marker_applied = _upgrade_marker_applied(
            connection,
            _WORKFLOW_PACKAGE_STARTUP_CUTOVER_MARKER_KEY,
        )
        if not marker_applied and "runs" in table_names:
            _purge_workflow_package_run_artifacts(
                connection,
                table_names=table_names,
                run_columns=run_columns,
            )

        if not marker_applied or _browser_proven_package_preset_needs_reseed(connection):
            connection.execute(
                text("DELETE FROM workflow_packages WHERE key = :package_key"),
                {"package_key": _PRESET_PACKAGE_KEY},
            )
            _insert_browser_proven_package_preset(connection, preset_sql_path)

        _ensure_browser_proven_package_preset_schedules(connection)

        if not marker_applied:
            _mark_upgrade_applied(
                connection,
                _WORKFLOW_PACKAGE_STARTUP_CUTOVER_MARKER_KEY,
            )


def _ensure_platform_reference_tables(engine: Engine, table_names: set[str]) -> None:
    if not {"agents", "capabilities", "mcp_servers", "workflows"} <= table_names:
        return
    with engine.begin() as connection:
        if "workflow_agent_refs" in table_names:
            workflow_ref_columns = {
                column["name"] for column in inspect(engine).get_columns("workflow_agent_refs")
            }
            if not {"workflow_id", "agent_id"} <= workflow_ref_columns:
                connection.exec_driver_sql('DROP TABLE IF EXISTS "workflow_agent_refs" CASCADE')
                table_names.discard("workflow_agent_refs")
        for statement in _PLATFORM_REFERENCE_TABLE_STATEMENTS:
            connection.exec_driver_sql(statement)
    table_names.update(_PLATFORM_REFERENCE_TABLE_NAMES)


def _delete_rows_with_unresolved_dependency_refs(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        if {"agents", "model_connections", "output_schemas"} <= table_names:
            connection.exec_driver_sql(
                """
                DELETE FROM agents AS agent
                WHERE NOT EXISTS (
                    SELECT 1 FROM model_connections AS model_connection
                    WHERE model_connection.id = agent.model_connection_id
                ) OR NOT EXISTS (
                    SELECT 1 FROM output_schemas AS output_schema
                    WHERE output_schema.id = agent.output_schema_id
                )
                """
            )
        if {"agents", "capabilities"} <= table_names:
            connection.exec_driver_sql(
                """
                DELETE FROM agents AS agent
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(agent.capabilities) AS capability(value)
                    WHERE (capability.value ->> 'capabilityId') IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM capabilities AS stored
                        WHERE stored.id = (capability.value ->> 'capabilityId')::integer
                      )
                )
                """
            )
        if {"agents", "mcp_servers"} <= table_names:
            connection.exec_driver_sql(
                """
                DELETE FROM agents AS agent
                WHERE EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(agent.mcp_servers) AS mcp_server(value)
                    WHERE (mcp_server.value ->> 'mcpServerId') IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM mcp_servers AS stored
                        WHERE stored.id = (mcp_server.value ->> 'mcpServerId')::integer
                      )
                )
                """
            )


def _drop_version_shaped_run_provenance_columns(
    connection: Connection,
    run_columns: set[str],
) -> None:
    for column_name in _RUN_WORKFLOW_PACKAGE_REMOVED_PROVENANCE_COLUMNS:
        if column_name in run_columns:
            connection.exec_driver_sql(
                f"ALTER TABLE runs DROP COLUMN IF EXISTS {column_name} CASCADE"
            )
            run_columns.discard(column_name)


def _normalize_run_extension_dependencies(connection: Connection) -> None:
    connection.exec_driver_sql(
        """
        UPDATE runs
        SET extension_dependencies = COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'extensionKey', dependency.value ->> 'extensionKey',
                        'surfaces', COALESCE(
                            (
                                SELECT jsonb_agg(surface.value ORDER BY surface.ordinality)
                                FROM jsonb_array_elements(
                                    CASE
                                        WHEN jsonb_typeof(dependency.value -> 'surfaces') = 'array'
                                        THEN dependency.value -> 'surfaces'
                                        ELSE '[]'::jsonb
                                    END
                                ) WITH ORDINALITY AS surface(value, ordinality)
                                WHERE jsonb_typeof(surface.value) = 'string'
                            ),
                            '[]'::jsonb
                        ),
                        'fields', COALESCE(
                            (
                                SELECT jsonb_agg(field.value ORDER BY field.ordinality)
                                FROM jsonb_array_elements(
                                    CASE
                                        WHEN jsonb_typeof(dependency.value -> 'fields') = 'array'
                                        THEN dependency.value -> 'fields'
                                        ELSE '[]'::jsonb
                                    END
                                ) WITH ORDINALITY AS field(value, ordinality)
                                WHERE jsonb_typeof(field.value) = 'string'
                            ),
                            '[]'::jsonb
                        )
                    )
                    ORDER BY dependency.ordinality
                )
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(runs.extension_dependencies) = 'array'
                        THEN runs.extension_dependencies
                        ELSE '[]'::jsonb
                    END
                ) WITH ORDINALITY AS dependency(value, ordinality)
                WHERE jsonb_typeof(dependency.value) = 'object'
                  AND dependency.value ? 'extensionKey'
                  AND btrim(dependency.value ->> 'extensionKey') <> ''
            ),
            '[]'::jsonb
        )
        """
    )


def _ensure_run_workflow_package_provenance_support(
    engine: Engine,
    table_names: set[str],
) -> None:
    if "runs" not in table_names:
        return

    run_columns = {column["name"] for column in inspect(engine).get_columns("runs")}
    with engine.begin() as connection:
        target_kind_check = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS definition
                FROM pg_constraint
                WHERE conname = 'ck_runs_target_kind'
                  AND conrelid = 'runs'::regclass
                """
            )
        ).scalar_one_or_none()
        if "workflowPackage" not in str(target_kind_check or ""):
            connection.exec_driver_sql(
                "ALTER TABLE runs DROP CONSTRAINT IF EXISTS ck_runs_target_kind"
            )
            connection.exec_driver_sql(
                "ALTER TABLE runs ADD CONSTRAINT ck_runs_target_kind "
                "CHECK (target_kind IN ('agent', 'workflow', 'workflowPackage'))"
            )
        if "extension_dependencies" not in run_columns and "extension_snapshots" in run_columns:
            connection.exec_driver_sql(
                "ALTER TABLE runs RENAME COLUMN extension_snapshots TO extension_dependencies"
            )
            run_columns.discard("extension_snapshots")
            run_columns.add("extension_dependencies")
        for column_name, column_type in _RUN_WORKFLOW_PACKAGE_PROVENANCE_COLUMNS.items():
            if column_name not in run_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD COLUMN {column_name} {column_type}"
                )
                run_columns.add(column_name)
        if "extension_snapshots" in run_columns:
            connection.exec_driver_sql(
                """
                UPDATE runs
                SET extension_dependencies = extension_snapshots
                WHERE extension_snapshots IS NOT NULL
                  AND (
                    extension_dependencies IS NULL
                    OR extension_dependencies = '[]'::jsonb
                  )
                """
            )
            connection.exec_driver_sql("ALTER TABLE runs DROP COLUMN extension_snapshots")
            run_columns.discard("extension_snapshots")
        _drop_version_shaped_run_provenance_columns(connection, run_columns)
        _normalize_run_extension_dependencies(connection)
        connection.exec_driver_sql(
            "ALTER TABLE runs ALTER COLUMN extension_dependencies SET DEFAULT '[]'::jsonb"
        )
        connection.exec_driver_sql(
            "ALTER TABLE runs ALTER COLUMN extension_dependencies SET NOT NULL"
        )
        for column_name, column_type in _RUN_TARGET_REFERENCE_COLUMNS.items():
            if column_name not in run_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD COLUMN {column_name} {column_type}"
                )
                run_columns.add(column_name)
        for statement in _RUN_WORKFLOW_PACKAGE_PROVENANCE_INDEXES:
            connection.exec_driver_sql(statement)


def _ensure_platform_foreign_keys(engine: Engine, table_names: set[str]) -> None:
    if not {"agents", "runs", "workflows", "workflow_packages"} <= table_names:
        return
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            UPDATE runs
            SET agent_id = target_id
            WHERE target_kind = 'agent'
              AND agent_id IS NULL
              AND EXISTS (SELECT 1 FROM agents WHERE agents.id = runs.target_id)
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE runs
            SET workflow_id = target_id
            WHERE target_kind = 'workflow'
              AND workflow_id IS NULL
              AND EXISTS (SELECT 1 FROM workflows WHERE workflows.id = runs.target_id)
            """
        )
        connection.exec_driver_sql(
            "UPDATE runs SET agent_id = NULL "
            "WHERE agent_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM agents WHERE agents.id = runs.agent_id)"
        )
        connection.exec_driver_sql(
            "UPDATE runs SET workflow_id = NULL "
            "WHERE workflow_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM workflows WHERE workflows.id = runs.workflow_id)"
        )
        connection.exec_driver_sql(
            "UPDATE runs SET workflow_package_id = NULL "
            "WHERE workflow_package_id IS NOT NULL "
            "AND NOT EXISTS ("
            "SELECT 1 FROM workflow_packages "
            "WHERE workflow_packages.id = runs.workflow_package_id"
            ")"
        )
        for constraint_name in (
            "fk_agents_model_connection_id",
            "agents_model_connection_id_fkey",
        ):
            _drop_constraint_if_exists(connection, "agents", constraint_name)
        connection.exec_driver_sql(
            "ALTER TABLE agents ADD CONSTRAINT fk_agents_model_connection_id "
            "FOREIGN KEY (model_connection_id) "
            "REFERENCES model_connections(id) ON DELETE RESTRICT"
        )
        for constraint_name in ("fk_agents_output_schema_id", "agents_output_schema_id_fkey"):
            _drop_constraint_if_exists(connection, "agents", constraint_name)
        connection.exec_driver_sql(
            "ALTER TABLE agents ADD CONSTRAINT fk_agents_output_schema_id "
            "FOREIGN KEY (output_schema_id) "
            "REFERENCES output_schemas(id) ON DELETE RESTRICT"
        )
        run_constraints = {
            "fk_runs_agent_id": (
                "runs_agent_id_fkey",
                "FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE",
            ),
            "fk_runs_workflow_id": (
                "runs_workflow_id_fkey",
                "FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE",
            ),
            "fk_runs_workflow_package_id": (
                "runs_workflow_package_id_fkey",
                "FOREIGN KEY (workflow_package_id) "
                "REFERENCES workflow_packages(id) ON DELETE CASCADE",
            ),
        }
        for constraint_name, (default_name, constraint_sql) in run_constraints.items():
            _drop_constraint_if_exists(connection, "runs", constraint_name)
            _drop_constraint_if_exists(connection, "runs", default_name)
            connection.exec_driver_sql(
                f"ALTER TABLE runs ADD CONSTRAINT {constraint_name} {constraint_sql}"
            )


def _backfill_platform_reference_tables(engine: Engine, table_names: set[str]) -> None:
    if not _PLATFORM_REFERENCE_TABLE_NAMES <= table_names:
        return
    with engine.begin() as connection:
        for table_name in _PLATFORM_REFERENCE_TABLE_NAMES:
            connection.exec_driver_sql(f"TRUNCATE TABLE {table_name} RESTART IDENTITY")
        connection.exec_driver_sql(
            """
            INSERT INTO workflow_agent_refs (workflow_id, agent_id)
            SELECT DISTINCT workflow.id, agent.id
            FROM workflows AS workflow
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(workflow.steps) = 'array'
                THEN workflow.steps ELSE '[]'::jsonb END
            ) AS step(value)
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(step.value -> 'agents') = 'array'
                THEN step.value -> 'agents' ELSE '[]'::jsonb END
            ) AS step_agent(value)
            JOIN agents AS agent ON agent.id = (step_agent.value ->> 'agentId')::integer
            WHERE (step_agent.value ->> 'agentId') IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO agent_capability_refs (agent_id, capability_id, capability_key)
            SELECT DISTINCT agent.id, capability.id, cap_ref.value ->> 'capabilityKey'
            FROM agents AS agent
            CROSS JOIN LATERAL jsonb_array_elements(agent.capabilities) AS cap_ref(value)
            JOIN capabilities AS capability
              ON capability.id = (cap_ref.value ->> 'capabilityId')::integer
            WHERE (cap_ref.value ->> 'capabilityId') IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO agent_mcp_server_refs (agent_id, mcp_server_id, mcp_server_key)
            SELECT DISTINCT agent.id, mcp_server.id, mcp_server_ref.value ->> 'mcpServerKey'
            FROM agents AS agent
            CROSS JOIN LATERAL jsonb_array_elements(agent.mcp_servers) AS mcp_server_ref(value)
            JOIN mcp_servers AS mcp_server
              ON mcp_server.id = (mcp_server_ref.value ->> 'mcpServerId')::integer
            WHERE (mcp_server_ref.value ->> 'mcpServerId') IS NOT NULL
            ON CONFLICT DO NOTHING
            """
        )


def _ensure_agent_platform_tables(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        for table_name, statements in _AGENT_PLATFORM_TABLE_STATEMENTS:
            for statement in statements:
                connection.exec_driver_sql(statement)
            table_names.add(table_name)


def _ensure_pgvector_extension(engine: Engine) -> bool:
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    except SQLAlchemyError:
        return False
    return True


def _ensure_core_memory_tables(engine: Engine, table_names: set[str]) -> None:
    with engine.begin() as connection:
        for statement in _CORE_MEMORY_TABLE_STATEMENTS:
            connection.exec_driver_sql(statement)
        _drop_constraint_if_exists(
            connection,
            "agent_memory_entries",
            "ck_agent_memory_entries_scope_type",
        )
        connection.exec_driver_sql(
            "ALTER TABLE agent_memory_entries "
            "ADD CONSTRAINT ck_agent_memory_entries_scope_type "
            "CHECK (scope_type IN "
            "('workspace', 'package', 'workflow', 'run', 'agent', 'namespace'))"
        )
    table_names.update(_CORE_MEMORY_TABLE_NAMES)

    if not _ensure_pgvector_extension(engine):
        return

    with engine.begin() as connection:
        for statement in _CORE_MEMORY_PGVECTOR_TABLE_STATEMENTS:
            connection.exec_driver_sql(statement)
    table_names.update(_CORE_MEMORY_PGVECTOR_TABLE_NAMES)


def _agent_platform_hard_cutover_required(engine: Engine, table_names: set[str]) -> bool:
    """Detect stale execution storage, not backfillable authoring-column drift."""
    inspector = inspect(engine)
    for table_name, required_columns in _RUNTIME_CUTOVER_REQUIRED_COLUMNS.items():
        if table_name not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if _RUNTIME_LEGACY_COLUMNS.get(table_name, frozenset()) & columns:
            return True
        comparable_columns = set(columns)
        if table_name == "runs" and "extension_snapshots" in comparable_columns:
            comparable_columns.add("extension_dependencies")
        if not required_columns <= comparable_columns:
            return True
    return False


def _reset_agent_platform_runtime_tables(engine: Engine, table_names: set[str]) -> None:
    statements_by_table = dict(_AGENT_PLATFORM_TABLE_STATEMENTS)
    with engine.begin() as connection:
        for table_name in _RUNTIME_HARD_CUTOVER_DROP_ORDER:
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            table_names.discard(table_name)
        for table_name in _RUNTIME_HARD_CUTOVER_CREATE_ORDER:
            for statement in statements_by_table[table_name]:
                connection.exec_driver_sql(statement)
            table_names.add(table_name)


def _global_authoring_cleanup_is_representable(engine: Engine, table_names: set[str]) -> bool:
    if "runs" not in table_names:
        return True
    if not _GLOBAL_AUTHORING_CLEANUP_REQUIRED_PACKAGE_TABLES <= table_names:
        return False
    run_columns = {column["name"] for column in inspect(engine).get_columns("runs")}
    return _GLOBAL_AUTHORING_CLEANUP_REQUIRED_RUN_COLUMNS <= run_columns


def _delete_clean_break_global_authoring_rows(engine: Engine, table_names: set[str]) -> None:
    if not _global_authoring_cleanup_is_representable(engine, table_names):
        return
    with engine.begin() as connection:
        if "runs" in table_names:
            stale_run_subquery = "SELECT run.id FROM runs AS run " + (
                f"WHERE NOT ({_REPRESENTABLE_PACKAGE_RUN_SQL})"
            )
            if "run_operation_invocations" in table_names:
                delete_operation_invocations_sql = (
                    "DELETE FROM run_operation_invocations WHERE run_id IN "
                    + f"({stale_run_subquery})"
                )
                _ = connection.exec_driver_sql(delete_operation_invocations_sql)
            if "run_agent_invocations" in table_names:
                delete_invocations_sql = (
                    "DELETE FROM run_agent_invocations WHERE run_id IN " + f"({stale_run_subquery})"
                )
                _ = connection.exec_driver_sql(delete_invocations_sql)
            if "run_steps" in table_names:
                delete_steps_sql = (
                    "DELETE FROM run_steps WHERE run_id IN " + f"({stale_run_subquery})"
                )
                _ = connection.exec_driver_sql(delete_steps_sql)
            delete_runs_sql = (
                "DELETE FROM runs AS run WHERE NOT " + f"({_REPRESENTABLE_PACKAGE_RUN_SQL})"
            )
            _ = connection.exec_driver_sql(delete_runs_sql)

        for table_name in _GLOBAL_AUTHORING_TABLES:
            if table_name in table_names:
                _ = connection.exec_driver_sql(f'DELETE FROM "{table_name}"')


def _ensure_model_connection_key_support(engine: Engine, table_names: set[str]) -> None:
    if "model_connections" not in table_names:
        return

    inspector = inspect(engine)
    model_connection_columns = {
        column["name"]: column for column in inspector.get_columns("model_connections")
    }
    model_connection_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("model_connections")
        if constraint.get("name")
    }

    with engine.begin() as connection:
        if "key" not in model_connection_columns:
            connection.exec_driver_sql("ALTER TABLE model_connections ADD COLUMN key VARCHAR(120)")

        model_connection_rows = (
            connection.execute(
                text("SELECT id, key, name, model_id FROM model_connections ORDER BY id ASC")
            )
            .mappings()
            .all()
        )
        used_keys: set[str] = set()
        for row in model_connection_rows:
            raw_key = row["key"]
            raw_key_text = str(raw_key).strip() if raw_key is not None else ""
            base_key = normalize_legacy_model_connection_key(
                name=raw_key_text or row["name"],
                model_id=row["model_id"],
            )
            stable_key = build_unique_model_connection_key(base_key, used_keys)
            if raw_key_text != stable_key:
                connection.execute(
                    text(
                        "UPDATE model_connections "
                        "SET key = :key, updated_at = NOW() "
                        "WHERE id = :connection_id"
                    ),
                    {"key": stable_key, "connection_id": row["id"]},
                )

        connection.exec_driver_sql("ALTER TABLE model_connections ALTER COLUMN key SET NOT NULL")
        if "uq_model_connections_key" not in model_connection_unique_constraints:
            connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD CONSTRAINT uq_model_connections_key UNIQUE (key)"
            )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_model_connections_key ON model_connections (key)"
        )


def _scrub_legacy_model_connection_kind_snapshot_json(  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
    connection: Connection,
    table_names: set[str],
) -> None:
    inspector = inspect(connection)
    if "agents" in table_names:
        agent_columns = {column["name"] for column in inspector.get_columns("agents")}
        if "model_connection_snapshot" in agent_columns:
            updated_at_assignment = ", updated_at = NOW()" if "updated_at" in agent_columns else ""
            _ = connection.execute(
                text(
                    f"""
                    UPDATE agents
                    SET model_connection_snapshot = (
                            model_connection_snapshot - 'connectionKind' - 'connection_kind'  -- OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                        ){updated_at_assignment}
                    WHERE jsonb_typeof(model_connection_snapshot) = 'object'
                      AND model_connection_snapshot ?| ARRAY['connectionKind', 'connection_kind'] -- OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                    """
                )
            )

    if "run_workflow_package_snapshots" in table_names:
        snapshot_columns = {
            column["name"] for column in inspector.get_columns("run_workflow_package_snapshots")
        }
        if "resolved_model_connections" in snapshot_columns:
            updated_at_assignment = (
                ", updated_at = NOW()" if "updated_at" in snapshot_columns else ""
            )
            _ = connection.execute(
                text(
                    f"""
                    UPDATE run_workflow_package_snapshots
                    SET resolved_model_connections = COALESCE(
                            (
                                SELECT jsonb_agg(
                                    CASE
                                        WHEN jsonb_typeof(profile.value) = 'object'
                                        THEN profile.value - 'connectionKind' - 'connection_kind' -- OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                                        ELSE profile.value
                                    END
                                    ORDER BY profile.ordinality
                                )
                                FROM jsonb_array_elements(
                                    CASE
                                        WHEN jsonb_typeof(resolved_model_connections) = 'array'
                                        THEN resolved_model_connections
                                        ELSE '[]'::jsonb
                                    END
                                ) WITH ORDINALITY AS profile(value, ordinality)
                            ),
                            '[]'::jsonb
                        ){updated_at_assignment}
                    WHERE EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(
                            CASE
                                WHEN jsonb_typeof(resolved_model_connections) = 'array'
                                THEN resolved_model_connections
                                ELSE '[]'::jsonb
                            END
                        ) AS profile(value)
                        WHERE jsonb_typeof(profile.value) = 'object'
                          AND profile.value ?| ARRAY['connectionKind', 'connection_kind'] -- OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                    )
                    """
                )
            )


def _remove_legacy_model_connection_kind_support(  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
    engine: Engine, table_names: set[str]
) -> None:
    if not ({"agents", "model_connections", "run_workflow_package_snapshots"} & table_names):
        return

    inspector = inspect(engine)
    model_connection_columns: dict[str, object] = {}
    model_connection_kind_checks: set[str] = set()  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
    if "model_connections" in table_names:
        model_connection_columns = {
            column["name"]: column for column in inspector.get_columns("model_connections")
        }
        for constraint in inspector.get_check_constraints("model_connections"):
            constraint_name = constraint.get("name")
            if not constraint_name:
                continue
            if constraint_name == _MODEL_CONNECTION_KIND_CHECK or "connection_kind" in str(
                constraint.get("sqltext") or ""
            ):  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                model_connection_kind_checks.add(
                    str(constraint_name)
                )  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP

    with engine.begin() as connection:
        _scrub_legacy_model_connection_kind_snapshot_json(
            connection, table_names
        )  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
        if "model_connections" not in table_names:
            return
        if (
            "connection_kind" in model_connection_columns
        ):  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
            _ = connection.execute(
                text(
                    """
                    DELETE FROM model_connections
                    WHERE connection_kind = :legacy_connection_kind -- OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
                    """
                ),
                {
                    "legacy_connection_kind": "deterministic_smoke"
                },  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
            )
        for (
            constraint_name
        ) in model_connection_kind_checks:  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
            _drop_constraint_if_exists(connection, "model_connections", constraint_name)
        if (
            "connection_kind" in model_connection_columns
        ):  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections DROP COLUMN IF EXISTS connection_kind"  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
            )


def _is_flexible_model_connection_reasoning_effort_check(sqltext: object) -> bool:
    normalized_sql = re.sub(r"\s+", " ", str(sqltext or "").lower())
    return all(
        token in normalized_sql
        for token in ("reasoning_effort", "is null", "length", "btrim", "128")
    )


def _ensure_model_connection_reasoning_effort_support(
    engine: Engine,
    table_names: set[str],
) -> None:
    if "model_connections" not in table_names:
        return

    inspector = inspect(engine)
    model_connection_columns = {
        column["name"]: column for column in inspector.get_columns("model_connections")
    }
    reasoning_effort_column = model_connection_columns.get("reasoning_effort")
    reasoning_effort_check = next(
        (
            constraint
            for constraint in inspector.get_check_constraints("model_connections")
            if constraint.get("name") == _MODEL_CONNECTION_REASONING_EFFORT_CHECK
        ),
        None,
    )
    has_flexible_reasoning_effort_check = (
        reasoning_effort_check is not None
        and _is_flexible_model_connection_reasoning_effort_check(
            reasoning_effort_check.get("sqltext")
        )
    )

    with engine.begin() as connection:
        if reasoning_effort_check is not None and not has_flexible_reasoning_effort_check:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections DROP CONSTRAINT "
                + _MODEL_CONNECTION_REASONING_EFFORT_CHECK
            )
            has_flexible_reasoning_effort_check = False

        if reasoning_effort_column is None:
            _ = connection.exec_driver_sql(
                " ".join(
                    (
                        "ALTER TABLE model_connections ADD COLUMN reasoning_effort",
                        "VARCHAR(128) DEFAULT 'medium'",
                    )
                )
            )
        else:
            _ = connection.exec_driver_sql(
                " ".join(
                    (
                        "ALTER TABLE model_connections ALTER COLUMN reasoning_effort",
                        "SET DEFAULT 'medium'",
                    )
                )
            )
            if reasoning_effort_column.get("nullable") is False:
                _ = connection.exec_driver_sql(
                    " ".join(
                        (
                            "ALTER TABLE model_connections ALTER COLUMN reasoning_effort",
                            "DROP NOT NULL",
                        )
                    )
                )
            if getattr(reasoning_effort_column.get("type"), "length", None) != 128:
                _ = connection.exec_driver_sql(
                    " ".join(
                        (
                            "ALTER TABLE model_connections ALTER COLUMN reasoning_effort",
                            "TYPE VARCHAR(128) USING reasoning_effort::VARCHAR(128)",
                        )
                    )
                )

        if not has_flexible_reasoning_effort_check:
            _ = connection.exec_driver_sql(
                " ".join(
                    (
                        "ALTER TABLE model_connections ADD CONSTRAINT",
                        _MODEL_CONNECTION_REASONING_EFFORT_CHECK,
                        f"CHECK ({_MODEL_CONNECTION_REASONING_EFFORT_CHECK_SQL})",
                    )
                )
            )


def _ensure_model_connection_protocol_contract_support(
    engine: Engine,
    table_names: set[str],
) -> None:
    if "model_connections" not in table_names:
        return

    inspector = inspect(engine)
    model_connection_columns = {
        column["name"]: column for column in inspector.get_columns("model_connections")
    }
    model_connection_check_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("model_connections")
        if constraint.get("name")
    }

    with engine.begin() as connection:
        if "ck_model_connections_api_style" in model_connection_check_constraints:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections DROP CONSTRAINT ck_model_connections_api_style"
            )
            model_connection_check_constraints.discard("ck_model_connections_api_style")

        if "protocol_profile" not in model_connection_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN protocol_profile "
                "VARCHAR(40) NOT NULL DEFAULT 'openai_responses'"
            )
        else:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ALTER COLUMN protocol_profile "
                "SET DEFAULT 'openai_responses'"
            )

        protocol_profile_expression = (
            "CASE api_style "
            "WHEN 'chat_completions' THEN 'openai_chat_completions' "
            "WHEN 'responses' THEN 'openai_responses' "
            "ELSE 'openai_responses' END"
            if "api_style" in model_connection_columns
            else "'openai_responses'"
        )
        _ = connection.execute(
            text(
                f"""
                UPDATE model_connections
                SET protocol_profile = {protocol_profile_expression}, updated_at = NOW()
                WHERE protocol_profile IS NULL
                   OR protocol_profile NOT IN :allowed_protocol_profiles
                """
            ).bindparams(bindparam("allowed_protocol_profiles", expanding=True)),
            {"allowed_protocol_profiles": _MODEL_CONNECTION_ALLOWED_PROTOCOL_PROFILES},
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ALTER COLUMN protocol_profile SET NOT NULL"
        )

        if "capabilities" not in model_connection_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN capabilities JSONB "
                f"NOT NULL DEFAULT {_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL}"
            )
        else:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ALTER COLUMN capabilities "
                f"SET DEFAULT {_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL}"
            )
        _ = connection.exec_driver_sql(
            "UPDATE model_connections "
            f"SET capabilities = {_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL}, updated_at = NOW() "
            "WHERE capabilities IS NULL OR jsonb_typeof(capabilities) <> 'object'"
        )
        _ = connection.exec_driver_sql(
            "UPDATE model_connections "
            f"SET capabilities = {_MODEL_CONNECTION_DEFAULT_CAPABILITIES_SQL}, updated_at = NOW() "
            "WHERE jsonb_path_exists(capabilities, "
            '\'$.*.status ? (!(@ == "supported" || @ == "unsupported" '
            '|| @ == "unknown" || @ == "notApplicable"))\')'
        )
        _ = connection.exec_driver_sql(
            "UPDATE model_connections "
            "SET capabilities = capabilities - 'multimodalInput', updated_at = NOW() "
            "WHERE capabilities ? 'multimodalInput'"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ALTER COLUMN capabilities SET NOT NULL"
        )

        _ensure_model_connection_policy_column(
            connection,
            model_connection_columns,
            "output_strategy_policy",
            "VARCHAR(40)",
            _MODEL_CONNECTION_DEFAULT_OUTPUT_STRATEGY_POLICY,
            _MODEL_CONNECTION_ALLOWED_OUTPUT_STRATEGY_POLICIES,
        )
        _ensure_model_connection_policy_column(
            connection,
            model_connection_columns,
            "parallel_tool_calls_policy",
            "VARCHAR(20)",
            _MODEL_CONNECTION_DEFAULT_PARALLEL_TOOL_CALLS_POLICY,
            _MODEL_CONNECTION_ALLOWED_TOOL_POLICIES,
        )
        _ensure_model_connection_policy_column(
            connection,
            model_connection_columns,
            "reasoning_policy",
            "VARCHAR(20)",
            _MODEL_CONNECTION_DEFAULT_REASONING_POLICY,
            _MODEL_CONNECTION_ALLOWED_BINARY_POLICIES,
        )
        _ensure_model_connection_policy_column(
            connection,
            model_connection_columns,
            "streaming_policy",
            "VARCHAR(20)",
            _MODEL_CONNECTION_DEFAULT_STREAMING_POLICY,
            _MODEL_CONNECTION_ALLOWED_BINARY_POLICIES,
        )

        if "last_probed_at" not in model_connection_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN last_probed_at TIMESTAMPTZ"
            )
        if "probe_cache_ttl_seconds" not in model_connection_columns:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ADD COLUMN probe_cache_ttl_seconds "
                "INTEGER NOT NULL DEFAULT 900"
            )
        else:
            _ = connection.exec_driver_sql(
                "ALTER TABLE model_connections ALTER COLUMN probe_cache_ttl_seconds SET DEFAULT 900"
            )
        _ = connection.exec_driver_sql(
            "UPDATE model_connections SET probe_cache_ttl_seconds = 900, updated_at = NOW() "
            "WHERE probe_cache_ttl_seconds IS NULL OR probe_cache_ttl_seconds <= 0"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ALTER COLUMN probe_cache_ttl_seconds SET NOT NULL"
        )

        for constraint_name in (
            _MODEL_CONNECTION_PROTOCOL_PROFILE_CHECK,
            _MODEL_CONNECTION_CAPABILITY_STATUS_CHECK,
            _MODEL_CONNECTION_OUTPUT_STRATEGY_POLICY_CHECK,
            _MODEL_CONNECTION_PARALLEL_TOOL_CALLS_POLICY_CHECK,
            _MODEL_CONNECTION_REASONING_POLICY_CHECK,
            _MODEL_CONNECTION_STREAMING_POLICY_CHECK,
            _MODEL_CONNECTION_PROBE_CACHE_TTL_CHECK,
        ):
            if constraint_name in model_connection_check_constraints:
                _ = connection.exec_driver_sql(
                    f"ALTER TABLE model_connections DROP CONSTRAINT {constraint_name}"
                )

        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_PROTOCOL_PROFILE_CHECK
            + " CHECK (protocol_profile IN ('openai_chat_completions', 'openai_responses'))"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_CAPABILITY_STATUS_CHECK
            + " CHECK (jsonb_typeof(capabilities) = 'object' "
            + "AND NOT jsonb_path_exists(capabilities, "
            + '\'$.*.status ? (!(@ == "supported" || @ == "unsupported" '
            + '|| @ == "unknown" || @ == "notApplicable"))\'))'
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_OUTPUT_STRATEGY_POLICY_CHECK
            + " CHECK (output_strategy_policy IN ('require_strict_schema', "
            + "'prefer_strict_schema', 'allow_json_object_validation', 'allow_plain_text'))"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_PARALLEL_TOOL_CALLS_POLICY_CHECK
            + " CHECK (parallel_tool_calls_policy IN ('allow', 'serialize', 'forbid'))"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_REASONING_POLICY_CHECK
            + " CHECK (reasoning_policy IN ('allow', 'forbid'))"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_STREAMING_POLICY_CHECK
            + " CHECK (streaming_policy IN ('allow', 'forbid'))"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections ADD CONSTRAINT "
            + _MODEL_CONNECTION_PROBE_CACHE_TTL_CHECK
            + " CHECK (probe_cache_ttl_seconds > 0)"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections DROP COLUMN IF EXISTS api_style"
        )


def _ensure_model_connection_policy_column(
    connection: Connection,
    model_connection_columns: Mapping[str, object],
    column_name: str,
    column_type: str,
    default_value: str,
    allowed_values: tuple[str, ...],
) -> None:
    if column_name not in model_connection_columns:
        _ = connection.exec_driver_sql(
            f"ALTER TABLE model_connections ADD COLUMN {column_name} {column_type} "
            f"NOT NULL DEFAULT {_sql_string_literal(default_value)}"
        )
    else:
        _ = connection.exec_driver_sql(
            f"ALTER TABLE model_connections ALTER COLUMN {column_name} "
            f"SET DEFAULT {_sql_string_literal(default_value)}"
        )
    _ = connection.execute(
        text(
            f"""
            UPDATE model_connections
            SET {column_name} = :default_value, updated_at = NOW()
            WHERE {column_name} IS NULL OR {column_name} NOT IN :allowed_values
            """
        ).bindparams(bindparam("allowed_values", expanding=True)),
        {"allowed_values": allowed_values, "default_value": default_value},
    )
    _ = connection.exec_driver_sql(
        f"ALTER TABLE model_connections ALTER COLUMN {column_name} SET NOT NULL"
    )


def _drop_model_connection_api_key_metadata_columns(
    engine: Engine,
    table_names: set[str],
) -> None:
    if "model_connections" not in table_names:
        return

    inspector = inspect(engine)
    model_connection_columns = {
        column["name"] for column in inspector.get_columns("model_connections")
    }
    stale_columns = set(_MODEL_CONNECTION_STALE_SECRET_METADATA_COLUMNS) & model_connection_columns

    with engine.begin() as connection:
        for column_name in sorted(stale_columns):
            _ = connection.exec_driver_sql(
                f"ALTER TABLE model_connections DROP COLUMN IF EXISTS {column_name}"
            )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections DROP COLUMN IF EXISTS organization"
        )
        _ = connection.exec_driver_sql(
            "ALTER TABLE model_connections DROP COLUMN IF EXISTS project"
        )


def _ensure_agent_model_connection_support(engine: Engine, table_names: set[str]) -> None:
    if "agents" not in table_names:
        return

    inspector = inspect(engine)
    agent_columns = {column["name"] for column in inspector.get_columns("agents")}

    with engine.begin() as connection:
        if "model_connection_id" not in agent_columns:
            connection.exec_driver_sql("ALTER TABLE agents ADD COLUMN model_connection_id INTEGER")
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_agents_model_connection ON agents (model_connection_id)"
        )


def _ensure_agent_model_connection_snapshot_support(engine: Engine, table_names: set[str]) -> None:
    if not {"agents", "model_connections"} <= table_names:
        return

    inspector = inspect(engine)
    agent_columns = {column["name"]: column for column in inspector.get_columns("agents")}
    model_connection_columns = {
        column["name"]: column for column in inspector.get_columns("model_connections")
    }
    api_style_snapshot_expression = (
        "CASE model_connection.protocol_profile "
        + "WHEN 'openai_chat_completions' THEN 'chat_completions' "
        + "WHEN 'openai_responses' THEN 'responses' ELSE 'responses' END"
        if "protocol_profile" in model_connection_columns
        else (
            "CASE WHEN model_connection.api_style IN ('responses', 'chat_completions') "
            + "THEN model_connection.api_style ELSE 'responses' END"
            if "api_style" in model_connection_columns
            else "'responses'"
        )
    )

    with engine.begin() as connection:
        if "model_connection_snapshot" not in agent_columns:
            connection.exec_driver_sql(
                "ALTER TABLE agents "
                "ADD COLUMN model_connection_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
            )

        _ = connection.execute(
            text(
                f"""
                UPDATE agents AS agent
                SET model_connection_snapshot = jsonb_build_object(
                        'base_url', model_connection.base_url,
                        'model_id', model_connection.model_id,
                        'reasoning_effort', model_connection.reasoning_effort,
                        'api_style', {api_style_snapshot_expression},
                        'timeout_seconds', model_connection.timeout_seconds
                    ),
                    updated_at = NOW()
                FROM model_connections AS model_connection
                WHERE agent.model_connection_id = model_connection.id
                  AND (
                    agent.model_connection_snapshot IS NULL
                    OR jsonb_typeof(agent.model_connection_snapshot) <> 'object'
                    OR agent.model_connection_snapshot = '{{}}'::jsonb
                    OR NOT (
                        agent.model_connection_snapshot ?& ARRAY[
                            'base_url',
                            'model_id',
                            'reasoning_effort',
                            'api_style',
                            'timeout_seconds'
                        ]
                    )
                    OR COALESCE(agent.model_connection_snapshot->>'api_style', '') NOT IN (
                        'responses',
                        'chat_completions'
                    )
                    OR (
                        agent.model_connection_snapshot ? 'reasoning_effort'
                        AND agent.model_connection_snapshot->'reasoning_effort' <> 'null'::jsonb
                        AND (
                            jsonb_typeof(
                                agent.model_connection_snapshot->'reasoning_effort'
                            ) <> 'string'
                            OR length(
                                btrim(agent.model_connection_snapshot->>'reasoning_effort')
                            ) NOT BETWEEN 1 AND 128
                        )
                    )
                  )
                """
            )
        )
        _ = connection.execute(
            text(
                """
                UPDATE agents
                SET model_connection_snapshot = (
                    model_connection_snapshot - 'organization' - 'project'
                ),
                    updated_at = NOW()
                WHERE model_connection_snapshot ?| ARRAY['organization', 'project']
                """
            )
        )
        connection.exec_driver_sql(
            "ALTER TABLE agents ALTER COLUMN model_connection_snapshot SET DEFAULT '{}'::jsonb"
        )
        snapshot_column = agent_columns.get("model_connection_snapshot")
        if snapshot_column is None or snapshot_column.get("nullable", True):
            connection.exec_driver_sql(
                "ALTER TABLE agents ALTER COLUMN model_connection_snapshot SET NOT NULL"
            )


def _ensure_agent_manifest_columns(engine: Engine, table_names: set[str]) -> None:
    if "agents" not in table_names:
        return

    inspector = inspect(engine)
    agent_columns = {column["name"]: column for column in inspector.get_columns("agents")}

    with engine.begin() as connection:
        if "manifest_api_version" not in agent_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ADD COLUMN manifest_api_version VARCHAR(80)
                NOT NULL DEFAULT {_AGENT_MANIFEST_API_VERSION_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE agents
                    SET manifest_api_version = :manifest_api_version
                    WHERE manifest_api_version IS NULL
                    """
                ),
                {"manifest_api_version": AGENT_MANIFEST_API_VERSION},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ALTER COLUMN manifest_api_version
                SET DEFAULT {_AGENT_MANIFEST_API_VERSION_SQL}
                """
            )
            if agent_columns["manifest_api_version"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE agents ALTER COLUMN manifest_api_version SET NOT NULL"
                )

        if "manifest_source" not in agent_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ADD COLUMN manifest_source TEXT
                NOT NULL DEFAULT {_TEMPORARY_AGENT_MANIFEST_SOURCE_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE agents
                    SET manifest_source = :manifest_source
                    WHERE manifest_source IS NULL
                    """
                ),
                {"manifest_source": TEMPORARY_AGENT_MANIFEST_SOURCE},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ALTER COLUMN manifest_source
                SET DEFAULT {_TEMPORARY_AGENT_MANIFEST_SOURCE_SQL}
                """
            )
            if agent_columns["manifest_source"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE agents ALTER COLUMN manifest_source SET NOT NULL"
                )

        if "manifest_hash" not in agent_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ADD COLUMN manifest_hash VARCHAR(64)
                NOT NULL DEFAULT {_TEMPORARY_AGENT_MANIFEST_HASH_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE agents
                    SET manifest_hash = :manifest_hash
                    WHERE manifest_hash IS NULL
                    """
                ),
                {"manifest_hash": TEMPORARY_AGENT_MANIFEST_HASH},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ALTER COLUMN manifest_hash
                SET DEFAULT {_TEMPORARY_AGENT_MANIFEST_HASH_SQL}
                """
            )
            if agent_columns["manifest_hash"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE agents ALTER COLUMN manifest_hash SET NOT NULL"
                )

        if "compiler_version" not in agent_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ADD COLUMN compiler_version VARCHAR(80)
                NOT NULL DEFAULT {_AGENT_MANIFEST_COMPILER_VERSION_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE agents
                    SET compiler_version = :compiler_version
                    WHERE compiler_version IS NULL
                    """
                ),
                {"compiler_version": AGENT_MANIFEST_COMPILER_VERSION},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE agents
                ALTER COLUMN compiler_version
                SET DEFAULT {_AGENT_MANIFEST_COMPILER_VERSION_SQL}
                """
            )
            if agent_columns["compiler_version"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE agents ALTER COLUMN compiler_version SET NOT NULL"
                )


def _ensure_workflow_manifest_columns(engine: Engine, table_names: set[str]) -> None:
    if "workflows" not in table_names:
        return

    inspector = inspect(engine)
    workflow_columns = {column["name"]: column for column in inspector.get_columns("workflows")}

    with engine.begin() as connection:
        if "manifest_api_version" not in workflow_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE workflows
                ADD COLUMN manifest_api_version VARCHAR(80)
                NOT NULL DEFAULT {_WORKFLOW_MANIFEST_API_VERSION_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE workflows
                    SET manifest_api_version = :manifest_api_version
                    WHERE manifest_api_version IS NULL
                    """
                ),
                {"manifest_api_version": WORKFLOW_MANIFEST_API_VERSION},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE workflows
                ALTER COLUMN manifest_api_version
                SET DEFAULT {_WORKFLOW_MANIFEST_API_VERSION_SQL}
                """
            )
            if workflow_columns["manifest_api_version"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE workflows ALTER COLUMN manifest_api_version SET NOT NULL"
                )
        if "manifest_source" not in workflow_columns:
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE workflows
                ADD COLUMN manifest_source TEXT
                NOT NULL DEFAULT {_TEMPORARY_WORKFLOW_MANIFEST_SOURCE_SQL}
                """
            )
        else:
            _ = connection.execute(
                text(
                    """
                    UPDATE workflows
                    SET manifest_source = :manifest_source
                    WHERE manifest_source IS NULL
                    """
                ),
                {"manifest_source": TEMPORARY_WORKFLOW_MANIFEST_SOURCE},
            )
            _ = connection.exec_driver_sql(
                f"""
                ALTER TABLE workflows
                ALTER COLUMN manifest_source
                SET DEFAULT {_TEMPORARY_WORKFLOW_MANIFEST_SOURCE_SQL}
                """
            )
            if workflow_columns["manifest_source"].get("nullable", True):
                _ = connection.exec_driver_sql(
                    "ALTER TABLE workflows ALTER COLUMN manifest_source SET NOT NULL"
                )


def _remove_dead_agent_runtime_fields(engine: Engine, table_names: set[str]) -> None:
    if "agents" not in table_names:
        return

    inspector = inspect(engine)
    agent_columns = {column["name"] for column in inspector.get_columns("agents")}

    with engine.begin() as connection:
        if "temperature" in agent_columns:
            connection.exec_driver_sql(
                "ALTER TABLE agents DROP COLUMN IF EXISTS temperature CASCADE"
            )
        if "max_tool_rounds" in agent_columns:
            connection.exec_driver_sql(
                "ALTER TABLE agents DROP COLUMN IF EXISTS max_tool_rounds CASCADE"
            )
        if "streaming" in agent_columns:
            connection.exec_driver_sql("ALTER TABLE agents DROP COLUMN IF EXISTS streaming CASCADE")


def _remove_global_authoring_allocation_columns(engine: Engine, table_names: set[str]) -> None:
    if not {"agents", "workflows"} & table_names:
        return

    inspector = inspect(engine)
    agent_column = "_".join(("budget", "usd"))
    workflow_column = "_".join(("aggregate", "budget", "usd"))

    with engine.begin() as connection:
        if "agents" in table_names:
            agent_columns = {column["name"] for column in inspector.get_columns("agents")}
            if agent_column in agent_columns:
                _drop_constraint_if_exists(
                    connection,
                    "agents",
                    "_".join(("ck", "agents", "budget", "usd", "non", "negative")),
                )
                connection.exec_driver_sql(
                    f"ALTER TABLE agents DROP COLUMN IF EXISTS {agent_column} CASCADE"
                )
        if "workflows" in table_names:
            workflow_columns = {column["name"] for column in inspector.get_columns("workflows")}
            if workflow_column in workflow_columns:
                _drop_constraint_if_exists(
                    connection,
                    "workflows",
                    "_".join(("ck", "workflows", "aggregate", "budget", "non", "negative")),
                )
                connection.exec_driver_sql(
                    f"ALTER TABLE workflows DROP COLUMN IF EXISTS {workflow_column} CASCADE"
                )


def _remove_run_cost_columns(engine: Engine, table_names: set[str]) -> None:
    cost_word = "cost"
    currency_suffix = "usd"
    run_scopes = ("total", "inherited", "executed")
    run_column_names = tuple(f"{scope}_{cost_word}_{currency_suffix}" for scope in run_scopes)
    run_constraint_names = tuple(
        f"ck_runs_{scope}_{cost_word}_non_negative" for scope in run_scopes
    )
    invocation_column_name = f"{cost_word}_{currency_suffix}"
    invocation_constraint_name = f"ck_run_agent_invocations_{cost_word}_non_negative"

    inspector = inspect(engine)
    if "runs" in table_names:
        run_columns = {column["name"] for column in inspector.get_columns("runs")}
        run_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("runs")
            if constraint.get("name")
        }
        with engine.begin() as connection:
            for constraint_name in run_constraint_names:
                if constraint_name in run_constraints:
                    _ = connection.exec_driver_sql(
                        f"ALTER TABLE runs DROP CONSTRAINT IF EXISTS {constraint_name}"
                    )
            for column_name in run_column_names:
                if column_name in run_columns:
                    _ = connection.exec_driver_sql(
                        f"ALTER TABLE runs DROP COLUMN IF EXISTS {column_name} CASCADE"
                    )

    if "run_agent_invocations" in table_names:
        invocation_columns = {
            column["name"] for column in inspector.get_columns("run_agent_invocations")
        }
        invocation_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("run_agent_invocations")
            if constraint.get("name")
        }
        with engine.begin() as connection:
            if invocation_constraint_name in invocation_constraints:
                statement = (
                    "ALTER TABLE run_agent_invocations DROP CONSTRAINT IF EXISTS "
                    + invocation_constraint_name
                )
                _ = connection.exec_driver_sql(statement)
            if invocation_column_name in invocation_columns:
                statement = (
                    "ALTER TABLE run_agent_invocations DROP COLUMN IF EXISTS "
                    + f"{invocation_column_name} CASCADE"
                )
                _ = connection.exec_driver_sql(statement)


def _backfill_agent_model_connections(
    engine: Engine,
    table_names: set[str],
) -> None:
    if not {"agents", "model_connections"} <= table_names:
        return

    inspector = inspect(engine)
    agent_columns = {column["name"]: column for column in inspector.get_columns("agents")}
    if "model_connection_id" not in agent_columns or "model" not in agent_columns:
        return

    needs_non_null_enforcement = bool(agent_columns["model_connection_id"].get("nullable", True))

    with engine.begin() as connection:
        used_model_connection_keys = set(
            connection.execute(text("SELECT key FROM model_connections ORDER BY key ASC")).scalars()
        )
        unresolved_agent_count = connection.execute(
            text("SELECT COUNT(*) FROM agents WHERE model_connection_id IS NULL")
        ).scalar_one()
        if unresolved_agent_count == 0:
            if needs_non_null_enforcement:
                connection.exec_driver_sql(
                    "ALTER TABLE agents ALTER COLUMN model_connection_id SET NOT NULL"
                )
            return

        legacy_models = connection.execute(
            text(
                "SELECT DISTINCT BTRIM(model) AS model_id "
                "FROM agents "
                "WHERE model_connection_id IS NULL AND model IS NOT NULL AND BTRIM(model) <> '' "
                "ORDER BY model_id"
            )
        ).scalars()

        for legacy_model in legacy_models:
            placeholder_parameters = {
                "base_url": _MODEL_CONNECTION_PLACEHOLDER_BASE_URL,
                "model_id": legacy_model,
                "name": legacy_model,
                "protocol_profile": _MODEL_CONNECTION_DEFAULT_PROTOCOL_PROFILE,
                "reasoning_effort": _MODEL_CONNECTION_PLACEHOLDER_REASONING_EFFORT,
                "timeout_seconds": _MODEL_CONNECTION_PLACEHOLDER_TIMEOUT_SECONDS,
            }
            placeholder_connection_id = connection.execute(
                text(
                    "SELECT id FROM model_connections "
                    "WHERE status = 'active' "
                    "AND name = :name "
                    "AND model_id = :model_id "
                    "AND base_url = :base_url "
                    "AND reasoning_effort = :reasoning_effort "
                    "AND protocol_profile = :protocol_profile "
                    "AND timeout_seconds = :timeout_seconds "
                    "AND secret_payload = '{}'::jsonb "
                    "ORDER BY id LIMIT 1"
                ),
                placeholder_parameters,
            ).scalar_one_or_none()

            if placeholder_connection_id is None:
                placeholder_parameters["key"] = build_unique_model_connection_key(
                    normalize_legacy_model_connection_key(
                        name=legacy_model,
                        model_id=legacy_model,
                    ),
                    used_model_connection_keys,
                )
                placeholder_connection_id = connection.execute(
                    text(
                        "INSERT INTO model_connections ("
                        "key, status, name, description, base_url, "
                        "model_id, reasoning_effort, protocol_profile, timeout_seconds, "
                        "secret_payload, created_at, updated_at"
                        ") VALUES ("
                        ":key, 'active', :name, '', :base_url, :model_id, "
                        ":reasoning_effort, :protocol_profile, :timeout_seconds, '{}'::jsonb, "
                        "NOW(), NOW()"
                        ") RETURNING id"
                    ),
                    placeholder_parameters,
                ).scalar_one()

            connection.execute(
                text(
                    "UPDATE agents "
                    "SET model_connection_id = :model_connection_id, updated_at = NOW() "
                    "WHERE model_connection_id IS NULL AND BTRIM(model) = :legacy_model"
                ),
                {
                    "legacy_model": legacy_model,
                    "model_connection_id": placeholder_connection_id,
                },
            )

        remaining_null_count = connection.execute(
            text("SELECT COUNT(*) FROM agents WHERE model_connection_id IS NULL")
        ).scalar_one()
        if needs_non_null_enforcement and remaining_null_count == 0:
            connection.exec_driver_sql(
                "ALTER TABLE agents ALTER COLUMN model_connection_id SET NOT NULL"
            )


def _ensure_run_lifecycle_support(engine: Engine, table_names: set[str]) -> None:
    if "runs" not in table_names:
        return

    inspector = inspect(engine)
    run_columns = {column["name"]: column for column in inspector.get_columns("runs")}
    run_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("runs")
        if constraint.get("name")
    }

    with engine.begin() as connection:
        if "queued_at" not in run_columns:
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN queued_at TIMESTAMPTZ")
            connection.execute(
                text(
                    """
                    UPDATE runs
                    SET queued_at = COALESCE(created_at, started_at, NOW())
                    WHERE queued_at IS NULL
                    """
                )
            )
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN queued_at SET NOT NULL")
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN queued_at SET DEFAULT NOW()")
        else:
            connection.execute(
                text(
                    """
                    UPDATE runs
                    SET queued_at = COALESCE(created_at, started_at, NOW())
                    WHERE queued_at IS NULL
                    """
                )
            )
            queued_at_column = run_columns["queued_at"]
            if queued_at_column.get("nullable", True):
                connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN queued_at SET NOT NULL")
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN queued_at SET DEFAULT NOW()")
        if "started_at" in run_columns:
            started_at_column = run_columns["started_at"]
            if not started_at_column.get("nullable", True):
                connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN started_at DROP NOT NULL")
            connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN started_at DROP DEFAULT")
        else:
            connection.exec_driver_sql("ALTER TABLE runs ADD COLUMN started_at TIMESTAMPTZ")
        connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN status SET DEFAULT 'queued'")
        if "ck_runs_status" in run_checks:
            connection.exec_driver_sql("ALTER TABLE runs DROP CONSTRAINT ck_runs_status")
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT ck_runs_status "
            "CHECK (status IN ('queued', 'running', 'succeeded', 'failed'))"
        )


def _ensure_run_scheduler_metadata_support(engine: Engine, table_names: set[str]) -> None:
    if "runs" not in table_names:
        return

    inspector = inspect(engine)
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    with engine.begin() as connection:
        for column_name, column_type in _RUN_SCHEDULER_METADATA_COLUMNS.items():
            if column_name not in run_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE runs ADD COLUMN {column_name} {column_type}"
                )
                run_columns.add(column_name)
        connection.exec_driver_sql(
            """
            UPDATE runs
            SET execution_scope_key = CASE
                WHEN target_kind = 'workflowPackage' THEN 'package:' || COALESCE(
                    NULLIF(btrim(workflow_package_key), ''),
                    NULLIF(btrim(target_key), ''),
                    target_id::text
                )
                WHEN target_kind IS NOT NULL AND btrim(target_kind) <> '' THEN
                    'target:' || target_kind || ':' || COALESCE(
                        NULLIF(btrim(target_key), ''),
                        target_id::text
                    )
                ELSE NULL
            END
            WHERE execution_scope_key IS NULL OR btrim(execution_scope_key) = ''
            """
        )
        connection.exec_driver_sql(
            """
            UPDATE runs
            SET concurrency_policy = CASE
                WHEN target_kind = 'workflowPackage' THEN 'serial'
                ELSE 'parallel'
            END
            WHERE concurrency_policy IS NULL
               OR btrim(concurrency_policy) = ''
               OR concurrency_policy NOT IN ('serial', 'parallel')
            """
        )
        connection.exec_driver_sql(
            "UPDATE runs SET attempt_count = 0 WHERE attempt_count IS NULL OR attempt_count < 0"
        )
        connection.exec_driver_sql(
            "ALTER TABLE runs ALTER COLUMN concurrency_policy SET DEFAULT 'serial'"
        )
        connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN concurrency_policy SET NOT NULL")
        connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN attempt_count SET DEFAULT 0")
        connection.exec_driver_sql("ALTER TABLE runs ALTER COLUMN attempt_count SET NOT NULL")
        _drop_constraint_if_exists(connection, "runs", "ck_runs_concurrency_policy")
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT ck_runs_concurrency_policy "
            "CHECK (concurrency_policy IN ('serial', 'parallel'))"
        )
        _drop_constraint_if_exists(connection, "runs", "ck_runs_attempt_count_non_negative")
        connection.exec_driver_sql(
            "ALTER TABLE runs ADD CONSTRAINT ck_runs_attempt_count_non_negative "
            "CHECK (attempt_count >= 0)"
        )
        for statement in _RUN_SCHEDULER_NON_UNIQUE_INDEXES:
            connection.exec_driver_sql(statement)


def _ensure_run_scheduler_serial_index(engine: Engine, table_names: set[str]) -> None:
    if "runs" not in table_names:
        return
    run_columns = {column["name"] for column in inspect(engine).get_columns("runs")}
    if not {"execution_scope_key", "concurrency_policy"} <= run_columns:
        return
    with engine.begin() as connection:
        connection.exec_driver_sql(_RUN_SCHEDULER_SERIAL_INDEX_SQL)


def _ensure_run_graph_metadata_support(engine: Engine, table_names: set[str]) -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "run_steps" in table_names:
            run_step_columns = {column["name"] for column in inspector.get_columns("run_steps")}
            if "graph_metadata" not in run_step_columns:
                connection.exec_driver_sql("ALTER TABLE run_steps ADD COLUMN graph_metadata JSONB")
        if "run_agent_invocations" in table_names:
            invocation_columns = {
                column["name"] for column in inspector.get_columns("run_agent_invocations")
            }
            if "graph_metadata" not in invocation_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE run_agent_invocations ADD COLUMN graph_metadata JSONB"
                )
        if "run_operation_invocations" in table_names:
            operation_columns = {
                column["name"] for column in inspector.get_columns("run_operation_invocations")
            }
            if "graph_metadata" not in operation_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE run_operation_invocations ADD COLUMN graph_metadata JSONB"
                )


def _recover_stale_agent_platform_runs(engine: Engine, table_names: set[str]) -> None:
    if "runs" not in table_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE runs
                SET status = 'failed',
                    error = COALESCE(NULLIF(error, ''), :restart_failure_message),
                    finished_at = COALESCE(finished_at, NOW()),
                    updated_at = NOW()
                WHERE status = 'running'
                """
            ),
            {"restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE},
        )
        if "run_steps" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_steps
                    SET status = 'failed',
                        error = COALESCE(NULLIF(error, ''), :restart_failure_message),
                        finished_at = COALESCE(finished_at, NOW()),
                        updated_at = NOW()
                    WHERE status = 'running'
                    """
                ),
                {"restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE},
            )
            connection.execute(
                text(
                    """
                    UPDATE run_steps AS step
                    SET status = 'skipped',
                        error = COALESCE(NULLIF(step.error, ''), :pending_skip_message),
                        finished_at = COALESCE(step.finished_at, NOW()),
                        updated_at = NOW()
                    FROM runs AS run
                    WHERE step.run_id = run.id
                      AND run.status = 'failed'
                      AND step.status = 'pending'
                    """
                ),
                {"pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE},
            )
        if "run_agent_invocations" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_agent_invocations
                    SET status = 'failed',
                        error_code = COALESCE(NULLIF(error_code, ''), 'startup_recovery'),
                        error_message = COALESCE(
                            NULLIF(error_message, ''),
                            :restart_failure_message
                        ),
                        finished_at = COALESCE(finished_at, NOW()),
                        updated_at = NOW()
                    WHERE status = 'running'
                    """
                ),
                {"restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE},
            )
            connection.execute(
                text(
                    """
                    UPDATE run_agent_invocations AS invocation
                    SET status = 'skipped',
                        error_code = COALESCE(
                            NULLIF(invocation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(invocation.error_message, ''),
                            :pending_skip_message
                        ),
                        finished_at = COALESCE(invocation.finished_at, NOW()),
                        updated_at = NOW()
                    FROM runs AS run
                    WHERE invocation.run_id = run.id
                      AND run.status = 'failed'
                      AND invocation.status = 'pending'
                    """
                ),
                {"pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE},
            )
        if "run_operation_invocations" in table_names:
            connection.execute(
                text(
                    """
                    UPDATE run_operation_invocations
                    SET status = 'failed',
                        error_code = COALESCE(NULLIF(error_code, ''), 'startup_recovery'),
                        error_message = COALESCE(
                            NULLIF(error_message, ''),
                            :restart_failure_message
                        ),
                        finished_at = COALESCE(finished_at, NOW()),
                        updated_at = NOW()
                    WHERE status = 'running'
                    """
                ),
                {"restart_failure_message": _AGENT_PLATFORM_RESTART_FAILURE_MESSAGE},
            )
            connection.execute(
                text(
                    """
                    UPDATE run_operation_invocations AS operation
                    SET status = 'skipped',
                        error_code = COALESCE(
                            NULLIF(operation.error_code, ''),
                            'startup_recovery'
                        ),
                        error_message = COALESCE(
                            NULLIF(operation.error_message, ''),
                            :pending_skip_message
                        ),
                        finished_at = COALESCE(operation.finished_at, NOW()),
                        updated_at = NOW()
                    FROM runs AS run
                    WHERE operation.run_id = run.id
                      AND run.status = 'failed'
                      AND operation.status = 'pending'
                    """
                ),
                {"pending_skip_message": _AGENT_PLATFORM_PENDING_SKIP_MESSAGE},
            )


def _reset_legacy_mcp_server_table(engine: Engine, table_names: set[str]) -> None:
    if "mcp_servers" not in table_names:
        return

    inspector = inspect(engine)
    mcp_columns = {column["name"] for column in inspector.get_columns("mcp_servers")}
    expected_columns = {"id", "key", "version", "status", "config", "created_at", "updated_at"}
    if mcp_columns == expected_columns:
        return

    if "config" in mcp_columns and not (
        {"transport", "command", "url", "auth", "enabled"} & mcp_columns
    ):
        return

    statements = dict(_AGENT_PLATFORM_TABLE_STATEMENTS)["mcp_servers"]
    with engine.begin() as connection:
        connection.exec_driver_sql('DROP TABLE IF EXISTS "mcp_servers" CASCADE')
        for statement in statements:
            connection.exec_driver_sql(statement)
    table_names.add("mcp_servers")


def _sanitize_retired_stock_analysis_resources(engine: Engine, table_names: set[str]) -> None:
    del engine, table_names


def _drop_tables(engine: Engine, table_names: set[str], tables: tuple[str, ...]) -> None:
    with engine.begin() as connection:
        for table_name in tables:
            if table_name not in table_names:
                continue
            connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            table_names.discard(table_name)


def _repair_legacy_agent_memory_report_sources(engine: Engine, table_names: set[str]) -> None:
    if "reports" not in table_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE reports
                SET source = 'agent',
                    metadata = jsonb_set(
                        metadata,
                        '{createdBy}',
                        jsonb_strip_nulls(
                            jsonb_build_object(
                                'type', 'agent',
                                'runId', (metadata->'analysis'->>'runId')::int,
                                'agentKey', metadata->'analysis'->'agentKey',
                                'agentVersion', (metadata->'analysis'->>'agentVersion')::int,
                                'agentName', metadata->'analysis'->'agentName',
                                'workflowKey', metadata->'analysis'->'workflowKey',
                                'workflowVersion', metadata->'analysis'->'workflowVersion',
                                'stepId', metadata->'analysis'->'stepId',
                                'slot', metadata->'analysis'->'slot',
                                'traceId', metadata->'analysis'->'traceId'
                            )
                        ),
                        true
                    ),
                    updated_at = NOW()
                WHERE source = 'external'
                  AND jsonb_typeof(metadata) = 'object'
                  AND jsonb_typeof(metadata->'analysis') = 'object'
                  AND metadata->'analysis'->>'reviewType' = 'agent_memory'
                  AND metadata->'analysis'->>'versionGroup' = 'agent_memory/v1'
                  AND btrim(COALESCE(metadata->'analysis'->>'agentKey', '')) <> ''
                  AND (metadata->'analysis'->>'agentVersion') ~ '^[0-9]+$'
                  AND (metadata->'analysis'->>'runId') ~ '^[0-9]+$'
                """
            )
        )


def upgrade_legacy_schema(engine: Engine) -> None:
    validate_supported_database_engine(engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    hard_cutover_required = _agent_platform_hard_cutover_required(engine, table_names)
    _ensure_extension_state_table(engine, table_names)
    _cutover_capability_storage(engine, table_names)
    if hard_cutover_required:
        _reset_agent_platform_runtime_tables(engine, table_names)
    _ensure_hard_delete_lifecycle_schema(engine, table_names)
    _ensure_workflow_package_tables(engine, table_names)
    _ensure_agent_platform_tables(engine, table_names)
    _ensure_run_workflow_package_provenance_support(engine, table_names)
    _remove_run_cost_columns(engine, table_names)
    if not hard_cutover_required and _agent_platform_hard_cutover_required(engine, table_names):
        _reset_agent_platform_runtime_tables(engine, table_names)
        _ensure_agent_platform_tables(engine, table_names)
        _ensure_run_workflow_package_provenance_support(engine, table_names)
        _remove_run_cost_columns(engine, table_names)
    _ensure_workflow_package_schedule_tables(engine, table_names)
    _ensure_runtime_input_registry_table(engine, table_names)
    _ensure_browser_proven_package_preset(engine, table_names)
    _delete_clean_break_global_authoring_rows(engine, table_names)
    _ensure_model_connection_key_support(engine, table_names)
    _remove_legacy_model_connection_kind_support(
        engine, table_names
    )  # OMO_ALLOW_LEGACY_MODEL_CONNECTION_CLEANUP
    _ensure_model_connection_reasoning_effort_support(engine, table_names)
    _ensure_model_connection_protocol_contract_support(engine, table_names)
    _drop_model_connection_api_key_metadata_columns(engine, table_names)
    _ensure_agent_manifest_columns(engine, table_names)
    _ensure_workflow_manifest_columns(engine, table_names)
    _remove_dead_agent_runtime_fields(engine, table_names)
    _remove_global_authoring_allocation_columns(engine, table_names)
    _ensure_agent_model_connection_support(engine, table_names)
    _backfill_agent_model_connections(
        engine,
        table_names,
    )
    _ensure_agent_model_connection_snapshot_support(engine, table_names)
    _reset_legacy_mcp_server_table(engine, table_names)
    _ensure_hard_delete_lifecycle_schema(engine, table_names)
    _delete_rows_with_unresolved_dependency_refs(engine, table_names)
    _ensure_platform_reference_tables(engine, table_names)
    _backfill_platform_reference_tables(engine, table_names)
    _ensure_platform_foreign_keys(engine, table_names)
    _ensure_run_lifecycle_support(engine, table_names)
    _ensure_run_scheduler_metadata_support(engine, table_names)
    _ensure_run_graph_metadata_support(engine, table_names)
    _ensure_core_memory_tables(engine, table_names)
    _recover_stale_agent_platform_runs(engine, table_names)
    _ensure_run_scheduler_serial_index(engine, table_names)

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
        _repair_legacy_agent_memory_report_sources(engine, table_names)

    if "market_quotes" in table_names:
        market_quote_columns = {column["name"] for column in inspector.get_columns("market_quotes")}
        if "name" not in market_quote_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE market_quotes ADD COLUMN name VARCHAR(255)")

    _sanitize_retired_stock_analysis_resources(engine, table_names)
    _drop_tables(engine, table_names, _LEGACY_BACKEND_TABLES)
    _drop_tables(engine, table_names, _OBSOLETE_TABLES)
