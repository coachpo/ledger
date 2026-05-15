from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin


class RunStep(IdMixin, TimestampMixin, Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_index", name="uq_run_steps_run_step_index"),
        CheckConstraint("step_index > 0", name="ck_run_steps_step_index_positive"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_run_steps_status",
        ),
        CheckConstraint("origin IN ('planned', 'copied')", name="ck_run_steps_origin"),
        CheckConstraint(
            "source_step_index IS NULL OR source_step_index > 0",
            name="ck_run_steps_source_step_index_positive",
        ),
        Index("ix_run_steps_run_step_index", "run_id", "step_index"),
        Index("ix_run_steps_run_status", "run_id", "status"),
        Index("ix_run_steps_source_run_step", "source_run_step_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_index: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="planned",
        server_default="planned",
    )
    source_run_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_step_index: Mapped[int | None] = mapped_column(nullable=True)
    graph_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    run: Mapped[object] = relationship(
        "Run",
        back_populates="steps",
        foreign_keys=[run_id],
    )
    source_run: Mapped[object | None] = relationship("Run", foreign_keys=[source_run_id])
    source_run_step: Mapped[RunStep | None] = relationship(
        "RunStep",
        foreign_keys=lambda: [RunStep.source_run_step_id],
        remote_side=lambda: [RunStep.id],
        back_populates="copied_steps",
    )
    copied_steps: Mapped[list[RunStep]] = relationship(
        "RunStep",
        foreign_keys=lambda: [RunStep.source_run_step_id],
        back_populates="source_run_step",
        passive_deletes=True,
    )
    invocations: Mapped[list[object]] = relationship(
        "RunAgentInvocation",
        back_populates="run_step",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RunAgentInvocation.position",
    )
    operation_invocations: Mapped[list[object]] = relationship(
        "RunOperationInvocation",
        back_populates="run_step",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RunOperationInvocation.run_step_id",
        order_by="RunOperationInvocation.position",
    )
