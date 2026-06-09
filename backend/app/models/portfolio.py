from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Portfolio(IdMixin, TimestampMixin, Base):
    __tablename__: str = "portfolios"
    __table_args__: tuple[UniqueConstraint, Index] = (
        UniqueConstraint("slug", name="uq_portfolios_slug"),
        Index("ix_portfolios_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    balances: Mapped[list[object]] = relationship(
        "Balance",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    positions: Mapped[list[object]] = relationship(
        "Position",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    trading_operations: Mapped[list[object]] = relationship(
        "TradingOperation",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
