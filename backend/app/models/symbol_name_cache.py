from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class SymbolNameCache(IdMixin, Base):
    __tablename__ = "symbol_name_cache"
    __table_args__ = (
        UniqueConstraint("symbol", name="uq_symbol_name_cache_symbol"),
        Index("ix_symbol_name_cache_fetched_at", "fetched_at"),
        {"prefixes": ["UNLOGGED"]},
    )

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
