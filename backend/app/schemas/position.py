from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.common import CamelModel


class PositionCreate(CamelModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=120)
    quantity: Decimal
    average_cost: Decimal

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = normalize_symbol(value)
        if not normalized:
            raise ValueError("Symbol is required")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Quantity must be greater than zero")
        return parsed

    @field_validator("average_cost", mode="before")
    @classmethod
    def validate_average_cost(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Average cost must be greater than or equal to zero")
        return parsed


class PositionUpdate(CamelModel):
    name: str | None = Field(default=None, max_length=120)
    quantity: Decimal | None = None
    average_cost: Decimal | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal_string(value)
        if parsed <= 0:
            raise ValueError("Quantity must be greater than zero")
        return parsed

    @field_validator("average_cost", mode="before")
    @classmethod
    def validate_average_cost(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Average cost must be greater than or equal to zero")
        return parsed

    @model_validator(mode="after")
    def validate_payload(self) -> PositionUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "quantity" in self.model_fields_set and self.quantity is None:
            raise ValueError("Quantity is required")
        if "average_cost" in self.model_fields_set and self.average_cost is None:
            raise ValueError("Average cost is required")
        return self


class PositionRead(CamelModel):
    id: int
    portfolio_id: int
    symbol: str
    name: str | None
    quantity: Decimal
    average_cost: Decimal
    currency: str
    created_at: datetime
    updated_at: datetime


class PositionSymbolLookupRead(CamelModel):
    symbol: str
    name: str | None


class PositionCompactRead(CamelModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    currency: str
