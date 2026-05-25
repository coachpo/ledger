from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class PgVector(UserDefinedType[Any]):
    cache_ok = True

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **kw: object) -> str:
        del kw
        if self.dimensions is None:
            return "VECTOR"
        return f"VECTOR({self.dimensions})"


class AgentMemoryEntry(IdMixin, Base):
    __tablename__ = "agent_memory_entries"
    __table_args__ = (
        UniqueConstraint("memory_id", name="uq_agent_memory_entries_memory_id"),
        CheckConstraint(
            "scope_type IN ('workspace', 'package', 'workflow', 'run', 'agent', 'namespace')",
            name="ck_agent_memory_entries_scope_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'resolved', 'expired')",
            name="ck_agent_memory_entries_status",
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
            "jsonb_typeof(attributes) = 'object'",
            name="ck_agent_memory_entries_attributes",
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
            "ix_agent_memory_entries_scope_status_kind",
            "scope_type",
            "scope_key",
            "status",
            "kind",
        ),
        Index("ix_agent_memory_entries_status_kind", "status", "kind"),
        Index("ix_agent_memory_entries_content_hash", "content_hash"),
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
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    subject_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
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
            "status IN ('pending', 'resolved', 'expired')",
            name="ck_agent_memory_revisions_status",
        ),
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
            "jsonb_typeof(attributes) = 'object'",
            name="ck_agent_memory_revisions_attributes",
        ),
        CheckConstraint(
            "source_run_id > 0",
            name="ck_agent_memory_revisions_source_run_id_positive",
        ),
        Index("ix_agent_memory_revisions_entry", "memory_entry_id"),
        Index("ix_agent_memory_revisions_content_hash", "content_hash"),
        Index("ix_agent_memory_revisions_created_at", "created_at"),
        Index("ix_agent_memory_revisions_supersedes", "supersedes_revision_id"),
    )

    memory_entry_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
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
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
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


class AgentMemoryChunk(IdMixin, Base):
    __tablename__ = "agent_memory_chunks"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_agent_memory_chunks_chunk_id"),
        UniqueConstraint(
            "memory_revision_id",
            "chunk_index",
            name="uq_agent_memory_chunks_revision_index",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_agent_memory_chunks_chunk_index_non_negative",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_agent_memory_chunks_token_count_non_negative",
        ),
        CheckConstraint(
            "content_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_chunks_content_hash",
        ),
        CheckConstraint(
            "source_content_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_chunks_source_content_hash",
        ),
        CheckConstraint(
            "jsonb_typeof(attributes) = 'object'",
            name="ck_agent_memory_chunks_attributes",
        ),
        Index("ix_agent_memory_chunks_entry", "memory_entry_id"),
        Index("ix_agent_memory_chunks_revision", "memory_revision_id"),
        Index("ix_agent_memory_chunks_memory_id", "memory_id"),
        Index("ix_agent_memory_chunks_revision_id", "revision_id"),
        Index("ix_agent_memory_chunks_content_hash", "content_hash"),
        Index("ix_agent_memory_chunks_chunking_version", "chunking_version"),
    )

    memory_entry_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_revision_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_id: Mapped[str] = mapped_column(String(160), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(200), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int | None] = mapped_column(nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )


class AgentMemoryEmbedding(IdMixin, Base):
    __tablename__ = "agent_memory_embeddings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'ready', 'stale', 'failed')",
            name="ck_agent_memory_embeddings_status",
        ),
        CheckConstraint(
            "embedding_dimensions > 0",
            name="ck_agent_memory_embeddings_dimensions_positive",
        ),
        CheckConstraint(
            "content_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_embeddings_content_hash",
        ),
        CheckConstraint(
            "embedding_config_hash IS NULL OR embedding_config_hash ~ '^[a-f0-9]{64}$'",
            name="ck_agent_memory_embeddings_config_hash",
        ),
        CheckConstraint(
            "status <> 'ready' OR embedding IS NOT NULL",
            name="ck_agent_memory_embeddings_ready_has_vector",
        ),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_agent_memory_embeddings_metadata",
        ),
        Index("ix_agent_memory_embeddings_chunk", "memory_chunk_id"),
        Index("ix_agent_memory_embeddings_entry", "memory_entry_id"),
        Index("ix_agent_memory_embeddings_revision", "memory_revision_id"),
        Index("ix_agent_memory_embeddings_status", "status"),
        Index("ix_agent_memory_embeddings_model_status", "embedding_model", "status"),
        Index(
            "ix_agent_memory_embeddings_provenance",
            "embedding_model",
            "embedding_dimensions",
            "chunking_version",
            "content_hash",
        ),
        Index(
            "uq_agent_memory_embeddings_chunk_provenance",
            "memory_chunk_id",
            sql_text("COALESCE(embedding_provider, '')"),
            "embedding_model",
            "embedding_dimensions",
            "chunking_version",
            "content_hash",
            sql_text("COALESCE(embedding_config_hash, '')"),
            unique=True,
        ),
    )

    memory_chunk_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_entry_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_revision_id: Mapped[int] = mapped_column(
        ForeignKey("agent_memory_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_id: Mapped[str] = mapped_column(String(160), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(PgVector(), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunking_version: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding_config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class RunMemoryEvent(IdMixin, Base):
    __tablename__ = "run_memory_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'retrieved', 'injected', 'written', 'reused', "
            "'superseded', 'reviewed', 'failed'"
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
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
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
