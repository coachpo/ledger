from __future__ import annotations

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class TextTemplate(IdMixin, TimestampMixin, Base):
    __tablename__ = "text_templates"
    __table_args__ = (UniqueConstraint("name", name="uq_text_templates_name"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
