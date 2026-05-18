# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal, cast

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)

from app.schemas.common import CamelModel

WORKFLOW_PACKAGE_MANIFEST_API_VERSION = "signaldeck.workflowPackage/v1"
WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS = ("GET", "POST")

_STABLE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_MCP_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,119}$")
_TOOL_KEY_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,256}$")
_REF_EXPR_RE = re.compile(r"^\$\{\{\s*(?P<body>[^{}]+?)\s*\}\}$")
_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_NODE_OUTPUT_RE = re.compile(
    r"^nodes\.(?P<node_id>[a-z][a-z0-9_]{0,119})\.outputs\."
    + r"(?P<slot>[a-z][a-z0-9_]{0,119})(?:\.(?P<path>.+))?$"
)
_SECRET_REF_BODY_RE = re.compile(r"^secrets\.(?P<key>[a-z][a-z0-9_]{0,119})$")

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Description must be a string")
    return value.strip()


def _stable_key(value: object, *, field_name: str, allow_hyphen: bool = False) -> str:
    normalized = _required_text(value, field_name=field_name)
    pattern = _MCP_KEY_RE if allow_hyphen else _STABLE_KEY_RE
    if pattern.fullmatch(normalized) is None:
        suffix = (
            "lowercase letters, numbers, underscores, and hyphens"
            if allow_hyphen
            else "lowercase letters, numbers, and underscores"
        )
        raise ValueError(f"{field_name} must start with a lowercase letter and use only {suffix}")
    return normalized


def _local_ref(value: object, *, field_name: str, allow_hyphen: bool = False) -> str:
    if isinstance(value, str) and "@" in value:
        raise ValueError(f"{field_name} must use a package-local key without @version")
    return _stable_key(value, field_name=field_name, allow_hyphen=allow_hyphen)


def _json_schema(value: dict[str, JsonValue], *, field_name: str) -> dict[str, JsonValue]:
    if value.get("type") != "object":
        raise ValueError(f"{field_name} must be an object schema")
    return value


def _string_map(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object of string values")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in cast(dict[object, object], value).items():
        key = _required_text(raw_key, field_name=f"{field_name} key")
        normalized[key] = _required_text(raw_value, field_name=f"{field_name}.{key}")
    return normalized


def _ref_list(value: object, *, field_name: str, allow_hyphen: bool = False) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array of package-local keys")
    return [
        _local_ref(item, field_name=field_name, allow_hyphen=allow_hyphen)
        for item in cast(list[object], value)
    ]


class WorkflowPackageManifestDiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class WorkflowPackageManifestDiagnostic(CamelModel):
    severity: WorkflowPackageManifestDiagnosticSeverity
    message: str
    path: str
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)


class WorkflowPackageManifestMetadata(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="Package key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)


class WorkflowPackageCapabilityProfile(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    tool_keys: list[str] = Field(min_length=1, alias="toolKeys")

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="Capability profile key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)

    @field_validator("tool_keys", mode="before")
    @classmethod
    def validate_tool_keys(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("toolKeys must be an array of server-declared global tool keys")
        keys: list[str] = []
        for item in cast(list[object], value):
            key = _required_text(item, field_name="Tool key")
            if _TOOL_KEY_RE.fullmatch(key) is None:
                raise ValueError("Tool keys must use server-declared global tool key syntax")
            keys.append(key)
        return keys


class WorkflowPackageOutputSchema(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    json_schema: dict[str, JsonValue] = Field(alias="jsonSchema")

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="Output schema key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _json_schema(value, field_name="jsonSchema")


class WorkflowPackageMcpServer(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    transport: Literal["stdio", "http-sse"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    tool_keys: list[str] = Field(default_factory=list, alias="toolKeys")

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="MCP server key", allow_hyphen=True)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)

    @field_validator("command", "url", mode="before")
    @classmethod
    def validate_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = _required_text(value, field_name="MCP server field")
        return normalized

    @field_validator("args", mode="before")
    @classmethod
    def validate_args(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("args must be an array of strings")
        return [
            _required_text(item, field_name="MCP argument") for item in cast(list[object], value)
        ]

    @field_validator("env", "headers", "query", mode="before")
    @classmethod
    def validate_inline_string_map(cls, value: object, info: ValidationInfo) -> dict[str, str]:
        return _string_map(value, field_name=info.field_name or "MCP inline map")

    @field_validator("tool_keys", mode="before")
    @classmethod
    def validate_tool_keys(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("toolKeys must be an array of server-declared global tool keys")
        keys: list[str] = []
        for item in cast(list[object], value):
            key = _required_text(item, field_name="Tool key")
            if _TOOL_KEY_RE.fullmatch(key) is None:
                raise ValueError("Tool keys must use server-declared global tool key syntax")
            keys.append(key)
        return keys

    @model_validator(mode="after")
    def validate_transport_shape(self) -> WorkflowPackageMcpServer:
        provided_fields = self.model_fields_set
        if self.transport == "stdio":
            if not self.command or not self.args:
                raise ValueError("stdio MCP servers require command and args")
            unsupported = sorted(provided_fields.intersection({"url", "headers", "query"}))
            if unsupported:
                raise ValueError(
                    "stdio MCP servers only support inline env values; unsupported fields: "
                    + ", ".join(unsupported)
                )
            return self

        if not self.url:
            raise ValueError("http-sse MCP servers require url")
        unsupported = sorted(provided_fields.intersection({"command", "args", "env"}))
        if unsupported:
            raise ValueError(
                "http-sse MCP servers only support inline headers and query values; "
                + "unsupported fields: "
                + ", ".join(unsupported)
            )
        return self


class WorkflowPackageAgent(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    model_connection: str = Field(alias="modelConnection", min_length=1, max_length=120)
    system_prompt: str = Field(alias="systemPrompt", min_length=1)
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    output_schema: str = Field(alias="outputSchema", min_length=1, max_length=120)
    capability_profiles: list[str] = Field(default_factory=list, alias="capabilityProfiles")
    mcp_servers: list[str] = Field(default_factory=list, alias="mcpServers")

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="Agent key")

    @field_validator("name", "system_prompt", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _required_text(value, field_name="Agent field")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)

    @field_validator("model_connection", mode="before")
    @classmethod
    def validate_model_connection(cls, value: object) -> str:
        return _stable_key(value, field_name="Model connection")

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _json_schema(value, field_name="inputSchema")

    @field_validator("output_schema", mode="before")
    @classmethod
    def validate_output_schema(cls, value: object) -> str:
        return _local_ref(value, field_name="outputSchema")

    @field_validator("capability_profiles", mode="before")
    @classmethod
    def validate_capability_profiles(cls, value: object) -> list[str]:
        return _ref_list(value, field_name="capabilityProfiles")

    @field_validator("mcp_servers", mode="before")
    @classmethod
    def validate_mcp_servers(cls, value: object) -> list[str]:
        return _ref_list(value, field_name="mcpServers", allow_hyphen=True)


class WorkflowPackageReference(CamelModel):
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
            return value.model_dump()
        if not isinstance(value, str):
            raise ValueError("References must use ${{ ... }} expression strings")
        expression = value.strip()
        match = _REF_EXPR_RE.fullmatch(expression)
        if match is None:
            raise ValueError("References must use ${{ ... }} expression strings")
        body = match.group("body").strip()
        if body.startswith("inputs."):
            input_path = body.removeprefix("inputs.")
            if _PATH_RE.fullmatch(input_path) is None:
                raise ValueError("Input reference path must use dot-separated field names")
            return {
                "expression": expression,
                "source": "inputs",
                "path": input_path,
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
        if output_path is not None and _PATH_RE.fullmatch(output_path) is None:
            raise ValueError("Node output path must use dot-separated field names")
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


class WorkflowPackageSecretReference(CamelModel):
    expression: str
    source: Literal["secrets"]
    key: str

    @model_validator(mode="before")
    @classmethod
    def parse_expression(cls, value: object) -> dict[str, str]:
        if isinstance(value, cls):
            return value.model_dump()
        if not isinstance(value, str):
            raise ValueError("Secret references must use ${{ secrets.<key> }} expression strings")
        expression = value.strip()
        match = _REF_EXPR_RE.fullmatch(expression)
        if match is None:
            raise ValueError("Secret references must use ${{ secrets.<key> }} expression strings")
        body = match.group("body").strip()
        secret_match = _SECRET_REF_BODY_RE.fullmatch(body)
        if secret_match is None:
            raise ValueError("Secret references must target secrets.<key>")
        return {"expression": expression, "source": "secrets", "key": secret_match.group("key")}

    @model_serializer(mode="plain")
    def serialize_expression(self) -> str:
        return self.expression


def _validate_http_request_value(value: object, *, field_name: str) -> JsonValue:
    if isinstance(value, dict):
        return {
            _required_text(key, field_name=f"{field_name} key"): _validate_http_request_value(
                item,
                field_name=f"{field_name}.{key}",
            )
            for key, item in cast(dict[object, object], value).items()
        }
    if isinstance(value, list):
        return [
            _validate_http_request_value(item, field_name=f"{field_name}[{index}]")
            for index, item in enumerate(cast(list[object], value))
        ]
    if isinstance(value, str):
        expression = value.strip()
        if "${{" not in expression:
            return value
        match = _REF_EXPR_RE.fullmatch(expression)
        if match is None:
            raise ValueError(
                f"{field_name} references must use standalone ${{{{ ... }}}} expression strings"
            )
        body = match.group("body").strip()
        if body.startswith("secrets."):
            _ = WorkflowPackageSecretReference.model_validate(expression)
            return expression
        _ = WorkflowPackageReference.model_validate(expression)
        return expression
    if isinstance(value, int | float | bool) or value is None:
        return cast(JsonValue, value)
    raise ValueError(f"{field_name} must be JSON-compatible")


class WorkflowPackageHttpResponse(CamelModel):
    output_schema: str = Field(alias="outputSchema", min_length=1, max_length=120)

    @field_validator("output_schema", mode="before")
    @classmethod
    def validate_output_schema(cls, value: object) -> str:
        return _local_ref(value, field_name="HTTP response outputSchema")


class WorkflowPackageHttpNode(CamelModel):
    kind: Literal["http"] = "http"
    id: str = Field(min_length=1, max_length=120)
    slot: str = Field(min_length=1, max_length=120)
    method: str = Field(min_length=1, max_length=16)
    url: str = Field(min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: JsonValue | None = None
    response: WorkflowPackageHttpResponse
    timeout_seconds: StrictInt = Field(default=30, alias="timeoutSeconds", gt=0, le=30)
    optional: StrictBool = False

    @field_validator("id", "slot", mode="before")
    @classmethod
    def validate_local_id(cls, value: object) -> str:
        return _stable_key(value, field_name="HTTP node field")

    @field_validator("method", mode="before")
    @classmethod
    def validate_method(cls, value: object) -> str:
        normalized = _required_text(value, field_name="HTTP method").upper()
        if not normalized.isalpha():
            raise ValueError("HTTP method must contain only letters")
        return normalized

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: object) -> str:
        normalized = _required_text(value, field_name="HTTP url")
        _ = _validate_http_request_value(normalized, field_name="url")
        return normalized

    @field_validator("headers", "query", mode="before")
    @classmethod
    def validate_request_string_map(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> dict[str, str]:
        field_name = info.field_name or "HTTP request map"
        mapping = _string_map(value, field_name=field_name)
        for key, item in mapping.items():
            _ = _validate_http_request_value(item, field_name=f"{field_name}.{key}")
        return mapping

    @field_validator("body", mode="before")
    @classmethod
    def validate_body(cls, value: object) -> JsonValue | None:
        return _validate_http_request_value(value, field_name="body")


class WorkflowPackageStepNode(CamelModel):
    kind: Literal["step"] = "step"
    id: str = Field(min_length=1, max_length=120)
    slot: str = Field(min_length=1, max_length=120)
    uses: str = Field(min_length=1, max_length=120)
    inputs: dict[str, WorkflowPackageReference] = Field(default_factory=dict, alias="with")
    optional: StrictBool = False

    @field_validator("id", "slot", mode="before")
    @classmethod
    def validate_local_id(cls, value: object) -> str:
        return _stable_key(value, field_name="Node field")

    @field_validator("uses", mode="before")
    @classmethod
    def validate_uses(cls, value: object) -> str:
        return _local_ref(value, field_name="Step agent")


class WorkflowPackageSequenceNode(CamelModel):
    kind: Literal["sequence"] = "sequence"
    id: str = Field(min_length=1, max_length=120)
    nodes: list[WorkflowPackageNode] = Field(min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _stable_key(value, field_name="Node id")


class WorkflowPackageFanoutBranch(CamelModel):
    id: str = Field(min_length=1, max_length=120)
    node: WorkflowPackageNode

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _stable_key(value, field_name="Branch id")


class WorkflowPackageFanoutNode(CamelModel):
    kind: Literal["fanout"] = "fanout"
    id: str = Field(min_length=1, max_length=120)
    branches: list[WorkflowPackageFanoutBranch] = Field(min_length=1, max_length=16)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _stable_key(value, field_name="Node id")


class WorkflowPackageLoopNode(CamelModel):
    kind: Literal["loop"] = "loop"
    id: str = Field(min_length=1, max_length=120)
    max_iterations: StrictInt = Field(alias="maxIterations", gt=0, le=10)
    sequence: WorkflowPackageSequenceNode
    state: dict[str, WorkflowPackageReference] = Field(default_factory=dict)

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _stable_key(value, field_name="Node id")


WorkflowPackageNode = Annotated[
    WorkflowPackageStepNode
    | WorkflowPackageHttpNode
    | WorkflowPackageSequenceNode
    | WorkflowPackageFanoutNode
    | WorkflowPackageLoopNode,
    Field(discriminator="kind"),
]


class WorkflowPackageWorkflowOutput(CamelModel):
    from_: WorkflowPackageReference = Field(alias="from")

    @field_validator("from_")
    @classmethod
    def validate_output_ref(cls, value: WorkflowPackageReference) -> WorkflowPackageReference:
        if value.source != "nodes":
            raise ValueError("Workflow output must reference a node output")
        return value


class WorkflowPackageWorkflow(CamelModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    input_schema: dict[str, JsonValue] = Field(alias="inputSchema")
    flow: WorkflowPackageNode
    output: WorkflowPackageWorkflowOutput

    @field_validator("key", mode="before")
    @classmethod
    def validate_key(cls, value: object) -> str:
        return _stable_key(value, field_name="Workflow key")

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return _required_text(value, field_name="Name")

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, value: object) -> str:
        return _optional_text(value)

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _json_schema(value, field_name="inputSchema")


class WorkflowPackageManifestSpec(CamelModel):
    inputs: dict[str, JsonValue]
    capability_profiles: list[WorkflowPackageCapabilityProfile] = Field(
        default_factory=list, alias="capabilityProfiles"
    )
    output_schemas: list[WorkflowPackageOutputSchema] = Field(
        default_factory=list, alias="outputSchemas"
    )
    mcp_servers: list[WorkflowPackageMcpServer] = Field(default_factory=list, alias="mcpServers")
    agents: list[WorkflowPackageAgent] = Field(default_factory=list)
    workflows: list[WorkflowPackageWorkflow] = Field(default_factory=list)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return _json_schema(value, field_name="spec.inputs")


class WorkflowPackageManifest(CamelModel):
    api_version: Literal["signaldeck.workflowPackage/v1"] = Field(alias="apiVersion")
    kind: Literal["WorkflowPackage"]
    metadata: WorkflowPackageManifestMetadata
    spec: WorkflowPackageManifestSpec


class WorkflowPackageManifestParseResult(CamelModel):
    manifest: WorkflowPackageManifest | None = None
    diagnostics: list[WorkflowPackageManifestDiagnostic] = Field(default_factory=list)


_ = WorkflowPackageHttpNode.model_rebuild()
_ = WorkflowPackageSequenceNode.model_rebuild()
_ = WorkflowPackageFanoutBranch.model_rebuild()
_ = WorkflowPackageFanoutNode.model_rebuild()
_ = WorkflowPackageLoopNode.model_rebuild()
_ = WorkflowPackageWorkflow.model_rebuild()
_ = WorkflowPackageManifest.model_rebuild()


__all__ = [
    "WORKFLOW_PACKAGE_HTTP_ALLOWED_METHODS",
    "WORKFLOW_PACKAGE_MANIFEST_API_VERSION",
    "JsonValue",
    "WorkflowPackageAgent",
    "WorkflowPackageCapabilityProfile",
    "WorkflowPackageFanoutBranch",
    "WorkflowPackageFanoutNode",
    "WorkflowPackageHttpNode",
    "WorkflowPackageHttpResponse",
    "WorkflowPackageLoopNode",
    "WorkflowPackageManifest",
    "WorkflowPackageManifestDiagnostic",
    "WorkflowPackageManifestDiagnosticSeverity",
    "WorkflowPackageManifestMetadata",
    "WorkflowPackageManifestParseResult",
    "WorkflowPackageManifestSpec",
    "WorkflowPackageMcpServer",
    "WorkflowPackageNode",
    "WorkflowPackageOutputSchema",
    "WorkflowPackageReference",
    "WorkflowPackageSecretReference",
    "WorkflowPackageSequenceNode",
    "WorkflowPackageStepNode",
    "WorkflowPackageWorkflow",
    "WorkflowPackageWorkflowOutput",
]
