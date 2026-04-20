from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Skill(IdMixin, TimestampMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated', 'archived')",
            name="ck_skills_status",
        ),
        CheckConstraint("version > 0", name="ck_skills_version_positive"),
        UniqueConstraint("key", "version", name="uq_skills_key_version"),
        Index("ix_skills_key", "key"),
        Index("ix_skills_status", "status"),
        Index(
            "uq_skills_published_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
        Index(
            "uq_skills_draft_key",
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
    tool_definitions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
