from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class WorkflowMemoryItem(IdMixin, Base):
    __tablename__ = "workflow_memory_items"
    __table_args__ = (
        CheckConstraint(
            "policy_status IN ('proposed', 'rejected', 'quarantined', "
            "'review_pending', 'committed')",
            name="ck_workflow_memory_items_policy_status",
        ),
        CheckConstraint(
            "lifecycle_status IN ('active', 'superseded', 'expired', 'deleted')",
            name="ck_workflow_memory_items_lifecycle_status",
        ),
        UniqueConstraint("memory_id", name="uq_workflow_memory_items_memory_id"),
        Index(
            "ix_workflow_memory_items_retrieval_scope",
            "package_key",
            "workflow_key",
            "agent_key",
            "step_id",
            "namespace",
            "policy_status",
            "lifecycle_status",
            "expires_at",
            "deleted_at",
        ),
        Index("ix_workflow_memory_items_superseded_by", "superseded_by_id"),
        Index("ix_workflow_memory_items_run_invocation", "run_id", "invocation_id"),
    )

    memory_id: Mapped[str] = mapped_column(String(160), nullable=False)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    step_id: Mapped[str] = mapped_column(String(160), nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    policy_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="committed", server_default="committed"
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_memory_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_memory_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_memory_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
        onupdate=utcnow,
    )


class WorkflowMemoryProposal(IdMixin, Base):
    __tablename__ = "workflow_memory_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'rejected', 'quarantined', " "'review_pending', 'committed')",
            name="ck_workflow_memory_proposals_status",
        ),
        UniqueConstraint("proposal_id", name="uq_workflow_memory_proposals_proposal_id"),
        Index(
            "ix_workflow_memory_proposals_scope",
            "package_key",
            "workflow_key",
            "agent_key",
            "step_id",
        ),
        Index("ix_workflow_memory_proposals_run_invocation", "run_id", "invocation_id"),
    )

    proposal_id: Mapped[str] = mapped_column(String(160), nullable=False)
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    step_id: Mapped[str] = mapped_column(String(160), nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_output_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detectors_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="proposed", server_default="proposed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
        onupdate=utcnow,
    )


class WorkflowMemoryDecision(IdMixin, Base):
    __tablename__ = "workflow_memory_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('commit', 'reject', 'quarantine', 'review')",
            name="ck_workflow_memory_decisions_decision",
        ),
        CheckConstraint(
            "decided_by IN ('policy', 'review_api')",
            name="ck_workflow_memory_decisions_decided_by",
        ),
        UniqueConstraint("decision_id", name="uq_workflow_memory_decisions_decision_id"),
        Index("ix_workflow_memory_decisions_proposal", "proposal_id"),
    )

    decision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    proposal_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_memory_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    decided_by: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )


class WorkflowMemoryAuditEvent(IdMixin, Base):
    __tablename__ = "workflow_memory_audit_events"
    __table_args__ = (
        Index("ix_workflow_memory_audit_events_target", "target_type", "target_id"),
        Index("ix_workflow_memory_audit_events_scope", "package_key", "workflow_key"),
        Index("ix_workflow_memory_audit_events_run_invocation", "run_id", "invocation_id"),
    )

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    step_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )


class WorkflowMemoryRevision(IdMixin, Base):
    __tablename__ = "workflow_memory_revisions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_workflow_memory_revisions_version_positive"),
        UniqueConstraint("revision_id", name="uq_workflow_memory_revisions_revision_id"),
        UniqueConstraint(
            "memory_item_id",
            "version",
            name="uq_workflow_memory_revisions_item_version",
        ),
        Index("ix_workflow_memory_revisions_item", "memory_item_id"),
    )

    memory_item_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_memory_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    supersedes_revision_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )


class WorkflowMemoryQuarantine(IdMixin, Base):
    __tablename__ = "workflow_memory_quarantine"
    __table_args__ = (
        CheckConstraint(
            "memory_item_id IS NOT NULL OR proposal_id IS NOT NULL",
            name="ck_workflow_memory_quarantine_target",
        ),
        Index("ix_workflow_memory_quarantine_memory_item", "memory_item_id"),
        Index("ix_workflow_memory_quarantine_proposal", "proposal_id"),
        Index("ix_workflow_memory_quarantine_run_invocation", "run_id", "invocation_id"),
    )

    memory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_memory_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_memory_proposals.id", ondelete="CASCADE"),
        nullable=True,
    )
    run_id: Mapped[int | None] = mapped_column(nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detectors_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )


class WorkflowMemoryConsolidationRun(IdMixin, Base):
    __tablename__ = "workflow_memory_consolidation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_workflow_memory_consolidation_runs_status",
        ),
        UniqueConstraint(
            "consolidation_id",
            name="uq_workflow_memory_consolidation_runs_consolidation_id",
        ),
        Index("ix_workflow_memory_consolidation_runs_scope", "package_key", "workflow_key"),
    )

    consolidation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_memory_ids_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    output_memory_ids_json: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    stats_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=sql_text("now()")
    )
