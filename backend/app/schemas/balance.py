from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from app.core.formatting import parse_decimal_string
from app.schemas.common import CamelModel, OperationType


class BalanceBase(CamelModel):
    label: str = Field(min_length=1, max_length=60)
    amount: Decimal
    operation_type: OperationType

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Label is required")
        return normalized

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> Decimal:
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Amount must be greater than or equal to zero")
        return parsed


class BalanceCreate(BalanceBase):
    pass


class BalanceUpdate(CamelModel):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    amount: Decimal | None = None
    operation_type: OperationType | None = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Label is required")
        return normalized

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Amount must be greater than or equal to zero")
        return parsed

    @model_validator(mode="after")
    def validate_payload(self) -> BalanceUpdate:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "label" in self.model_fields_set and self.label is None:
            raise ValueError("Label is required")
        if "amount" in self.model_fields_set and self.amount is None:
            raise ValueError("Amount is required")
        return self


class BalanceRead(CamelModel):
    id: int
    portfolio_id: int
    label: str
    amount: Decimal
    operation_type: OperationType
    has_trading_operations: bool = False
    currency: str
    created_at: datetime
    updated_at: datetime


class BalanceCompactRead(CamelModel):
    id: int
    label: str
    amount: Decimal
    currency: str
