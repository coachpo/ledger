from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.services.extension_service import ExtensionService, ExtensionStateSnapshot

FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance"

PORTFOLIO_SERVICE_SURFACE = "service.portfolio"
BALANCE_SERVICE_SURFACE = "service.balance"
POSITION_SERVICE_SURFACE = "service.position"
TRADING_OPERATION_SERVICE_SURFACE = "service.trading_operation"
CSV_IMPORT_SERVICE_SURFACE = "service.csv_import"
MARKET_DATA_SERVICE_SURFACE = "service.market_data"
TEXT_TEMPLATE_SERVICE_SURFACE = "service.text_template"
TEMPLATE_COMPILER_SURFACE = "service.template_compiler"
REPORT_SERVICE_SURFACE = "service.report"
MEMORY_SERVICE_SURFACE = "service.memory"
MEMORY_REPORT_SERVICE_SURFACE = "service.memory_report"
MEMORY_CONTEXT_SERVICE_SURFACE = "service.memory_context"
RETURN_RESOLUTION_SERVICE_SURFACE = "service.return_resolution"
REFLECTION_SERVICE_SURFACE = "service.reflection"


class ExtensionGate(Protocol):
    def require_enabled(
        self,
        extension_key: str,
        *,
        surface: str,
    ) -> ExtensionStateSnapshot: ...


def require_extension_enabled(
    session: Session,
    *,
    extension_key: str,
    surface: str,
) -> ExtensionStateSnapshot:
    return ExtensionService(session).require_enabled(extension_key, surface=surface)


def require_finance_workspace_enabled(
    session: Session,
    *,
    surface: str,
) -> ExtensionStateSnapshot:
    return require_extension_enabled(
        session,
        extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
        surface=surface,
    )


__all__ = [
    "BALANCE_SERVICE_SURFACE",
    "CSV_IMPORT_SERVICE_SURFACE",
    "ExtensionGate",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "MARKET_DATA_SERVICE_SURFACE",
    "MEMORY_CONTEXT_SERVICE_SURFACE",
    "MEMORY_REPORT_SERVICE_SURFACE",
    "MEMORY_SERVICE_SURFACE",
    "PORTFOLIO_SERVICE_SURFACE",
    "POSITION_SERVICE_SURFACE",
    "REFLECTION_SERVICE_SURFACE",
    "REPORT_SERVICE_SURFACE",
    "RETURN_RESOLUTION_SERVICE_SURFACE",
    "TEMPLATE_COMPILER_SURFACE",
    "TEXT_TEMPLATE_SERVICE_SURFACE",
    "TRADING_OPERATION_SERVICE_SURFACE",
    "require_extension_enabled",
    "require_finance_workspace_enabled",
]
