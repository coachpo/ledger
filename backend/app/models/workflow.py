from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin

WORKFLOW_MANIFEST_API_VERSION = "signaldeck.workflow/v1"
TEMPORARY_WORKFLOW_MANIFEST_SOURCE = (
    "apiVersion: signaldeck.workflow/v1\n"
    "kind: Workflow\n"
    "metadata:\n"
    "  source: legacy-payload-placeholder\n"
)


class Workflow(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated')",
            name="ck_workflows_status",
        ),
        CheckConstraint("version > 0", name="ck_workflows_version_positive"),
        CheckConstraint(
            "aggregate_budget_usd >= 0",
            name="ck_workflows_aggregate_budget_non_negative",
        ),
        UniqueConstraint("key", "version", name="uq_workflows_key_version"),
        Index("ix_workflows_key", "key"),
        Index("ix_workflows_status", "status"),
        Index(
            "uq_workflows_published_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
        Index(
            "uq_workflows_draft_key",
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
        default=WORKFLOW_MANIFEST_API_VERSION,
        server_default=WORKFLOW_MANIFEST_API_VERSION,
    )
    manifest_source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
        server_default=TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
    )
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    output_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    aggregate_budget_usd: Mapped[Decimal] = mapped_column(
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
