from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.balance import Balance
    from app.models.position import Position
    from app.models.trading_operation import TradingOperation


class Portfolio(IdMixin, TimestampMixin, Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_portfolios_slug"),
        Index("ix_portfolios_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)

    balances: Mapped[list[Balance]] = relationship(
        "Balance",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    positions: Mapped[list[Position]] = relationship(
        "Position",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    trading_operations: Mapped[list[TradingOperation]] = relationship(
        "TradingOperation",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
