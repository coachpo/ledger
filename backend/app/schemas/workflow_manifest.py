from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import (
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel

WORKFLOW_MANIFEST_API_VERSION = "ledger.workflow/v1"

_STABLE_MANIFEST_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_STABLE_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_STABLE_SLOT_RE = _STABLE_STEP_ID_RE
_AGENT_USE_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]{0,119})@(?P<version>[1-9][0-9]*)$")
_REFERENCE_EXPR_RE = re.compile(r"^\$\{\{\s*(?P<body>[^{}]+?)\s*\}\}$")
_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_STEP_OUTPUT_RE = re.compile(
    r"^steps\.(?P<step_id>[a-z][a-z0-9_]{0,119})\.outputs\."
    + r"(?P<slot>[a-z][a-z0-9_]{0,119})(?:\.(?P<path>.+))?$"
)

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Description must be a string")
    normalized = value.strip()
    return normalized or None


def _validate_stable_key(value: object, *, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name=field_name)
    if _STABLE_MANIFEST_KEY_RE.fullmatch(normalized) is None:
        raise ValueError(
            f"{field_name} must start with a lowercase letter and use only lowercase letters, "
            + "numbers, and underscores"
        )
    return normalized


def _validate_step_id(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Step id")
    if _STABLE_STEP_ID_RE.fullmatch(normalized) is None:
        raise ValueError(
            "Step id must start with a lowercase letter and use only lowercase letters, "
            + "numbers, and underscores"
        )
    return normalized


def _validate_slot(value: object) -> str:
    normalized = _normalize_required_text(value, field_name="Slot")
    if _STABLE_SLOT_RE.fullmatch(normalized) is None:
        raise ValueError(
            "Slot must start with a lowercase letter and use only lowercase letters, "
            + "numbers, and underscores"
        )
    return normalized


def _validate_reference_path(value: str, *, field_name: str) -> str:
    if _PATH_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must use dot-separated field names made of letters, numbers, "
            + "and underscores"
        )
    return value


class WorkflowManifestDiagnosticSeverity(str, Enum):  # noqa: UP042
    ERROR = "error"
    WARNING = "warning"


class WorkflowManifestDiagnostic(CamelModel):
    severity: WorkflowManifestDiagnosticSeverity
    message: str
    path: str
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)


class WorkflowManifestAgentUse(CamelModel):
    key: str
    version: int = Field(ge=1)

    @classmethod
    def parse(cls, value: object) -> WorkflowManifestAgentUse:
        if not isinstance(value, str):
            raise ValueError("Agent uses must be a string in the form <agent_key>@<version>")
        normalized = value.strip()
        match = _AGENT_USE_RE.fullmatch(normalized)
        if match is None:
            raise ValueError(
                "Agent uses must pin an exact numeric version as <agent_key>@<version>"
            )
        return cls(key=match.group("key"), version=int(match.group("version")))


class WorkflowManifestReference(CamelModel):
    expression: str
    source: Literal["inputs", "steps"]
    path: str | None = None
    step_id: str | None = None
    slot: str | None = None
    output_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def parse_expression(cls, value: object) -> dict[str, str | None]:
        if isinstance(value, cls):
            return {
                "expression": value.expression,
                "source": value.source,
                "path": value.path,
                "step_id": value.step_id,
                "slot": value.slot,
                "output_path": value.output_path,
            }
        if not isinstance(value, str):
            raise ValueError("References must use ${{ ... }} expression strings")
        expression = value.strip()
        match = _REFERENCE_EXPR_RE.fullmatch(expression)
        if match is None:
            raise ValueError("References must use ${{ ... }} expression strings")
        body = match.group("body").strip()
        if body.startswith("inputs."):
            input_path = body.removeprefix("inputs.")
            return {
                "expression": expression,
                "source": "inputs",
                "path": _validate_reference_path(input_path, field_name="Input reference path"),
                "step_id": None,
                "slot": None,
                "output_path": None,
            }

        step_match = _STEP_OUTPUT_RE.fullmatch(body)
        if step_match is None:
            raise ValueError(
                "References must target inputs.<path> or steps.<stepId>.outputs.<slot>[.<path>]"
            )
        output_path = step_match.group("path")
        if output_path is not None:
            output_path = _validate_reference_path(output_path, field_name="Step output path")
        return {
            "expression": expression,
            "source": "steps",
            "path": None,
            "step_id": step_match.group("step_id"),
            "slot": step_match.group("slot"),
            "output_path": output_path,
        }

    @model_serializer(mode="plain")
    def serialize_expression(self) -> str:
        return self.expression


class WorkflowManifestMetadata(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _validate_stable_key(value, field_name="Workflow key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _normalize_optional_text(value) or ""


class WorkflowManifestStepAgent(CamelModel):
    slot: str = Field(min_length=1, max_length=120)
    uses: WorkflowManifestAgentUse
    inputs: dict[str, WorkflowManifestReference] = Field(default_factory=dict, alias="with")
    optional: StrictBool = False

    @field_validator("slot", mode="before")
    @classmethod
    def validate_slot(cls, value: object) -> str:
        return _validate_slot(value)

    @field_validator("uses", mode="before")
    @classmethod
    def validate_uses(cls, value: object) -> WorkflowManifestAgentUse:
        return WorkflowManifestAgentUse.parse(value)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(
        cls,
        value: dict[str, WorkflowManifestReference],
    ) -> dict[str, WorkflowManifestReference]:
        normalized: dict[str, WorkflowManifestReference] = {}
        for raw_key, reference in value.items():
            field_name = _normalize_required_text(raw_key, field_name="Input field")
            if field_name in normalized:
                raise ValueError(f"Duplicate input field: {field_name}")
            normalized[field_name] = reference
        return normalized

    @field_serializer("uses", when_used="json")
    def serialize_uses(self, value: WorkflowManifestAgentUse) -> str:
        return f"{value.key}@{value.version}"


class WorkflowManifestStep(CamelModel):
    id: str = Field(min_length=1, max_length=120)
    agents: list[WorkflowManifestStepAgent] = Field(min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_step_id(value)


class WorkflowManifestOutput(CamelModel):
    from_: WorkflowManifestReference = Field(alias="from")

    @field_validator("from_")
    @classmethod
    def validate_output_source(cls, value: WorkflowManifestReference) -> WorkflowManifestReference:
        if value.source != "steps":
            raise ValueError("Workflow output must reference a step output")
        return value


class WorkflowManifest(CamelModel):
    api_version: Literal["ledger.workflow/v1"] = Field(alias="apiVersion")
    kind: Literal["Workflow"]
    metadata: WorkflowManifestMetadata
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    steps: list[WorkflowManifestStep] = Field(min_length=1)
    output: WorkflowManifestOutput

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("inputSchema must be an object schema")
        return value


class WorkflowManifestParseResult(CamelModel):
    manifest: WorkflowManifest | None = None
    diagnostics: list[WorkflowManifestDiagnostic] = Field(default_factory=list)


_ = WorkflowManifest.model_rebuild()


__all__ = [
    "WORKFLOW_MANIFEST_API_VERSION",
    "WorkflowManifest",
    "WorkflowManifestAgentUse",
    "WorkflowManifestDiagnostic",
    "WorkflowManifestDiagnosticSeverity",
    "WorkflowManifestMetadata",
    "WorkflowManifestOutput",
    "WorkflowManifestParseResult",
    "WorkflowManifestReference",
    "WorkflowManifestStep",
    "WorkflowManifestStepAgent",
]
