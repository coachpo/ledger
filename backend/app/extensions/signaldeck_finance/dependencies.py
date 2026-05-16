from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.extensions.signaldeck_finance.provider_factories import create_quote_provider
from app.services.balance_service import BalanceService
from app.services.csv_import_service import CsvImportService
from app.services.market_data_service import MarketDataService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import QuoteProvider
from app.services.report_service import ReportService
from app.services.template_compiler_service import TemplateCompilerService
from app.services.text_template_service import TextTemplateService
from app.services.trading_operation_service import TradingOperationService


def get_finance_workspace_session() -> Iterator[Session]:
    yield from get_db_session()


def get_quote_provider() -> QuoteProvider:
    return create_quote_provider()


def get_portfolio_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> PortfolioService:
    return PortfolioService(session)


def get_balance_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> BalanceService:
    return BalanceService(session)


def get_position_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> PositionService:
    return PositionService(session, quote_provider)


def get_csv_import_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> CsvImportService:
    return CsvImportService(session)


def get_trading_operation_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> TradingOperationService:
    return TradingOperationService(session, quote_provider)


def get_market_data_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> MarketDataService:
    return MarketDataService(session=session, quote_provider=quote_provider)


def get_text_template_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> TextTemplateService:
    return TextTemplateService(session)


def get_report_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
) -> ReportService:
    return ReportService(session)


def get_template_compiler_service(
    session: Annotated[Session, Depends(get_finance_workspace_session)],
    market_data_service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> TemplateCompilerService:
    return TemplateCompilerService(session, market_data_service)


__all__ = [
    "get_balance_service",
    "get_csv_import_service",
    "get_finance_workspace_session",
    "get_market_data_service",
    "get_portfolio_service",
    "get_position_service",
    "get_quote_provider",
    "get_report_service",
    "get_template_compiler_service",
    "get_text_template_service",
    "get_trading_operation_service",
]
