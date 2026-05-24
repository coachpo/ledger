from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, cast

from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.schemas.mcp_server import McpToolSnapshot

_MCP_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.@/-]{1,128}$")
_OPENAI_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_RESERVED_SCHEMA_KEYS = {
    "$ref",
    "oneOf",
    "anyOf",
    "allOf",
    "not",
    "patternProperties",
    "dependentSchemas",
    "unevaluatedProperties",
}
PACKAGE_PRIVATE_MCP_VERSION = 1
_PACKAGE_PRIVATE_SEARCH_TOOL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query for the MCP tool."},
    },
}
_PACKAGE_PRIVATE_MCP_TOOL_INPUT_SCHEMAS: dict[str, Mapping[str, object]] = {
    "web_search_exa": _PACKAGE_PRIVATE_SEARCH_TOOL_INPUT_SCHEMA,
}
SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS = frozenset(_PACKAGE_PRIVATE_MCP_TOOL_INPUT_SCHEMAS)

type ExecutionToolKind = Literal["native_runtime", "mcp"]
type ExecutionToolRedactionPolicy = Literal["native.runtime.output", "mcp.output.redact_text"]
NATIVE_RUNTIME_REDACTION_POLICY: ExecutionToolRedactionPolicy = "native.runtime.output"
MCP_RUNTIME_REDACTION_POLICY: ExecutionToolRedactionPolicy = "mcp.output.redact_text"


@dataclass(frozen=True, slots=True)
class ExecutionToolDescriptor:
    kind: ExecutionToolKind
    tool_key: str
    openai_function_name: str
    description: str
    strict_schema: dict[str, object]
    schema_hash: str
    redaction_policy: ExecutionToolRedactionPolicy
    owner_extension_key: str | None = None
    mcp_server_key: str | None = None
    mcp_server_version: int | None = None
    original_tool_name: str | None = None


class McpToolAdapterError(ValueError):
    pass


def build_mcp_tool_snapshot(
    *,
    server_key: str,
    server_version: int,
    original_tool_name: str,
    input_schema: Mapping[str, object],
    reserved_function_names: set[str] | None = None,
) -> McpToolSnapshot:
    normalized_name = normalize_mcp_openai_function_name(
        server_key=server_key,
        original_tool_name=original_tool_name,
        reserved_function_names=reserved_function_names or set(),
    )
    strict_schema = convert_mcp_input_schema(input_schema)
    schema_hash = hash_strict_schema(strict_schema)
    return McpToolSnapshot.model_validate(
        {
            "mcpServerKey": server_key,
            "mcpServerVersion": server_version,
            "frozenToolKey": f"{server_key}@{server_version}:{normalized_name}",
            "originalToolName": original_tool_name,
            "openaiFunctionName": normalized_name,
            "schemaHash": schema_hash,
            "strictSchema": strict_schema,
            "reverseMapping": {normalized_name: original_tool_name},
        }
    )


def normalize_mcp_openai_function_name(
    *,
    server_key: str,
    original_tool_name: str,
    reserved_function_names: set[str],
) -> str:
    if _MCP_TOOL_NAME_RE.fullmatch(original_tool_name) is None:
        raise McpToolAdapterError("MCP tool name contains unsupported characters")
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", server_key).strip("_")
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", original_tool_name).strip("_")
    candidate = re.sub(r"_+", "_", f"mcp_{prefix}_{suffix}")
    if not candidate or candidate[0].isdigit():
        candidate = f"mcp_{candidate}"
    if len(candidate) > 112:
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:12]
        candidate = f"{candidate[:99].rstrip('_')}_{digest}"
    if _OPENAI_NAME_RE.fullmatch(candidate) is None:
        raise McpToolAdapterError("MCP tool name could not be converted to OpenAI function name")
    if candidate in reserved_function_names:
        raise McpToolAdapterError("MCP OpenAI function name collides with an existing tool")
    return candidate


def convert_mcp_input_schema(schema: Mapping[str, object]) -> dict[str, object]:
    return _convert_schema_node(dict(schema), path="inputSchema", require_object_root=True)


def hash_strict_schema(schema: Mapping[str, object]) -> str:
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def package_private_mcp_tool_input_schema(tool_name: str) -> Mapping[str, object]:
    schema = _PACKAGE_PRIVATE_MCP_TOOL_INPUT_SCHEMAS.get(tool_name.strip().lower())
    if schema is None:
        raise McpToolAdapterError(
            f"Package-private MCP tool {tool_name!r} does not have a runtime input schema."
        )
    return deepcopy(dict(schema))


def build_native_runtime_tool_descriptor(
    *,
    key: str,
    openai_function_name: str,
    description: str,
    parameters_schema: Mapping[str, object],
    owner_extension_key: str | None,
) -> ExecutionToolDescriptor:
    strict_schema = deepcopy(dict(parameters_schema))
    return ExecutionToolDescriptor(
        kind="native_runtime",
        tool_key=key,
        openai_function_name=openai_function_name,
        description=description,
        strict_schema=strict_schema,
        schema_hash=hash_strict_schema(strict_schema),
        redaction_policy=NATIVE_RUNTIME_REDACTION_POLICY,
        owner_extension_key=owner_extension_key,
    )


def build_package_private_mcp_tool_descriptor(
    *,
    server_key: str,
    original_tool_name: str,
    owner_extension_key: str,
    reserved_function_names: set[str] | None = None,
) -> ExecutionToolDescriptor:
    snapshot = build_mcp_tool_snapshot(
        server_key=server_key,
        server_version=PACKAGE_PRIVATE_MCP_VERSION,
        original_tool_name=original_tool_name,
        input_schema=package_private_mcp_tool_input_schema(original_tool_name),
        reserved_function_names=reserved_function_names,
    )
    return mcp_snapshot_to_execution_descriptor(
        snapshot,
        owner_extension_key=owner_extension_key,
    )


def mcp_snapshot_to_execution_descriptor(
    snapshot: McpToolSnapshot,
    *,
    owner_extension_key: str | None,
) -> ExecutionToolDescriptor:
    strict_schema = deepcopy(snapshot.strict_schema)
    schema_hash = _validated_descriptor_schema_hash(
        strict_schema,
        expected_hash=snapshot.schema_hash,
    )
    return ExecutionToolDescriptor(
        kind="mcp",
        tool_key=snapshot.frozen_tool_key,
        openai_function_name=snapshot.openai_function_name,
        description=f"External MCP tool {snapshot.original_tool_name}",
        strict_schema=strict_schema,
        schema_hash=schema_hash,
        redaction_policy=MCP_RUNTIME_REDACTION_POLICY,
        owner_extension_key=owner_extension_key,
        mcp_server_key=snapshot.mcp_server_key,
        mcp_server_version=snapshot.mcp_server_version,
        original_tool_name=snapshot.original_tool_name,
    )


def execution_tool_descriptor_to_payload(
    descriptor: ExecutionToolDescriptor,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": descriptor.kind,
        "toolKey": descriptor.tool_key,
        "openaiFunctionName": descriptor.openai_function_name,
        "description": descriptor.description,
        "strictSchema": deepcopy(descriptor.strict_schema),
        "schemaHash": descriptor.schema_hash,
        "redactionPolicy": descriptor.redaction_policy,
    }
    if descriptor.owner_extension_key is not None:
        payload["ownerExtensionKey"] = descriptor.owner_extension_key
    if descriptor.kind == "mcp":
        payload.update(
            {
                "mcpServerKey": descriptor.mcp_server_key,
                "mcpServerVersion": descriptor.mcp_server_version,
                "originalToolName": descriptor.original_tool_name,
            }
        )
    return payload


def execution_tool_descriptor_from_payload(
    payload: Mapping[str, object],
) -> ExecutionToolDescriptor:
    kind = _descriptor_kind(payload.get("kind"))
    strict_schema = _descriptor_schema(payload.get("strictSchema"))
    schema_hash = _validated_descriptor_schema_hash(
        strict_schema,
        expected_hash=_required_descriptor_text(payload.get("schemaHash"), field="schemaHash"),
    )
    redaction_policy = _descriptor_redaction_policy(payload.get("redactionPolicy"))
    descriptor = ExecutionToolDescriptor(
        kind=kind,
        tool_key=_required_descriptor_text(payload.get("toolKey"), field="toolKey"),
        openai_function_name=_required_descriptor_text(
            payload.get("openaiFunctionName"),
            field="openaiFunctionName",
        ),
        description=_required_descriptor_text(payload.get("description"), field="description"),
        strict_schema=strict_schema,
        schema_hash=schema_hash,
        redaction_policy=redaction_policy,
        owner_extension_key=_optional_descriptor_text(payload.get("ownerExtensionKey")),
        mcp_server_key=_optional_descriptor_text(payload.get("mcpServerKey")),
        mcp_server_version=_optional_descriptor_int(payload.get("mcpServerVersion")),
        original_tool_name=_optional_descriptor_text(payload.get("originalToolName")),
    )
    _validate_descriptor_shape(descriptor)
    return descriptor


def mcp_tool_snapshot_from_descriptor(descriptor: ExecutionToolDescriptor) -> McpToolSnapshot:
    if descriptor.kind != "mcp":
        raise McpToolAdapterError("MCP tool descriptor kind is required")
    if (
        descriptor.mcp_server_key is None
        or descriptor.mcp_server_version is None
        or descriptor.original_tool_name is None
    ):
        raise McpToolAdapterError("MCP tool descriptor identity is incomplete")
    return McpToolSnapshot.model_validate(
        {
            "mcpServerKey": descriptor.mcp_server_key,
            "mcpServerVersion": descriptor.mcp_server_version,
            "frozenToolKey": descriptor.tool_key,
            "originalToolName": descriptor.original_tool_name,
            "openaiFunctionName": descriptor.openai_function_name,
            "schemaHash": descriptor.schema_hash,
            "strictSchema": deepcopy(descriptor.strict_schema),
            "reverseMapping": {descriptor.openai_function_name: descriptor.original_tool_name},
        }
    )


def execution_tool_descriptor_to_signaldeck_tool_declaration(
    descriptor: ExecutionToolDescriptor,
) -> SignalDeckToolDeclaration:
    return SignalDeckToolDeclaration(
        kind=descriptor.kind,
        tool_key=descriptor.tool_key,
        model_name=descriptor.openai_function_name,
        description=descriptor.description,
        input_schema=deepcopy(descriptor.strict_schema),
        schema_hash=descriptor.schema_hash,
        strict=True,
        owner_extension_key=descriptor.owner_extension_key,
    )


def execution_tool_descriptor_to_openai_tool(
    descriptor: ExecutionToolDescriptor,
) -> dict[str, object]:
    declaration = execution_tool_descriptor_to_signaldeck_tool_declaration(descriptor)
    return {
        "type": "function",
        "name": declaration.model_name,
        "description": declaration.description,
        "strict": declaration.strict,
        "parameters": deepcopy(dict(declaration.input_schema)),
    }


def _descriptor_kind(value: object) -> ExecutionToolKind:
    if isinstance(value, str) and value in {"native_runtime", "mcp"}:
        return cast(ExecutionToolKind, value)
    raise McpToolAdapterError("Tool descriptor kind is invalid")


def _descriptor_redaction_policy(value: object) -> ExecutionToolRedactionPolicy:
    if isinstance(value, str) and value in {
        NATIVE_RUNTIME_REDACTION_POLICY,
        MCP_RUNTIME_REDACTION_POLICY,
    }:
        return cast(ExecutionToolRedactionPolicy, value)
    raise McpToolAdapterError("Tool descriptor redactionPolicy is invalid")


def _descriptor_schema(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise McpToolAdapterError("Tool descriptor strictSchema must be an object")
    return deepcopy(dict(value))


def _validated_descriptor_schema_hash(
    strict_schema: Mapping[str, object],
    *,
    expected_hash: str,
) -> str:
    computed_hash = hash_strict_schema(strict_schema)
    if computed_hash != expected_hash:
        raise McpToolAdapterError("Tool descriptor schemaHash does not match strictSchema")
    return expected_hash


def _required_descriptor_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise McpToolAdapterError(f"Tool descriptor {field} is required")
    return value.strip()


def _optional_descriptor_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise McpToolAdapterError("Optional tool descriptor text fields must be non-empty strings")
    return value.strip()


def _optional_descriptor_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise McpToolAdapterError("Optional tool descriptor integer fields must be integers")
    return value


def _validate_descriptor_shape(descriptor: ExecutionToolDescriptor) -> None:
    if descriptor.kind == "native_runtime":
        if descriptor.redaction_policy != NATIVE_RUNTIME_REDACTION_POLICY:
            raise McpToolAdapterError("Native runtime descriptor redactionPolicy is invalid")
        return
    if descriptor.redaction_policy != MCP_RUNTIME_REDACTION_POLICY:
        raise McpToolAdapterError("MCP descriptor redactionPolicy is invalid")
    if (
        descriptor.mcp_server_key is None
        or descriptor.mcp_server_version is None
        or descriptor.original_tool_name is None
    ):
        raise McpToolAdapterError("MCP descriptor identity is incomplete")


def _convert_schema_node(
    schema: object,
    *,
    path: str,
    require_object_root: bool = False,
) -> dict[str, object]:
    if not isinstance(schema, Mapping):
        raise McpToolAdapterError(f"{path} must be an object")
    raw = _string_key_mapping(schema, path=path)
    unsupported = sorted(set(raw) & _RESERVED_SCHEMA_KEYS)
    if unsupported:
        raise McpToolAdapterError(f"{path} contains unsupported keywords: {', '.join(unsupported)}")
    type_values = _schema_type_values(raw.get("type"), path=path)
    if require_object_root and "object" not in type_values:
        raise McpToolAdapterError("MCP input schema root must be object")
    converted: dict[str, object] = {"type": raw["type"]}
    optional_keys = ("description", "enum", "const", "minimum", "maximum", "minLength", "maxLength")
    for optional_key in optional_keys:
        if optional_key in raw:
            converted[optional_key] = deepcopy(raw[optional_key])
    if "object" in type_values:
        converted.update(_convert_object_schema(raw, path=path))
    if "array" in type_values:
        if "items" not in raw:
            raise McpToolAdapterError(f"{path}.items is required for arrays")
        converted["items"] = _convert_schema_node(raw["items"], path=f"{path}.items")
    allowed = {
        "type",
        "description",
        "enum",
        "const",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
    }
    if "object" in type_values:
        allowed.update({"properties", "required", "additionalProperties"})
    if "array" in type_values:
        allowed.add("items")
    extra = sorted(set(raw) - allowed)
    if extra:
        raise McpToolAdapterError(f"{path} contains unsupported keywords: {', '.join(extra)}")
    return converted


def _convert_object_schema(raw: Mapping[str, object], *, path: str) -> dict[str, object]:
    raw_properties = raw.get("properties", {})
    if not isinstance(raw_properties, Mapping):
        raise McpToolAdapterError(f"{path}.properties must be an object")
    properties = _string_key_mapping(raw_properties, path=f"{path}.properties")
    converted_properties = {
        key: _convert_schema_node(value, path=f"{path}.properties.{key}")
        for key, value in sorted(properties.items())
    }
    required = sorted(properties)
    return {
        "properties": converted_properties,
        "required": required,
        "additionalProperties": False,
    }


def _string_key_mapping(value: Mapping[object, object], *, path: str) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise McpToolAdapterError(f"{path} keys must be non-empty strings")
        normalized[key] = item
    return normalized


def _schema_type_values(raw_type: object, *, path: str) -> set[str]:
    if isinstance(raw_type, str):
        values = {raw_type}
    elif isinstance(raw_type, Sequence) and not isinstance(raw_type, (str, bytes, bytearray)):
        values = {str(item) for item in raw_type}
    else:
        raise McpToolAdapterError(f"{path}.type is required")
    supported = {"object", "array", "string", "number", "integer", "boolean", "null"}
    unsupported = sorted(values - supported)
    if unsupported:
        joined = ", ".join(unsupported)
        raise McpToolAdapterError(f"{path}.type contains unsupported values: {joined}")
    return values


def snapshot_to_openai_tool(snapshot: McpToolSnapshot) -> dict[str, object]:
    descriptor = mcp_snapshot_to_execution_descriptor(snapshot, owner_extension_key=None)
    return execution_tool_descriptor_to_openai_tool(descriptor)


__all__ = [
    "ExecutionToolDescriptor",
    "MCP_RUNTIME_REDACTION_POLICY",
    "McpToolAdapterError",
    "NATIVE_RUNTIME_REDACTION_POLICY",
    "PACKAGE_PRIVATE_MCP_VERSION",
    "SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS",
    "build_mcp_tool_snapshot",
    "build_native_runtime_tool_descriptor",
    "build_package_private_mcp_tool_descriptor",
    "convert_mcp_input_schema",
    "execution_tool_descriptor_from_payload",
    "execution_tool_descriptor_to_openai_tool",
    "execution_tool_descriptor_to_payload",
    "execution_tool_descriptor_to_signaldeck_tool_declaration",
    "hash_strict_schema",
    "mcp_snapshot_to_execution_descriptor",
    "mcp_tool_snapshot_from_descriptor",
    "normalize_mcp_openai_function_name",
    "package_private_mcp_tool_input_schema",
    "snapshot_to_openai_tool",
]
