from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class CapabilityRegistryEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "capability_registry_entries"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('seeded', 'managed', 'imported')",
            name="ck_capability_registry_entries_origin",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'ARCHIVED')",
            name="ck_capability_registry_entries_status",
        ),
        CheckConstraint(
            "type IN ('tool', 'connector', 'bundle')",
            name="ck_capability_registry_entries_type",
        ),
        CheckConstraint(
            "approval_mode IN ('not_required', 'required')",
            name="ck_capability_registry_entries_approval_mode",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_capability_registry_entries_version_positive",
        ),
        CheckConstraint(
            "(type = 'bundle' AND bundle_members IS NOT NULL) OR "
            "(type <> 'bundle' AND bundle_members IS NULL)",
            name="ck_capability_registry_entries_bundle_members",
        ),
        CheckConstraint(
            "type = 'bundle' OR adapter_key IS NOT NULL",
            name="ck_capability_registry_entries_adapter_key_required",
        ),
        CheckConstraint(
            "type = 'bundle' OR config_schema IS NOT NULL",
            name="ck_capability_registry_entries_config_schema_required",
        ),
        CheckConstraint(
            "(type = 'connector' AND transport IS NOT NULL AND lifecycle IS NOT NULL) OR "
            "(type <> 'connector' AND transport IS NULL AND lifecycle IS NULL)",
            name="ck_capability_registry_entries_connector_fields",
        ),
        UniqueConstraint("key", "version", name="uq_capability_registry_entries_key_version"),
        Index("ix_capability_registry_entries_key", "key"),
        Index("ix_capability_registry_entries_type", "type"),
        Index(
            "uq_capability_registry_entries_active_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_capability_registry_entries_draft_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'DRAFT'"),
        ),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    approval_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    adapter_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    config_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bundle_members: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    transport: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lifecycle: Mapped[str | None] = mapped_column(String(40), nullable=True)
