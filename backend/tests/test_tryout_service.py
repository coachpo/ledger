from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.models.agent_spec import AgentSpec
from app.models.runtime_approval import RuntimeApproval
from app.models.runtime_checkpoint import RuntimeCheckpoint
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.models.runtime_trace_event import RuntimeTraceEvent
from app.schemas.tryout import TryoutExecute
from app.services.tryout_service import TryoutService


def _build_agent_spec(*, key: str, version: int = 1, status: str = "ACTIVE") -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        instructions=f"Instructions for {key}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "json", "schema": None, "description": "Output"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_tryout_run(
    *,
    status: str = "QUEUED",
    retention_class: str = "ephemeral",
    expires_at=None,
    trace_summary: dict[str, Any] | None = None,
    approval_summary: dict[str, Any] | None = None,
) -> RuntimeRun:
    return RuntimeRun(
        caller_type="tryout",
        caller_id=None,
        execution_kind="single_agent",
        workflow_spec_key=None,
        workflow_spec_version=None,
        agent_spec_key="tryout_agent",
        agent_spec_version=1,
        caller_scope_key=None,
        caller_identity_key=None,
        attempt_number=1,
        status=status,
        input_hash="1" * 64,
        output_hash=None,
        retention_class=retention_class,
        expires_at=expires_at,
        trace_summary=trace_summary
        or {
            "eventCount": 1,
            "toolCallCount": 0,
            "warningCount": 0,
            "lastEventAt": None,
        },
        approval_summary=approval_summary
        or {
            "totalCount": 0,
            "pendingCount": 0,
            "approvedCount": 0,
            "deniedCount": 0,
            "expiredCount": 0,
        },
    )


def _build_artifact(
    *,
    run_id: int,
    final_output: Any | None = None,
    report_markdown: str | None = None,
    terminal_error_code: str | None = None,
    terminal_error_message: str | None = None,
) -> RuntimeRunArtifact:
    return RuntimeRunArtifact(
        run_id=run_id,
        entry_prompt_hash="a" * 64,
        full_user_prompt_hash="b" * 64,
        raw_mention_handles=[],
        resolved_persona_profile_refs=[],
        resolved_builtin_versions=[],
        resolved_role_versions=[],
        resolved_character_versions=[],
        resolved_bundle_versions=[],
        resolved_tool_versions=[],
        resolved_connector_versions=[],
        mentioned_target_outputs=[],
        resolved_mentions=[],
        resolved_workflow_agent_refs=None,
        resolved_capabilities=[],
        final_output=final_output,
        report_markdown=report_markdown,
        terminal_error_code=terminal_error_code,
        terminal_error_message=terminal_error_message,
    )


def _runtime_row_counts(session: Session) -> tuple[int, int, int]:
    return (
        int(session.scalar(select(func.count()).select_from(RuntimeRun)) or 0),
        int(session.scalar(select(func.count()).select_from(RuntimeRunArtifact)) or 0),
        int(session.scalar(select(func.count()).select_from(RuntimeTraceEvent)) or 0),
    )


def test_create_tryout_defaults_to_ephemeral_shell_and_reads_back_canonical_summaries(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_build_agent_spec(key="tryout_agent"))
        session.commit()

        service = TryoutService(session)
        before = utcnow()
        created = service.create_tryout(
            TryoutExecute.model_validate(
                {
                    "agentSpecKey": "tryout_agent",
                    "inputs": {"ticker": "MSFT"},
                }
            )
        )

        persisted_run = session.get(RuntimeRun, created.run_id)
        assert persisted_run is not None
        assert created.status == "SUCCEEDED"
        assert created.expires_at is not None
        assert (
            timedelta(hours=23, minutes=59)
            <= created.expires_at - before
            <= timedelta(hours=24, minutes=1)
        )
        assert persisted_run.caller_type == "tryout"
        assert persisted_run.retention_class == "ephemeral"
        assert persisted_run.expires_at == created.expires_at
        assert _runtime_row_counts(session) == (1, 1, 4)

        detail = service.get_tryout(created.run_id)
        assert detail.run_id == created.run_id
        assert detail.status == "SUCCEEDED"
        assert detail.final_output == {
            "executionKind": "single_agent",
            "agent": {"key": "tryout_agent", "version": 1, "name": "tryout_agent-1"},
            "inputs": {"ticker": "MSFT"},
            "personaProfileKeys": [],
            "capabilities": [],
            "summary": "Executed tryout_agent-1 from frozen pinned refs.",
        }
        assert detail.report_markdown == (
            "# Single-Agent Execution\n\n"
            "- Agent: tryout_agent-1 (tryout_agent v1)\n"
            "- Personas: none\n"
            "- Capabilities: none\n"
            "- Summary: Executed tryout_agent-1 from frozen pinned refs."
        )
        assert detail.trace_summary.event_count == 4
        assert detail.approval_summary.total_count == 0
        assert detail.expires_at == created.expires_at


def test_get_tryout_surfaces_canonical_runtime_artifact_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_tryout_run(
            status="SUCCEEDED",
            retention_class="persistent",
            expires_at=None,
            trace_summary={
                "eventCount": 4,
                "toolCallCount": 1,
                "warningCount": 0,
                "lastEventAt": None,
            },
            approval_summary={
                "totalCount": 1,
                "pendingCount": 0,
                "approvedCount": 1,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        session.add(run)
        session.flush()
        session.add(
            _build_artifact(
                run_id=run.id,
                final_output={"message": "done"},
                report_markdown="# Tryout Report",
            )
        )
        session.commit()

        detail = TryoutService(session).get_tryout(run.id)
        assert detail.run_id == run.id
        assert detail.status == "SUCCEEDED"
        assert detail.final_output == {"message": "done"}
        assert detail.report_markdown == "# Tryout Report"
        assert detail.trace_summary.event_count == 4
        assert detail.approval_summary.approved_count == 1
        assert detail.terminal_error is None


def test_persist_tryout_waiting_approval_keeps_same_identity_and_attached_state(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        expires_at = utcnow() + timedelta(hours=24)
        run = _build_tryout_run(
            status="WAITING_APPROVAL",
            expires_at=expires_at,
            approval_summary={
                "totalCount": 1,
                "pendingCount": 1,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                _build_artifact(run_id=run.id),
                RuntimeApproval(
                    run_id=run.id,
                    step_key="review",
                    capability_key="ledger.review",
                    status="PENDING",
                ),
                RuntimeCheckpoint(
                    run_id=run.id,
                    checkpoint_index=0,
                    step_key="review",
                    serialized_state={"cursor": "approval"},
                ),
            ]
        )
        session.commit()

        persisted = TryoutService(session).persist_tryout(run.id)
        persisted_run = session.get(RuntimeRun, run.id)
        assert persisted_run is not None
        assert persisted.run_id == run.id
        assert persisted.status == "WAITING_APPROVAL"
        assert persisted.expires_at is None
        assert persisted.approval_summary.pending_count == 1
        assert persisted_run.retention_class == "persistent"
        assert persisted_run.expires_at is None
        assert (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(RuntimeApproval)
                    .where(RuntimeApproval.run_id == run.id)
                )
                or 0
            )
            == 1
        )
        assert (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(RuntimeCheckpoint)
                    .where(RuntimeCheckpoint.run_id == run.id)
                )
                or 0
            )
            == 1
        )


def test_create_tryout_rejects_seeded_backtest_workflow_before_runtime_rows_exist(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = TryoutService(session)
        assert _runtime_row_counts(session) == (0, 0, 0)

        with pytest.raises(ApiError, match="rollback-window seeded backtest workflows") as exc_info:
            service.create_tryout(
                TryoutExecute.model_validate(
                    {
                        "workflowSpecKey": "seeded_internal_backtest_v1",
                        "inputs": {"ticker": "AAPL"},
                    }
                )
            )

        assert exc_info.value.code == "tryout_seeded_backtest_workflow_not_allowed"
        assert _runtime_row_counts(session) == (0, 0, 0)


def test_persist_tryout_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(_build_agent_spec(key="tryout_agent"))
        session.commit()

        service = TryoutService(session)
        created = service.create_tryout(
            TryoutExecute.model_validate(
                {
                    "agentSpecKey": "tryout_agent",
                    "inputs": {"ticker": "NVDA"},
                }
            )
        )

        first = service.persist_tryout(created.run_id)
        second = service.persist_tryout(created.run_id)
        persisted_run = session.get(RuntimeRun, created.run_id)
        assert persisted_run is not None
        assert first.run_id == created.run_id
        assert second.run_id == created.run_id
        assert first.expires_at is None
        assert second.expires_at is None
        assert persisted_run.retention_class == "persistent"
        assert persisted_run.expires_at is None
        assert int(session.scalar(select(func.count()).select_from(RuntimeRun)) or 0) == 1
