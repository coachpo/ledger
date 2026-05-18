from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.run import (
    RunRerunCreateRequest,
    RunRerunDraftRead,
    RunStatus,
    RunStepReplayCreateRequest,
    RunStepReplayDraftRead,
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


def test_step_replay_contracts_use_parameters_object_and_reject_extra_fields() -> None:
    draft_payload = {
        "sourceRunId": 11,
        "replayStepIndex": 2,
        "targetKind": RunTargetKind.WORKFLOW.value,
        "targetId": 42,
        "targetKey": "portfolio_review",
        "parameters": {"ticker": "MSFT"},
        "packageProvenance": None,
    }

    draft = RunStepReplayDraftRead.model_validate(draft_payload)
    create = RunStepReplayCreateRequest.model_validate(
        {"replayStepIndex": 2, "parameters": {"ticker": "MSFT"}}
    )

    assert draft.model_dump(by_alias=True, mode="json") == draft_payload
    assert create.model_dump(by_alias=True, mode="json") == {
        "replayStepIndex": 2,
        "parameters": {"ticker": "MSFT"},
    }
    with pytest.raises(ValidationError):
        _ = RunStepReplayCreateRequest.model_validate(
            {"replayStepIndex": 2, "parameters": {"ticker": "MSFT"}, "unexpected": True}
        )
    with pytest.raises(ValidationError):
        _ = RunStepReplayCreateRequest.model_validate({"replayStepIndex": 2, "parameters": "MSFT"})
