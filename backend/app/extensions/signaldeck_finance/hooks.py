from __future__ import annotations

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.extensions.signaldeck_finance.provider_factories import create_deterministic_quote_provider
from app.services.extension_gate import (
    MEMORY_CONTEXT_SERVICE_SURFACE,
    MEMORY_FOLLOW_UP_SERVICE_SURFACE,
    MEMORY_REPORT_SERVICE_SURFACE,
    MEMORY_SERVICE_SURFACE,
    REFLECTION_SERVICE_SURFACE,
    REPORT_BACKED_MEMORY_STORE_SURFACE,
    REPORT_SERVICE_SURFACE,
    RETURN_RESOLUTION_SERVICE_SURFACE,
    TEMPLATE_COMPILER_SURFACE,
    require_finance_workspace_enabled,
)
from app.services.market_data_service import MarketDataService
from app.services.memory_follow_up_service import MemoryFollowUpService
from app.services.run_lifecycle import ExtensionRunLifecycleHooks, WorkflowPackageStartContext


def run_memory_follow_up_on_workflow_package_start(
    context: WorkflowPackageStartContext,
) -> None:
    quote_provider = (
        context.provider_bundle.quote_provider
        or context.provider_bundle.fallback_quote_provider
        or create_deterministic_quote_provider()
    )
    _ = MemoryFollowUpService(
        context.session,
        MarketDataService(session=context.session, quote_provider=quote_provider),
    ).run_due(context.now)


def register_run_lifecycle_hooks() -> tuple[ExtensionRunLifecycleHooks, ...]:
    return (
        ExtensionRunLifecycleHooks(
            extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
            on_workflow_package_start=run_memory_follow_up_on_workflow_package_start,
        ),
    )


__all__ = [
    "MEMORY_CONTEXT_SERVICE_SURFACE",
    "MEMORY_FOLLOW_UP_SERVICE_SURFACE",
    "MEMORY_REPORT_SERVICE_SURFACE",
    "MEMORY_SERVICE_SURFACE",
    "REFLECTION_SERVICE_SURFACE",
    "REPORT_BACKED_MEMORY_STORE_SURFACE",
    "REPORT_SERVICE_SURFACE",
    "RETURN_RESOLUTION_SERVICE_SURFACE",
    "TEMPLATE_COMPILER_SURFACE",
    "register_run_lifecycle_hooks",
    "require_finance_workspace_enabled",
    "run_memory_follow_up_on_workflow_package_start",
]
