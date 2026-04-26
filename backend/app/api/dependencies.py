from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents import SkillRegistry, get_default_skill_registry
from app.agents.mcp import DefaultMcpConnectionTester, McpConnectionTester
from app.core.config import get_settings
from app.db.session import get_db_session, get_session_factory
from app.services.agent_service import AgentService
from app.services.balance_service import BalanceService
from app.services.csv_import_service import CsvImportService
from app.services.market_data_service import MarketDataService
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_service import OutputSchemaService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import (
    DeterministicQuoteProvider,
    QuoteProvider,
    YahooFinanceQuoteProvider,
)
from app.services.report_service import ReportService
from app.services.reset_seed_service import ResetSeedService
from app.services.run_service import RunService
from app.services.skill_service import SkillService
from app.services.template_compiler_service import TemplateCompilerService
from app.services.text_template_service import TextTemplateService
from app.services.trading_operation_service import TradingOperationService
from app.services.workflow_service import WorkflowService


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
    if settings.quote_provider_backend == "deterministic":
        return DeterministicQuoteProvider()
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


def get_reset_seed_service() -> ResetSeedService:
    return ResetSeedService()


def get_skill_registry() -> SkillRegistry:
    return get_default_skill_registry()


def get_skill_service(
    session: Annotated[Session, Depends(get_session)],
    skill_registry: Annotated[SkillRegistry, Depends(get_skill_registry)],
) -> SkillService:
    return SkillService(session, skill_registry)


def get_mcp_connection_tester() -> McpConnectionTester:
    return DefaultMcpConnectionTester()


def get_mcp_server_service(
    session: Annotated[Session, Depends(get_session)],
    connection_tester: Annotated[McpConnectionTester, Depends(get_mcp_connection_tester)],
) -> McpServerService:
    return McpServerService(session, connection_tester)


def get_model_connection_service(
    session: Annotated[Session, Depends(get_session)],
) -> ModelConnectionService:
    return ModelConnectionService(session)


def get_output_schema_service(
    session: Annotated[Session, Depends(get_session)],
) -> OutputSchemaService:
    return OutputSchemaService(session)


def get_agent_service(
    session: Annotated[Session, Depends(get_session)],
    skill_registry: Annotated[SkillRegistry, Depends(get_skill_registry)],
    connection_tester: Annotated[McpConnectionTester, Depends(get_mcp_connection_tester)],
) -> AgentService:
    return AgentService(session, skill_registry, connection_tester)


def get_workflow_service(
    session: Annotated[Session, Depends(get_session)],
) -> WorkflowService:
    return WorkflowService(session)


def get_run_service(
    session: Annotated[Session, Depends(get_session)],
) -> RunService:
    return RunService(session, get_session_factory())


def get_template_compiler_service(
    session: Annotated[Session, Depends(get_session)],
    market_data_service: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> TemplateCompilerService:
    return TemplateCompilerService(session, market_data_service)
