from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.backtest import BacktestFrequency
from app.schemas.common import CamelModel


class BacktestWebhookDispatch(CamelModel):
    backtest_id: int
    cycle_date: date
    total_cycles: int = Field(ge=1)
    completed_cycles: int = Field(ge=0)
    frequency: BacktestFrequency
    report_slug: str = Field(min_length=1)
    report_download_url: str = Field(min_length=1)
    callback_base_url: str = Field(min_length=1)
    benchmark_symbols: list[str] = Field(default_factory=list)


class BacktestWebhookDispatchResponse(CamelModel):
    status: str
    report_slug: str
    decision_count: int = Field(ge=0)
    symbols: list[str] = Field(default_factory=list)


class BacktestWebhookDispatchAcceptedResponse(CamelModel):
    status: str
    backtest_id: int
    cycle_date: date
