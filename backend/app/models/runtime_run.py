from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

_TRACE_SUMMARY_DEFAULT = {
    "eventCount": 0,
    "toolCallCount": 0,
    "warningCount": 0,
    "lastEventAt": None,
}
_APPROVAL_SUMMARY_DEFAULT = {
    "totalCount": 0,
    "pendingCount": 0,
    "approvedCount": 0,
    "deniedCount": 0,
    "expiredCount": 0,
}
_TRACE_SUMMARY_SERVER_DEFAULT = json.dumps(_TRACE_SUMMARY_DEFAULT, separators=(",", ":"))
_APPROVAL_SUMMARY_SERVER_DEFAULT = json.dumps(
    _APPROVAL_SUMMARY_DEFAULT,
    separators=(",", ":"),
)


def _default_trace_summary() -> dict[str, Any]:
    return dict(_TRACE_SUMMARY_DEFAULT)


def _default_approval_summary() -> dict[str, Any]:
    return dict(_APPROVAL_SUMMARY_DEFAULT)


class RuntimeRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "runtime_runs"
    __table_args__ = (
        CheckConstraint(
            "caller_type IN ('tryout', 'studio', 'api')",
            name="ck_runtime_runs_caller_type",
        ),
        CheckConstraint(
            "execution_kind IN ('workflow', 'single_agent')",
            name="ck_runtime_runs_execution_kind",
        ),
        CheckConstraint(
            (
                "status IN ('QUEUED', 'RUNNING', 'WAITING_APPROVAL', "
                "'SUCCEEDED', 'FAILED', 'CANCELLED')"
            ),
            name="ck_runtime_runs_status",
        ),
        CheckConstraint(
            "retention_class IN ('ephemeral', 'persistent')",
            name="ck_runtime_runs_retention_class",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_runtime_runs_attempt_number_positive",
        ),
        CheckConstraint(
            "(execution_kind = 'workflow' AND workflow_spec_key IS NOT NULL AND "
            "workflow_spec_version IS NOT NULL AND agent_spec_key IS NULL AND "
            "agent_spec_version IS NULL) OR "
            "(execution_kind = 'single_agent' AND agent_spec_key IS NOT NULL AND "
            "agent_spec_version IS NOT NULL AND workflow_spec_key IS NULL AND "
            "workflow_spec_version IS NULL)",
            name="ck_runtime_runs_execution_target_fields",
        ),
        UniqueConstraint(
            "caller_type",
            "caller_id",
            "caller_scope_key",
            "attempt_number",
            name="uq_runtime_runs_caller_scope_attempt",
        ),
        Index("ix_runtime_runs_status", "status"),
        Index("ix_runtime_runs_caller", "caller_type", "caller_id", "caller_scope_key"),
        Index("ix_runtime_runs_workflow", "workflow_spec_key", "workflow_spec_version"),
        Index("ix_runtime_runs_agent", "agent_spec_key", "agent_spec_version"),
        Index("ix_runtime_runs_caller_identity_key", "caller_identity_key"),
    )

    caller_type: Mapped[str] = mapped_column(String(20), nullable=False)
    caller_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    workflow_spec_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_spec_version: Mapped[int | None] = mapped_column(nullable=True)
    agent_spec_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_spec_version: Mapped[int | None] = mapped_column(nullable=True)
    caller_scope_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    caller_identity_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    attempt_number: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_class: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="persistent",
        server_default="persistent",
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trace_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=_default_trace_summary,
        server_default=_TRACE_SUMMARY_SERVER_DEFAULT,
    )
    approval_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=_default_approval_summary,
        server_default=_APPROVAL_SUMMARY_SERVER_DEFAULT,
    )
