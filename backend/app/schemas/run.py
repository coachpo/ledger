from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.memory import MemoryArtifactRead
from app.schemas.model_connection import ModelConnectionKind


class RunStatus(str, Enum):  # noqa: UP042
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunStepStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStepOrigin(str, Enum):  # noqa: UP042
    PLANNED = "planned"
    COPIED = "copied"


class RunInvocationInputMode(str, Enum):  # noqa: UP042
    PASSTHROUGH = "passthrough"
    WIRED = "wired"


class RunInvocationResolvedInputOrigin(str, Enum):  # noqa: UP042
    DERIVED = "derived"
    EDITED = "edited"
    COPIED = "copied"
    PASSTHROUGH = "passthrough"


class RunInvocationOutputOrigin(str, Enum):  # noqa: UP042
    EXECUTED = "executed"
    EDITED = "edited"
    COPIED = "copied"


class RunInvocationResourceScope(str, Enum):  # noqa: UP042
    GLOBAL = "global"
    PACKAGE_LOCAL = "packageLocal"


def _scoped_resource_ref(
    *,
    scope: RunInvocationResourceScope,
    identifier: int,
    key: str | None = None,
    version: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"scope": scope.value}
    if scope == RunInvocationResourceScope.PACKAGE_LOCAL:
        payload["localId"] = identifier
    else:
        payload["id"] = identifier
    if key:
        payload["key"] = key
    if version is not None:
        payload["version"] = version
    return payload


class RunOperationKind(str, Enum):  # noqa: UP042
    HTTP = "http"


class RunTargetKind(str, Enum):  # noqa: UP042
    AGENT = "agent"
    WORKFLOW = "workflow"
    WORKFLOW_PACKAGE = "workflowPackage"


def _coerce_legacy_target_identity(value: Any) -> Any:
    if not isinstance(value, dict):
        return value

    data = dict(value)
    legacy_keys = (
        "workflowId",
        "workflowKey",
        "workflowVersion",
        "workflow_id",
        "workflow_key",
        "workflow_version",
    )
    has_legacy_identity = any(legacy_key in data for legacy_key in legacy_keys)
    legacy_pairs = (
        ("workflowId", "targetId"),
        ("workflowKey", "targetKey"),
        ("workflow_id", "target_id"),
        ("workflow_key", "target_key"),
    )
    for legacy_key, target_key in legacy_pairs:
        if target_key not in data and legacy_key in data:
            data[target_key] = data[legacy_key]
        data.pop(legacy_key, None)
    data.pop("workflowVersion", None)
    data.pop("workflow_version", None)

    has_target_kind = "targetKind" in data or "target_kind" in data
    if not has_target_kind and has_legacy_identity:
        data["targetKind"] = RunTargetKind.WORKFLOW.value
    return data


class RunAgentErrorRead(CamelModel):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class RunAgentInvocationRead(CamelModel):
    id: int
    run_step_id: int
    run_id: int
    step_index: int = Field(ge=1)
    slot: str
    position: int = Field(ge=0)
    agent_ref: dict[str, object] = Field(default_factory=dict)
    output_schema_ref: dict[str, object] = Field(default_factory=dict)
    agent_id: int = Field(
        description="Transitional compatibility field; prefer agentRef for scoped identity.",
        json_schema_extra={"deprecated": True},
    )
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int = Field(
        description="Transitional compatibility field; prefer outputSchemaRef for scoped identity.",
        json_schema_extra={"deprecated": True},
    )
    output_schema_version: int = Field(ge=1)
    identity_scope: RunInvocationResourceScope = Field(
        default=RunInvocationResourceScope.GLOBAL,
        exclude=True,
    )
    output_schema_key: str | None = Field(default=None, exclude=True)
    input_mode: RunInvocationInputMode
    wiring: dict[str, Any] = Field(default_factory=dict)
    graph_metadata: dict[str, Any] | None = None
    optional: bool
    status: RunStepStatus
    resolved_input: dict[str, Any] = Field(default_factory=dict)
    resolved_input_origin: RunInvocationResolvedInputOrigin
    output: Any | None = None
    output_origin: RunInvocationOutputOrigin | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: list[dict[str, Any]] = Field(default_factory=list)
    tokens: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    trace_span_id: str | None = None
    source_invocation_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    persisted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def populate_scoped_refs(self) -> Self:
        if not self.agent_ref:
            self.agent_ref = _scoped_resource_ref(
                scope=self.identity_scope,
                identifier=self.agent_id,
                key=self.agent_key,
                version=self.agent_version,
            )
        if not self.output_schema_ref:
            self.output_schema_ref = _scoped_resource_ref(
                scope=self.identity_scope,
                identifier=self.output_schema_id,
                key=self.output_schema_key,
                version=self.output_schema_version,
            )
        return self

    @field_validator("started_at", "finished_at", "persisted_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunOperationInvocationRead(CamelModel):
    id: int
    run_step_id: int
    run_id: int
    step_index: int = Field(ge=1)
    slot: str
    position: int = Field(ge=0)
    operation_key: str
    operation_kind: RunOperationKind
    output_schema_ref: dict[str, object] = Field(default_factory=dict)
    output_schema_id: int = Field(
        ge=1,
        description="Transitional compatibility field; prefer outputSchemaRef for scoped identity.",
        json_schema_extra={"deprecated": True},
    )
    output_schema_version: int = Field(ge=1)
    identity_scope: RunInvocationResourceScope = Field(
        default=RunInvocationResourceScope.GLOBAL,
        exclude=True,
    )
    output_schema_key: str | None = Field(default=None, exclude=True)
    method: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1)
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    response_metadata: dict[str, Any] = Field(default_factory=dict)
    graph_metadata: dict[str, Any] | None = None
    optional: bool
    status: RunStepStatus
    output: Any | None = None
    output_origin: RunInvocationOutputOrigin | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_details: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    trace_span_id: str | None = None
    source_operation_invocation_id: int | None = None
    source_run_id: int | None = None
    source_run_step_id: int | None = None
    source_step_index: int | None = Field(default=None, ge=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    persisted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def populate_scoped_refs(self) -> Self:
        if not self.output_schema_ref:
            self.output_schema_ref = _scoped_resource_ref(
                scope=self.identity_scope,
                identifier=self.output_schema_id,
                key=self.output_schema_key,
                version=self.output_schema_version,
            )
        return self

    @field_validator("started_at", "finished_at", "persisted_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunStepRead(CamelModel):
    id: int
    run_id: int
    index: int = Field(ge=1)
    status: RunStepStatus
    origin: RunStepOrigin
    source_run_step_id: int | None = None
    source_run_id: int | None = None
    source_step_index: int | None = Field(default=None, ge=1)
    graph_metadata: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    persisted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    invocations: list[RunAgentInvocationRead] = Field(default_factory=list)
    operation_invocations: list[RunOperationInvocationRead] = Field(default_factory=list)

    @field_validator("started_at", "finished_at", "persisted_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunCreatedRead(CamelModel):
    id: int
    status: RunStatus
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    trace_id: str | None = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RunListItemRead(CamelModel):
    id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    status: RunStatus
    total_tokens: int = Field(ge=0)
    trace_id: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @field_validator("queued_at", "started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunListRead(CamelModel):
    items: list[RunListItemRead]


class RunMemoryArtifactRead(MemoryArtifactRead):
    pass


class RunPackageLocalResourceRefsRead(CamelModel):
    agents: list[str] = Field(default_factory=list)
    output_schemas: list[str] = Field(default_factory=list)
    capability_profiles: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)


class RunPackageResolvedModelConnectionRead(CamelModel):
    key: str
    name: str
    connection_kind: ModelConnectionKind
    base_url: str
    model_id: str
    reasoning_effort: str | None = None
    api_style: str
    timeout_seconds: int = Field(ge=1)
    has_api_key: bool


class RunPackagePreflightSummaryRead(CamelModel):
    ready: bool
    blocking_errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class RunPackageLaunchSnapshotRead(CamelModel):
    workflow_key: str
    workflow_name: str
    workflow_description: str
    input_schema: dict[str, Any]
    parameters: dict[str, Any]


class RunCurrentPackageAuditRead(CamelModel):
    available: bool
    status: str | None = None
    manifest_hash: str | None = None
    compiled_hash: str | None = None
    manifest_hash_matches_snapshot: bool | None = None
    compiled_hash_matches_snapshot: bool | None = None
    unavailable_reason: str | None = None


class RunExtensionDependencyRead(CamelModel):
    extension_key: str
    surfaces: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class RunPackageProvenanceRead(CamelModel):
    workflow_package_id: int
    workflow_package_key: str
    workflow_package_name: str
    workflow_package_description: str
    workflow_package_status: str | None = None
    workflow_package_manifest_hash: str
    workflow_package_compiled_hash: str
    workflow_key: str
    workflow_name: str
    workflow_description: str
    manifest_source: str
    package_definition: dict[str, Any]
    compiled_plan: dict[str, Any]
    launch_snapshot: RunPackageLaunchSnapshotRead | None = None
    extension_dependencies: list[RunExtensionDependencyRead] = Field(default_factory=list)
    local_resource_refs: RunPackageLocalResourceRefsRead
    resolved_model_connections: list[RunPackageResolvedModelConnectionRead] = Field(
        default_factory=list
    )
    preflight_summary: RunPackagePreflightSummaryRead | None = None
    current_package: RunCurrentPackageAuditRead | None = None


class RunRead(CamelModel):
    id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    input: dict[str, Any]
    source_run_id: int | None = None
    lineage_root_run_id: int | None = None
    replay_step_index: int | None = Field(default=None, ge=1)
    resume_step_index: int = Field(ge=1)
    final_output: Any | None = None
    status: RunStatus
    total_tokens: int = Field(ge=0)
    inherited_tokens: int = Field(ge=0)
    executed_tokens: int = Field(ge=0)
    trace_id: str | None = None
    error: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[RunStepRead] = Field(default_factory=list)
    memory_artifacts: list[RunMemoryArtifactRead] = Field(default_factory=list)
    extension_dependencies: list[RunExtensionDependencyRead] = Field(default_factory=list)
    package_provenance: RunPackageProvenanceRead | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_target_identity(cls, value: Any) -> Any:
        return _coerce_legacy_target_identity(value)

    @model_validator(mode="after")
    def require_workflow_package_snapshot_provenance(self) -> Self:
        if self.target_kind == RunTargetKind.WORKFLOW_PACKAGE and self.package_provenance is None:
            raise ValueError(
                "workflow package runs require run-owned executable snapshot provenance"
            )
        return self

    @field_validator("queued_at", "started_at", "finished_at", "created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunRerunDraftRead(CamelModel):
    source_run_id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    parameters: dict[str, object]
    package_provenance: RunPackageProvenanceRead | None = None


class RunRerunCreateRequest(CamelModel):
    parameters: dict[str, object]


class RunStepReplayDraftRead(CamelModel):
    source_run_id: int
    replay_step_index: int = Field(ge=1)
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    parameters: dict[str, object]
    package_provenance: RunPackageProvenanceRead | None = None


class RunStepReplayCreateRequest(CamelModel):
    replay_step_index: int = Field(ge=1)
    parameters: dict[str, object]


__all__ = [
    "RunAgentErrorRead",
    "RunAgentInvocationRead",
    "RunCreatedRead",
    "RunExtensionDependencyRead",
    "RunInvocationInputMode",
    "RunInvocationOutputOrigin",
    "RunInvocationResolvedInputOrigin",
    "RunInvocationResourceScope",
    "RunListItemRead",
    "RunOperationInvocationRead",
    "RunOperationKind",
    "RunListRead",
    "RunMemoryArtifactRead",
    "RunCurrentPackageAuditRead",
    "RunPackageLaunchSnapshotRead",
    "RunPackageLocalResourceRefsRead",
    "RunPackagePreflightSummaryRead",
    "RunPackageProvenanceRead",
    "RunPackageResolvedModelConnectionRead",
    "RunRead",
    "RunRerunCreateRequest",
    "RunRerunDraftRead",
    "RunStepReplayCreateRequest",
    "RunStepReplayDraftRead",
    "RunStatus",
    "RunStepOrigin",
    "RunStepRead",
    "RunStepStatus",
    "RunTargetKind",
]
