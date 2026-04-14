from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class RuntimeApproval(IdMixin, Base):
    __tablename__ = "runtime_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DENIED', 'EXPIRED')",
            name="ck_runtime_approvals_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND actor IS NULL AND reason IS NULL AND resolved_at IS NULL) OR "
            "(status IN ('APPROVED', 'DENIED') AND actor IS NOT NULL AND reason IS NOT NULL "
            "AND resolved_at IS NOT NULL) OR "
            "(status = 'EXPIRED' AND actor IS NULL AND reason IS NOT NULL AND "
            "resolved_at IS NOT NULL)",
            name="ck_runtime_approvals_resolution_fields",
        ),
        Index("ix_runtime_approvals_run_id", "run_id"),
        Index("ix_runtime_approvals_status", "status"),
        Index("ix_runtime_approvals_capability_key", "capability_key"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runtime_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability_key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
