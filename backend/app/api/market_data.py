from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.extensions.signaldeck_finance.dependencies import MarketDataServiceDependency
from app.schemas.market_data import MarketHistoryRead, MarketQuoteListRead

router = APIRouter(prefix="/portfolios/{portfolio_id}/market-data", tags=["market-data"])


@router.get("/quotes", response_model=MarketQuoteListRead)
def get_quotes(
    portfolio_id: int,
    symbols: Annotated[str, Query(..., min_length=1)],
    service: MarketDataServiceDependency,
) -> MarketQuoteListRead:
    symbol_list = [part.strip() for part in symbols.split(",") if part.strip()]
    return service.get_quotes(portfolio_id, symbol_list)


@router.get("/history", response_model=MarketHistoryRead)
def get_history(
    portfolio_id: int,
    symbols: Annotated[str, Query(..., min_length=1)],
    service: MarketDataServiceDependency,
    range_value: Annotated[
        Literal["1mo", "3mo", "ytd", "1y", "max"],
        Query(alias="range"),
    ] = "3mo",
) -> MarketHistoryRead:
    symbol_list = [part.strip() for part in symbols.split(",") if part.strip()]
    return service.get_history(portfolio_id, symbol_list, range_value)
