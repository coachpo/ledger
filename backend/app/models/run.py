from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, event
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin


class Run(IdMixin, TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('agent', 'workflow', 'workflowPackage')",
            name="ck_runs_target_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_runs_status",
        ),
        CheckConstraint("target_version > 0", name="ck_runs_target_version_positive"),
        CheckConstraint("resume_step_index > 0", name="ck_runs_resume_step_index_positive"),
        CheckConstraint(
            "forked_from_step_index IS NULL OR forked_from_step_index > 0",
            name="ck_runs_forked_from_step_index_positive",
        ),
        CheckConstraint("total_tokens >= 0", name="ck_runs_total_tokens_non_negative"),
        CheckConstraint("inherited_tokens >= 0", name="ck_runs_inherited_tokens_non_negative"),
        CheckConstraint("executed_tokens >= 0", name="ck_runs_executed_tokens_non_negative"),
        Index("ix_runs_status", "status"),
        Index("ix_runs_target", "target_kind", "target_id", "target_version"),
        Index("ix_runs_target_key", "target_kind", "target_key", "target_version"),
        Index("ix_runs_source_run", "source_run_id"),
        Index("ix_runs_lineage_root", "lineage_root_run_id"),
        Index("ix_runs_workflow_package", "workflow_package_id"),
        Index("ix_runs_workflow_package_key", "workflow_package_key"),
        Index("ix_runs_workflow_package_workflow_key", "workflow_package_workflow_key"),
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_workflow_id: Mapped[int | None] = mapped_column(
        "workflow_id",
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(nullable=False)
    target_key: Mapped[str] = mapped_column(String(120), nullable=False)
    target_version: Mapped[int] = mapped_column(nullable=False)
    workflow_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_packages.id", ondelete="SET NULL"),
        nullable=True,
    )
    workflow_package_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_package_workflow_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extension_dependencies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    lineage_root_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    forked_from_step_index: Mapped[int | None] = mapped_column(nullable=True)
    resume_step_index: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    final_output: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    total_tokens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    inherited_tokens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    executed_tokens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    source_run: Mapped[Run | None] = relationship(
        "Run",
        foreign_keys=lambda: [Run.source_run_id],
        remote_side=lambda: [Run.id],
        back_populates="forked_runs",
    )
    forked_runs: Mapped[list[Run]] = relationship(
        "Run",
        foreign_keys=lambda: [Run.source_run_id],
        back_populates="source_run",
        passive_deletes=True,
    )
    lineage_root_run: Mapped[Run | None] = relationship(
        "Run",
        foreign_keys=lambda: [Run.lineage_root_run_id],
        remote_side=lambda: [Run.id],
        back_populates="lineage_descendants",
    )
    lineage_descendants: Mapped[list[Run]] = relationship(
        "Run",
        foreign_keys=lambda: [Run.lineage_root_run_id],
        back_populates="lineage_root_run",
        passive_deletes=True,
    )
    steps: Mapped[list[object]] = relationship(
        "RunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RunStep.run_id",
        order_by="RunStep.step_index",
    )
    workflow_package_snapshot: Mapped[RunWorkflowPackageSnapshot | None] = relationship(
        "RunWorkflowPackageSnapshot",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    def _set_workflow_target_kind(self) -> None:
        if getattr(self, "target_kind", None) is None:
            self.target_kind = "workflow"

    @property
    def workflow_id(self) -> int:
        return self.target_id

    @workflow_id.setter
    def workflow_id(self, value: int) -> None:
        self._set_workflow_target_kind()
        self.target_id = value

    @property
    def workflow_key(self) -> str:
        return self.target_key

    @workflow_key.setter
    def workflow_key(self, value: str) -> None:
        self._set_workflow_target_kind()
        self.target_key = value

    @property
    def workflow_version(self) -> int:
        return self.target_version

    @workflow_version.setter
    def workflow_version(self, value: int) -> None:
        self._set_workflow_target_kind()
        self.target_version = value


class RunWorkflowPackageSnapshot(TimestampMixin, Base):
    __tablename__ = "run_workflow_package_snapshots"
    __table_args__ = (
        Index("ix_run_workflow_package_snapshots_package_key", "workflow_package_key"),
        Index("ix_run_workflow_package_snapshots_workflow_key", "workflow_key"),
        Index("ix_run_workflow_package_snapshots_manifest_hash", "manifest_hash"),
        Index("ix_run_workflow_package_snapshots_compiled_hash", "compiled_hash"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_package_id: Mapped[int] = mapped_column(nullable=False)
    workflow_package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_package_name: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_package_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    workflow_package_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_source: Mapped[str] = mapped_column(Text, nullable=False)
    package_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    extension_dependencies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    local_resource_refs: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    launch_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    resolved_model_connections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    preflight_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )

    run: Mapped[Run] = relationship("Run", back_populates="workflow_package_snapshot")


def _workflow_package_runs_pending_snapshot(session: Session) -> list[Run]:
    pending_runs: list[Run] = []
    for obj in [*session.new, *session.dirty]:
        if not isinstance(obj, Run):
            continue
        if obj.target_kind == "workflowPackage" and obj.workflow_package_snapshot is None:
            pending_runs.append(obj)
    return pending_runs


@event.listens_for(Session, "before_flush")
def _require_workflow_package_run_snapshot(
    session: Session,
    flush_context: object,
    instances: object,
) -> None:
    del flush_context, instances
    if _workflow_package_runs_pending_snapshot(session):
        raise ValueError("workflow package runs require a run-owned executable snapshot")
