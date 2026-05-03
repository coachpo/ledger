from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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


class RunAgentInvocation(IdMixin, TimestampMixin, Base):
    __tablename__ = "run_agent_invocations"
    __table_args__ = (
        UniqueConstraint("run_step_id", "slot", name="uq_run_agent_invocations_step_slot"),
        CheckConstraint("step_index > 0", name="ck_run_agent_invocations_step_index_positive"),
        CheckConstraint("position >= 0", name="ck_run_agent_invocations_position_non_negative"),
        CheckConstraint("agent_id > 0", name="ck_run_agent_invocations_agent_id_positive"),
        CheckConstraint(
            "agent_version > 0",
            name="ck_run_agent_invocations_agent_version_positive",
        ),
        CheckConstraint(
            "output_schema_id > 0",
            name="ck_run_agent_invocations_output_schema_id_positive",
        ),
        CheckConstraint(
            "output_schema_version > 0",
            name="ck_run_agent_invocations_output_schema_version_positive",
        ),
        CheckConstraint(
            "input_mode IN ('passthrough', 'wired')",
            name="ck_run_agent_invocations_input_mode",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_run_agent_invocations_status",
        ),
        CheckConstraint(
            "resolved_input_origin IN ('derived', 'edited', 'copied', 'passthrough')",
            name="ck_run_agent_invocations_resolved_input_origin",
        ),
        CheckConstraint(
            "output_origin IS NULL OR output_origin IN ('executed', 'edited', 'copied')",
            name="ck_run_agent_invocations_output_origin",
        ),
        CheckConstraint("tokens >= 0", name="ck_run_agent_invocations_tokens_non_negative"),
        CheckConstraint("cost_usd >= 0", name="ck_run_agent_invocations_cost_non_negative"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_run_agent_invocations_duration_non_negative",
        ),
        Index("ix_run_agent_invocations_run_step_index", "run_id", "step_index"),
        Index("ix_run_agent_invocations_run_status", "run_id", "status"),
        Index("ix_run_agent_invocations_agent_version", "agent_key", "agent_version"),
        Index("ix_run_agent_invocations_source_invocation", "source_invocation_id"),
    )

    run_step_id: Mapped[int] = mapped_column(
        ForeignKey("run_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(nullable=False)
    slot: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    agent_id: Mapped[int] = mapped_column(nullable=False)
    agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_version: Mapped[int] = mapped_column(nullable=False)
    output_schema_id: Mapped[int] = mapped_column(nullable=False)
    output_schema_version: Mapped[int] = mapped_column(nullable=False)
    input_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="wired",
        server_default="wired",
    )
    wiring: Mapped[dict[str, Any]] = mapped_column(
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
    resolved_input: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    resolved_input_origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="derived",
        server_default="derived",
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
    tokens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    trace_span_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_agent_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
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
        back_populates="invocations",
        foreign_keys=[run_step_id],
    )
    run: Mapped[object] = relationship("Run", foreign_keys=[run_id])
    source_invocation: Mapped[RunAgentInvocation | None] = relationship(
        "RunAgentInvocation",
        foreign_keys=lambda: [RunAgentInvocation.source_invocation_id],
        remote_side=lambda: [RunAgentInvocation.id],
        back_populates="copied_invocations",
    )
    copied_invocations: Mapped[list[RunAgentInvocation]] = relationship(
        "RunAgentInvocation",
        foreign_keys=lambda: [RunAgentInvocation.source_invocation_id],
        back_populates="source_invocation",
        passive_deletes=True,
    )
