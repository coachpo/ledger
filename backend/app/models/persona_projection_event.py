from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class PersonaProjectionEvent(IdMixin, Base):
    __tablename__ = "persona_projection_events"
    __table_args__ = (
        CheckConstraint(
            "legacy_entity_type IN ('role', 'character')",
            name="ck_persona_projection_events_entity_type",
        ),
        CheckConstraint(
            "operation IN ('create', 'reproject', 'deprecate', 'archive')",
            name="ck_persona_projection_events_operation",
        ),
        CheckConstraint(
            "persona_profile_version > 0",
            name="ck_persona_projection_events_profile_version_positive",
        ),
        CheckConstraint(
            "legacy_source_version > 0",
            name="ck_persona_projection_events_legacy_source_version_positive",
        ),
        Index(
            "ix_persona_projection_events_profile_version",
            "persona_profile_key",
            "persona_profile_version",
        ),
        Index(
            "ix_persona_projection_events_legacy_entity",
            "legacy_entity_type",
            "legacy_entity_key",
        ),
    )

    persona_profile_key: Mapped[str] = mapped_column(String(120), nullable=False)
    persona_profile_version: Mapped[int] = mapped_column(nullable=False)
    legacy_entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    legacy_entity_key: Mapped[str] = mapped_column(String(120), nullable=False)
    legacy_source_version: Mapped[int] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
