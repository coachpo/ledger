from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class AgentMemoryEntry(IdMixin, Base):
    __tablename__ = "agent_memory_entries"
    __table_args__ = (
        UniqueConstraint("memory_id", name="uq_agent_memory_entries_memory_id"),
        CheckConstraint(
            "scope_type IN ('workspace', 'package', 'workflow', 'run', 'agent', 'namespace')",
            name="ck_agent_memory_entries_scope_type",
        ),
        CheckConstraint(
            "content_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_entries_content_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(subject_refs) = 'array'",
            name="ck_agent_memory_entries_subject_refs",
        ),
        CheckConstraint(
            "source_run_id > 0",
            name="ck_agent_memory_entries_source_run_id_positive",
        ),
        CheckConstraint(
            "source_agent_version > 0",
            name="ck_agent_memory_entries_source_agent_version_positive",
        ),
        CheckConstraint(
            "source_workflow_version IS NULL OR source_workflow_version > 0",
            name="ck_agent_memory_entries_source_workflow_version_positive",
        ),
        Index("ix_agent_memory_entries_scope", "scope_type", "scope_key"),
        Index(
            "ix_agent_memory_entries_scope_visible_kind",
            "scope_type",
            "scope_key",
            "visible_to_workflow",
            "kind",
        ),
        Index("ix_agent_memory_entries_visible_kind", "visible_to_workflow", "kind"),
        Index("ix_agent_memory_entries_updated_at_id", "updated_at", "id"),
        Index(
            "ix_agent_memory_entries_visible_updated_at_id",
            "visible_to_workflow",
            "updated_at",
            "id",
        ),
        Index("ix_agent_memory_entries_content_hash", "content_hash"),
        Index(
            "ix_agent_memory_entries_subject_refs_gin",
            "subject_refs",
            postgresql_using="gin",
            postgresql_ops={"subject_refs": "jsonb_path_ops"},
        ),
        Index("ix_agent_memory_entries_source", "source_run_id", "source_agent_key"),
        Index(
            "uq_agent_memory_entries_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=sql_text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_agent_memory_entries_idempotency_fallback",
            "scope_type",
            "scope_key",
            "kind",
            "content_hash",
            "source_run_id",
            "source_agent_key",
            sql_text("COALESCE(source_step_id, '')"),
            sql_text("COALESCE(source_slot, '')"),
            unique=True,
            postgresql_where=sql_text("idempotency_key IS NULL"),
        ),
    )

    memory_id: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    visible_to_workflow: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    subject_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_by_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="agent",
        server_default="agent",
    )
    source_run_id: Mapped[int] = mapped_column(nullable=False)
    source_agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_agent_version: Mapped[int] = mapped_column(nullable=False)
    source_agent_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_workflow_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_workflow_version: Mapped[int | None] = mapped_column(nullable=True)
    source_step_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_slot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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


class AgentMemoryRevision(IdMixin, Base):
    __tablename__ = "agent_memory_revisions"
    __table_args__ = (
        UniqueConstraint("revision_id", name="uq_agent_memory_revisions_revision_id"),
        UniqueConstraint(
            "memory_entry_id",
            "version",
            name="uq_agent_memory_revisions_entry_version",
        ),
        CheckConstraint("version > 0", name="ck_agent_memory_revisions_version_positive"),
        CheckConstraint(
            "revision_action IN ('created', 'reused', 'superseded')",
            name="ck_agent_memory_revisions_action",
        ),
        CheckConstraint(
            "content_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_revisions_content_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(subject_refs) = 'array'",
            name="ck_agent_memory_revisions_subject_refs",
        ),
        CheckConstraint(
            "source_run_id > 0",
            name="ck_agent_memory_revisions_source_run_id_positive",
        ),
        Index("ix_agent_memory_revisions_entry", "memory_entry_id"),
        Index(
            "ix_agent_memory_revisions_entry_visible",
            "memory_entry_id",
            "visible_to_workflow",
        ),
        Index(
            "ix_agent_memory_revisions_visible_created_at",
            "visible_to_workflow",
            "created_at",
        ),
        Index("ix_agent_memory_revisions_content_hash", "content_hash"),
        Index(
            "ix_agent_memory_revisions_search_text",
            sql_text("to_tsvector('simple'::regconfig, summary || ' ' || content)"),
            postgresql_using="gin",
        ),
        Index("ix_agent_memory_revisions_created_at", "created_at"),
        Index("ix_agent_memory_revisions_supersedes", "supersedes_revision_id"),
    )

    memory_entry_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    visible_to_workflow: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    revision_action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="created",
        server_default="created",
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    supersedes_revision_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_run_id: Mapped[int] = mapped_column(nullable=False)
    source_agent_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_step_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_slot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    trace_span_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )


class RunMemoryEvent(IdMixin, Base):
    __tablename__ = "run_memory_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'retrieved', 'injected', 'written', 'reused', "
            "'superseded', 'reviewed', 'failed', "
            "'operator_created', 'operator_revised', 'operator_visibility_changed'"
            ")",
            name="ck_run_memory_events_event_type",
        ),
        CheckConstraint(
            "jsonb_typeof(filters) = 'object'",
            name="ck_run_memory_events_filters",
        ),
        CheckConstraint(
            "jsonb_typeof(budget) = 'object'",
            name="ck_run_memory_events_budget",
        ),
        CheckConstraint(
            "jsonb_typeof(result_snapshot) = 'object'",
            name="ck_run_memory_events_result_snapshot",
        ),
        CheckConstraint(
            "jsonb_typeof(status_snapshot) = 'object'",
            name="ck_run_memory_events_status_snapshot",
        ),
        Index("ix_run_memory_events_run_created_at", "run_id", "created_at", "id"),
        Index(
            "ix_run_memory_events_run_type_created_at",
            "run_id",
            "event_type",
            "created_at",
        ),
        Index("ix_run_memory_events_run_step", "run_step_id"),
        Index("ix_run_memory_events_agent_invocation", "run_agent_invocation_id"),
        Index("ix_run_memory_events_operation_invocation", "run_operation_invocation_id"),
        Index("ix_run_memory_events_memory_entry", "memory_entry_id"),
        Index("ix_run_memory_events_memory_revision", "memory_revision_id"),
        Index("ix_run_memory_events_trace_span", "trace_span_id"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_agent_invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_agent_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_operation_invocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("run_operation_invocations.id", ondelete="SET NULL"),
        nullable=True,
    )
    step_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invocation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memory_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    memory_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_memory_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    memory_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revision_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    retrieval_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    budget: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    injected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    status_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    trace_span_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
