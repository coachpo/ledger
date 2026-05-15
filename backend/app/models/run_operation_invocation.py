from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin


class RunOperationInvocation(IdMixin, TimestampMixin, Base):
    __tablename__ = "run_operation_invocations"
    __table_args__ = (
        UniqueConstraint("run_step_id", "slot", name="uq_run_operation_invocations_step_slot"),
        CheckConstraint(
            "step_index > 0",
            name="ck_run_operation_invocations_step_index_positive",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_run_operation_invocations_position_non_negative",
        ),
        CheckConstraint(
            "operation_kind IN ('http')",
            name="ck_run_operation_invocations_operation_kind",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_run_operation_invocations_status",
        ),
        CheckConstraint(
            "output_schema_id > 0",
            name="ck_run_operation_invocations_output_schema_id_positive",
        ),
        CheckConstraint(
            "output_schema_version > 0",
            name="ck_run_operation_invocations_output_schema_version_positive",
        ),
        CheckConstraint(
            "source_step_index IS NULL OR source_step_index > 0",
            name="ck_run_operation_invocations_source_step_index_positive",
        ),
        CheckConstraint(
            "output_origin IS NULL OR output_origin IN ('executed', 'edited', 'copied')",
            name="ck_run_operation_invocations_output_origin",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_run_operation_invocations_duration_non_negative",
        ),
        CheckConstraint(
            "timeout_seconds IS NULL OR timeout_seconds > 0",
            name="ck_run_operation_invocations_timeout_positive",
        ),
        Index("ix_run_operation_invocations_run_step_index", "run_id", "step_index"),
        Index("ix_run_operation_invocations_run_status", "run_id", "status"),
        Index("ix_run_operation_invocations_operation_key", "operation_key"),
        Index("ix_run_operation_invocations_source_operation", "source_operation_invocation_id"),
        Index("ix_run_operation_invocations_source_run", "source_run_id"),
        Index("ix_run_operation_invocations_source_run_step", "source_run_step_id"),
    )

    run_step_id: Mapped[int] = mapped_column(
        ForeignKey("run_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(nullable=False)
    slot: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    operation_key: Mapped[str] = mapped_column(String(120), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    output_schema_id: Mapped[int] = mapped_column(nullable=False)
    output_schema_version: Mapped[int] = mapped_column(nullable=False)
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    response_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    graph_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    optional: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    output: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    output_origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    trace_span_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_operation_invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_operation_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_run_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_step_index: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    persisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
        onupdate=utcnow,
    )

    run_step: Mapped[object] = relationship(
        "RunStep",
        back_populates="operation_invocations",
        foreign_keys=[run_step_id],
    )
    run: Mapped[object] = relationship("Run", foreign_keys=[run_id])
    source_operation_invocation: Mapped[RunOperationInvocation | None] = relationship(
        "RunOperationInvocation",
        foreign_keys=lambda: [RunOperationInvocation.source_operation_invocation_id],
        remote_side=lambda: [RunOperationInvocation.id],
        back_populates="copied_operation_invocations",
    )
    copied_operation_invocations: Mapped[list[RunOperationInvocation]] = relationship(
        "RunOperationInvocation",
        foreign_keys=lambda: [RunOperationInvocation.source_operation_invocation_id],
        back_populates="source_operation_invocation",
        passive_deletes=True,
    )
    source_run: Mapped[object | None] = relationship("Run", foreign_keys=[source_run_id])
    source_run_step: Mapped[object | None] = relationship(
        "RunStep",
        foreign_keys=[source_run_step_id],
    )
