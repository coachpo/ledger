# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnnecessaryIsInstance=false, reportUnusedCallResult=false
from __future__ import annotations

from copy import deepcopy
from io import StringIO
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from app.schemas.workflow_package_manifest import WorkflowPackageManifest
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

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
    manifest_source = package_payload.get("manifestSource", package_payload.get("manifest_source"))
    if not isinstance(manifest_source, str):
        raise ValueError("manifestSource must be a string")
    compiled = compile_workflow_package_manifest(manifest_source)
    package_definition = cast(dict[str, object], compiled["packageDefinition"])
    sanitized_definition = _sanitize_package_definition(deepcopy(package_definition))
    if sanitized_definition == package_definition:
        return manifest_source
    safe_definition = build_safe_package_definition(compiled)
    return _dump_manifest_yaml(safe_definition)


def build_workflow_package_manifest_hydration_payload(
    package_payload: dict[str, Any],
) -> dict[str, object]:
    manifest_source = export_workflow_package_yaml(package_payload)
    safe_definition = build_safe_package_definition(
        compile_workflow_package_manifest(manifest_source)
    )
    safe_source = _dump_manifest_yaml(safe_definition)
    compiled = compile_workflow_package_manifest(safe_source)
    return {
        "manifestSource": safe_source,
        "packageDefinition": safe_definition,
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
        _sanitize_package_definition(
            manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
        ),
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
        sanitized_item = _sanitize_package_definition(item)
        if raw_key == "args" and sanitized_item == []:
            continue
        sanitized[raw_key] = sanitized_item
    return sanitized


def _literalize_system_prompts(package_definition: dict[str, object]) -> None:
    spec = package_definition.get("spec")
    if not isinstance(spec, dict):
        return
    agents = spec.get("agents")
    if not isinstance(agents, list):
        return
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        system_prompt = agent.get("systemPrompt")
        if isinstance(system_prompt, str) and "\n" in system_prompt:
            agent["systemPrompt"] = LiteralScalarString(system_prompt)


def _dump_manifest_yaml(manifest: dict[str, object]) -> str:
    literalized = deepcopy(manifest)
    _literalize_system_prompts(literalized)
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.representer.ignore_aliases = lambda *_args: True
    stream = StringIO()
    yaml.dump(literalized, stream)
    return stream.getvalue()


__all__ = [
    "build_safe_package_definition",
    "build_workflow_package_manifest_hydration_payload",
    "export_workflow_package_yaml",
]
