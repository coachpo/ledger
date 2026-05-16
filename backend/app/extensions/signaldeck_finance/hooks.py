from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEMPLATE_COMPILER_SURFACE = "service.template_compiler"
REPORT_SERVICE_SURFACE = "service.report"
MEMORY_SERVICE_SURFACE = "service.memory"
MEMORY_REPORT_SERVICE_SURFACE = "service.memory_report"
MEMORY_CONTEXT_SERVICE_SURFACE = "service.memory_context"
REPORT_BACKED_MEMORY_STORE_SURFACE = "service.report_backed_memory_store"
RETURN_RESOLUTION_SERVICE_SURFACE = "service.return_resolution"
REFLECTION_SERVICE_SURFACE = "service.reflection"
MEMORY_FOLLOW_UP_SERVICE_SURFACE = "service.memory_follow_up"


class _ExtensionServiceProtocol(Protocol):
    def require_enabled(self, extension_key: str, *, surface: str) -> object: ...


class _ExtensionServiceFactoryProtocol(Protocol):
    def __call__(self, session: Session) -> _ExtensionServiceProtocol: ...


def require_finance_workspace_enabled(
    session: Session,
    *,
    surface: str,
) -> object:
    service_module = import_module("app.services.extension_service")
    raw_service_factory = cast(object, getattr(service_module, "ExtensionService", None))
    if not callable(raw_service_factory):
        raise RuntimeError("ExtensionService is not available")
    service_factory = cast(_ExtensionServiceFactoryProtocol, raw_service_factory)
    return service_factory(session).require_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        surface=surface,
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
    "require_finance_workspace_enabled",
]
