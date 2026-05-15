from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ExtensionState(IdMixin, TimestampMixin, Base):
    __tablename__ = "extension_states"
    __table_args__ = (
        CheckConstraint("state_version > 0", name="ck_extension_states_version_positive"),
        UniqueConstraint("extension_key", name="uq_extension_states_extension_key"),
        Index("ix_extension_states_extension_key", "extension_key"),
        Index("ix_extension_states_enabled", "enabled"),
    )

    extension_key: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_text("true"),
    )
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )


__all__ = ["ExtensionState"]
