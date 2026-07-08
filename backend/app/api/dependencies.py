# pyright: reportMissingImports=false
from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents import ToolCatalog
from app.db.session import get_db_session, get_session_factory
from app.extensions.registry import build_execution_provider_bundle
from app.services.execution_providers import ExecutionProviderBundle
from app.services.model_connection_probe_service import ModelConnectionProbeService
from app.services.model_connection_service import ModelConnectionService
from app.services.run_service import RunService
from app.services.workflow_package_preflight import WorkflowPackagePreflightService
from app.services.workflow_package_schedule_service import WorkflowPackageScheduleService
from app.services.workflow_package_service import WorkflowPackageService


def get_session() -> Iterator[Session]:
    yield from get_db_session()


def get_tool_catalog() -> ToolCatalog:
    return ToolCatalog()


def get_execution_provider_bundle() -> ExecutionProviderBundle:
    return build_execution_provider_bundle()


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
) -> WorkflowPackagePreflightService:
    from app.services.workflow_package_preflight import WorkflowPackagePreflightService

    return WorkflowPackagePreflightService(session)


def get_run_service(
    session: Annotated[Session, Depends(get_session)],
    provider_bundle: Annotated[ExecutionProviderBundle, Depends(get_execution_provider_bundle)],
    preflight_service: Annotated[
        WorkflowPackagePreflightService,
        Depends(get_workflow_package_preflight_service),
    ],
) -> RunService:
    from app.services.run_service import RunService

    return RunService(
        session,
        get_session_factory(),
        provider_bundle=provider_bundle,
        preflight_service=preflight_service,
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
    "get_model_connection_probe_service",
    "get_model_connection_service",
    "get_run_service",
    "get_session",
    "get_tool_catalog",
    "get_workflow_package_preflight_service",
    "get_workflow_package_schedule_service",
    "get_workflow_package_service",
]
