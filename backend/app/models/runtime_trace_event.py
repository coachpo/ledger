from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class RuntimeTraceEvent(IdMixin, Base):
    __tablename__ = "runtime_trace_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('RUN_CREATED', 'STEP_STARTED', 'STEP_COMPLETED', 'TOOL_CALLED', "
            "'TOOL_RETURNED', 'APPROVAL_REQUESTED', 'APPROVAL_RESOLVED', 'RUN_COMPLETED', "
            "'RUN_FAILED', 'RUN_CANCELLED', 'RUN_EXPIRED', 'WARNING_EMITTED')",
            name="ck_runtime_trace_events_event_type",
        ),
        CheckConstraint(
            "event_index >= 0",
            name="ck_runtime_trace_events_event_index_non_negative",
        ),
        UniqueConstraint("run_id", "event_index", name="uq_runtime_trace_events_run_event_index"),
        Index("ix_runtime_trace_events_run_id", "run_id"),
        Index("ix_runtime_trace_events_event_type", "event_type"),
        Index("ix_runtime_trace_events_approval_id", "approval_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runtime_runs.id", ondelete="CASCADE"), nullable=False
    )
    event_index: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capability_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approval_id: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
