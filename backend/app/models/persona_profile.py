from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class PersonaProfile(IdMixin, TimestampMixin, Base):
    __tablename__ = "persona_profiles"
    __table_args__ = (
        CheckConstraint(
            "origin IN ('seeded', 'managed', 'imported')",
            name="ck_persona_profiles_origin",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'DEPRECATED', 'ARCHIVED')",
            name="ck_persona_profiles_status",
        ),
        CheckConstraint(
            "kind IN ('role_template', 'character_profile', 'builtin_profile', 'managed_persona')",
            name="ck_persona_profiles_kind",
        ),
        CheckConstraint("version > 0", name="ck_persona_profiles_version_positive"),
        CheckConstraint(
            "(parent_profile_key IS NULL AND parent_profile_version IS NULL) OR "
            "(parent_profile_key IS NOT NULL AND parent_profile_version IS NOT NULL)",
            name="ck_persona_profiles_parent_pair",
        ),
        CheckConstraint(
            "parent_profile_version IS NULL OR parent_profile_version > 0",
            name="ck_persona_profiles_parent_version_positive",
        ),
        CheckConstraint(
            "legacy_source_version IS NULL OR legacy_source_version > 0",
            name="ck_persona_profiles_legacy_source_version_positive",
        ),
        CheckConstraint(
            "legacy_entity_type IS NULL OR legacy_entity_type IN ('role', 'character')",
            name="ck_persona_profiles_legacy_entity_type",
        ),
        CheckConstraint(
            "(legacy_entity_type IS NULL AND legacy_entity_key IS NULL) OR "
            "(legacy_entity_type IS NOT NULL AND legacy_entity_key IS NOT NULL)",
            name="ck_persona_profiles_legacy_entity_pair",
        ),
        UniqueConstraint("key", "version", name="uq_persona_profiles_key_version"),
        Index("ix_persona_profiles_key", "key"),
        Index("ix_persona_profiles_canonical_target_id", "canonical_target_id"),
        Index("ix_persona_profiles_handle", "handle"),
        Index("ix_persona_profiles_legacy_entity", "legacy_entity_type", "legacy_entity_key"),
        Index(
            "uq_persona_profiles_active_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_persona_profiles_draft_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'DRAFT'"),
        ),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    canonical_target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_profile_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    parent_profile_version: Mapped[int | None] = mapped_column(nullable=True)
    legacy_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    legacy_entity_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    legacy_source_version: Mapped[int | None] = mapped_column(nullable=True)
    system_prompt_fragment: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    prompt_append_fragment: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        server_default="",
    )
    default_capability_bundle_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
