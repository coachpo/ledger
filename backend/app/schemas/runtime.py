from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone, normalize_runtime_inputs


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


class SpecOrigin(StrEnum):
    SEEDED = "seeded"
    MANAGED = "managed"
    IMPORTED = "imported"


class SpecLifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class PersonaProfileKind(StrEnum):
    ROLE_TEMPLATE = "role_template"
    CHARACTER_PROFILE = "character_profile"
    BUILTIN_PROFILE = "builtin_profile"
    MANAGED_PERSONA = "managed_persona"


class CapabilityType(StrEnum):
    TOOL = "tool"
    CONNECTOR = "connector"
    BUNDLE = "bundle"


class ApprovalMode(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"


class RuntimeCallerType(StrEnum):
    BACKTEST = "backtest"
    TRYOUT = "tryout"
    STUDIO = "studio"
    API = "api"


class RuntimeExecutionKind(StrEnum):
    WORKFLOW = "workflow"
    SINGLE_AGENT = "single_agent"


class RuntimeRunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RuntimeApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class RuntimeRetentionClass(StrEnum):
    EPHEMERAL = "ephemeral"
    PERSISTENT = "persistent"


class RuntimeTraceEventType(StrEnum):
    RUN_CREATED = "RUN_CREATED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    TOOL_CALLED = "TOOL_CALLED"
    TOOL_RETURNED = "TOOL_RETURNED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_EXPIRED = "RUN_EXPIRED"
    WARNING_EMITTED = "WARNING_EMITTED"


class RuntimeFlagChangeResult(StrEnum):
    APPLIED = "applied"
    REJECTED = "rejected"


class TraceSummary(CamelModel):
    event_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    last_event_at: datetime | None = None

    @field_validator("last_event_at")
    @classmethod
    def validate_last_event_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class ApprovalSummary(CamelModel):
    total_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    denied_count: int = Field(ge=0)
    expired_count: int = Field(ge=0)


class TerminalError(CamelModel):
    code: str
    message: str

    @field_validator("code", "message", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class PersonaProfileRef(CamelModel):
    persona_profile_key: str
    persona_profile_version: int | None = Field(default=None, ge=1)
    canonical_target_id: str | None = None
    persona_kind: PersonaProfileKind | None = None
    origin: SpecOrigin | None = None
    selection_source: str | None = None
    parent_persona_profile_ref: PersonaProfileRef | None = None
    legacy_source_version: int | None = Field(default=None, ge=1)

    @field_validator("persona_profile_key", mode="before")
    @classmethod
    def validate_persona_profile_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Persona profile key")

    @field_validator("canonical_target_id", "selection_source", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class CapabilityRef(CamelModel):
    capability_key: str
    capability_version: int | None = Field(default=None, ge=1)
    capability_type: CapabilityType | None = None
    selection_source: str | None = None
    effective_approval_mode: ApprovalMode | None = None
    effective_config: dict[str, Any] | None = None

    @field_validator("capability_key", mode="before")
    @classmethod
    def validate_capability_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Capability key")

    @field_validator("selection_source", mode="before")
    @classmethod
    def validate_selection_source(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class ResolvedCapabilityRead(CamelModel):
    capability_key: str
    capability_version: int = Field(ge=1)
    capability_type: CapabilityType
    approval_mode: ApprovalMode
    display_name: str | None = None
    transport: str | None = None
    lifecycle: str | None = None
    effective_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capability_key", mode="before")
    @classmethod
    def validate_capability_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Capability key")

    @field_validator("display_name", "transport", "lifecycle", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class WorkflowAgentRef(CamelModel):
    step_key: str
    agent_spec_key: str
    agent_spec_version: int = Field(ge=1)
    persona_profile_refs: list[PersonaProfileRef] = Field(default_factory=list)
    capability_refs: list[CapabilityRef] = Field(default_factory=list)

    @field_validator("step_key", "agent_spec_key", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class ResolvedBuiltinVersionRead(CamelModel):
    canonical_target_id: str
    handle: str
    revision: int = Field(ge=1)


class ResolvedRoleVersionRead(CamelModel):
    canonical_target_id: str
    role_id: int = Field(ge=1)
    version: int = Field(ge=1)


class ResolvedCharacterVersionRead(CamelModel):
    canonical_target_id: str
    character_id: int = Field(ge=1)
    version: int = Field(ge=1)


class ResolvedBundleVersionRead(CamelModel):
    bundle_key: str
    revision: int = Field(ge=1)


class ResolvedToolVersionRead(CamelModel):
    tool_id: str
    revision: int = Field(ge=1)


class ResolvedConnectorVersionRead(CamelModel):
    connector_id: str
    revision: int = Field(ge=1)


class ResolvedMentionRead(CamelModel):
    original_text: str
    source_handle: str
    canonical_target_id: str
    target_type: str
    mention_order: int = Field(ge=0)
    persona_profile_key: str
    persona_profile_version: int = Field(ge=1)
    legacy_role_id: int | None = None
    legacy_role_version: int | None = Field(default=None, ge=1)
    legacy_character_id: int | None = None
    legacy_character_version: int | None = Field(default=None, ge=1)

    @field_validator(
        "original_text",
        "source_handle",
        "canonical_target_id",
        "target_type",
        "persona_profile_key",
        mode="before",
    )
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class ApprovalDetailSummary(CamelModel):
    approval_mode: ApprovalMode | None = None
    display_name: str | None = None
    transport: str | None = None

    @field_validator("display_name", "transport", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)


class RuntimeRunCreate(CamelModel):
    caller_type: RuntimeCallerType
    caller_id: int | None = None
    caller_scope_key: str | None = None
    caller_identity_key: str | None = None
    execution_kind: RuntimeExecutionKind
    workflow_spec_key: str | None = None
    workflow_spec_version: int | None = Field(default=None, ge=1)
    agent_spec_key: str | None = None
    agent_spec_version: int | None = Field(default=None, ge=1)
    inputs: dict[str, str] = Field(default_factory=dict)
    persona_profile_refs: list[PersonaProfileRef] = Field(default_factory=list)
    persist_run: bool = True

    @field_validator("caller_scope_key", "caller_identity_key", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("workflow_spec_key", "agent_spec_key", mode="before")
    @classmethod
    def validate_optional_key(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_inputs(cls, value: object) -> dict[str, str]:
        return normalize_runtime_inputs(value)

    @model_validator(mode="after")
    def validate_target_fields(self) -> RuntimeRunCreate:
        if self.execution_kind == RuntimeExecutionKind.WORKFLOW:
            if not self.workflow_spec_key:
                raise ValueError("Workflow execution requires workflowSpecKey")
            if self.agent_spec_key is not None or self.agent_spec_version is not None:
                raise ValueError("Workflow execution cannot include agent spec fields")
        else:
            if not self.agent_spec_key:
                raise ValueError("Single-agent execution requires agentSpecKey")
            if self.workflow_spec_key is not None or self.workflow_spec_version is not None:
                raise ValueError("Single-agent execution cannot include workflow spec fields")
        return self


class RuntimeRunCreated(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId", "id"), ge=1)
    status: RuntimeRunStatus
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RuntimeRunListItem(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId", "id"), ge=1)
    status: RuntimeRunStatus
    caller_type: RuntimeCallerType
    caller_id: int | None = None
    caller_scope_key: str | None = None
    caller_identity_key: str | None = None
    execution_kind: RuntimeExecutionKind
    workflow_spec_key: str | None = None
    workflow_spec_version: int | None = None
    agent_spec_key: str | None = None
    agent_spec_version: int | None = None
    attempt_number: int = Field(ge=1)
    expires_at: datetime | None = None
    created_at: datetime

    @field_validator(
        "caller_scope_key",
        "caller_identity_key",
        "workflow_spec_key",
        "agent_spec_key",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("expires_at", "created_at")
    @classmethod
    def validate_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class RuntimeRunRead(RuntimeRunListItem):
    pending_approval_ids: list[int] = Field(default_factory=list)
    final_output: Any | None = None
    trace_summary: TraceSummary
    approval_summary: ApprovalSummary
    terminal_error_code: str | None = Field(default=None, exclude=True)
    terminal_error_message: str | None = Field(default=None, exclude=True)
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @computed_field
    def terminal_error(self) -> TerminalError | None:
        if self.terminal_error_code is None or self.terminal_error_message is None:
            return None
        return TerminalError(code=self.terminal_error_code, message=self.terminal_error_message)


class RuntimeRunListRead(CamelModel):
    items: list[RuntimeRunListItem]
    next_cursor: str | None = None


class RuntimeArtifactRead(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId", "id"), ge=1)
    final_output: Any | None = None
    terminal_error_code: str | None = Field(default=None, exclude=True)
    terminal_error_message: str | None = Field(default=None, exclude=True)
    report_markdown: str | None = None
    normalized_trade_decisions: list[dict[str, Any]] | None = None
    entry_prompt_hash: str
    full_user_prompt_hash: str
    authored_entry_prompt_body: str | None = None
    compiled_entry_prompt_body: str | None = None
    execution_context_body: str | None = None
    prompt_report_slug: str | None = None
    raw_mention_handles: list[str] = Field(default_factory=list)
    resolved_mentions: list[ResolvedMentionRead] = Field(default_factory=list)
    mentioned_target_outputs: list[dict[str, Any]] = Field(default_factory=list)
    resolved_persona_profile_refs: list[PersonaProfileRef] = Field(default_factory=list)
    resolved_workflow_agent_refs: list[WorkflowAgentRef] | None = None
    resolved_capabilities: list[ResolvedCapabilityRead] = Field(default_factory=list)
    resolved_builtin_versions: list[ResolvedBuiltinVersionRead] = Field(default_factory=list)
    resolved_role_versions: list[ResolvedRoleVersionRead] = Field(default_factory=list)
    resolved_character_versions: list[ResolvedCharacterVersionRead] = Field(default_factory=list)
    resolved_bundle_versions: list[ResolvedBundleVersionRead] = Field(default_factory=list)
    resolved_tool_versions: list[ResolvedToolVersionRead] = Field(default_factory=list)
    resolved_connector_versions: list[ResolvedConnectorVersionRead] = Field(default_factory=list)
    trace_summary: TraceSummary
    approval_summary: ApprovalSummary
    created_at: datetime | None = None

    @field_validator(
        "report_markdown",
        "authored_entry_prompt_body",
        "compiled_entry_prompt_body",
        "execution_context_body",
        "prompt_report_slug",
        mode="before",
    )
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("entry_prompt_hash", "full_user_prompt_hash", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)

    @computed_field
    def terminal_error(self) -> TerminalError | None:
        if self.terminal_error_code is None or self.terminal_error_message is None:
            return None
        return TerminalError(code=self.terminal_error_code, message=self.terminal_error_message)


class RuntimeArtifactListRead(CamelModel):
    items: list[RuntimeArtifactRead]
    next_cursor: str | None = None


class RuntimeApprovalListItem(CamelModel):
    approval_id: int = Field(validation_alias=AliasChoices("approval_id", "approvalId", "id"), ge=1)
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId"), ge=1)
    status: RuntimeApprovalStatus
    capability_key: str
    step_key: str
    caller_type: RuntimeCallerType
    caller_id: int | None = None
    created_at: datetime

    @field_validator("capability_key", "step_key", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeApprovalRead(RuntimeApprovalListItem):
    summary: ApprovalDetailSummary
    allowed_actions: list[Literal["approve", "deny"]] = Field(default_factory=list)


class RuntimeApprovalListRead(CamelModel):
    items: list[RuntimeApprovalListItem]
    next_cursor: str | None = None


class RuntimeApprovalActionRequest(CamelModel):
    actor: str
    reason: str

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class RuntimeApprovalActionRead(CamelModel):
    approval_id: int = Field(validation_alias=AliasChoices("approval_id", "approvalId", "id"), ge=1)
    status: RuntimeApprovalStatus
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId"), ge=1)
    resolved_at: datetime
    run_status: RuntimeRunStatus

    @field_validator("resolved_at")
    @classmethod
    def validate_resolved_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeCancelRead(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId", "id"), ge=1)
    status: RuntimeRunStatus
    approval_summary: ApprovalSummary


class RuntimeTraceEventListItem(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId"), ge=1)
    event_index: int = Field(ge=0)
    event_type: RuntimeTraceEventType
    step_key: str | None = None
    capability_key: str | None = None
    caller_type: RuntimeCallerType
    caller_id: int | None = None
    created_at: datetime

    @field_validator("step_key", "capability_key", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeTraceEventRead(RuntimeTraceEventListItem):
    approval_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeTraceEventListRead(CamelModel):
    items: list[RuntimeTraceEventRead]
    next_cursor: str | None = None


class RuntimeCheckpointRead(CamelModel):
    checkpoint_id: int = Field(
        validation_alias=AliasChoices("checkpoint_id", "checkpointId", "id"),
        ge=1,
    )
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId"), ge=1)
    checkpoint_index: int = Field(ge=0)
    step_key: str
    serialized_state: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("step_key", mode="before")
    @classmethod
    def validate_step_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Step key")

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_datetimes(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeControlFlagRead(CamelModel):
    flag_key: str
    enabled: bool
    updated_at: datetime

    @field_validator("flag_key", mode="before")
    @classmethod
    def validate_flag_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Flag key")

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeControlFlagListRead(CamelModel):
    items: list[RuntimeControlFlagRead]


class RuntimeControlFlagUpdateRequest(CamelModel):
    enabled: bool
    actor: str
    reason: str

    @field_validator("actor", "reason", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")


class RuntimeFlagChangeEventRead(CamelModel):
    event_id: int = Field(validation_alias=AliasChoices("event_id", "eventId", "id"), ge=1)
    flag_key: str
    old_enabled: bool
    new_enabled: bool
    actor: str
    reason: str
    result: RuntimeFlagChangeResult
    created_at: datetime

    @field_validator("flag_key", "actor", "reason", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Value")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeFlagChangeEventListRead(CamelModel):
    items: list[RuntimeFlagChangeEventRead]
    next_cursor: str | None = None


PersonaProfileRef.model_rebuild()
