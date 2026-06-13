# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingImports=false
from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies import (
    get_workflow_package_runtime_input_registry_service,
    get_workflow_package_service,
)
from app.core.errors import validation_error
from app.schemas.workflow_package import (
    WorkflowPackageImportRequest,
    WorkflowPackageLaunchCreateRequest,
    WorkflowPackageLaunchCreateResponse,
    WorkflowPackageLaunchRead,
    WorkflowPackageListRead,
    WorkflowPackageManifestRead,
    WorkflowPackageManifestRequest,
    WorkflowPackagePreflightRequest,
    WorkflowPackageRead,
    WorkflowPackageRuntimeInputEntryRead,
    WorkflowPackageRuntimeInputPresetEntryCreateRequest,
    WorkflowPackageRuntimeInputPresetEntryUpdateRequest,
    WorkflowPackageRuntimeInputRegistryRead,
    WorkflowPackageSecretBindingListRead,
    WorkflowPackageSecretBindingRead,
    WorkflowPackageSecretBindingUpdateRequest,
    WorkflowPackageUpdateRequest,
    WorkflowPackageValidationRead,
)
from app.services.workflow_package_runtime_input_registry import (
    WorkflowPackageRuntimeInputRegistryService,
)
from app.services.workflow_package_service import WorkflowPackageService


def reject_removed_version_query(request: Request) -> None:
    if "version" not in request.query_params:
        return
    raise validation_error(
        "Workflow package request validation failed",
        [
            {
                "field": "version",
                "issue": "Workflow package version selection is no longer supported",
            }
        ],
    )


def reject_removed_status_query(request: Request) -> None:
    if "status" not in request.query_params:
        return
    raise validation_error(
        "Workflow package request validation failed",
        [
            {
                "field": "status",
                "issue": "Workflow package status filtering is no longer supported",
            }
        ],
    )


router = APIRouter(
    prefix="/workflow-packages",
    tags=["workflow-packages"],
    dependencies=[Depends(reject_removed_version_query)],
)


@router.get(
    "",
    response_model=WorkflowPackageListRead,
    dependencies=[Depends(reject_removed_status_query)],
)
def list_workflow_packages(
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageListRead:
    return service.list_packages()


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


@router.get(
    "/{package_id}/secret-bindings",
    response_model=WorkflowPackageSecretBindingListRead,
)
def list_workflow_package_secret_bindings(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageSecretBindingListRead:
    return service.list_secret_bindings(package_id)


@router.put(
    "/{package_id}/secret-bindings/{key}",
    response_model=WorkflowPackageSecretBindingRead,
)
def upsert_workflow_package_secret_binding(
    package_id: int,
    key: str,
    payload: WorkflowPackageSecretBindingUpdateRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageSecretBindingRead:
    return service.upsert_secret_binding(package_id, key, payload)


@router.delete(
    "/{package_id}/secret-bindings/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_workflow_package_secret_binding(
    package_id: int,
    key: str,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> Response:
    service.delete_secret_binding(package_id, key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{package_id}/runtime-input-registry",
    response_model=WorkflowPackageRuntimeInputRegistryRead,
)
def list_workflow_package_runtime_input_registry(
    package_id: int,
    workflow_key: Annotated[str, Query(alias="workflowKey")],
    service: Annotated[
        WorkflowPackageRuntimeInputRegistryService,
        Depends(get_workflow_package_runtime_input_registry_service),
    ],
) -> WorkflowPackageRuntimeInputRegistryRead:
    registry = service.list_registry(package_id, workflow_key)
    return WorkflowPackageRuntimeInputRegistryRead.model_validate(registry)


@router.post(
    "/{package_id}/runtime-input-registry/presets",
    response_model=WorkflowPackageRuntimeInputEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workflow_package_runtime_input_preset_entry(
    package_id: int,
    workflow_key: Annotated[str, Query(alias="workflowKey")],
    payload: WorkflowPackageRuntimeInputPresetEntryCreateRequest,
    service: Annotated[
        WorkflowPackageRuntimeInputRegistryService,
        Depends(get_workflow_package_runtime_input_registry_service),
    ],
) -> WorkflowPackageRuntimeInputEntryRead:
    entry = service.create_preset_entry(
        package_id,
        workflow_key,
        name=cast(str | None, payload.name),
        payload=payload.payload,
    )
    return WorkflowPackageRuntimeInputEntryRead.model_validate(entry)


@router.patch(
    "/{package_id}/runtime-input-registry/presets/{entry_id}",
    response_model=WorkflowPackageRuntimeInputEntryRead,
)
def update_workflow_package_runtime_input_preset_entry(
    package_id: int,
    entry_id: int,
    workflow_key: Annotated[str, Query(alias="workflowKey")],
    payload: WorkflowPackageRuntimeInputPresetEntryUpdateRequest,
    service: Annotated[
        WorkflowPackageRuntimeInputRegistryService,
        Depends(get_workflow_package_runtime_input_registry_service),
    ],
) -> WorkflowPackageRuntimeInputEntryRead:
    if "name" in payload.model_fields_set and "payload" in payload.model_fields_set:
        entry = service.update_preset_entry(
            package_id,
            workflow_key,
            entry_id,
            name=cast(str | None, payload.name),
            payload=payload.payload,
        )
    elif "name" in payload.model_fields_set:
        entry = service.update_preset_entry(
            package_id,
            workflow_key,
            entry_id,
            name=cast(str | None, payload.name),
        )
    elif "payload" in payload.model_fields_set:
        entry = service.update_preset_entry(
            package_id,
            workflow_key,
            entry_id,
            payload=payload.payload,
        )
    else:
        entry = service.update_preset_entry(package_id, workflow_key, entry_id)
    return WorkflowPackageRuntimeInputEntryRead.model_validate(entry)


@router.delete(
    "/{package_id}/runtime-input-registry/presets/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_workflow_package_runtime_input_preset_entry(
    package_id: int,
    entry_id: int,
    workflow_key: Annotated[str, Query(alias="workflowKey")],
    service: Annotated[
        WorkflowPackageRuntimeInputRegistryService,
        Depends(get_workflow_package_runtime_input_registry_service),
    ],
) -> Response:
    service.delete_preset_entry(package_id, workflow_key, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{package_id}/manifest", response_model=WorkflowPackageManifestRead)
def get_workflow_package_manifest(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageManifestRead:
    return service.get_manifest(package_id)


@router.get("/{package_id}/export", response_model=None)
def export_workflow_package(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> Response:
    return service.export_package(package_id)


@router.post("/{package_id}/preflight", response_model=WorkflowPackageLaunchRead)
def preflight_workflow_package(
    package_id: int,
    payload: WorkflowPackagePreflightRequest,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
) -> WorkflowPackageLaunchRead:
    return service.preflight_package(
        package_id,
        workflow_key=payload.workflow_key,
        parameters=payload.parameters,
    )


@router.get("/{package_id}/launch", response_model=WorkflowPackageLaunchRead)
def get_workflow_package_launch(
    package_id: int,
    service: Annotated[WorkflowPackageService, Depends(get_workflow_package_service)],
    workflow_key: Annotated[str | None, Query(alias="workflowKey")] = None,
) -> WorkflowPackageLaunchRead:
    return service.get_launch(package_id, workflow_key=workflow_key)


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
