from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel

WORKFLOW_MANIFEST_V1_API_VERSION = "ledger.workflow/v1"
WORKFLOW_MANIFEST_V2_API_VERSION = "ledger.workflow/v2"
WORKFLOW_MANIFEST_API_VERSION = WORKFLOW_MANIFEST_V1_API_VERSION
WORKFLOW_MANIFEST_V2_MAX_LOOP_ITERATIONS = 10
WORKFLOW_MANIFEST_V2_MAX_FANOUT_BRANCHES = 16

_STABLE_MANIFEST_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_STABLE_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_STABLE_NODE_ID_RE = _STABLE_STEP_ID_RE
_STABLE_SLOT_RE = _STABLE_STEP_ID_RE
_AGENT_USE_RE = re.compile(r"^(?P<key>[a-z][a-z0-9_]{0,119})@(?P<version>[1-9][0-9]*)$")
_REFERENCE_EXPR_RE = re.compile(r"^\$\{\{\s*(?P<body>[^{}]+?)\s*\}\}$")
_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_STEP_OUTPUT_RE = re.compile(
    r"^steps\.(?P<step_id>[a-z][a-z0-9_]{0,119})\.outputs\."
    + r"(?P<slot>[a-z][a-z0-9_]{0,119})(?:\.(?P<path>.+))?$"
)
_NODE_OUTPUT_RE = re.compile(
    r"^nodes\.(?P<node_id>[a-z][a-z0-9_]{0,119})\.outputs\."
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


def _validate_node_id(value: object, *, field_name: str = "Node id") -> str:
    normalized = _normalize_required_text(value, field_name=field_name)
    if _STABLE_NODE_ID_RE.fullmatch(normalized) is None:
        raise ValueError(
            f"{field_name} must start with a lowercase letter and use only lowercase letters, "
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


def _normalize_mapping_keys[
    MappingValue,
](value: dict[str, MappingValue], *, field_name: str) -> dict[str, MappingValue]:
    normalized: dict[str, MappingValue] = {}
    for raw_key, item in value.items():
        key = _normalize_required_text(raw_key, field_name=field_name)
        if key in normalized:
            raise ValueError(f"Duplicate {field_name.lower()}: {key}")
        normalized[key] = item
    return normalized


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


class WorkflowManifestV2Reference(CamelModel):
    expression: str
    source: Literal["inputs", "nodes"]
    path: str | None = None
    node_id: str | None = None
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
                "node_id": value.node_id,
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
                "node_id": None,
                "slot": None,
                "output_path": None,
            }
        node_match = _NODE_OUTPUT_RE.fullmatch(body)
        if node_match is None:
            raise ValueError(
                "References must target inputs.<path> or nodes.<nodeId>.outputs.<slot>[.<path>]"
            )
        output_path = node_match.group("path")
        if output_path is not None:
            output_path = _validate_reference_path(output_path, field_name="Node output path")
        return {
            "expression": expression,
            "source": "nodes",
            "path": None,
            "node_id": node_match.group("node_id"),
            "slot": node_match.group("slot"),
            "output_path": output_path,
        }

    @model_serializer(mode="plain")
    def serialize_expression(self) -> str:
        return self.expression


class WorkflowManifestV2StepNode(CamelModel):
    kind: Literal["step"] = "step"
    id: str = Field(min_length=1, max_length=120)
    slot: str = Field(min_length=1, max_length=120)
    uses: WorkflowManifestAgentUse
    inputs: dict[str, WorkflowManifestV2Reference] = Field(default_factory=dict, alias="with")
    optional: StrictBool = False

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_node_id(value)

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
        value: dict[str, WorkflowManifestV2Reference],
    ) -> dict[str, WorkflowManifestV2Reference]:
        return _normalize_mapping_keys(value, field_name="Input field")

    @field_serializer("uses", when_used="json")
    def serialize_uses(self, value: WorkflowManifestAgentUse) -> str:
        return f"{value.key}@{value.version}"


class WorkflowManifestV2SequenceNode(CamelModel):
    kind: Literal["sequence"] = "sequence"
    id: str = Field(min_length=1, max_length=120)
    nodes: list[WorkflowManifestV2Node] = Field(min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_node_id(value)


class WorkflowManifestV2FanoutBranch(CamelModel):
    id: str = Field(min_length=1, max_length=120)
    node: WorkflowManifestV2Node

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_node_id(value, field_name="Branch id")


class WorkflowManifestV2FanoutNode(CamelModel):
    kind: Literal["fanout"] = "fanout"
    id: str = Field(min_length=1, max_length=120)
    branches: list[WorkflowManifestV2FanoutBranch] = Field(
        min_length=1,
        max_length=WORKFLOW_MANIFEST_V2_MAX_FANOUT_BRANCHES,
    )

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_node_id(value)


class WorkflowManifestV2LoopNode(CamelModel):
    kind: Literal["loop"] = "loop"
    id: str = Field(min_length=1, max_length=120)
    max_iterations: StrictInt = Field(
        alias="maxIterations",
        gt=0,
        le=WORKFLOW_MANIFEST_V2_MAX_LOOP_ITERATIONS,
    )
    sequence: WorkflowManifestV2SequenceNode
    state: dict[str, WorkflowManifestV2Reference] = Field(default_factory=dict)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _validate_node_id(value)

    @field_validator("state")
    @classmethod
    def validate_state(
        cls,
        value: dict[str, WorkflowManifestV2Reference],
    ) -> dict[str, WorkflowManifestV2Reference]:
        return _normalize_mapping_keys(value, field_name="State field")


WorkflowManifestV2Node = Annotated[
    WorkflowManifestV2StepNode
    | WorkflowManifestV2SequenceNode
    | WorkflowManifestV2FanoutNode
    | WorkflowManifestV2LoopNode,
    Field(discriminator="kind"),
]


class WorkflowManifestV2Output(CamelModel):
    from_: WorkflowManifestV2Reference = Field(alias="from")

    @field_validator("from_")
    @classmethod
    def validate_output_source(
        cls,
        value: WorkflowManifestV2Reference,
    ) -> WorkflowManifestV2Reference:
        if value.source != "nodes":
            raise ValueError("Workflow output must reference a node output")
        return value


class WorkflowManifestV2PostRunMemorySource(CamelModel):
    ticker: WorkflowManifestV2Reference
    action: WorkflowManifestV2Reference
    rationale: WorkflowManifestV2Reference
    risk_summary: WorkflowManifestV2Reference = Field(alias="riskSummary")
    execution_plan: WorkflowManifestV2Reference = Field(alias="executionPlan")
    portfolio_slug: WorkflowManifestV2Reference | None = Field(
        default=None,
        alias="portfolioSlug",
    )
    horizon_days: WorkflowManifestV2Reference | None = Field(
        default=None,
        alias="horizonDays",
    )
    confidence: WorkflowManifestV2Reference | None = None
    decision_summary: WorkflowManifestV2Reference | None = Field(
        default=None,
        alias="decisionSummary",
    )


class WorkflowManifestV2PostRunMemory(CamelModel):
    enabled: StrictBool = False
    source: WorkflowManifestV2PostRunMemorySource | None = None
    benchmark_symbol: WorkflowManifestV2Reference | None = Field(
        default=None,
        alias="benchmarkSymbol",
    )

    @model_validator(mode="after")
    def validate_source_when_enabled(self) -> WorkflowManifestV2PostRunMemory:
        if self.enabled and self.source is None:
            raise ValueError("postRunMemory.source is required when enabled")
        return self


class WorkflowManifestV2(CamelModel):
    api_version: Literal["ledger.workflow/v2"] = Field(alias="apiVersion")
    kind: Literal["Workflow"]
    metadata: WorkflowManifestMetadata
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    flow: WorkflowManifestV2Node
    output: WorkflowManifestV2Output
    post_run_memory: WorkflowManifestV2PostRunMemory = Field(
        default_factory=WorkflowManifestV2PostRunMemory,
        alias="postRunMemory",
    )

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("inputSchema must be an object schema")
        return value


type WorkflowManifestDocument = WorkflowManifest | WorkflowManifestV2


class WorkflowManifestParseResult(CamelModel):
    manifest: WorkflowManifestDocument | None = None
    diagnostics: list[WorkflowManifestDiagnostic] = Field(default_factory=list)


_ = WorkflowManifest.model_rebuild()
_ = WorkflowManifestV2SequenceNode.model_rebuild()
_ = WorkflowManifestV2FanoutBranch.model_rebuild()
_ = WorkflowManifestV2FanoutNode.model_rebuild()
_ = WorkflowManifestV2LoopNode.model_rebuild()
_ = WorkflowManifestV2.model_rebuild()


__all__ = [
    "WORKFLOW_MANIFEST_API_VERSION",
    "WORKFLOW_MANIFEST_V1_API_VERSION",
    "WORKFLOW_MANIFEST_V2_API_VERSION",
    "WORKFLOW_MANIFEST_V2_MAX_FANOUT_BRANCHES",
    "WORKFLOW_MANIFEST_V2_MAX_LOOP_ITERATIONS",
    "WorkflowManifest",
    "WorkflowManifestAgentUse",
    "WorkflowManifestDiagnostic",
    "WorkflowManifestDiagnosticSeverity",
    "WorkflowManifestDocument",
    "WorkflowManifestMetadata",
    "WorkflowManifestOutput",
    "WorkflowManifestParseResult",
    "WorkflowManifestReference",
    "WorkflowManifestStep",
    "WorkflowManifestStepAgent",
    "WorkflowManifestV2",
    "WorkflowManifestV2FanoutBranch",
    "WorkflowManifestV2FanoutNode",
    "WorkflowManifestV2LoopNode",
    "WorkflowManifestV2Node",
    "WorkflowManifestV2Output",
    "WorkflowManifestV2PostRunMemory",
    "WorkflowManifestV2PostRunMemorySource",
    "WorkflowManifestV2Reference",
    "WorkflowManifestV2SequenceNode",
    "WorkflowManifestV2StepNode",
]
