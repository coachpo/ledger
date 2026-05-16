# pyright: reportMissingImports=false
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.agents.mcp import DefaultMcpConnectionTester, McpConnectionTester
from app.db.session import get_db_session, get_session_factory
from app.extensions.signaldeck_finance.dependencies import (
    get_balance_service as get_balance_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_csv_import_service as get_csv_import_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_market_data_service as get_market_data_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_portfolio_service as get_portfolio_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_position_service as get_position_service,
)
from app.extensions.signaldeck_finance.dependencies import get_quote_provider as get_quote_provider
from app.extensions.signaldeck_finance.dependencies import get_report_service as get_report_service
from app.extensions.signaldeck_finance.dependencies import (
    get_template_compiler_service as get_template_compiler_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_text_template_service as get_text_template_service,
)
from app.extensions.signaldeck_finance.dependencies import (
    get_trading_operation_service as get_trading_operation_service,
)
from app.services.agent_service import AgentService
from app.services.capability_service import CapabilityService
from app.services.extension_service import ExtensionService, ExtensionStateSnapshot
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_service import OutputSchemaService
from app.services.quote_provider import QuoteProvider
from app.services.run_service import RunService
from app.services.workflow_package_service import WorkflowPackageService
from app.services.workflow_service import WorkflowService


def get_session() -> Iterator[Session]:
    yield from get_db_session()


def get_tool_catalog(
    session: Annotated[Session, Depends(get_session)],
) -> ToolCatalog:
    return ExtensionService(session).get_tool_catalog()


def get_extension_service(
    session: Annotated[Session, Depends(get_session)],
) -> ExtensionService:
    return ExtensionService(session)


def require_extension_enabled(
    *,
    extension_key: str,
    surface: str,
) -> Callable[[ExtensionService], ExtensionStateSnapshot]:
    def dependency(
        service: Annotated[ExtensionService, Depends(get_extension_service)],
    ) -> ExtensionStateSnapshot:
        return service.require_enabled(extension_key, surface=surface)

    return dependency


def get_capability_service(
    session: Annotated[Session, Depends(get_session)],
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
) -> CapabilityService:
    return CapabilityService(session, tool_catalog)


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
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
    connection_tester: Annotated[McpConnectionTester, Depends(get_mcp_connection_tester)],
) -> AgentService:
    return AgentService(session, tool_catalog, connection_tester)


def get_workflow_service(
    session: Annotated[Session, Depends(get_session)],
) -> WorkflowService:
    return WorkflowService(session)


def get_workflow_package_service(
    session: Annotated[Session, Depends(get_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
) -> WorkflowPackageService:
    return WorkflowPackageService(
        session,
        get_session_factory(),
        quote_provider=quote_provider,
        tool_catalog=tool_catalog,
    )


def get_run_service(
    session: Annotated[Session, Depends(get_session)],
    quote_provider: Annotated[QuoteProvider, Depends(get_quote_provider)],
) -> RunService:
    return RunService(session, get_session_factory(), quote_provider=quote_provider)


__all__ = [
    "get_agent_service",
    "get_balance_service",
    "get_capability_service",
    "get_csv_import_service",
    "get_extension_service",
    "get_market_data_service",
    "get_mcp_connection_tester",
    "get_mcp_server_service",
    "get_model_connection_service",
    "get_output_schema_service",
    "get_portfolio_service",
    "get_position_service",
    "get_quote_provider",
    "get_report_service",
    "get_run_service",
    "get_session",
    "get_template_compiler_service",
    "get_text_template_service",
    "get_tool_catalog",
    "get_trading_operation_service",
    "get_workflow_package_service",
    "get_workflow_service",
    "require_extension_enabled",
]
