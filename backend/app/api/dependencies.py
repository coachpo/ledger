# pyright: reportMissingImports=false
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.core.errors import ApiError
from app.db.session import get_db_session, get_session_factory
from app.services.execution_providers import ExecutionProviderBundle
from app.services.extension_service import ExtensionService, ResolvedExtensionState
from app.services.memory_service import MemoryService
from app.services.model_connection_probe_service import ModelConnectionProbeService
from app.services.model_connection_service import ModelConnectionService
from app.services.quote_provider import QuoteProvider
from app.services.run_service import RunService
from app.services.workflow_package_runtime_input_registry import (
    WorkflowPackageRuntimeInputRegistryService,
)
from app.services.workflow_package_service import WorkflowPackageService


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


def get_memory_service(
    session: Annotated[Session, Depends(get_session)],
) -> MemoryService:
    return MemoryService(session)


def require_extension_enabled(
    *,
    extension_key: str,
    surface: str,
) -> Callable[[ExtensionService], ResolvedExtensionState]:
    def dependency(
        service: Annotated[ExtensionService, Depends(get_extension_service)],
    ) -> ResolvedExtensionState:
        return service.require_enabled(extension_key, surface=surface)

    return dependency


def get_execution_provider_bundle(
    extension_service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> ExecutionProviderBundle:
    return extension_service.get_execution_provider_bundle()


def get_quote_provider(
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
) -> QuoteProvider:
    provider = provider_bundle.quote_provider or provider_bundle.fallback_quote_provider
    if provider is None:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="quote_provider_unavailable",
            message="No quote provider is available for the enabled extensions.",
        )
    return provider


def get_model_connection_service(
    session: Annotated[Session, Depends(get_session)],
) -> ModelConnectionService:
    return ModelConnectionService(session)


def get_model_connection_probe_service(
    session: Annotated[Session, Depends(get_session)],
) -> ModelConnectionProbeService:
    return ModelConnectionProbeService(session)


def get_workflow_package_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
) -> WorkflowPackageService:
    return WorkflowPackageService(
        session,
        get_session_factory(),
        provider_bundle=provider_bundle,
        tool_catalog=tool_catalog,
    )


def get_workflow_package_runtime_input_registry_service(
    session: Annotated[Session, Depends(get_session)],
) -> WorkflowPackageRuntimeInputRegistryService:
    return WorkflowPackageRuntimeInputRegistryService(session)


def get_run_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
) -> RunService:
    return RunService(session, get_session_factory(), provider_bundle=provider_bundle)


__all__ = [
    "get_execution_provider_bundle",
    "get_extension_service",
    "get_memory_service",
    "get_model_connection_probe_service",
    "get_model_connection_service",
    "get_quote_provider",
    "get_run_service",
    "get_session",
    "get_tool_catalog",
    "get_workflow_package_runtime_input_registry_service",
    "get_workflow_package_service",
    "require_extension_enabled",
]
