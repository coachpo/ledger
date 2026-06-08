from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.extensions.signaldeck_finance.provider_factories import create_quote_provider
from app.extensions.signaldeck_finance.service_gate import (
    BALANCE_SERVICE_SURFACE,
    CSV_IMPORT_SERVICE_SURFACE,
    MARKET_DATA_SERVICE_SURFACE,
    MEMORY_REPORT_SERVICE_SURFACE,
    PORTFOLIO_SERVICE_SURFACE,
    POSITION_SERVICE_SURFACE,
    REFLECTION_SERVICE_SURFACE,
    REPORT_SERVICE_SURFACE,
    RETURN_RESOLUTION_SERVICE_SURFACE,
    TEMPLATE_COMPILER_SURFACE,
    TEXT_TEMPLATE_SERVICE_SURFACE,
    TRADING_OPERATION_SERVICE_SURFACE,
)
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

FinanceSharedServiceClassification = Literal[
    "move-now",
    "keep-shared-behind-neutral-seam",
    "wrapped-by-finance-factory",
]


@dataclass(frozen=True, slots=True)
class FinanceSharedServiceOwnership:
    service_name: str
    module_path: str
    classification: FinanceSharedServiceClassification
    surface: str
    rationale: str


_SHARED_NEUTRAL_GATE_RATIONALE = (
    "Finance behavior uses shared service implementations behind neutral extension gates; "
    "construction is supplied through finance-owned factories and every direct entrypoint "
    "blocks when the extension is disabled."
)

FINANCE_SHARED_SERVICE_OWNERSHIP_MAP: tuple[FinanceSharedServiceOwnership, ...] = (
    FinanceSharedServiceOwnership(
        "MarketDataService",
        "app.services.market_data_service",
        "keep-shared-behind-neutral-seam",
        MARKET_DATA_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "PositionService",
        "app.services.position_service",
        "keep-shared-behind-neutral-seam",
        POSITION_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "PortfolioService",
        "app.services.portfolio_service",
        "keep-shared-behind-neutral-seam",
        PORTFOLIO_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "BalanceService",
        "app.services.balance_service",
        "keep-shared-behind-neutral-seam",
        BALANCE_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TradingOperationService",
        "app.services.trading_operation_service",
        "keep-shared-behind-neutral-seam",
        TRADING_OPERATION_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "CsvImportService",
        "app.services.csv_import_service",
        "keep-shared-behind-neutral-seam",
        CSV_IMPORT_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TextTemplateService",
        "app.services.text_template_service",
        "keep-shared-behind-neutral-seam",
        TEXT_TEMPLATE_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "ReportService",
        "app.services.report_service",
        "keep-shared-behind-neutral-seam",
        REPORT_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "TemplateCompilerService",
        "app.services.template_compiler_service",
        "keep-shared-behind-neutral-seam",
        TEMPLATE_COMPILER_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "MemoryReportService",
        "app.services.memory_report_service",
        "keep-shared-behind-neutral-seam",
        MEMORY_REPORT_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "ReflectionService",
        "app.services.reflection_service",
        "keep-shared-behind-neutral-seam",
        REFLECTION_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
    ),
    FinanceSharedServiceOwnership(
        "ReturnResolutionService",
        "app.services.return_resolution_service",
        "keep-shared-behind-neutral-seam",
        RETURN_RESOLUTION_SERVICE_SURFACE,
        _SHARED_NEUTRAL_GATE_RATIONALE,
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
    "FINANCE_SHARED_SERVICE_OWNERSHIP_MAP",
    "FinanceSharedServiceClassification",
    "FinanceSharedServiceOwnership",
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
