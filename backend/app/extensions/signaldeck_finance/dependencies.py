from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.extensions.signaldeck_finance.config import get_finance_workspace_settings
from app.extensions.signaldeck_finance.provider_factories import create_quote_provider
from app.extensions.signaldeck_finance.service_gate import (
    BALANCE_SERVICE_SURFACE,
    CSV_IMPORT_SERVICE_SURFACE,
    MARKET_DATA_SERVICE_SURFACE,
    MEMORY_REPORT_SERVICE_SURFACE,
    PORTFOLIO_SERVICE_SURFACE,
    POSITION_SERVICE_SURFACE,
    REPORT_SERVICE_SURFACE,
    TEMPLATE_COMPILER_SURFACE,
    TEXT_TEMPLATE_SERVICE_SURFACE,
    TRADING_OPERATION_SERVICE_SURFACE,
)
from app.extensions.signaldeck_finance.services.balance_service import BalanceService
from app.extensions.signaldeck_finance.services.csv_import_service import CsvImportService
from app.extensions.signaldeck_finance.services.market_data_service import MarketDataService
from app.extensions.signaldeck_finance.services.portfolio_service import PortfolioService
from app.extensions.signaldeck_finance.services.position_service import PositionService
from app.extensions.signaldeck_finance.services.report_service import ReportService
from app.extensions.signaldeck_finance.services.template_compiler_service import (
    TemplateCompilerService,
)
from app.extensions.signaldeck_finance.services.text_template_service import TextTemplateService
from app.extensions.signaldeck_finance.services.trading_operation_service import (
    TradingOperationService,
)
from app.services.quote_provider import QuoteProvider

FinanceSharedServiceClassification = Literal[
    "move-now",
    "wrapped-by-finance-factory",
]


@dataclass(frozen=True, slots=True)
class FinanceSharedServiceOwnership:
    service_name: str
    module_path: str
    classification: FinanceSharedServiceClassification
    surface: str
    rationale: str


_FINANCE_OWNED_SERVICE_RATIONALE = (
    "Finance behavior lives in extension-owned service implementations; "
    "construction is supplied through finance-owned factories and every direct entrypoint "
    "blocks when the extension is disabled."
)

FINANCE_SHARED_SERVICE_OWNERSHIP_MAP: tuple[FinanceSharedServiceOwnership, ...] = (
    FinanceSharedServiceOwnership(
        "MarketDataService",
        "app.extensions.signaldeck_finance.services.market_data_service",
        "move-now",
        MARKET_DATA_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "PositionService",
        "app.extensions.signaldeck_finance.services.position_service",
        "move-now",
        POSITION_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "PortfolioService",
        "app.extensions.signaldeck_finance.services.portfolio_service",
        "move-now",
        PORTFOLIO_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "BalanceService",
        "app.extensions.signaldeck_finance.services.balance_service",
        "move-now",
        BALANCE_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TradingOperationService",
        "app.extensions.signaldeck_finance.services.trading_operation_service",
        "move-now",
        TRADING_OPERATION_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "CsvImportService",
        "app.extensions.signaldeck_finance.services.csv_import_service",
        "move-now",
        CSV_IMPORT_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TextTemplateService",
        "app.extensions.signaldeck_finance.services.text_template_service",
        "move-now",
        TEXT_TEMPLATE_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "ReportService",
        "app.extensions.signaldeck_finance.services.report_service",
        "move-now",
        REPORT_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TemplateCompilerService",
        "app.extensions.signaldeck_finance.services.template_compiler_service",
        "move-now",
        TEMPLATE_COMPILER_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "MemoryReportService",
        "app.extensions.signaldeck_finance.services.memory_report_service",
        "move-now",
        MEMORY_REPORT_SERVICE_SURFACE,
        _FINANCE_OWNED_SERVICE_RATIONALE,
    ),
)


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
    settings = get_finance_workspace_settings()
    return MarketDataService(
        session=session,
        quote_provider=quote_provider,
        quote_stale_after_minutes=settings.quote_stale_after_minutes,
    )


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


PortfolioServiceDependency = Annotated[
    PortfolioService,
    Depends(get_portfolio_service),
]
BalanceServiceDependency = Annotated[
    BalanceService,
    Depends(get_balance_service),
]
PositionServiceDependency = Annotated[
    PositionService,
    Depends(get_position_service),
]
CsvImportServiceDependency = Annotated[
    CsvImportService,
    Depends(get_csv_import_service),
]
TradingOperationServiceDependency = Annotated[
    TradingOperationService,
    Depends(get_trading_operation_service),
]
MarketDataServiceDependency = Annotated[
    MarketDataService,
    Depends(get_market_data_service),
]
TextTemplateServiceDependency = Annotated[
    TextTemplateService,
    Depends(get_text_template_service),
]
ReportServiceDependency = Annotated[
    ReportService,
    Depends(get_report_service),
]
TemplateCompilerServiceDependency = Annotated[
    TemplateCompilerService,
    Depends(get_template_compiler_service),
]


__all__ = [
    "FINANCE_SHARED_SERVICE_OWNERSHIP_MAP",
    "BalanceServiceDependency",
    "CsvImportServiceDependency",
    "FinanceSharedServiceClassification",
    "FinanceSharedServiceOwnership",
    "MarketDataServiceDependency",
    "PortfolioServiceDependency",
    "PositionServiceDependency",
    "ReportServiceDependency",
    "TemplateCompilerServiceDependency",
    "TextTemplateServiceDependency",
    "TradingOperationServiceDependency",
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
