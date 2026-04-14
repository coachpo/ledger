from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base


class RuntimeRunArtifact(Base):
    __tablename__ = "runtime_run_artifacts"
    __table_args__ = (
        Index("ix_runtime_run_artifacts_prompt_report_slug", "prompt_report_slug"),
        Index("ix_runtime_run_artifacts_terminal_error_code", "terminal_error_code"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("runtime_runs.id", ondelete="CASCADE"), primary_key=True
    )
    entry_prompt_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    full_user_prompt_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default="",
    )
    authored_entry_prompt_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_entry_prompt_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_context_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_report_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_mention_handles: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_persona_profile_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_trade_decisions: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    resolved_builtin_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_role_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_character_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_bundle_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_tool_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_connector_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    mentioned_target_outputs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_mentions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    resolved_workflow_agent_refs: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    resolved_capabilities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    final_output: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    terminal_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    terminal_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
