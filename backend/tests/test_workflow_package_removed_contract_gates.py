from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from tests.test_workflow_package_manifest_http_node import assert_removed_contract_tokens_absent

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SQL_SEED_PATHS = (
    _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research.sql",
    _REPO_ROOT / "backend" / "app" / "db" / "digital_oracle_researcher.sql",
)
_DEMO_PRESET_OWNER_EXPECTATIONS = (
    {
        "name": "TradingAgents demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "tradingagents_advisory_research.yaml",
        "sql_seed_path": (
            _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research.sql"
        ),
        "owned_tool_prefix": "signaldeck.finance.",
        "forbidden_fragments": ("signaldeck.digital_oracle",),
    },
    {
        "name": "Digital Oracle researcher demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "digital_oracle_researcher.yaml",
        "sql_seed_path": _REPO_ROOT / "backend" / "app" / "db" / "digital_oracle_researcher.sql",
        "owned_tool_prefix": "signaldeck.digital_oracle.",
        "forbidden_fragments": ("signaldeck.finance", "web_search_exa"),
    },
)
_SQL_BASE64_DECODE_RE: re.Pattern[str] = re.compile(
    r"decode\('([^']+)'\s*,\s*'base64'\)",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNALDECK_TOOL_KEY_RE: re.Pattern[str] = re.compile(
    r"signaldeck\.(?:finance|digital_oracle)(?:\.[A-Za-z0-9_]+)+"
)
S13_DEFERRED_REMOVED_OPENAPI_TOKENS = (
    "Budget USD",
    "budgetUsd",
    "budget_usd",
    "aggregate_budget_usd",
    "aggregateBudgetUsd",
    "BudgetUsd",
    "validation_summary",
    "validationSummary",
)
LIVE_OPENAPI_CONTRACT_SCHEMAS = (
    "RunPackageProvenanceRead",
    "RunRead",
    "WorkflowPackageLaunchRead",
    "WorkflowPackageManifestRead",
    "WorkflowPackagePreflightRead",
    "WorkflowPackageRead",
    "WorkflowPackageValidationRead",
)


def _decoded_sql_payloads(sql_seed_path: Path) -> list[str]:
    sql_source = sql_seed_path.read_text(encoding="utf-8")
    encoded_payloads = cast(list[str], _SQL_BASE64_DECODE_RE.findall(sql_source))
    return [
        base64.b64decode(encoded_payload, validate=True).decode("utf-8")
        for encoded_payload in encoded_payloads
    ]


def _assert_owner_scoped_tool_usage(
    source: str,
    *,
    context: str,
    owned_tool_prefix: str,
    forbidden_fragments: tuple[str, ...],
) -> None:
    forbidden_hits = sorted(fragment for fragment in forbidden_fragments if fragment in source)
    assert not forbidden_hits, f"{context} contains non-owner tool references: {forbidden_hits}"
    tool_keys = sorted(set(cast(list[str], _SIGNALDECK_TOOL_KEY_RE.findall(source))))
    non_owner_tool_keys = [
        tool_key for tool_key in tool_keys if not tool_key.startswith(owned_tool_prefix)
    ]
    assert (
        not non_owner_tool_keys
    ), f"{context} contains tool keys outside {owned_tool_prefix}: {non_owner_tool_keys}"


def test_openapi_workflow_package_contracts_exclude_removed_tokens(app: FastAPI) -> None:
    openapi = cast(dict[str, object], app.openapi())
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])
    checked_schemas = {
        schema_name: schemas[schema_name]
        for schema_name in LIVE_OPENAPI_CONTRACT_SCHEMAS
        if schema_name in schemas
    }
    serialized_schemas = json.dumps(checked_schemas, default=str, sort_keys=True)

    assert {"RunRead", "WorkflowPackageRead"} <= checked_schemas.keys()
    assert not any(token in serialized_schemas for token in S13_DEFERRED_REMOVED_OPENAPI_TOKENS)
    assert not any(
        token in schema_name
        for schema_name in schemas
        for token in S13_DEFERRED_REMOVED_OPENAPI_TOKENS
    )
    assert_removed_contract_tokens_absent(
        checked_schemas,
        context="workflow package and run OpenAPI schemas",
    )


def test_sql_seed_payloads_decode_without_removed_contract_tokens() -> None:
    decoded_payload_count = 0
    for sql_seed_path in _SQL_SEED_PATHS:
        for decoded_payload in _decoded_sql_payloads(sql_seed_path):
            decoded_payload_count += 1
            assert_removed_contract_tokens_absent(
                decoded_payload,
                context=f"decoded SQL payload in {sql_seed_path.relative_to(_REPO_ROOT)}",
            )
    assert decoded_payload_count > 0


def test_demo_presets_and_sql_seeds_use_only_their_extension_tools() -> None:
    for expectation in _DEMO_PRESET_OWNER_EXPECTATIONS:
        name = cast(str, expectation["name"])
        manifest_path = cast(Path, expectation["manifest_path"])
        sql_seed_path = cast(Path, expectation["sql_seed_path"])
        owned_tool_prefix = cast(str, expectation["owned_tool_prefix"])
        forbidden_fragments = cast(tuple[str, ...], expectation["forbidden_fragments"])

        manifest_source = manifest_path.read_text(encoding="utf-8")
        _assert_owner_scoped_tool_usage(
            manifest_source,
            context=f"{name} manifest",
            owned_tool_prefix=owned_tool_prefix,
            forbidden_fragments=forbidden_fragments,
        )

        decoded_payloads = _decoded_sql_payloads(sql_seed_path)
        assert decoded_payloads
        for decoded_payload in decoded_payloads:
            _assert_owner_scoped_tool_usage(
                decoded_payload,
                context=f"{name} SQL seed payload",
                owned_tool_prefix=owned_tool_prefix,
                forbidden_fragments=forbidden_fragments,
            )
