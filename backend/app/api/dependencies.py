from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session, get_session_factory
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.agent_spec_service import AgentSpecService
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.backtest_service import BacktestService
from app.services.balance_service import BalanceService
from app.services.capability_registry_service import CapabilityRegistryService
from app.services.csv_import_service import CsvImportService
from app.services.market_data_service import MarketDataService
from app.services.orchestration_service import OrchestrationService
from app.services.persona_profile_service import PersonaProfileService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import QuoteProvider, YahooFinanceQuoteProvider
from app.services.report_service import ReportService
from app.services.runtime_control_service import RuntimeControlService
from app.services.studio_query_service import StudioQueryService
from app.services.template_compiler_service import TemplateCompilerService
from app.services.text_template_service import TextTemplateService
from app.services.trading_operation_service import TradingOperationService
from app.services.tryout_service import TryoutService
from app.services.workflow_spec_service import WorkflowSpecService


def get_session() -> Iterator[Session]:
    yield from get_db_session()


def get_portfolio_service(
    session: Annotated[Session, Depends(get_session)],
) -> PortfolioService:
    return PortfolioService(session)


def get_balance_service(
    session: Annotated[Session, Depends(get_session)],
) -> BalanceService:
    return BalanceService(session)


def get_quote_provider() -> QuoteProvider:
    settings = get_settings()
    return YahooFinanceQuoteProvider(timeout=settings.quote_provider_timeout_seconds)


def get_position_service(
    session: Annotated[Session, Depends(get_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> PositionService:
    return PositionService(session, quote_provider)


def get_csv_import_service(
    session: Annotated[Session, Depends(get_session)],
) -> CsvImportService:
    return CsvImportService(session)


def get_trading_operation_service(
    session: Annotated[Session, Depends(get_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> TradingOperationService:
    return TradingOperationService(session, quote_provider)


def get_market_data_service(
    session: Annotated[Session, Depends(get_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> MarketDataService:
    return MarketDataService(session=session, quote_provider=quote_provider)


def get_text_template_service(
    session: Annotated[Session, Depends(get_session)],
) -> TextTemplateService:
    return TextTemplateService(session)


def get_report_service(
    session: Annotated[Session, Depends(get_session)],
) -> ReportService:
    return ReportService(session)


def get_orchestration_service(
    session: Annotated[Session, Depends(get_session)],
) -> OrchestrationService:
    return OrchestrationService(session)


def get_persona_profile_service(
    session: Annotated[Session, Depends(get_session)],
) -> PersonaProfileService:
    return PersonaProfileService(session)


def get_agent_spec_service(
    session: Annotated[Session, Depends(get_session)],
) -> AgentSpecService:
    return AgentSpecService(session)


def get_workflow_spec_service(
    session: Annotated[Session, Depends(get_session)],
) -> WorkflowSpecService:
    return WorkflowSpecService(session)


def get_capability_registry_service(
    session: Annotated[Session, Depends(get_session)],
) -> CapabilityRegistryService:
    return CapabilityRegistryService(session)


def get_agent_runtime_service(
    session: Annotated[Session, Depends(get_session)],
) -> AgentRuntimeService:
    return AgentRuntimeService(session, get_session_factory())


def get_studio_query_service(
    session: Annotated[Session, Depends(get_session)],
) -> StudioQueryService:
    return StudioQueryService(session)


def get_tryout_service(
    session: Annotated[Session, Depends(get_session)],
) -> TryoutService:
    return TryoutService(session)


def get_backtest_service(
    session: Annotated[Session, Depends(get_session)],
) -> BacktestService:
    return BacktestService(session, get_session_factory())


def get_backtest_cycle_service(
    session: Annotated[Session, Depends(get_session)],
) -> BacktestCycleService:
    return BacktestCycleService(session, get_session_factory())


def get_runtime_control_service(
    session: Annotated[Session, Depends(get_session)],
) -> RuntimeControlService:
    return RuntimeControlService(session)


def get_template_compiler_service(
    session: Annotated[Session, Depends(get_session)],
    market_data_service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> TemplateCompilerService:
    return TemplateCompilerService(session, market_data_service)
