from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin
from app.models.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
)


class WorkflowCheckpoint(IdMixin, Base):
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_workflow_checkpoints_sequence_positive"),
        UniqueConstraint("checkpoint_id", name="uq_workflow_checkpoints_checkpoint_id"),
        Index(
            "ix_workflow_checkpoints_scope_run_sequence",
            "owner_type",
            "owner_id",
            "package_key",
            "workflow_key",
            "run_id",
            "agent_key",
            "step_id",
            "checkpoint_type",
            "sequence",
            "id",
        ),
        Index(
            "ix_workflow_checkpoints_owner_run_invocation",
            "owner_type",
            "owner_id",
            "run_id",
            "invocation_id",
        ),
    )

    checkpoint_id: Mapped[str] = mapped_column(String(160), nullable=False)
    owner_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        server_default=DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
    )
    owner_id: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default=DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        server_default=DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    )
    run_id: Mapped[int] = mapped_column(nullable=False)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    checkpoint_type: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence: Mapped[int] = mapped_column(nullable=False)
    state_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    retention: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )
