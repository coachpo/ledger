from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class AgentSpec(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_specs"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('seeded', 'managed', 'imported')",
            name="ck_agent_specs_origin",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'ARCHIVED')",
            name="ck_agent_specs_status",
        ),
        CheckConstraint("version > 0", name="ck_agent_specs_version_positive"),
        UniqueConstraint("key", "version", name="uq_agent_specs_key_version"),
        Index("ix_agent_specs_key", "key"),
        Index("ix_agent_specs_status", "status"),
        Index(
            "uq_agent_specs_active_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_agent_specs_draft_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'DRAFT'"),
        ),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    model_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    final_output_contract: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    default_capability_bundle_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    default_persona_profile_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
