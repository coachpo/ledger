from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.common import CamelModel


class BacktestStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_CALLBACK = "AWAITING_CALLBACK"
    PROCESSING_CALLBACK = "PROCESSING_CALLBACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BacktestFrequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class BacktestPriceMode(StrEnum):
    CLOSING_PRICE = "CLOSING_PRICE"


class BacktestCommissionMode(StrEnum):
    ZERO = "ZERO"
    FIXED = "FIXED"
    PERCENTAGE = "PERCENTAGE"


class TradeDecision(CamelModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    quantity: int | None = None
    target_price: Decimal | None = None
    reasoning: str

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = normalize_symbol(value)
        if not normalized:
            raise ValueError("Symbol is required")
        return normalized

    @field_validator("target_price", mode="before")
    @classmethod
    def validate_target_price(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal_string(value)
        if parsed < 0:
            raise ValueError("Target price must be greater than or equal to zero")
        return parsed


class BacktestDecisionSummary(CamelModel):
    symbol: str
    action: Literal["BUY", "SELL", "HOLD"]
    reasoning: str | None = None
    quantity: int | None = None
    target_price: Decimal | None = None
    executed: bool | None = None
    failure_reason: str | None = None


class BacktestRecentActivityEntry(CamelModel):
    cycle_date: date
    decisions: list[BacktestDecisionSummary]


class BacktestCurvePoint(CamelModel):
    date: date
    value: Decimal


class BacktestPortfolioResults(CamelModel):
    starting_value: Decimal
    ending_value: Decimal
    total_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal | None = None
    total_trades: int
    win_rate: Decimal
    total_commission: Decimal


class BacktestBenchmarkResults(CamelModel):
    starting_price: Decimal
    ending_price: Decimal
    total_return: Decimal


class BacktestTradeLogEntry(CamelModel):
    cycle_date: date
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal | None = None
    requested_price: Decimal | None = None
    executed_price: Decimal | None = None
    executed: bool
    report_slug: str | None = None
    failure_reason: str | None = None
    commission: Decimal | None = None
    profit: Decimal | None = None


class BacktestResults(CamelModel):
    portfolio: BacktestPortfolioResults
    benchmarks: dict[str, BacktestBenchmarkResults]
    equity_curve: list[BacktestCurvePoint]
    benchmark_curves: dict[str, list[BacktestCurvePoint]]
    drawdown_curve: list[BacktestCurvePoint]
    trades: list[BacktestTradeLogEntry]


class BacktestCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    portfolio_id: int
    template_id: int | None = None
    create_template: bool = False
    template_name: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: BacktestFrequency
    start_date: date
    end_date: date
    webhook_url: str = Field(min_length=1, max_length=1000)
    webhook_timeout: int = Field(default=600, ge=30, le=3600)
    price_mode: BacktestPriceMode
    commission_mode: BacktestCommissionMode
    commission_value: Decimal = Decimal("0")
    benchmark_symbols: list[str] = Field(min_length=1)

    @field_validator("name", "webhook_url", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        if value is None:
            raise ValueError("Value is required")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("Value is required")
        return normalized

    @field_validator("template_name", mode="before")
    @classmethod
    def validate_optional_template_name(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized

    @field_validator("commission_value", mode="before")
    @classmethod
    def validate_optional_decimal(cls, value: object) -> Decimal | None:
        if value is None or value == "":
            return None
        return parse_decimal_string(value)

    @field_validator("benchmark_symbols", mode="before")
    @classmethod
    def coerce_benchmark_symbols(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @field_validator("benchmark_symbols")
    @classmethod
    def validate_benchmark_symbols(cls, value: list[str]) -> list[str]:
        normalized_symbols: list[str] = []
        seen: set[str] = set()
        for symbol in value:
            normalized = normalize_symbol(symbol)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_symbols.append(normalized)
        if not normalized_symbols:
            raise ValueError("Select at least one benchmark")
        return normalized_symbols

    @model_validator(mode="after")
    def validate_payload(self) -> BacktestCreate:
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        today = date.today()
        if self.start_date >= today or self.end_date >= today:
            raise ValueError("Backtest dates must be in the past")
        if self.commission_mode == BacktestCommissionMode.PERCENTAGE:
            if (
                self.commission_value is None
                or self.commission_value < 0
                or self.commission_value > 1
            ):
                raise ValueError("Commission percentage must be a decimal fraction between 0 and 1")
        if self.commission_value is None:
            self.commission_value = Decimal("0")
        if self.commission_value < 0:
            raise ValueError("Commission value must be greater than or equal to zero")
        return self


class BacktestRead(CamelModel):
    id: int
    portfolio_id: int
    portfolio_name: str | None = None
    template_id: int
    deposit_balance_id: int
    name: str
    status: BacktestStatus
    frequency: BacktestFrequency
    start_date: date
    end_date: date
    current_cycle_date: date | None = None
    total_cycles: int
    completed_cycles: int
    webhook_url: str
    webhook_timeout: int
    price_mode: BacktestPriceMode
    commission_mode: BacktestCommissionMode
    commission_value: Decimal
    benchmark_symbols: list[str]
    current_cycle_status: str | None = None
    recent_activity: list[BacktestRecentActivityEntry] | None = None
    results: BacktestResults | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("recent_activity", mode="before")
    @classmethod
    def validate_recent_activity(cls, value: Any) -> Any:
        if value is None:
            return None
        return value

    @field_validator("results", mode="before")
    @classmethod
    def validate_results(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict) and set(value.keys()) == {"_run_state"}:
            return None
        return value
