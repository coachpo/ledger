from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import run as run_schemas
from app.schemas.run import (
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
        "targetKind": RunTargetKind.WORKFLOW.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "parameters": {"ticker": "MSFT"},
        "packageProvenance": None,
    }

    draft = RunRerunDraftRead.model_validate(draft_payload)
    create = RunRerunCreateRequest.model_validate({"parameters": {"ticker": "MSFT"}})

    assert draft.model_dump(by_alias=True, mode="json") == draft_payload
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
        "targetKind": RunTargetKind.WORKFLOW.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "invocationInput": {"ticker": "MSFT", "notes": "adjust thesis"},
        "packageProvenance": None,
    }

    fork_draft_read = getattr(run_schemas, "RunForkDraftRead")
    fork_create_request = getattr(run_schemas, "RunForkCreateRequest")
    draft = fork_draft_read.model_validate(draft_payload)
    create = fork_create_request.model_validate(
        {"sourceInvocationId": 77, "invocationInput": {"ticker": "MSFT"}}
    )

    assert draft.model_dump(by_alias=True, mode="json") == draft_payload
    assert create.model_dump(by_alias=True, mode="json") == {
        "sourceInvocationId": 77,
        "invocationInput": {"ticker": "MSFT"},
    }
    with pytest.raises(ValidationError):
        _ = fork_create_request.model_validate(
            {
                "sourceInvocationId": 77,
                "invocationInput": {"ticker": "MSFT"},
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError):
        _ = fork_create_request.model_validate(
            {"sourceInvocationId": 77, "invocationInput": "MSFT"}
        )
    with pytest.raises(ValidationError):
        _ = fork_create_request.model_validate(
            {"sourceInvocationId": 77, "parameters": {"ticker": "MSFT"}}
        )
    with pytest.raises(ValidationError):
        _ = fork_create_request.model_validate(
            {"replayStepIndex": 2, "invocationInput": {"ticker": "MSFT"}}
        )


def test_run_read_preserves_legacy_replay_lineage_as_read_only_fields() -> None:
    timestamp = "2026-05-03T12:00:00Z"
    legacy_replay_lineage_payload = {
        "id": 99,
        "targetKind": RunTargetKind.WORKFLOW.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "input": {"ticker": "TSLA"},
        "sourceRunId": 11,
        "lineageRootRunId": 11,
        "replayStepIndex": 2,
        "resumeStepIndex": 2,
        "finalOutput": {"summary": "legacy replay output"},
        "status": RunStatus.SUCCEEDED.value,
        "totalTokens": 12,
        "inheritedTokens": 5,
        "executedTokens": 7,
        "traceId": "trace-legacy-replay",
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
                        "agentId": 1,
                        "agentKey": "package_analyst",
                        "agentVersion": 1,
                        "outputSchemaId": 1,
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
                        "traceSpanId": "span-legacy-replay",
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
        "memoryArtifacts": [],
        "memoryEvents": [],
        "extensionDependencies": [],
        "packageProvenance": None,
    }

    read = RunRead.model_validate(legacy_replay_lineage_payload)
    dumped = read.model_dump(by_alias=True, mode="json")

    assert dumped["sourceRunId"] == 11
    assert dumped["lineageRootRunId"] == 11
    assert dumped["replayStepIndex"] == 2
    assert dumped["resumeStepIndex"] == 2
    legacy_step = dumped["steps"][0]
    assert legacy_step["origin"] == "copied"
    assert legacy_step["sourceRunStepId"] == 101
    assert legacy_step["sourceRunId"] == 11
    assert legacy_step["sourceStepIndex"] == 1
    legacy_invocation = legacy_step["invocations"][0]
    assert legacy_invocation["sourceInvocationId"] == 77
    assert legacy_invocation["resolvedInputOrigin"] == "copied"
