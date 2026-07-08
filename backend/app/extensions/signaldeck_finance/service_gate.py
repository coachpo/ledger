from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY

if TYPE_CHECKING:
    from app.services.extension_service import ResolvedExtensionState

MARKET_DATA_SERVICE_SURFACE = "service.market_data"
TEXT_TEMPLATE_SERVICE_SURFACE = "service.text_template"
TEMPLATE_COMPILER_SURFACE = "service.template_compiler"
REPORT_SERVICE_SURFACE = "service.report"


def require_finance_workspace_enabled(
    session: Session,
    *,
    surface: str,
) -> ResolvedExtensionState:
    from app.services.extension_gate import require_extension_enabled

    return require_extension_enabled(
        session,
        extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
        surface=surface,
    )


__all__ = [
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "MARKET_DATA_SERVICE_SURFACE",
    "REPORT_SERVICE_SURFACE",
    "TEMPLATE_COMPILER_SURFACE",
    "TEXT_TEMPLATE_SERVICE_SURFACE",
    "require_finance_workspace_enabled",
]
