from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.orchestration_role import OrchestrationRole


class OrchestrationCharacter(IdMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_characters"
    __table_args__ = (
        UniqueConstraint("handle", name="uq_orchestration_characters_handle"),
        Index("ix_orchestration_characters_display_name", "display_name"),
        Index("ix_orchestration_characters_role_id", "role_id"),
    )

    handle: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("orchestration_roles.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_append: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_bundle_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    role: Mapped[OrchestrationRole] = relationship("OrchestrationRole", back_populates="characters")
