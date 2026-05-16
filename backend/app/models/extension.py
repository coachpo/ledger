from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExtensionState(Base):
    __tablename__: str = "extension_states"

    extension_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_text("true"),
    )


__all__ = ["ExtensionState"]
