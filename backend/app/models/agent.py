from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin

AGENT_MANIFEST_API_VERSION = "ledger.agent/v1"
AGENT_MANIFEST_COMPILER_VERSION = "agent-manifest-compiler/v1"
TEMPORARY_AGENT_MANIFEST_SOURCE = (
    "apiVersion: ledger.agent/v1\n"
    "kind: Agent\n"
    "metadata:\n"
    "  source: legacy-payload-placeholder\n"
)
TEMPORARY_AGENT_MANIFEST_HASH = "98e17b8a6f1bd584aab673e2ab817f26173a7a1cd19ec5890c5bd2f0099c2f3b"


class Agent(IdMixin, TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated')",
            name="ck_agents_status",
        ),
        CheckConstraint("version > 0", name="ck_agents_version_positive"),
        CheckConstraint(
            "output_schema_version > 0",
            name="ck_agents_output_schema_version_positive",
        ),
        CheckConstraint("budget_usd >= 0", name="ck_agents_budget_usd_non_negative"),
        UniqueConstraint("key", "version", name="uq_agents_key_version"),
        Index("ix_agents_key", "key"),
        Index("ix_agents_status", "status"),
        Index("ix_agents_model_connection", "model_connection_id"),
        Index("ix_agents_output_schema", "output_schema_id", "output_schema_version"),
        Index(
            "uq_agents_published_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
        Index(
            "uq_agents_draft_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'draft'"),
        ),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    manifest_api_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=AGENT_MANIFEST_API_VERSION,
        server_default=AGENT_MANIFEST_API_VERSION,
    )
    manifest_source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TEMPORARY_AGENT_MANIFEST_SOURCE,
        server_default=TEMPORARY_AGENT_MANIFEST_SOURCE,
    )
    manifest_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=TEMPORARY_AGENT_MANIFEST_HASH,
        server_default=TEMPORARY_AGENT_MANIFEST_HASH,
    )
    compiler_version: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=AGENT_MANIFEST_COMPILER_VERSION,
        server_default=AGENT_MANIFEST_COMPILER_VERSION,
    )
    model_connection_id: Mapped[int] = mapped_column(
        ForeignKey("model_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_connection_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema_id: Mapped[int] = mapped_column(
        ForeignKey("output_schemas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    output_schema_version: Mapped[int] = mapped_column(nullable=False)
    capabilities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    mcp_servers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    budget_usd: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
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
