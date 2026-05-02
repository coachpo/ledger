from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy

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
    return {
        "type": "function",
        "name": snapshot.openai_function_name,
        "description": f"External MCP tool {snapshot.original_tool_name}",
        "strict": True,
        "parameters": deepcopy(snapshot.strict_schema),
    }


__all__ = [
    "McpToolAdapterError",
    "build_mcp_tool_snapshot",
    "convert_mcp_input_schema",
    "hash_strict_schema",
    "normalize_mcp_openai_function_name",
    "snapshot_to_openai_tool",
]
