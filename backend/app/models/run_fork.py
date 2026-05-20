from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.run import Run


class RunFork(Base):
    __tablename__ = "run_forks"
    __table_args__ = (
        CheckConstraint(
            "source_step_index > 0",
            name="ck_run_forks_source_step_index_positive",
        ),
        CheckConstraint(
            "resume_step_index > 0",
            name="ck_run_forks_resume_step_index_positive",
        ),
        Index("ix_run_forks_source_run", "source_run_id"),
        Index("ix_run_forks_lineage_root", "lineage_root_run_id"),
        Index("ix_run_forks_source_invocation", "source_invocation_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    lineage_root_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_agent_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_step_index: Mapped[int] = mapped_column(nullable=False)
    resume_step_index: Mapped[int] = mapped_column(nullable=False)
    invocation_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

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

    run: Mapped[Run] = relationship(
        "Run",
        foreign_keys=[run_id],
        back_populates="fork",
    )
    source_run: Mapped[Run | None] = relationship(
        "Run",
        foreign_keys=[source_run_id],
        back_populates="source_fork_artifacts",
    )
    lineage_root_run: Mapped[Run | None] = relationship(
        "Run",
        foreign_keys=[lineage_root_run_id],
        back_populates="lineage_root_fork_artifacts",
    )
