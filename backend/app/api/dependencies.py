# pyright: reportMissingImports=false
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.db.session import get_db_session, get_session_factory
from app.services.execution_providers import ExecutionProviderBundle
from app.services.extension_service import ExtensionService, ResolvedExtensionState
from app.services.model_connection_probe_service import ModelConnectionProbeService
from app.services.model_connection_service import ModelConnectionService
from app.services.run_service import RunService
from app.services.workflow_package_preflight import WorkflowPackagePreflightService
from app.services.workflow_package_schedule_service import WorkflowPackageScheduleService
from app.services.workflow_package_service import WorkflowPackageService


def get_session() -> Iterator[Session]:
    yield from get_db_session()


def get_extension_service(
    session: Annotated[Session, Depends(get_session)],
) -> ExtensionService:
    from app.services.extension_service import ExtensionService

    return ExtensionService(session)


def get_tool_catalog(
    extension_service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> ToolCatalog:
    return extension_service.get_tool_catalog()


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


def get_model_connection_service(
    session: Annotated[Session, Depends(get_session)],
) -> ModelConnectionService:
    from app.services.model_connection_service import ModelConnectionService

    return ModelConnectionService(session)


def get_model_connection_probe_service(
    session: Annotated[Session, Depends(get_session)],
) -> ModelConnectionProbeService:
    return ModelConnectionProbeService(session)


def get_workflow_package_preflight_service(
    session: Annotated[Session, Depends(get_session)],
    extension_service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> WorkflowPackagePreflightService:
    from app.services.workflow_package_preflight import WorkflowPackagePreflightService

    return WorkflowPackagePreflightService(session, extension_service=extension_service)


def get_run_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
    preflight_service: Annotated[
        WorkflowPackagePreflightService,
        Depends(get_workflow_package_preflight_service),
    ],
    extension_service: Annotated[ExtensionService, Depends(get_extension_service)],
) -> RunService:
    from app.services.run_service import RunService

    return RunService(
        session,
        get_session_factory(),
        provider_bundle=provider_bundle,
        preflight_service=preflight_service,
        extension_service=extension_service,
    )


def get_workflow_package_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
    tool_catalog: Annotated[ToolCatalog, Depends(get_tool_catalog)],
    preflight_service: Annotated[
        WorkflowPackagePreflightService,
        Depends(get_workflow_package_preflight_service),
    ],
    run_service: Annotated[RunService, Depends(get_run_service)],
) -> WorkflowPackageService:
    return WorkflowPackageService(
        session,
        get_session_factory(),
        provider_bundle=provider_bundle,
        tool_catalog=tool_catalog,
        run_service=run_service,
        preflight_service=preflight_service,
    )


def get_workflow_package_schedule_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
    run_service: Annotated[RunService, Depends(get_run_service)],
) -> WorkflowPackageScheduleService:
    from app.services.workflow_package_schedule_service import WorkflowPackageScheduleService

    return WorkflowPackageScheduleService(
        session,
        get_session_factory(),
        provider_bundle=provider_bundle,
        run_service=run_service,
    )


__all__ = [
    "get_execution_provider_bundle",
    "get_extension_service",
    "get_model_connection_probe_service",
    "get_model_connection_service",
    "get_run_service",
    "get_session",
    "get_tool_catalog",
    "get_workflow_package_preflight_service",
    "get_workflow_package_schedule_service",
    "get_workflow_package_service",
    "require_extension_enabled",
]
