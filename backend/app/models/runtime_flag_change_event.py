from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class RuntimeFlagChangeEvent(IdMixin, Base):
    __tablename__ = "runtime_flag_change_events"
    __table_args__ = (
        CheckConstraint(
            "result IN ('applied', 'rejected')",
            name="ck_runtime_flag_change_events_result",
        ),
        Index("ix_runtime_flag_change_events_flag_key", "flag_key"),
        Index("ix_runtime_flag_change_events_created_at", "created_at"),
    )

    flag_key: Mapped[str] = mapped_column(String(120), nullable=False)
    old_enabled: Mapped[bool] = mapped_column(nullable=False)
    new_enabled: Mapped[bool] = mapped_column(nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
