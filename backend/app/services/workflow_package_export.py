# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnusedCallResult=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from app.schemas.workflow_package_manifest import WorkflowPackageManifest
from app.services.workflow_package_manifest_compiler import (
    MCP_SECRET_PROJECTION_AUTHORING,
    compile_workflow_package_manifest,
)
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
    "url",
    "toolKeys",
}


def export_workflow_package_yaml(package_payload: dict[str, Any]) -> str:
    hydrated = build_workflow_package_manifest_hydration_payload(package_payload)
    return cast(str, hydrated["manifestSource"])


def build_workflow_package_manifest_hydration_payload(
    package_payload: dict[str, Any],
) -> dict[str, object]:
    safe_definition = build_safe_package_definition(package_payload)
    result = decompile_workflow_package_definition(
        safe_definition,
        verify_lossless=True,
        secret_projection_mode=MCP_SECRET_PROJECTION_AUTHORING,
    )
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


__all__ = [
    "build_safe_package_definition",
    "build_workflow_package_manifest_hydration_payload",
    "export_workflow_package_yaml",
]
