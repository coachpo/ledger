from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.orchestration_character import OrchestrationCharacter


class OrchestrationRole(IdMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_roles"
    __table_args__ = (
        UniqueConstraint("key", name="uq_orchestration_roles_key"),
        UniqueConstraint("name", name="uq_orchestration_roles_name"),
        Index("ix_orchestration_roles_name", "name"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    characters: Mapped[list[OrchestrationCharacter]] = relationship(
        "OrchestrationCharacter",
        back_populates="role",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
