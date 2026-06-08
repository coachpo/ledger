from __future__ import annotations

from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.services.extension_gate import require_extension_enabled
from app.services.extension_service import ResolvedExtensionState

PORTFOLIO_SERVICE_SURFACE = "service.portfolio"
BALANCE_SERVICE_SURFACE = "service.balance"
POSITION_SERVICE_SURFACE = "service.position"
TRADING_OPERATION_SERVICE_SURFACE = "service.trading_operation"
CSV_IMPORT_SERVICE_SURFACE = "service.csv_import"
MARKET_DATA_SERVICE_SURFACE = "service.market_data"
TEXT_TEMPLATE_SERVICE_SURFACE = "service.text_template"
TEMPLATE_COMPILER_SURFACE = "service.template_compiler"
REPORT_SERVICE_SURFACE = "service.report"
MEMORY_REPORT_SERVICE_SURFACE = "service.memory_report"
RETURN_RESOLUTION_SERVICE_SURFACE = "service.return_resolution"
REFLECTION_SERVICE_SURFACE = "service.reflection"


def require_finance_workspace_enabled(
    session: Session,
    *,
    surface: str,
) -> ResolvedExtensionState:
    return require_extension_enabled(
        session,
        extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
        surface=surface,
    )


__all__ = [
    "BALANCE_SERVICE_SURFACE",
    "CSV_IMPORT_SERVICE_SURFACE",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "MARKET_DATA_SERVICE_SURFACE",
    "MEMORY_REPORT_SERVICE_SURFACE",
    "PORTFOLIO_SERVICE_SURFACE",
    "POSITION_SERVICE_SURFACE",
    "REFLECTION_SERVICE_SURFACE",
    "REPORT_SERVICE_SURFACE",
    "RETURN_RESOLUTION_SERVICE_SURFACE",
    "TEMPLATE_COMPILER_SURFACE",
    "TEXT_TEMPLATE_SERVICE_SURFACE",
    "TRADING_OPERATION_SERVICE_SURFACE",
    "require_finance_workspace_enabled",
]
