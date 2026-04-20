from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel, ensure_timezone

_STABLE_WORKFLOW_KEY_RE = r"^[a-z][a-z0-9_]{0,119}$"
_STABLE_SLOT_NAME_RE = _STABLE_WORKFLOW_KEY_RE
_SOURCE_PATH_RE = r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"


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


class WorkflowStatus(str, Enum):  # noqa: UP042
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


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
        return {
            key: value
            for key, value in serialized.items()
            if value is not None
        }


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


class WorkflowOutputAgentWrite(CamelModel):
    kind: Literal["agent"] = "agent"
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int | None = Field(default=None, ge=1)
    wiring: dict[str, WorkflowWireSource] = Field(default_factory=dict)

    @field_validator("agent_key", mode="before")
    @classmethod
    def validate_agent_key(cls, value: object) -> str:
        return _normalize_workflow_key(value)

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


WorkflowOutputSpecWrite = Annotated[
    Union[WorkflowOutputSlotWrite, WorkflowOutputAgentWrite],  # noqa: UP007
    Field(discriminator="kind"),
]


class WorkflowStepAgentRead(CamelModel):
    agent_id: int
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int
    output_schema_version: int = Field(ge=1)
    slot: str
    wiring: dict[str, WorkflowWireSource]
    optional: bool
    budget_usd: Decimal


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


class WorkflowOutputAgentRead(CamelModel):
    kind: Literal["agent"] = "agent"
    agent_id: int
    agent_key: str
    agent_version: int = Field(ge=1)
    output_schema_id: int
    output_schema_version: int = Field(ge=1)
    wiring: dict[str, WorkflowWireSource]


WorkflowOutputSpecRead = Annotated[
    Union[WorkflowOutputSlotRead, WorkflowOutputAgentRead],  # noqa: UP007
    Field(discriminator="kind"),
]


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


class WorkflowRead(CamelModel):
    id: int
    key: str
    version: int = Field(ge=1)
    status: WorkflowStatus
    name: str
    description: str
    input_schema: dict[str, Any]
    steps: list[WorkflowStepRead]
    output_spec: WorkflowOutputSpecRead
    aggregate_budget_usd: Decimal
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class WorkflowListRead(CamelModel):
    items: list[WorkflowRead]


WorkflowRead.model_rebuild()
WorkflowCreate.model_rebuild()
WorkflowUpdate.model_rebuild()


__all__ = [
    "WorkflowCreate",
    "WorkflowListRead",
    "WorkflowOutputAgentRead",
    "WorkflowOutputAgentWrite",
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
    "WorkflowWireSource",
]
