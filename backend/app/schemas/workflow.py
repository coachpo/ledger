from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal, cast

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.workflow_manifest import WorkflowManifestDiagnostic

_STABLE_WORKFLOW_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"
_STABLE_SLOT_NAME_RE = _STABLE_WORKFLOW_KEY_RE
_SOURCE_PATH_RE = r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH = 262_144


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


def _normalize_workflow_key(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Key").lower()
    if re.fullmatch(_STABLE_WORKFLOW_KEY_RE, normalized) is None:
        raise ValueError(
            "Key must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _normalize_slot_name(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Slot").lower()
    if re.fullmatch(_STABLE_SLOT_NAME_RE, normalized) is None:
        raise ValueError(
            "Slot must start with a letter and use only lowercase letters, numbers, and underscores"
        )
    return normalized


def _normalize_source_path(value: object) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    if re.fullmatch(_SOURCE_PATH_RE, normalized) is None:
        raise ValueError(
            "Path must use dot-separated field names made of letters, numbers, and underscores"
        )
    return normalized


def _normalize_wiring_field_name(value: object) -> str:
    return _normalize_required_text(value, field_name="Wiring field")


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


def _external_field_name(field_name: str) -> str:
    return {
        "input_schema": "inputSchema",
        "manifest_source": "manifestSource",
        "output_spec": "outputSpec",
    }.get(field_name, field_name)


def _omit_none_compiled_graph(serialized: dict[str, object]) -> dict[str, object]:
    for key in ("compiledGraph", "compiled_graph"):
        if serialized.get(key) is None:
            _ = serialized.pop(key, None)
    return serialized


class WorkflowStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class WorkflowWireSource(CamelModel):
    source: Literal["input", "step"] = Field(alias="from")
    path: str | None = None
    step_index: int | None = Field(default=None, ge=1)
    slot: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> str | None:
        return _normalize_source_path(value)

    @field_validator("slot", mode="before")
    @classmethod
    def validate_slot(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_slot_name(value)

    @model_validator(mode="after")
    def validate_source(self) -> WorkflowWireSource:
        if self.source == "input":
            if self.step_index is not None or self.slot is not None:
                raise ValueError("Input sources cannot set stepIndex or slot")
            return self
        if self.step_index is None:
            raise ValueError("Step sources must set stepIndex")
        if self.slot is None:
            raise ValueError("Step sources must set slot")
        return self

    @model_serializer(mode="wrap")
    def serialize_without_nulls(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, Any]:
        serialized = handler(self)
        return {key: value for key, value in serialized.items() if value is not None}


class WorkflowStepAgentWrite(CamelModel):
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int | None = Field(default=None, ge=1)
    slot: str = Field(min_length=1, max_length=120)
    wiring: dict[str, WorkflowWireSource] = Field(default_factory=dict)
    optional: bool = False

    @field_validator("agent_key", mode="before")
    @classmethod
    def validate_agent_key(cls, value: object) -> str:
        return _normalize_workflow_key(value)

    @field_validator("slot", mode="before")
    @classmethod
    def validate_slot(cls, value: object) -> str:
        return _normalize_slot_name(value)

    @field_validator("wiring")
    @classmethod
    def validate_wiring(cls, value: dict[str, WorkflowWireSource]) -> dict[str, WorkflowWireSource]:
        normalized: dict[str, WorkflowWireSource] = {}
        for raw_key, raw_value in value.items():
            field_name = _normalize_wiring_field_name(raw_key)
            if field_name in normalized:
                raise ValueError(f"Duplicate wiring field: {field_name}")
            normalized[field_name] = raw_value
        return normalized


class WorkflowStepWrite(CamelModel):
    index: int = Field(ge=1)
    agents: list[WorkflowStepAgentWrite] = Field(min_length=1)


class WorkflowOutputSlotWrite(CamelModel):
    kind: Literal["slot"] = "slot"
    step_index: int = Field(ge=1)
    slot: str = Field(min_length=1, max_length=120)
    path: str | None = None

    @field_validator("slot", mode="before")
    @classmethod
    def validate_slot(cls, value: object) -> str:
        return _normalize_slot_name(value)

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> str | None:
        return _normalize_source_path(value)


WorkflowOutputSpecWrite = WorkflowOutputSlotWrite


class WorkflowStepAgentRead(CamelModel):
    agent_id: int
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int
    output_schema_version: int = Field(ge=1)
    slot: str
    wiring: dict[str, WorkflowWireSource]
    optional: bool


class WorkflowStepRead(CamelModel):
    index: int = Field(ge=1)
    agents: list[WorkflowStepAgentRead]


class WorkflowOutputSlotRead(CamelModel):
    kind: Literal["slot"] = "slot"
    step_index: int = Field(ge=1)
    slot: str
    path: str | None = None
    agent_id: int
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int
    output_schema_version: int = Field(ge=1)


WorkflowOutputSpecRead = WorkflowOutputSlotRead


class WorkflowVersionBase(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    input_schema: dict[str, Any]
    steps: list[WorkflowStepWrite] = Field(min_length=1)
    output_spec: WorkflowOutputSpecWrite

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""


class WorkflowCreate(WorkflowVersionBase):
    key: str = Field(min_length=1, max_length=120)

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _normalize_workflow_key(value)


class WorkflowUpdate(WorkflowVersionBase):
    pass


class WorkflowCreateRequest(CamelModel):
    key: str | None = Field(default=None, min_length=1, max_length=120)
    manifest_source: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str = ""
    input_schema: dict[str, Any] | None = None
    steps: list[WorkflowStepWrite] | None = None
    output_spec: WorkflowOutputSpecWrite | None = None

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_workflow_key(value)

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str | None:
        if value is None:
            return None
        return _validate_manifest_source(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @model_validator(mode="after")
    def validate_authoring_mode(self) -> WorkflowCreateRequest:
        compiled_fields = {"key", "name", "description", "input_schema", "steps", "output_spec"}
        if self.manifest_source is not None:
            mixed_fields = compiled_fields & self.model_fields_set
            if mixed_fields:
                names = ", ".join(sorted(_external_field_name(field) for field in mixed_fields))
                raise ValueError(f"manifestSource cannot be combined with {names}")
            return self

        required_fields = {"key", "name", "input_schema", "steps", "output_spec"}
        missing_fields = [
            _external_field_name(field)
            for field in sorted(required_fields)
            if getattr(self, field) is None
        ]
        if missing_fields:
            raise ValueError(
                "Either manifestSource or the compiled workflow fields are required; "
                + f"missing {', '.join(missing_fields)}"
            )
        return self

    def to_workflow_create(self) -> WorkflowCreate:
        return WorkflowCreate.model_validate(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class WorkflowUpdateRequest(CamelModel):
    manifest_source: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str = ""
    input_schema: dict[str, Any] | None = None
    steps: list[WorkflowStepWrite] | None = None
    output_spec: WorkflowOutputSpecWrite | None = None

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str | None:
        if value is None:
            return None
        return _validate_manifest_source(value)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""

    @model_validator(mode="after")
    def validate_authoring_mode(self) -> WorkflowUpdateRequest:
        compiled_fields = {"name", "description", "input_schema", "steps", "output_spec"}
        if self.manifest_source is not None:
            mixed_fields = compiled_fields & self.model_fields_set
            if mixed_fields:
                names = ", ".join(sorted(_external_field_name(field) for field in mixed_fields))
                raise ValueError(f"manifestSource cannot be combined with {names}")
            return self

        required_fields = {"name", "input_schema", "steps", "output_spec"}
        missing_fields = [
            _external_field_name(field)
            for field in sorted(required_fields)
            if getattr(self, field) is None
        ]
        if missing_fields:
            raise ValueError(
                "Either manifestSource or the compiled workflow fields are required; "
                + f"missing {', '.join(missing_fields)}"
            )
        return self

    def to_workflow_update(self) -> WorkflowUpdate:
        return WorkflowUpdate.model_validate(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class WorkflowManifestValidationRequest(CamelModel):
    manifest_source: str

    @field_validator("manifest_source", mode="before")
    @classmethod
    def validate_manifest_source(cls, value: object) -> str:
        return _validate_manifest_source(value)


class WorkflowManifestValidationMetadata(CamelModel):
    api_version: str
    key: str
    name: str
    description: str


class WorkflowManifestValidationRead(CamelModel):
    diagnostics: list[WorkflowManifestDiagnostic]
    metadata: WorkflowManifestValidationMetadata | None = None
    compiled_payload: dict[str, Any] | None = None
    compiled_graph: dict[str, object] | None = None
    run_input_schema: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def serialize_without_empty_graph(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        return _omit_none_compiled_graph(cast(dict[str, object], handler(self)))


class WorkflowRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: WorkflowStatus
    name: str
    description: str
    manifest_api_version: str
    manifest_source: str
    input_schema: dict[str, Any]
    steps: list[WorkflowStepRead]
    output_spec: WorkflowOutputSpecRead
    compiled_graph: dict[str, object] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @model_serializer(mode="wrap")
    def serialize_without_empty_graph(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        return _omit_none_compiled_graph(cast(dict[str, object], handler(self)))


class WorkflowListRead(CamelModel):
    items: list[WorkflowRead]


class WorkflowVersionRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: WorkflowStatus
    name: str
    description: str
    input_schema: dict[str, object]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowVersionListRead(CamelModel):
    items: list[WorkflowVersionRead]


class WorkflowLaunchRead(CamelModel):
    workflow_id: int
    key: str
    version: int = Field(ge=1)
    name: str
    description: str
    input_schema: dict[str, object]


class WorkflowLaunchCreateRequest(CamelModel):
    version: int = Field(ge=1)
    parameters: dict[str, object]


class WorkflowLaunchCreateResponse(CamelModel):
    id: int
    status: Literal["queued", "running", "succeeded", "failed"]
    workflow_id: int
    workflow_key: str
    workflow_version: int = Field(ge=1)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


WorkflowRead.model_rebuild()
WorkflowCreate.model_rebuild()
WorkflowUpdate.model_rebuild()
WorkflowCreateRequest.model_rebuild()
WorkflowUpdateRequest.model_rebuild()


__all__ = [
    "WorkflowCreate",
    "WorkflowCreateRequest",
    "WorkflowLaunchCreateRequest",
    "WorkflowLaunchCreateResponse",
    "WorkflowLaunchRead",
    "WorkflowListRead",
    "WorkflowVersionListRead",
    "WorkflowVersionRead",
    "WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH",
    "WorkflowManifestValidationMetadata",
    "WorkflowManifestValidationRead",
    "WorkflowManifestValidationRequest",
    "WorkflowOutputSlotRead",
    "WorkflowOutputSlotWrite",
    "WorkflowOutputSpecRead",
    "WorkflowOutputSpecWrite",
    "WorkflowRead",
    "WorkflowStatus",
    "WorkflowStepAgentRead",
    "WorkflowStepAgentWrite",
    "WorkflowStepRead",
    "WorkflowStepWrite",
    "WorkflowUpdate",
    "WorkflowUpdateRequest",
    "WorkflowWireSource",
]
