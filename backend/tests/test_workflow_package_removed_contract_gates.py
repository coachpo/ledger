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
_SQL_BASE64_DECODE_RE: re.Pattern[str] = re.compile(
    r"decode\('([^']+)'\s*,\s*'base64'\)",
    re.IGNORECASE | re.MULTILINE,
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
        sql_source = sql_seed_path.read_text(encoding="utf-8")
        encoded_payloads = cast(list[str], _SQL_BASE64_DECODE_RE.findall(sql_source))
        for encoded_payload in encoded_payloads:
            decoded_payload = base64.b64decode(encoded_payload, validate=True).decode("utf-8")
            decoded_payload_count += 1
            assert_removed_contract_tokens_absent(
                decoded_payload,
                context=f"decoded SQL payload in {sql_seed_path.relative_to(_REPO_ROOT)}",
            )
    assert decoded_payload_count > 0
