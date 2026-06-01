from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.memory import MemoryArtifactRead
from app.schemas.model_connection import ModelConnectionCompatibilityResolution


class RunStatus(str, Enum):  # noqa: UP042
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunQueueState(str, Enum):  # noqa: UP042
    WAITING = "waiting"
    BLOCKED = "blocked"


class RunQueueReason(str, Enum):  # noqa: UP042
    AWAITING_WORKER_CAPACITY = "awaiting-worker-capacity"
    BLOCKED_BY_PACKAGE_SERIAL_POLICY = "blocked-by-package-serial-policy"


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


class RunMemoryEventType(str, Enum):  # noqa: UP042
    RETRIEVED = "retrieved"
    INJECTED = "injected"
    WRITTEN = "written"
    REUSED = "reused"
    SUPERSEDED = "superseded"
    REVIEWED = "reviewed"
    FAILED = "failed"


_MEMORY_EVENT_FORBIDDEN_KEYS = frozenset(
    {
        "auditlinks",
        "downloadurl",
        "report",
        "reportid",
        "reportname",
        "reports",
        "reportslug",
        "url",
    }
)
_MEMORY_EVENT_SECRET_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "secretpayload",
    "token",
)
_MEMORY_EVENT_FORBIDDEN_TEXT_FRAGMENTS = (
    "# agent memory",
    "/api/v1/reports",
    "/reports/",
    "auditlinks",
    "download",
    "reportid",
    "reportname",
    "reportslug",
    "secretpayload",
)
_MEMORY_EVENT_REDACTED_TEXT = "[redacted]"


def _normalized_memory_event_key(value: object) -> str:
    return str(value).replace("_", "").replace("-", "").lower()


def _is_forbidden_memory_event_key(value: object) -> bool:
    normalized = _normalized_memory_event_key(value)
    if normalized in _MEMORY_EVENT_FORBIDDEN_KEYS:
        return True
    return any(fragment in normalized for fragment in _MEMORY_EVENT_SECRET_KEY_FRAGMENTS)


def _redact_memory_event_text(value: str) -> str:
    normalized = value.lower()
    if any(fragment in normalized for fragment in _MEMORY_EVENT_FORBIDDEN_TEXT_FRAGMENTS):
        return _MEMORY_EVENT_REDACTED_TEXT
    return value


def _redact_memory_event_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _redact_memory_event_payload(item)
            for key, item in value.items()
            if not _is_forbidden_memory_event_key(key)
        }
    if isinstance(value, list):
        return [_redact_memory_event_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_memory_event_text(value)
    return value


def _read_schema_payload(
    value: Any,
    *,
    field_names: tuple[str, ...],
    extra_names: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, dict):
        return dict(value)

    data: dict[str, Any] = {}
    for name in (*field_names, *extra_names):
        try:
            data[name] = getattr(value, name)
        except AttributeError:
            continue
    if data:
        return data
    return value


def _payload_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _payload_has(data: dict[str, Any], *keys: str) -> bool:
    return any(key in data for key in keys)


def _drop_payload_keys(data: dict[str, Any], *keys: str) -> None:
    for key in keys:
        data.pop(key, None)


def _payload_resource_scope(data: dict[str, Any]) -> RunInvocationResourceScope:
    value = _payload_value(data, "identityScope", "identity_scope")
    if value is None:
        return RunInvocationResourceScope.GLOBAL
    if isinstance(value, RunInvocationResourceScope):
        return value
    return RunInvocationResourceScope(str(value))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _scoped_resource_ref_from_payload(
    data: dict[str, Any],
    *,
    id_keys: tuple[str, ...],
    key_keys: tuple[str, ...],
    version_keys: tuple[str, ...],
) -> dict[str, object]:
    identifier = _payload_value(data, *id_keys)
    if identifier is None:
        return {}

    key = _payload_value(data, *key_keys)
    return _scoped_resource_ref(
        scope=_payload_resource_scope(data),
        identifier=int(identifier),
        key=None if key is None else str(key),
        version=_optional_int(_payload_value(data, *version_keys)),
    )


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
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_version: int = Field(ge=1)
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

    @model_validator(mode="before")
    @classmethod
    def populate_scoped_refs(cls, value: Any) -> Any:
        data = _read_schema_payload(
            value,
            field_names=tuple(cls.model_fields),
            extra_names=(
                "agent_id",
                "output_schema_id",
                "identity_scope",
                "output_schema_key",
            ),
        )
        if not isinstance(data, dict):
            return value

        if not _payload_has(data, "agentRef", "agent_ref"):
            data["agentRef"] = _scoped_resource_ref_from_payload(
                data,
                id_keys=("agentId", "agent_id"),
                key_keys=("agentKey", "agent_key"),
                version_keys=("agentVersion", "agent_version"),
            )
        if not _payload_has(data, "outputSchemaRef", "output_schema_ref"):
            data["outputSchemaRef"] = _scoped_resource_ref_from_payload(
                data,
                id_keys=("outputSchemaId", "output_schema_id"),
                key_keys=("outputSchemaKey", "output_schema_key"),
                version_keys=("outputSchemaVersion", "output_schema_version"),
            )
        _drop_payload_keys(
            data,
            "agentId",
            "agent_id",
            "outputSchemaId",
            "output_schema_id",
            "identityScope",
            "identity_scope",
            "outputSchemaKey",
            "output_schema_key",
        )
        return data

    @model_validator(mode="after")
    def require_scoped_refs(self) -> Self:
        if not self.agent_ref:
            raise ValueError("agentRef is required")
        if not self.output_schema_ref:
            raise ValueError("outputSchemaRef is required")
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
    output_schema_version: int = Field(ge=1)
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

    @model_validator(mode="before")
    @classmethod
    def populate_scoped_refs(cls, value: Any) -> Any:
        data = _read_schema_payload(
            value,
            field_names=tuple(cls.model_fields),
            extra_names=("output_schema_id", "identity_scope", "output_schema_key"),
        )
        if not isinstance(data, dict):
            return value

        if not _payload_has(data, "outputSchemaRef", "output_schema_ref"):
            data["outputSchemaRef"] = _scoped_resource_ref_from_payload(
                data,
                id_keys=("outputSchemaId", "output_schema_id"),
                key_keys=("outputSchemaKey", "output_schema_key"),
                version_keys=("outputSchemaVersion", "output_schema_version"),
            )
        _drop_payload_keys(
            data,
            "outputSchemaId",
            "output_schema_id",
            "identityScope",
            "identity_scope",
            "outputSchemaKey",
            "output_schema_key",
        )
        return data

    @model_validator(mode="after")
    def require_scoped_ref(self) -> Self:
        if not self.output_schema_ref:
            raise ValueError("outputSchemaRef is required")
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

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RunProgressRead(CamelModel):
    unit: Literal["invocation"]
    terminal_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    percent: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def require_consistent_counts(self) -> Self:
        if self.terminal_count > self.total_count:
            raise ValueError("terminalCount cannot exceed totalCount")
        return self


class RunQueueRead(CamelModel):
    state: RunQueueState
    reason: RunQueueReason
    message: str
    blocking_run_id: int | None = None


class RunListItemRead(CamelModel):
    id: int
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    status: RunStatus
    progress: RunProgressRead
    queue: RunQueueRead | None = None
    schedule_id: int | None = None
    schedule_fire_id: int | None = None
    scheduled_for: datetime | None = None
    schedule_reason: Literal["scheduled", "manual"] | None = None
    workflow_key: str | None = None
    total_tokens: int = Field(ge=0)
    trace_id: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @field_validator("scheduled_for", "queued_at", "started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RunListRead(CamelModel):
    items: list[RunListItemRead]


class RunMemoryArtifactRead(MemoryArtifactRead):
    pass


class RunMemoryEventRead(CamelModel):
    id: int
    run_id: int
    run_step_id: int | None = None
    run_agent_invocation_id: int | None = None
    run_operation_invocation_id: int | None = None
    step_id: str | None = None
    invocation_id: str | None = None
    event_type: RunMemoryEventType
    memory_id: str | None = None
    revision_id: str | None = None
    retrieval_mode: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    excerpt: str | None = None
    injected_text: str | None = None
    result_snapshot: dict[str, Any] = Field(default_factory=dict)
    status_snapshot: dict[str, Any] = Field(default_factory=dict)
    trace_span_id: str | None = None
    created_at: datetime

    @field_validator("filters", "budget", "result_snapshot", "status_snapshot", mode="before")
    @classmethod
    def redact_snapshots(cls, value: Any) -> dict[str, Any]:
        redacted = _redact_memory_event_payload({} if value is None else value)
        if isinstance(redacted, dict):
            return redacted
        return {}

    @field_validator("excerpt", "injected_text", mode="before")
    @classmethod
    def redact_text_snapshots(cls, value: object) -> str | None:
        if value is None:
            return None
        return _redact_memory_event_text(str(value))

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RunPackageLocalResourceRefsRead(CamelModel):
    agents: list[str] = Field(default_factory=list)
    output_schemas: list[str] = Field(default_factory=list)
    capability_profiles: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)


RunPackageResolvedModelConnectionRead = ModelConnectionCompatibilityResolution


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
    resolved_model_connections: list[ModelConnectionCompatibilityResolution] = Field(
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
    progress: RunProgressRead
    queue: RunQueueRead | None = None
    schedule_id: int | None = None
    schedule_fire_id: int | None = None
    scheduled_for: datetime | None = None
    schedule_reason: Literal["scheduled", "manual"] | None = None
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
    memory_events: list[RunMemoryEventRead] = Field(default_factory=list)
    extension_dependencies: list[RunExtensionDependencyRead] = Field(default_factory=list)
    package_provenance: RunPackageProvenanceRead | None = None

    @model_validator(mode="after")
    def require_workflow_package_snapshot_provenance(self) -> Self:
        if self.target_kind == RunTargetKind.WORKFLOW_PACKAGE and self.package_provenance is None:
            raise ValueError(
                "workflow package runs require run-owned executable snapshot provenance"
            )
        return self

    @field_validator(
        "scheduled_for",
        "queued_at",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    )
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
    ready: bool
    blocking_errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    package_provenance: RunPackageProvenanceRead | None = None


class RunRerunCreateRequest(CamelModel):
    parameters: dict[str, object]


class RunForkDraftRead(CamelModel):
    source_run_id: int
    source_invocation_id: int = Field(ge=1)
    target_kind: RunTargetKind
    target_id: int
    target_key: str
    invocation_input: dict[str, object]
    ready: bool
    blocking_errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    package_provenance: RunPackageProvenanceRead | None = None


class RunForkCreateRequest(CamelModel):
    source_invocation_id: int = Field(ge=1)
    invocation_input: dict[str, object]


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
    "RunMemoryEventRead",
    "RunMemoryEventType",
    "RunCurrentPackageAuditRead",
    "RunPackageLaunchSnapshotRead",
    "RunPackageLocalResourceRefsRead",
    "RunPackagePreflightSummaryRead",
    "RunPackageProvenanceRead",
    "RunPackageResolvedModelConnectionRead",
    "RunProgressRead",
    "RunQueueRead",
    "RunQueueReason",
    "RunQueueState",
    "RunRead",
    "RunRerunCreateRequest",
    "RunRerunDraftRead",
    "RunForkCreateRequest",
    "RunForkDraftRead",
    "RunStatus",
    "RunStepOrigin",
    "RunStepRead",
    "RunStepStatus",
    "RunTargetKind",
]
