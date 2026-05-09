# pyright: reportExplicitAny=false
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.workflow import WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH
from app.schemas.workflow_package_manifest import WorkflowPackageManifestDiagnostic


class WorkflowPackageStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    ACTIVE = "active"


class WorkflowPackageImportMode(str, Enum):  # noqa: UP042
    CREATE = "create"
    CREATE_VERSION = "createVersion"


def _validate_manifest_source(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("manifestSource must be a string")
    if not value.strip():
        raise ValueError("manifestSource is required")
    if len(value) > WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH:
        raise ValueError(
            f"manifestSource must be at most {WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH} characters"
        )
    return value


class WorkflowPackageManifestRequest(CamelModel):
    manifest_source: str

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str:
        return _validate_manifest_source(value)


class WorkflowPackageUpdateRequest(CamelModel):
    manifest_source: str | None = None
    status: WorkflowPackageStatus | None = None

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str | None:
        if value is None:
            return None
        return _validate_manifest_source(value)


class WorkflowPackageImportRequest(WorkflowPackageManifestRequest):
    mode: WorkflowPackageImportMode = WorkflowPackageImportMode.CREATE


class WorkflowPackageMetadataRead(CamelModel):
    api_version: str
    key: str
    name: str
    description: str


class WorkflowPackageValidationRead(CamelModel):
    diagnostics: list[WorkflowPackageManifestDiagnostic]
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    metadata: WorkflowPackageMetadataRead | None = None
    package_definition: dict[str, Any] | None = None
    compiled_plan: dict[str, Any] | None = None
    manifest_hash: str | None = None
    compiled_hash: str | None = None


class WorkflowPackageRead(CamelModel):
    id: int
    key: str
    name: str
    description: str
    status: WorkflowPackageStatus
    latest_version: int | None = None
    latest_version_id: int | None = None
    manifest_hash: str | None = None
    compiled_hash: str | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowPackageListRead(CamelModel):
    items: list[WorkflowPackageRead]


class WorkflowPackageVersionRead(CamelModel):
    id: int
    package_id: int
    version: int = Field(ge=1)
    manifest_hash: str
    compiled_hash: str
    validation_summary: dict[str, Any]
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    launched_at: datetime | None = None

    @field_validator("created_at", "launched_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class WorkflowPackageVersionListRead(CamelModel):
    items: list[WorkflowPackageVersionRead]


class WorkflowPackageLaunchRead(CamelModel):
    package_id: int
    package_key: str
    package_version: int = Field(ge=1)
    manifest_hash: str
    workflow_key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    ready: bool
    blocking_errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowPackageLaunchCreateRequest(CamelModel):
    version: int | None = Field(default=None, ge=1)
    workflow_key: str | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class WorkflowPackageLaunchCreateResponse(CamelModel):
    id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    workflow_package_id: int
    workflow_package_key: str
    workflow_package_version: int = Field(ge=1)
    workflow_key: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


__all__ = [
    "WorkflowPackageImportMode",
    "WorkflowPackageImportRequest",
    "WorkflowPackageLaunchCreateRequest",
    "WorkflowPackageLaunchCreateResponse",
    "WorkflowPackageLaunchRead",
    "WorkflowPackageListRead",
    "WorkflowPackageManifestRequest",
    "WorkflowPackageMetadataRead",
    "WorkflowPackageRead",
    "WorkflowPackageStatus",
    "WorkflowPackageUpdateRequest",
    "WorkflowPackageValidationRead",
    "WorkflowPackageVersionListRead",
    "WorkflowPackageVersionRead",
]
