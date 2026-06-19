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
    _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research_macro.sql",
    _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research_mixed_signals.sql",
)
_DEMO_PRESET_OWNER_EXPECTATIONS = (
    {
        "name": "TradingAgents demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "tradingagents_advisory_research.yaml",
        "sql_seed_path": (
            _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research.sql"
        ),
        "allowed_tool_prefixes": ("signaldeck.finance.",),
        "forbidden_tool_keys": (
            "signaldeck.digital_oracle.crypto_derivatives.lookup",
            "signaldeck.digital_oracle.cftc_positioning.lookup",
            "signaldeck.digital_oracle.macro_rates.lookup",
            "signaldeck.digital_oracle.market_sentiment.lookup",
            "signaldeck.digital_oracle.options.lookup",
            "signaldeck.digital_oracle.prediction_markets.lookup",
            "signaldeck.digital_oracle.sec_filings.lookup",
        ),
    },
    {
        "name": "Digital Oracle researcher demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "digital_oracle_researcher.yaml",
        "sql_seed_path": _REPO_ROOT / "backend" / "app" / "db" / "digital_oracle_researcher.sql",
        "allowed_tool_prefixes": ("signaldeck.digital_oracle.",),
        "forbidden_tool_keys": (),
    },
    {
        "name": "TradingAgents macro demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "tradingagents_advisory_research_macro.yaml",
        "sql_seed_path": (
            _REPO_ROOT / "backend" / "app" / "db" / "tradingagents_advisory_research_macro.sql"
        ),
        "allowed_tool_prefixes": ("signaldeck.finance.",),
        "forbidden_tool_keys": (
            "signaldeck.digital_oracle.crypto_derivatives.lookup",
            "signaldeck.digital_oracle.cftc_positioning.lookup",
            "signaldeck.digital_oracle.macro_rates.lookup",
            "signaldeck.digital_oracle.market_sentiment.lookup",
            "signaldeck.digital_oracle.options.lookup",
            "signaldeck.digital_oracle.prediction_markets.lookup",
            "signaldeck.digital_oracle.sec_filings.lookup",
        ),
    },
    {
        "name": "TradingAgents mixed-signals demo preset",
        "manifest_path": _REPO_ROOT / "demo" / "tradingagents_advisory_research_mixed_signals.yaml",
        "sql_seed_path": (
            _REPO_ROOT
            / "backend"
            / "app"
            / "db"
            / "tradingagents_advisory_research_mixed_signals.sql"
        ),
        "allowed_tool_prefixes": ("signaldeck.finance.", "signaldeck.digital_oracle."),
        "forbidden_tool_keys": (
            "signaldeck.digital_oracle.crypto_derivatives.lookup",
            "signaldeck.digital_oracle.cftc_positioning.lookup",
            "signaldeck.digital_oracle.sec_filings.lookup",
            "signaldeck.digital_oracle.market_sentiment.lookup",
            "signaldeck.digital_oracle.options.lookup",
        ),
    },
)
_SQL_BASE64_DECODE_RE: re.Pattern[str] = re.compile(
    r"decode\('([^']+)'\s*,\s*'base64'\)",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNALDECK_TOOL_KEY_RE: re.Pattern[str] = re.compile(
    r"signaldeck\.(?:finance|digital_oracle)(?:\.[A-Za-z0-9_]+)+"
)
_FINANCE_TOOL_KEYS = {
    "signaldeck.finance.fundamentals.lookup",
    "signaldeck.finance.indicators.lookup",
    "signaldeck.finance.insider_data.lookup",
    "signaldeck.finance.market_data.history_lookup",
    "signaldeck.finance.market_data.ohlcv_lookup",
    "signaldeck.finance.market_data.quote_lookup",
    "signaldeck.finance.news.lookup",
    "signaldeck.finance.positions.lookup",
    "signaldeck.finance.reports.lookup",
    "signaldeck.finance.social_sentiment.lookup",
}
_DIGITAL_ORACLE_PHASE1_NATIVE_TOOL_KEYS = {
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
}
_MACRO_PRIVATE_HTTP_OPERATION_IDS = {
    "fred_cpiaucsl_observations",
    "fred_fedfunds_observations",
    "fred_t10y2y_observations",
    "fred_unrate_observations",
    "treasury_rates_snapshot_json",
}
_DEMO_SQL_PAYLOAD_EXPECTATIONS = {
    "tradingagents_advisory_research.sql": (
        _FINANCE_TOOL_KEYS,
        set(),
        {"signaldeck.finance"},
    ),
    "tradingagents_advisory_research_macro.sql": (
        _FINANCE_TOOL_KEYS,
        _MACRO_PRIVATE_HTTP_OPERATION_IDS,
        {"signaldeck.finance"},
    ),
    "tradingagents_advisory_research_mixed_signals.sql": (
        _FINANCE_TOOL_KEYS
        | {
            "signaldeck.digital_oracle.macro_rates.lookup",
            "signaldeck.digital_oracle.prediction_markets.lookup",
        },
        set(),
        {"signaldeck.digital_oracle", "signaldeck.finance"},
    ),
    "digital_oracle_researcher.sql": (
        _DIGITAL_ORACLE_PHASE1_NATIVE_TOOL_KEYS,
        set(),
        {"signaldeck.digital_oracle", "signaldeck.finance"},
    ),
}
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


def _decoded_sql_artifacts(
    sql_seed_path: Path,
) -> tuple[str, dict[str, object], dict[str, object], list[dict[str, object]]]:
    decoded_payloads = _decoded_sql_payloads(sql_seed_path)
    assert len(decoded_payloads) == 4
    package_definition = cast(dict[str, object], json.loads(decoded_payloads[1]))
    compiled_plan = cast(dict[str, object], json.loads(decoded_payloads[2]))
    extension_dependencies = cast(list[dict[str, object]], json.loads(decoded_payloads[3]))
    return decoded_payloads[0], package_definition, compiled_plan, extension_dependencies


def _profile_tool_keys(package_definition: dict[str, object]) -> set[str]:
    spec = cast(dict[str, object], package_definition["spec"])
    profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    return {
        tool_key
        for profile in profiles
        for tool_key in cast(list[str], profile["toolKeys"])
    }


def _operation_ids(compiled_plan: dict[str, object]) -> set[str]:
    return {
        str(operation["operationKey"])
        for workflow in cast(list[dict[str, object]], compiled_plan["workflows"])
        for step in cast(list[dict[str, object]], workflow["steps"])
        for operation in cast(list[dict[str, object]], step.get("operations", []))
    }


def _assert_owner_scoped_tool_usage(
    source: str,
    *,
    context: str,
    allowed_tool_prefixes: tuple[str, ...],
    forbidden_tool_keys: tuple[str, ...],
) -> None:
    forbidden_hits = sorted(tool_key for tool_key in forbidden_tool_keys if tool_key in source)
    assert not forbidden_hits, f"{context} contains non-owner tool references: {forbidden_hits}"
    tool_keys = sorted(set(cast(list[str], _SIGNALDECK_TOOL_KEY_RE.findall(source))))
    non_owner_tool_keys = [
        tool_key
        for tool_key in tool_keys
        if not any(tool_key.startswith(prefix) for prefix in allowed_tool_prefixes)
    ]
    assert (
        not non_owner_tool_keys
    ), f"{context} contains tool keys outside {allowed_tool_prefixes}: {non_owner_tool_keys}"


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


def test_sql_seed_payloads_lock_tool_operation_and_extension_dependencies() -> None:
    for sql_seed_path in _SQL_SEED_PATHS:
        _, package_definition, compiled_plan, extension_dependencies = _decoded_sql_artifacts(
            sql_seed_path
        )
        expected_tool_keys, expected_operation_ids, expected_extension_keys = (
            _DEMO_SQL_PAYLOAD_EXPECTATIONS[sql_seed_path.name]
        )

        assert _profile_tool_keys(package_definition) == expected_tool_keys
        assert _operation_ids(compiled_plan) == expected_operation_ids
        assert {dependency["extensionKey"] for dependency in extension_dependencies} == (
            expected_extension_keys
        )


def test_demo_presets_and_sql_seeds_use_only_their_extension_tools() -> None:
    for expectation in _DEMO_PRESET_OWNER_EXPECTATIONS:
        name = cast(str, expectation["name"])
        manifest_path = cast(Path, expectation["manifest_path"])
        sql_seed_path = cast(Path, expectation["sql_seed_path"])
        allowed_tool_prefixes = cast(tuple[str, ...], expectation["allowed_tool_prefixes"])
        forbidden_tool_keys = cast(tuple[str, ...], expectation["forbidden_tool_keys"])

        manifest_source = manifest_path.read_text(encoding="utf-8")
        _assert_owner_scoped_tool_usage(
            manifest_source,
            context=f"{name} manifest",
            allowed_tool_prefixes=allowed_tool_prefixes,
            forbidden_tool_keys=forbidden_tool_keys,
        )

        decoded_payloads = _decoded_sql_payloads(sql_seed_path)
        assert decoded_payloads
        for decoded_payload in decoded_payloads:
            _assert_owner_scoped_tool_usage(
                decoded_payload,
                context=f"{name} SQL seed payload",
                allowed_tool_prefixes=allowed_tool_prefixes,
                forbidden_tool_keys=forbidden_tool_keys,
            )
