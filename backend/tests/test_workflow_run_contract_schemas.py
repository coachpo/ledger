from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.run import (
    RunRead,
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunTargetKind,
)


def test_run_status_contract_is_frozen() -> None:
    assert {status.value for status in RunStatus} == {
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_run_target_kind_contract_is_package_only() -> None:
    assert {target_kind.value for target_kind in RunTargetKind} == {"workflowPackage"}


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
    assert create.model_dump(by_alias=True, mode="json") == {"parameters": {"ticker": "MSFT"}}
    with pytest.raises(ValidationError):
        _ = RunRerunCreateRequest.model_validate(
            {"parameters": {"ticker": "MSFT"}, "unexpected": True}
        )
    with pytest.raises(ValidationError):
        _ = RunRerunCreateRequest.model_validate({"parameters": "MSFT"})


def test_run_read_rejects_non_package_target_kinds() -> None:
    timestamp = "2026-05-03T12:00:00Z"
    run_payload: dict[str, object] = {
        "id": 99,
        "targetKind": "workflow",
        "targetId": 42,
        "targetKey": "portfolio_review",
        "input": {"ticker": "TSLA"},
        "sourceRunId": 11,
        "finalOutput": {"summary": "run output"},
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
        "traceId": "trace-run",
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
                "origin": "planned",
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
                        "resolvedInputOrigin": "derived",
                        "output": {"summary": "source output"},
                        "outputOrigin": "executed",
                        "errorCode": None,
                        "errorMessage": None,
                        "errorDetails": [],
                        "tokens": 5,
                        "durationMs": 17,
                        "traceSpanId": "span-run",
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
        _ = RunRead.model_validate(run_payload)
