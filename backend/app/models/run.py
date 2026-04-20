from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin


class Run(IdMixin, TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_runs_status",
        ),
        CheckConstraint(
            "workflow_version > 0",
            name="ck_runs_workflow_version_positive",
        ),
        CheckConstraint("total_tokens >= 0", name="ck_runs_total_tokens_non_negative"),
        CheckConstraint(
            "total_cost_usd >= 0",
            name="ck_runs_total_cost_non_negative",
        ),
        Index("ix_runs_status", "status"),
        Index("ix_runs_workflow", "workflow_id", "workflow_version"),
        Index("ix_runs_workflow_key", "workflow_key", "workflow_version"),
    )

    workflow_id: Mapped[int] = mapped_column(nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_version: Mapped[int] = mapped_column(nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    per_step_outputs: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    final_output: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default="running",
    )
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    total_cost_usd: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
