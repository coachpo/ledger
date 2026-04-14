from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class RuntimeCheckpoint(IdMixin, TimestampMixin, Base):
    __tablename__ = "runtime_checkpoints"
    __table_args__ = (
        CheckConstraint(
            "checkpoint_index >= 0",
            name="ck_runtime_checkpoints_checkpoint_index_non_negative",
        ),
        UniqueConstraint("run_id", "checkpoint_index", name="uq_runtime_checkpoints_run_index"),
        Index("ix_runtime_checkpoints_run_id", "run_id"),
        Index("ix_runtime_checkpoints_step_key", "step_key"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runtime_runs.id", ondelete="CASCADE"), nullable=False
    )
    checkpoint_index: Mapped[int] = mapped_column(nullable=False)
    step_key: Mapped[str] = mapped_column(String(120), nullable=False)
    serialized_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
