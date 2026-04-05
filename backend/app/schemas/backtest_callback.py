from __future__ import annotations

from pydantic import Field

from app.schemas.backtest import TradeDecision
from app.schemas.common import CamelModel


class CycleReportUpload(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class CycleReportUploadResponse(CamelModel):
    slug: str


class CycleTradesRequest(CamelModel):
    decisions: list[TradeDecision]
    report_slug: str | None = None


class CycleTradeResult(CamelModel):
    symbol: str
    action: str
    executed: bool | None = None
    executed_price: str | None = None
    failure_reason: str | None = None


class CycleTradesResponse(CamelModel):
    executed: list[CycleTradeResult]


class CycleCompleteResponse(CamelModel):
    backtest_id: int
    status: str
    completed_cycles: int
    total_cycles: int
    next_cycle_date: str | None = None
    finished: bool
