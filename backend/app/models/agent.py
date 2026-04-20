from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin


class Agent(IdMixin, TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated', 'archived')",
            name="ck_agents_status",
        ),
        CheckConstraint("version > 0", name="ck_agents_version_positive"),
        CheckConstraint(
            "output_schema_version > 0",
            name="ck_agents_output_schema_version_positive",
        ),
        CheckConstraint(
            "max_tool_rounds > 0",
            name="ck_agents_max_tool_rounds_positive",
        ),
        CheckConstraint("budget_usd >= 0", name="ck_agents_budget_usd_non_negative"),
        UniqueConstraint("key", "version", name="uq_agents_key_version"),
        Index("ix_agents_key", "key"),
        Index("ix_agents_status", "status"),
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
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema_id: Mapped[int] = mapped_column(nullable=False)
    output_schema_version: Mapped[int] = mapped_column(nullable=False)
    skills: Mapped[list[dict[str, Any]]] = mapped_column(
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
    temperature: Mapped[float] = mapped_column(
        Float(asdecimal=False),
        nullable=False,
        default=0.0,
        server_default="0",
    )
    max_tool_rounds: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    budget_usd: Mapped[Decimal] = mapped_column(
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    streaming: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
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
