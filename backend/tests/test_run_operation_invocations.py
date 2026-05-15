from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy.orm import Session, sessionmaker

from app.models.run import Run
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.repositories.run_operation_invocation import RunOperationInvocationRepository
from app.schemas.run import RunOperationInvocationRead
from app.services.run_service import RunService

UTC_TZ = timezone.utc  # noqa: UP017


def _create_run_with_step(
    session: Session,
    *,
    run_status: str = "succeeded",
    step_status: str = "succeeded",
) -> tuple[Run, RunStep]:
    timestamp = datetime(2026, 5, 15, 8, 30, tzinfo=UTC_TZ)
    run = Run(
        target_kind="workflowPackage",
        target_id=1,
        target_key="operation_package",
        target_version=1,
        input={"ticker": "NVDA", "webhookUrl": "https://example.test/hook"},
        status=run_status,
        total_tokens=0,
        inherited_tokens=0,
        executed_tokens=0,
        started_at=timestamp,
        finished_at=timestamp if run_status in {"succeeded", "failed"} else None,
    )
    run.queued_at = timestamp
    session.add(run)
    session.flush()
    step = RunStep(
        run_id=run.id,
        step_index=1,
        status=step_status,
        origin="planned",
        graph_metadata={"nodeId": "notify_slack", "nodeKind": "http"},
        started_at=timestamp,
        finished_at=timestamp if step_status in {"succeeded", "failed"} else None,
        persisted_at=timestamp if step_status in {"succeeded", "failed", "skipped"} else None,
    )
    session.add(step)
    session.flush()
    return run, step


def _request_metadata_with_secrets() -> dict[str, Any]:
    return {
        "url": {"from": "input", "path": "webhookUrl"},
        "headers": {
            "Content-Type": "application/json",
            "Authorization": {
                "from": "secret",
                "key": "slack_webhook_token",
                "value": "slack-secret-value",
            },
        },
        "query": {"ticker": {"from": "input", "path": "ticker"}},
        "body": {
            "ticker": {"from": "input", "path": "ticker"},
            "token": {"from": "secret", "key": "body_token"},
            "rawToken": "body-secret-value",
        },
    }


def _create_succeeded_operation(
    session: Session,
    step: RunStep,
    *,
    output_origin: str = "executed",
) -> RunOperationInvocation:
    timestamp = datetime(2026, 5, 15, 8, 31, tzinfo=UTC_TZ)
    repository = RunOperationInvocationRepository(session)
    operation = repository.create_operation(
        run_step_id=step.id,
        run_id=step.run_id,
        step_index=step.step_index,
        slot="webhook_result",
        position=0,
        operation_key="notify_slack",
        operation_kind="http",
        output_schema_id=1,
        output_schema_version=1,
        method="POST",
        timeout_seconds=10,
        request_metadata=_request_metadata_with_secrets(),
        response_metadata={"statusCode": 200, "headers": {"content-type": "application/json"}},
        graph_metadata={"nodeId": "notify_slack", "nodeKind": "http"},
        optional=False,
    )
    return repository.persist_success(
        operation,
        output={"ok": True, "message": "queued"},
        output_origin=output_origin,
        response_metadata={"statusCode": 200, "headers": {"content-type": "application/json"}},
        duration_ms=42,
        trace_span_id="span-operation",
        finished_at=timestamp,
        persisted_at=timestamp,
    )


def test_operation_invocation_read_schema_redacts_request_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run, step = _create_run_with_step(session)
        operation = _create_succeeded_operation(session, step)
        session.commit()
        session.refresh(operation)

        operation_payload = cast(
            dict[str, object],
            RunOperationInvocationRead.model_validate(operation).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        request_metadata = cast(dict[str, Any], operation_payload["requestMetadata"])
        headers = cast(dict[str, Any], request_metadata["headers"])
        body = cast(dict[str, Any], request_metadata["body"])

        assert headers["Authorization"] == {
            "from": "secret",
            "key": "slack_webhook_token",
            "redacted": True,
        }
        assert body["token"] == {"from": "secret", "key": "body_token", "redacted": True}
        assert body["rawToken"] == {"redacted": True}
        assert operation_payload["responseMetadata"] == {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
        }
        assert operation_payload["output"] == {"ok": True, "message": "queued"}
        assert operation_payload["operationKind"] == "http"
        assert operation_payload["status"] == "succeeded"

        detail_payload = cast(
            dict[str, Any],
            RunService(session, session_factory).get_run(run.id).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        detail_step = cast(dict[str, Any], detail_payload["steps"][0])
        detail_operations = cast(list[dict[str, Any]], detail_step["operationInvocations"])
        serialized_detail = json.dumps(detail_payload, sort_keys=True)

    assert detail_step["invocations"] == []
    assert len(detail_operations) == 1
    assert detail_operations[0]["requestMetadata"] == request_metadata
    assert "slack-secret-value" not in serialized_detail
    assert "body-secret-value" not in serialized_detail
    assert "secretPayload" not in serialized_detail


def test_replay_copy_preserves_operation_provenance_and_redacted_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source_run, source_step = _create_run_with_step(session)
        source_operation = _create_succeeded_operation(session, source_step)
        target_run = Run(
            target_kind=source_run.target_kind,
            target_id=source_run.target_id,
            target_key=source_run.target_key,
            target_version=source_run.target_version,
            input=dict(source_run.input),
            status="queued",
            source_run_id=source_run.id,
            lineage_root_run_id=source_run.id,
            forked_from_step_index=2,
            resume_step_index=2,
            total_tokens=0,
            inherited_tokens=0,
            executed_tokens=0,
        )
        session.add(target_run)
        session.flush()

        RunService(session, session_factory)._copy_replay_context_rows(
            run=target_run,
            source_steps=[source_step],
        )
        session.commit()

        copied_operation = (
            session.query(RunOperationInvocation)
            .filter_by(run_id=target_run.id, slot="webhook_result")
            .one()
        )
        copied_detail = cast(
            dict[str, Any],
            RunService(session, session_factory).get_run(target_run.id).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        copied_operation_payload = copied_detail["steps"][0]["operationInvocations"][0]

    assert copied_operation.source_operation_invocation_id == source_operation.id
    assert copied_operation.source_run_id == source_run.id
    assert copied_operation.source_run_step_id == source_step.id
    assert copied_operation.source_step_index == source_step.step_index
    assert copied_operation.output_origin == "copied"
    assert copied_operation.output == {"ok": True, "message": "queued"}
    assert copied_operation.response_metadata == {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
    }
    assert copied_operation.request_metadata["body"]["rawToken"] == {"redacted": True}
    assert copied_operation_payload["sourceOperationInvocationId"] == source_operation.id
    assert copied_operation_payload["sourceRunId"] == source_run.id
    assert copied_operation_payload["sourceRunStepId"] == source_step.id
    assert copied_operation_payload["sourceStepIndex"] == source_step.step_index
