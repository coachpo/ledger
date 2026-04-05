from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def decimal_to_string(value: Decimal) -> str:
    return format(value, "f")


def format_decimal(value: Decimal, *, places: int) -> str:
    quantizer = Decimal("1") if places == 0 else Decimal(f"1.{'0' * places}")
    return format(value.quantize(quantizer, rounding=ROUND_HALF_UP), f".{places}f")


def format_nullable_decimal(value: Decimal | None, *, places: int = 2) -> str | None:
    if value is None:
        return None
    return format_decimal(value, places=places)


def portfolio_cash_total(balances: Sequence[object]) -> Decimal:
    total = Decimal("0")
    for balance in balances:
        amount = getattr(balance, "amount", None)
        if not isinstance(amount, Decimal):
            raise TypeError("Balance amount must be a Decimal")

        if str(getattr(balance, "operation_type", "")) == "WITHDRAWAL":
            total -= amount
            continue
        total += amount
    return total


def parse_decimal_string(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Decimal value is required")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Invalid decimal value") from exc
    raise ValueError("Decimal values must be strings")


def normalize_symbol(value: str) -> str:
    return value.strip().upper()


def normalize_currency(value: str) -> str:
    return value.strip().upper()
