from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.mcp_server import EncryptedJSONB


class ModelConnection(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_model_connections_status",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low', 'medium', 'high')",
            name="ck_model_connections_reasoning_effort",
        ),
        CheckConstraint(
            "api_style IN ('responses', 'chat_completions')",
            name="ck_model_connections_api_style",
        ),
        CheckConstraint(
            "timeout_seconds > 0",
            name="ck_model_connections_timeout_seconds_positive",
        ),
        UniqueConstraint("key", name="uq_model_connections_key"),
        Index("ix_model_connections_key", "key"),
        Index("ix_model_connections_status", "status"),
        Index("ix_model_connections_model_id", "model_id"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        server_default="medium",
    )
    api_style: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="responses",
        server_default="responses",
    )
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=60, server_default="60")
    secret_payload: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    has_api_key: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("false"),
    )
    api_key_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
