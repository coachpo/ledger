from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.extension_service import ExtensionStateSnapshot

TEMPLATE_COMPILER_SURFACE = "service.template_compiler"
REPORT_SERVICE_SURFACE = "service.report"
MEMORY_SERVICE_SURFACE = "service.memory"
MEMORY_REPORT_SERVICE_SURFACE = "service.memory_report"
MEMORY_CONTEXT_SERVICE_SURFACE = "service.memory_context"
REPORT_BACKED_MEMORY_STORE_SURFACE = "service.report_backed_memory_store"
RETURN_RESOLUTION_SERVICE_SURFACE = "service.return_resolution"
REFLECTION_SERVICE_SURFACE = "service.reflection"
MEMORY_FOLLOW_UP_SERVICE_SURFACE = "service.memory_follow_up"


@dataclass(frozen=True, slots=True)
class FinanceWorkspaceTemplateReportMemoryHookRegistration:
    key: str
    surface: str
    summary: str


FINANCE_WORKSPACE_TEMPLATE_REPORT_MEMORY_HOOKS = (
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="template_compiler",
        surface=TEMPLATE_COMPILER_SURFACE,
        summary="Template placeholders and report embeds are finance workspace behavior.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="report_service",
        surface=REPORT_SERVICE_SURFACE,
        summary="Report CRUD, generation, filters, and download lookup are finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="memory_service",
        surface=MEMORY_SERVICE_SURFACE,
        summary="Report-backed memory lifecycle access is finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="memory_report_service",
        surface=MEMORY_REPORT_SERVICE_SURFACE,
        summary="Agent-memory report compatibility writes are finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="memory_context_service",
        surface=MEMORY_CONTEXT_SERVICE_SURFACE,
        summary="Report-backed memory prompt reinjection is finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="report_backed_memory_store",
        surface=REPORT_BACKED_MEMORY_STORE_SURFACE,
        summary="The phase-1 report-backed memory store is finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="return_resolution_service",
        surface=RETURN_RESOLUTION_SERVICE_SURFACE,
        summary="Outcome return resolution for finance memory is finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="reflection_service",
        surface=REFLECTION_SERVICE_SURFACE,
        summary="Resolved-memory reflection automation is finance-owned.",
    ),
    FinanceWorkspaceTemplateReportMemoryHookRegistration(
        key="memory_follow_up_service",
        surface=MEMORY_FOLLOW_UP_SERVICE_SURFACE,
        summary="Scheduled memory follow-up automation is finance-owned.",
    ),
)


def require_finance_workspace_enabled(
    session: Session,
    *,
    surface: str,
) -> ExtensionStateSnapshot:
    from app.services.extension_service import ExtensionService

    return ExtensionService(session).require_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        surface=surface,
    )


def register() -> tuple[FinanceWorkspaceTemplateReportMemoryHookRegistration, ...]:
    return FINANCE_WORKSPACE_TEMPLATE_REPORT_MEMORY_HOOKS


__all__ = [
    "FINANCE_WORKSPACE_TEMPLATE_REPORT_MEMORY_HOOKS",
    "MEMORY_CONTEXT_SERVICE_SURFACE",
    "MEMORY_FOLLOW_UP_SERVICE_SURFACE",
    "MEMORY_REPORT_SERVICE_SURFACE",
    "MEMORY_SERVICE_SURFACE",
    "REFLECTION_SERVICE_SURFACE",
    "REPORT_BACKED_MEMORY_STORE_SURFACE",
    "REPORT_SERVICE_SURFACE",
    "RETURN_RESOLUTION_SERVICE_SURFACE",
    "TEMPLATE_COMPILER_SURFACE",
    "FinanceWorkspaceTemplateReportMemoryHookRegistration",
    "register",
    "require_finance_workspace_enabled",
]
