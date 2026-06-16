from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import run as run_schemas
from app.schemas.run import (
    RunForkCreateRequest,
    RunForkDraftRead,
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunTargetKind,
)
from app.schemas.workflow import (
    WorkflowLaunchCreateRequest,
    WorkflowLaunchCreateResponse,
    WorkflowLaunchRead,
    WorkflowStatus,
    WorkflowVersionRead,
)


def test_workflow_launch_create_request_accepts_exact_envelope_with_dynamic_parameters() -> None:
    request = WorkflowLaunchCreateRequest.model_validate(
        {"version": 3, "parameters": {"ticker": "MSFT", "nested": {"limit": 5}}}
    )

    assert request.model_dump(by_alias=True, mode="json") == {
        "version": 3,
        "parameters": {"ticker": "MSFT", "nested": {"limit": 5}},
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"parameters": {"ticker": "MSFT"}},
        {"version": 3},
        {"version": 3, "parameters": "MSFT"},
        {"version": 3, "parameters": ["MSFT"]},
        {"version": 3, "parameters": {"ticker": "MSFT"}, "unexpected": True},
    ],
)
def test_workflow_launch_create_request_rejects_invalid_envelopes(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _ = WorkflowLaunchCreateRequest.model_validate(payload)


def test_run_status_contract_is_frozen() -> None:
    assert {status.value for status in RunStatus} == {"queued", "running", "succeeded", "failed"}


def test_run_target_kind_contract_is_package_only() -> None:
    assert {target_kind.value for target_kind in RunTargetKind} == {"workflowPackage"}


def test_workflow_launch_read_contract_uses_camel_case_aliases() -> None:
    payload = {
        "workflowId": 42,
        "key": "portfolio_review",
        "version": 7,
        "name": "Portfolio Review",
        "description": "Review holdings",
        "inputSchema": {"type": "object"},
    }

    read = WorkflowLaunchRead.model_validate(payload)

    assert read.model_dump(by_alias=True, mode="json") == payload


def test_workflow_version_read_contract_uses_camel_case_aliases() -> None:
    payload = {
        "id": 42,
        "key": "portfolio_review",
        "version": 7,
        "status": WorkflowStatus.PUBLISHED.value,
        "name": "Portfolio Review",
        "description": "Review holdings",
        "inputSchema": {"type": "object"},
        "createdAt": "2026-05-03T12:00:00Z",
        "updatedAt": "2026-05-03T12:01:00Z",
    }

    read = WorkflowVersionRead.model_validate(payload)

    assert read.model_dump(by_alias=True, mode="json") == payload


def test_workflow_launch_create_response_contract_uses_queued_status() -> None:
    created_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    response = WorkflowLaunchCreateResponse.model_validate(
        {
            "id": 99,
            "status": "queued",
            "workflowId": 42,
            "workflowKey": "portfolio_review",
            "workflowVersion": 7,
            "createdAt": created_at,
        }
    )

    assert response.model_dump(by_alias=True, mode="json") == {
        "id": 99,
        "status": "queued",
        "workflowId": 42,
        "workflowKey": "portfolio_review",
        "workflowVersion": 7,
        "createdAt": "2026-05-03T12:00:00Z",
    }


def test_rerun_contracts_use_parameters_object_and_reject_extra_fields() -> None:
    draft_payload = {
        "sourceRunId": 11,
        "targetKind": RunTargetKind.WORKFLOW_PACKAGE.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "parameters": {"ticker": "MSFT"},
        "ready": True,
        "blockingErrors": [],
        "warnings": [],
        "packageProvenance": None,
    }

    draft = RunRerunDraftRead.model_validate(draft_payload)
    create = RunRerunCreateRequest.model_validate({"parameters": {"ticker": "MSFT"}})

    assert draft.model_dump(by_alias=True, mode="json") == draft_payload
    assert "facts" not in draft.model_dump(by_alias=True, mode="json")
    assert create.model_dump(by_alias=True, mode="json") == {"parameters": {"ticker": "MSFT"}}
    with pytest.raises(ValidationError):
        _ = RunRerunCreateRequest.model_validate(
            {"parameters": {"ticker": "MSFT"}, "unexpected": True}
        )
    with pytest.raises(ValidationError):
        _ = RunRerunCreateRequest.model_validate({"parameters": "MSFT"})


def test_fork_contracts_use_source_invocation_input_and_reject_extra_fields() -> None:
    expected_contract_names = {"RunForkDraftRead", "RunForkCreateRequest"}
    exported_contract_names = set(getattr(run_schemas, "__all__", ()))
    assert expected_contract_names <= exported_contract_names

    draft_payload = {
        "sourceRunId": 11,
        "sourceInvocationId": 77,
        "targetKind": RunTargetKind.WORKFLOW_PACKAGE.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "invocationInput": {"ticker": "MSFT", "notes": "adjust thesis"},
        "ready": True,
        "blockingErrors": [],
        "warnings": [],
        "packageProvenance": None,
    }

    draft = RunForkDraftRead.model_validate(draft_payload)
    create = RunForkCreateRequest.model_validate(
        {"sourceInvocationId": 77, "invocationInput": {"ticker": "MSFT"}}
    )

    assert draft.model_dump(by_alias=True, mode="json") == draft_payload
    assert "facts" not in draft.model_dump(by_alias=True, mode="json")
    assert create.model_dump(by_alias=True, mode="json") == {
        "sourceInvocationId": 77,
        "invocationInput": {"ticker": "MSFT"},
    }
    with pytest.raises(ValidationError):
        _ = RunForkCreateRequest.model_validate(
            {
                "sourceInvocationId": 77,
                "invocationInput": {"ticker": "MSFT"},
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        _ = RunForkCreateRequest.model_validate(
            {"sourceInvocationId": 77, "invocationInput": "MSFT"}
        )
    with pytest.raises(ValidationError):
        _ = RunForkCreateRequest.model_validate(
            {"sourceInvocationId": 77, "parameters": {"ticker": "MSFT"}}
        )
    with pytest.raises(ValidationError):
        _ = RunForkCreateRequest.model_validate(
            {"replayStepIndex": 2, "invocationInput": {"ticker": "MSFT"}}
        )


def test_run_read_rejects_non_package_target_kinds() -> None:
    timestamp = "2026-05-03T12:00:00Z"
    historical_lineage_payload: dict[str, object] = {
        "id": 99,
        "targetKind": "workflow",
        "targetId": 42,
        "targetKey": "portfolio_review",
        "input": {"ticker": "TSLA"},
        "sourceRunId": 11,
        "lineageRootRunId": 11,
        "replayStepIndex": 2,
        "resumeStepIndex": 2,
        "finalOutput": {"summary": "historical lineage output"},
        "status": RunStatus.SUCCEEDED.value,
        "progress": {
            "unit": "invocation",
            "terminalCount": 1,
            "totalCount": 1,
            "percent": 100,
        },
        "totalTokens": 12,
        "inheritedTokens": 5,
        "executedTokens": 7,
        "traceId": "trace-historical-lineage",
        "error": None,
        "queuedAt": timestamp,
        "startedAt": timestamp,
        "finishedAt": timestamp,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "steps": [
            {
                "id": 201,
                "runId": 99,
                "index": 1,
                "status": "succeeded",
                "origin": "copied",
                "sourceRunStepId": 101,
                "sourceRunId": 11,
                "sourceStepIndex": 1,
                "graphMetadata": None,
                "error": None,
                "startedAt": timestamp,
                "finishedAt": timestamp,
                "persistedAt": timestamp,
                "createdAt": timestamp,
                "updatedAt": timestamp,
                "invocations": [
                    {
                        "id": 301,
                        "runStepId": 201,
                        "runId": 99,
                        "stepIndex": 1,
                        "slot": "analysis",
                        "position": 0,
                        "agentRef": {
                            "scope": "packageLocal",
                            "localId": 1,
                            "key": "package_analyst",
                            "version": 1,
                        },
                        "outputSchemaRef": {
                            "scope": "packageLocal",
                            "localId": 1,
                            "key": "summary_output",
                            "version": 1,
                        },
                        "agentKey": "package_analyst",
                        "agentVersion": 1,
                        "outputSchemaVersion": 1,
                        "inputMode": "wired",
                        "wiring": {"ticker": "inputs.ticker"},
                        "graphMetadata": None,
                        "optional": False,
                        "status": "succeeded",
                        "resolvedInput": {"ticker": "MSFT"},
                        "resolvedInputOrigin": "copied",
                        "output": {"summary": "copied source output"},
                        "outputOrigin": "copied",
                        "errorCode": None,
                        "errorMessage": None,
                        "errorDetails": [],
                        "tokens": 5,
                        "durationMs": 17,
                        "traceSpanId": "span-historical-lineage",
                        "sourceInvocationId": 77,
                        "startedAt": timestamp,
                        "finishedAt": timestamp,
                        "persistedAt": timestamp,
                        "createdAt": timestamp,
                        "updatedAt": timestamp,
                    }
                ],
                "operationInvocations": [],
            }
        ],
        "extensionDependencies": [],
        "packageProvenance": None,
    }

    with pytest.raises(ValidationError):
        _ = RunRead.model_validate(historical_lineage_payload)
