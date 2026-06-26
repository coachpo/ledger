# pyright: reportExplicitAny=false
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.model_connection import ModelConnectionRuntimeProfile
from app.schemas.workflow_package_manifest import WorkflowPackageManifestDiagnostic

_SECRET_BINDING_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
MANIFEST_SOURCE_MAX_LENGTH = 262_144


def normalize_workflow_package_secret_binding_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Secret binding key must be a string")
    normalized = value.strip()
    if _SECRET_BINDING_KEY_RE.fullmatch(normalized) is None:
        raise ValueError(
            "Secret binding key must start with a lowercase letter and use only "
            + "lowercase letters, numbers, and underscores"
        )
    return normalized


def _validate_manifest_source(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("manifestSource must be a string")
    if not value.strip():
        raise ValueError("manifestSource is required")
    if len(value) > MANIFEST_SOURCE_MAX_LENGTH:
        raise ValueError(f"manifestSource must be at most {MANIFEST_SOURCE_MAX_LENGTH} characters")
    return value


class WorkflowPackageManifestRequest(CamelModel):
    manifest_source: str

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str:
        return _validate_manifest_source(value)


class WorkflowPackageUpdateRequest(CamelModel):
    manifest_source: str | None = None

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str | None:
        if value is None:
            return None
        return _validate_manifest_source(value)


class WorkflowPackageImportRequest(WorkflowPackageManifestRequest):
    pass


class WorkflowPackageMetadataRead(CamelModel):
    api_version: Literal["signaldeck.workflowPackage/v1"]
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


class WorkflowPackageManifestRead(CamelModel):
    package_id: int
    package_key: str
    manifest_source: str
    package_definition: dict[str, Any]
    manifest_hash: str
    compiled_hash: str


class WorkflowPackageSecretBindingRead(CamelModel):
    package_id: int
    key: str
    has_value: bool = Field(alias="hasValue")
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowPackageSecretBindingListRead(CamelModel):
    items: list[WorkflowPackageSecretBindingRead]


class WorkflowPackageSecretBindingUpdateRequest(CamelModel):
    value: str = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Secret binding value must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Secret binding value is required")
        return normalized


class WorkflowPackageRead(CamelModel):
    id: int
    key: str
    name: str
    description: str
    manifest_hash: str | None = None
    compiled_hash: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowPackageListRead(CamelModel):
    items: list[WorkflowPackageRead]


class WorkflowPackageLaunchRead(CamelModel):
    package_id: int
    package_key: str
    manifest_hash: str
    workflow_key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    ready: bool
    blocking_errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    resolved_model_connections: list[ModelConnectionRuntimeProfile] = Field(default_factory=list)


class WorkflowPackageRuntimeInputStaleRead(CamelModel):
    stale: bool
    reasons: list[dict[str, str | None]] = Field(default_factory=list)


class WorkflowPackageRuntimeInputCurrentMetadataRead(CamelModel):
    workflow_key: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema: dict[str, Any]


class WorkflowPackageRuntimeInputEntryRead(CamelModel):
    id: int
    package_id: int
    workflow_key: str
    slot: Literal["history", "preset"]
    name: str | None = None
    payload: dict[str, Any]
    source_kind: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema_snapshot: dict[str, Any] | None = None
    source_run_id: int | None = None
    stale: WorkflowPackageRuntimeInputStaleRead
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowPackageRuntimeInputRegistryRead(CamelModel):
    package_id: int
    package_key: str
    workflow_key: str
    current_metadata: WorkflowPackageRuntimeInputCurrentMetadataRead | None = None
    presets: list[WorkflowPackageRuntimeInputEntryRead]
    history: list[WorkflowPackageRuntimeInputEntryRead]


class WorkflowPackageRuntimeInputPresetEntryCreateRequest(CamelModel):
    name: object | None = None
    payload: object


class WorkflowPackageRuntimeInputPresetEntryUpdateRequest(CamelModel):
    name: object | None = None
    payload: object | None = None


class WorkflowPackagePreflightRequest(CamelModel):
    workflow_key: str | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class WorkflowPackageLaunchCreateRequest(CamelModel):
    workflow_key: str | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class WorkflowPackageLaunchCreateResponse(CamelModel):
    id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    workflow_package_id: int
    workflow_package_key: str
    workflow_key: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


__all__ = [
    "WorkflowPackageImportRequest",
    "WorkflowPackageLaunchCreateRequest",
    "WorkflowPackageLaunchCreateResponse",
    "WorkflowPackageLaunchRead",
    "WorkflowPackageListRead",
    "WorkflowPackageManifestRead",
    "WorkflowPackageManifestRequest",
    "WorkflowPackageMetadataRead",
    "WorkflowPackagePreflightRequest",
    "WorkflowPackageRead",
    "WorkflowPackageRuntimeInputCurrentMetadataRead",
    "WorkflowPackageRuntimeInputEntryRead",
    "WorkflowPackageRuntimeInputPresetEntryCreateRequest",
    "WorkflowPackageRuntimeInputPresetEntryUpdateRequest",
    "WorkflowPackageRuntimeInputRegistryRead",
    "WorkflowPackageRuntimeInputStaleRead",
    "WorkflowPackageSecretBindingListRead",
    "WorkflowPackageSecretBindingRead",
    "WorkflowPackageSecretBindingUpdateRequest",
    "WorkflowPackageUpdateRequest",
    "WorkflowPackageValidationRead",
    "normalize_workflow_package_secret_binding_key",
]
