from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from sqlalchemy.orm import Session, sessionmaker

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_preflight import (
    WorkflowPackageDiagnosticFact,
    WorkflowPackageDiagnosticLevel,
    WorkflowPackageDiagnosticProjectionContext,
    WorkflowPackagePreflightService,
)
from tests.test_workflow_package_manifest_http_node import http_node_package_source


def test_diagnostic_fact_identity_ignores_issue_text_and_preserves_first_occurrence() -> None:
    levels = {
        WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
            WorkflowPackageDiagnosticLevel.BLOCKING
        )
    }
    first_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        issue="first issue",
        subject="missing_model",
        metadata={"ordinal": 1},
        levels=levels,
    )
    duplicate_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        issue="duplicate issue",
        subject="missing_model",
        metadata={"ordinal": 2},
        levels=levels,
    )
    distinct_fact = WorkflowPackageDiagnosticFact(
        kind="execution_plan_invalid",
        code="execution_plan_invalid",
        issue="distinct issue",
        subject="advisory_research",
        metadata={"ordinal": 3},
        levels=levels,
    )

    assert first_fact.identity == duplicate_fact.identity

    blocking_errors, warnings = WorkflowPackagePreflightService._project_diagnostic_facts(
        [first_fact, duplicate_fact, distinct_fact],
        context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
    )

    assert [error["ordinal"] for error in blocking_errors] == [1, 3]
    assert warnings == []


def test_diagnostic_fact_projection_contexts_choose_expected_levels() -> None:
    missing_model_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_not_found",
        code="model_connection_not_found",
        issue="model missing",
        subject="missing_model",
        metadata={"source": "missing_model"},
        levels={
            WorkflowPackageDiagnosticProjectionContext.VALIDATION: (
                WorkflowPackageDiagnosticLevel.WARNING
            ),
            WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
        },
    )
    api_key_fact = WorkflowPackageDiagnosticFact(
        kind="model_connection_api_key_missing",
        code="model_connection_api_key_missing",
        issue="key missing",
        subject="missing_model",
        metadata={"source": "api_key"},
        levels={
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            )
        },
    )
    schema_fact = WorkflowPackageDiagnosticFact(
        kind="schema_invalid",
        code="schema_invalid",
        issue="schema invalid",
        metadata={"source": "schema"},
        levels={
            WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
            WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                WorkflowPackageDiagnosticLevel.BLOCKING
            ),
        },
    )

    validation_warnings = WorkflowPackagePreflightService._project_validation_warning_facts(
        [missing_model_fact, api_key_fact, schema_fact]
    )
    assert [warning["source"] for warning in validation_warnings] == ["missing_model"]

    launch_blocking_errors, launch_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            [missing_model_fact, api_key_fact, schema_fact],
            context=WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA,
        )
    )
    assert [error["source"] for error in launch_blocking_errors] == [
        "missing_model",
        "schema",
    ]
    assert launch_warnings == []

    strict_blocking_errors, strict_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            [missing_model_fact, api_key_fact, schema_fact],
            context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
        )
    )
    assert [error["source"] for error in strict_blocking_errors] == [
        "missing_model",
        "api_key",
        "schema",
    ]
    assert strict_warnings == []


def test_readiness_diagnostic_fact_adapter_deduplicates_missing_model_warning() -> None:
    readiness_facts = [
        *WorkflowPackagePreflightService._readiness_diagnostic_facts(
            [
                {
                    "message": "Model connection 'missing_model' was not found",
                }
            ],
            level=WorkflowPackageDiagnosticLevel.BLOCKING,
        ),
        *WorkflowPackagePreflightService._readiness_diagnostic_facts(
            [
                {
                    "message": "Model connection 'missing_model' was not found",
                    "severity": "warning",
                }
            ],
            level=WorkflowPackageDiagnosticLevel.WARNING,
        ),
    ]

    launch_blocking_errors, launch_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            readiness_facts,
            context=WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA,
        )
    )

    assert len(launch_blocking_errors) == 1
    assert launch_warnings == []


def test_validation_projection_hides_blocker_only_facts_but_strict_keeps_payloads() -> None:
    blocker_only_facts = [
        WorkflowPackageDiagnosticFact(
            kind="schema_invalid",
            code="schema_invalid",
            issue="schema invalid",
            metadata={"payload": "schema"},
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
        WorkflowPackageDiagnosticFact(
            kind="http_secret_missing",
            code="http_secret_missing",
            issue="secret missing",
            subject="body_token",
            metadata={"payload": "secret"},
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
        WorkflowPackageDiagnosticFact(
            kind="execution_plan_invalid",
            code="execution_plan_invalid",
            issue="cycle",
            metadata={"payload": "plan"},
            levels={
                WorkflowPackageDiagnosticProjectionContext.LAUNCH_METADATA: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
                WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS: (
                    WorkflowPackageDiagnosticLevel.BLOCKING
                ),
            },
        ),
    ]

    assert (
        WorkflowPackagePreflightService._project_validation_warning_facts(blocker_only_facts) == []
    )

    strict_blocking_errors, strict_warnings = (
        WorkflowPackagePreflightService._project_diagnostic_facts(
            blocker_only_facts,
            context=WorkflowPackageDiagnosticProjectionContext.STRICT_READINESS,
        )
    )

    assert [error["payload"] for error in strict_blocking_errors] == [
        "schema",
        "secret",
        "plan",
    ]
    assert strict_warnings == []


def test_http_operation_diagnostics_cover_unsupported_method_and_malformed_step_ref(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(http_node_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
    operation = cast(list[dict[str, Any]], workflow["steps"])[0]["operations"][0]
    output_schema_keys = {
        str(schema["key"]) for schema in cast(list[dict[str, Any]], compiled_plan["outputSchemas"])
    }

    with session_factory() as session:
        service = WorkflowPackagePreflightService(session)
        unsupported_method = deepcopy(operation)
        unsupported_method["method"] = "PATCH"
        method_facts = service._http_operation_errors(
            unsupported_method,
            workflow_key="notify",
            step_index=1,
            operation_index=0,
            output_schema_keys=output_schema_keys,
            configured_secret_keys={"body_token", "slack_webhook_token"},
            seen_operation_keys=set(),
            seen_slots=set(),
        )

        malformed_ref = deepcopy(operation)
        cast(dict[str, Any], malformed_ref["request"])["body"] = {
            "from": "step",
            "stepIndex": 1,
        }
        ref_facts = service._http_operation_errors(
            malformed_ref,
            workflow_key="notify",
            step_index=1,
            operation_index=0,
            output_schema_keys=output_schema_keys,
            configured_secret_keys={"body_token", "slack_webhook_token"},
            seen_operation_keys=set(),
            seen_slots=set(),
        )

    assert [fact.code for fact in method_facts] == ["http_operation_invalid"]
    assert [fact.code for fact in ref_facts] == ["http_operation_invalid"]
