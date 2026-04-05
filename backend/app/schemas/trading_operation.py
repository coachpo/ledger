from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.balance import BalanceCompactRead
from app.schemas.common import CamelModel, TradingSide, ensure_timezone
from app.schemas.position import PositionCompactRead


# Base class for all trading operations
class TradingOperationBase(CamelModel):
    symbol: str
    executed_at: datetime

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = normalize_symbol(value)
        if not normalized:
            raise ValueError("Symbol is required")
        return normalized

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class CashTradingOperationBase(TradingOperationBase):
    balance_id: int


class BuyOperationCreate(CashTradingOperationBase):
    side: Literal[TradingSide.BUY] = TradingSide.BUY
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Quantity must be greater than zero")
        return parsed

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Price must be greater than or equal to zero")
        return parsed

    @field_validator("commission", mode="before")
    @classmethod
    def validate_commission(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Commission must be greater than or equal to zero")
        return parsed


class SellOperationCreate(CashTradingOperationBase):
    side: Literal[TradingSide.SELL] = TradingSide.SELL
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Quantity must be greater than zero")
        return parsed

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Price must be greater than or equal to zero")
        return parsed

    @field_validator("commission", mode="before")
    @classmethod
    def validate_commission(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Commission must be greater than or equal to zero")
        return parsed


class DividendOperationCreate(CashTradingOperationBase):
    side: Literal[TradingSide.DIVIDEND] = TradingSide.DIVIDEND
    dividend_amount: Decimal
    commission: Decimal = Decimal("0")

    @field_validator("dividend_amount", mode="before")
    @classmethod
    def validate_dividend_amount(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Dividend amount must be greater than zero")
        return parsed

    @field_validator("commission", mode="before")
    @classmethod
    def validate_commission(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Commission must be greater than or equal to zero")
        return parsed


# SPLIT operation
class SplitOperationCreate(TradingOperationBase):
    side: Literal[TradingSide.SPLIT] = TradingSide.SPLIT
    split_ratio: Decimal

    @field_validator("split_ratio", mode="before")
    @classmethod
    def validate_split_ratio(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Split ratio must be greater than zero")
        return parsed


# Discriminated union for all operation types
TradingOperationCreate = Annotated[
    BuyOperationCreate | SellOperationCreate | DividendOperationCreate | SplitOperationCreate,
    Field(discriminator="side"),
]


class TradingOperationRead(CamelModel):
    id: int
    portfolio_id: int
    balance_id: int | None
    balance_label: str
    symbol: str
    side: TradingSide
    quantity: Decimal | None
    price: Decimal | None
    commission: Decimal
    dividend_amount: Decimal | None
    split_ratio: Decimal | None
    currency: str
    executed_at: datetime
    created_at: datetime


class TradingOperationResult(CamelModel):
    operation: TradingOperationRead
    updated_position: PositionCompactRead | None
    updated_balance: BalanceCompactRead | None
