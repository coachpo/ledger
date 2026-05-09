# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingImports=false
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_workflow_package_service
from app.schemas.workflow_package import (
    WorkflowPackageImportRequest,
    WorkflowPackageLaunchCreateRequest,
    WorkflowPackageLaunchCreateResponse,
    WorkflowPackageLaunchRead,
    WorkflowPackageListRead,
    WorkflowPackageManifestRequest,
    WorkflowPackageRead,
    WorkflowPackageStatus,
    WorkflowPackageUpdateRequest,
    WorkflowPackageValidationRead,
    WorkflowPackageVersionListRead,
)
from app.services.workflow_package_service import WorkflowPackageService

router = APIRouter(prefix="/workflow-packages", tags=["workflow-packages"])


@router.get("", response_model=WorkflowPackageListRead)
def list_workflow_packages(
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
    status_filter: Annotated[WorkflowPackageStatus | None, Query(alias="status")] = None,
) -> WorkflowPackageListRead:
    return service.list_packages(status_filter=status_filter)


@router.post("", response_model=WorkflowPackageRead, status_code=status.HTTP_201_CREATED)
def create_workflow_package(
    payload: WorkflowPackageManifestRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageRead:
    return service.create_package(payload)


@router.post("/validate-manifest", response_model=WorkflowPackageValidationRead)
def validate_workflow_package_manifest(
    payload: WorkflowPackageManifestRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageValidationRead:
    return service.validate_manifest(payload)


@router.post("/import", response_model=WorkflowPackageRead, status_code=status.HTTP_201_CREATED)
def import_workflow_package(
    payload: WorkflowPackageImportRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageRead:
    return service.import_package(payload)


@router.get("/{package_id}", response_model=WorkflowPackageRead)
def get_workflow_package(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageRead:
    return service.get_package(package_id)


@router.patch("/{package_id}", response_model=WorkflowPackageRead)
def update_workflow_package(
    package_id: int,
    payload: WorkflowPackageUpdateRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageRead:
    return service.update_package(package_id, payload)


@router.delete(
    "/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_workflow_package(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> Response:
    service.delete_package(package_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{package_id}/versions", response_model=WorkflowPackageVersionListRead)
def list_workflow_package_versions(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageVersionListRead:
    return service.list_versions(package_id)


@router.post("/{package_id}/versions", response_model=WorkflowPackageRead)
def create_workflow_package_version(
    package_id: int,
    payload: WorkflowPackageManifestRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageRead:
    return service.create_version(package_id, payload)


@router.get("/{package_id}/export", response_model=None)
def export_workflow_package(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    return service.export_package(package_id, version=version)


@router.post("/{package_id}/preflight", response_model=WorkflowPackageLaunchRead)
def preflight_workflow_package(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
    version: Annotated[int | None, Query(ge=1)] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
) -> WorkflowPackageLaunchRead:
    return service.preflight_package(package_id, version=version, workflow_key=workflow_key)


@router.get("/{package_id}/launch", response_model=WorkflowPackageLaunchRead)
def get_workflow_package_launch(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
    version: Annotated[int | None, Query(ge=1)] = None,
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
) -> WorkflowPackageLaunchRead:
    return service.get_launch(package_id, version=version, workflow_key=workflow_key)


@router.post(
    "/{package_id}/launches",
    response_model=WorkflowPackageLaunchCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_package_launch(
    package_id: int,
    payload: WorkflowPackageLaunchCreateRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageLaunchCreateResponse:
    return service.create_launch(package_id, payload)
