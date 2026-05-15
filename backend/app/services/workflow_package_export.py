# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnusedCallResult=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.schemas.workflow_package_manifest import WorkflowPackageManifest
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_definition

_FORBIDDEN_EXPORT_KEYS = {
    "id",
    "agentId",
    "modelConnectionId",
    "outputSchemaId",
    "capabilityId",
    "mcpServerId",
    "apiKey",
    "secret",
    "secretPayload",
    "encrypted",
    "password",
    "runHistory",
}
_MCP_EXPORT_KEYS = {
    "key",
    "name",
    "description",
    "transport",
    "command",
    "args",
    "env",
    "url",
    "headers",
    "query",
    "toolKeys",
    "secretRefs",
    "requiredBindings",
}


def export_workflow_package_yaml(package_payload: dict[str, Any]) -> str:
    hydrated = build_workflow_package_manifest_hydration_payload(package_payload)
    return cast(str, hydrated["manifestSource"])


def build_workflow_package_manifest_hydration_payload(
    package_payload: dict[str, Any],
) -> dict[str, object]:
    safe_definition = build_safe_package_definition(package_payload)
    result = decompile_workflow_package_definition(safe_definition, verify_lossless=True)
    compiled = compile_workflow_package_manifest(result.source)
    return {
        "manifestSource": result.source,
        "packageDefinition": result.package_definition,
        "manifestHash": str(compiled["manifestHash"]),
        "compiledHash": str(compiled["compiledHash"]),
    }


def build_safe_package_definition(package_payload: dict[str, Any]) -> dict[str, object]:
    raw_definition = package_payload.get("packageDefinition", package_payload)
    if not isinstance(raw_definition, dict):
        raise ValueError("packageDefinition must be an object")
    sanitized = _sanitize_package_definition(deepcopy(raw_definition))
    manifest = WorkflowPackageManifest.model_validate(sanitized)
    return cast(
        dict[str, object],
        manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def _sanitize_package_definition(value: object) -> object:
    if isinstance(value, dict):
        source = value
        if _looks_like_mcp_server(source):
            return _sanitize_mcp_server(source)
        sanitized: dict[str, object] = {}
        allow_local_id = (
            source.get("kind") in {"step", "http", "sequence", "fanout", "loop"} or "node" in source
        )
        for raw_key, item in source.items():
            if not isinstance(raw_key, str):
                continue
            if raw_key == "id" and allow_local_id:
                sanitized[raw_key] = _sanitize_package_definition(item)
                continue
            if raw_key in _FORBIDDEN_EXPORT_KEYS:
                continue
            sanitized[raw_key] = _sanitize_package_definition(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_package_definition(item) for item in value]
    return value


def _looks_like_mcp_server(value: dict[Any, Any]) -> bool:
    if "transport" not in value:
        return False
    return "key" in value and ("command" in value or "url" in value or "toolKeys" in value)


def _sanitize_mcp_server(server: dict[Any, Any]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for raw_key, item in server.items():
        if not isinstance(raw_key, str) or raw_key not in _MCP_EXPORT_KEYS:
            continue
        sanitized[raw_key] = _sanitize_package_definition(item)
    return sanitized


def _secret_metadata_from_raw_mcp(server: dict[Any, Any]) -> tuple[dict[str, list[str]], list[str]]:
    refs: dict[str, list[str]] = {}
    required: list[str] = []
    for section in ("env", "headers"):
        raw_mapping = server.get(section)
        if not isinstance(raw_mapping, dict):
            continue
        names = sorted(str(key) for key, value in raw_mapping.items() if str(key).strip() and value)
        if names:
            refs[section] = names
            prefix = "env" if section == "env" else "header"
            required.extend(f"{prefix}.{name}" for name in names)
    raw_auth = server.get("auth")
    if isinstance(raw_auth, dict):
        header = raw_auth.get("header")
        if isinstance(header, str) and header.strip():
            refs.setdefault("headers", [])
            if header.strip() not in refs["headers"]:
                refs["headers"].append(header.strip())
            required.append(f"header.{header.strip()}")
    return {key: sorted(set(values)) for key, values in refs.items()}, sorted(set(required))


def _sanitize_secret_metadata(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): sorted(set(_string_list(item)))
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, list):
        return sorted(set(_string_list(value)))
    return None


def _merge_secret_refs(
    left: dict[str, object], right: dict[str, list[str]]
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key, value in left.items():
        if isinstance(key, str):
            merged[key] = _string_list(value)
    for key, values in right.items():
        merged[key] = sorted(set(merged.get(key, [])) | set(values))
    return {key: values for key, values in merged.items() if values}


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        normalized = str(item).strip()
        if normalized:
            result.append(normalized)
    return result


__all__ = [
    "build_safe_package_definition",
    "build_workflow_package_manifest_hydration_payload",
    "export_workflow_package_yaml",
]
