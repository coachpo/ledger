from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.extensions.ledger_finance.dependencies import get_market_data_service
from app.schemas.market_data import MarketHistoryRead, MarketQuoteListRead
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/portfolios/{portfolio_id}/market-data", tags=["market-data"])


@router.get("/quotes", response_model=MarketQuoteListRead)
def get_quotes(
    portfolio_id: int,
    symbols: Annotated[str, Query(..., min_length=1)],
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> MarketQuoteListRead:
    symbol_list = [part.strip() for part in symbols.split(",") if part.strip()]
    return service.get_quotes(portfolio_id, symbol_list)


@router.get("/history", response_model=MarketHistoryRead)
def get_history(
    portfolio_id: int,
    symbols: Annotated[str, Query(..., min_length=1)],
    service: Annotated[MarketDataService, Depends(get_market_data_service)],
    range_value: Annotated[
        Literal["1mo", "3mo", "ytd", "1y", "max"],
        Query(alias="range"),
    ] = "3mo",
) -> MarketHistoryRead:
    symbol_list = [part.strip() for part in symbols.split(",") if part.strip()]
    return service.get_history(portfolio_id, symbol_list, range_value)
