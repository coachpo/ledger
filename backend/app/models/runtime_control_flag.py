from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base


class RuntimeControlFlag(Base):
    __tablename__ = "runtime_control_flags"

    flag_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
