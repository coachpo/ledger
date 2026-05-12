# pyright: reportMissingImports=false, reportExplicitAny=false, reportAny=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

# Private MCP env, headers, and query maps are manifest data and must survive round-trips.
_FORBIDDEN_EXPORT_KEYS = {
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


class WorkflowPackageManifestDecompilerError(ValueError):
    pass


@dataclass(frozen=True)
class WorkflowPackageManifestDecompileResult:
    source: str
    package_definition: dict[str, object]


def decompile_workflow_package_manifest(
    package_payload: dict[str, Any],
    *,
    verify_lossless: bool = True,
) -> WorkflowPackageManifestDecompileResult:
    package_definition = _extract_package_definition(package_payload)
    package_definition = cast(dict[str, object], _strip_forbidden_fields(package_definition))
    _literalize_system_prompts(package_definition)
    source = _dump_manifest_yaml(package_definition)
    if verify_lossless:
        compiled = compile_workflow_package_manifest(source)
        if compiled["packageDefinition"] != _strip_literal_scalars(package_definition):
            raise WorkflowPackageManifestDecompilerError(
                "Decompiled workflow package manifest did not round-trip losslessly"
            )
    return WorkflowPackageManifestDecompileResult(
        source=source,
        package_definition=cast(dict[str, object], _strip_literal_scalars(package_definition)),
    )


def decompile_workflow_package_definition(
    package_definition: dict[str, object],
    *,
    verify_lossless: bool = True,
) -> WorkflowPackageManifestDecompileResult:
    return decompile_workflow_package_manifest(
        {"packageDefinition": package_definition},
        verify_lossless=verify_lossless,
    )


def _extract_package_definition(package_payload: dict[str, Any]) -> dict[str, object]:
    raw_definition = package_payload.get("packageDefinition", package_payload)
    if not isinstance(raw_definition, dict):
        raise WorkflowPackageManifestDecompilerError("packageDefinition must be an object")
    return cast(dict[str, object], raw_definition)


def _strip_forbidden_fields(value: object) -> object:
    if isinstance(value, dict):
        source = cast(dict[object, object], value)
        allow_local_id = (
            source.get("kind") in {"step", "sequence", "fanout", "loop"} or "node" in source
        )
        sanitized: dict[str, object] = {}
        is_mcp_server = "transport" in source and "key" in source and (
            "command" in source or "url" in source or "toolKeys" in source
        )
        for key, item in source.items():
            if not isinstance(key, str):
                continue
            if key == "id" and not allow_local_id:
                continue
            if key in _FORBIDDEN_EXPORT_KEYS:
                continue
            stripped_item = _strip_forbidden_fields(item)
            if is_mcp_server and key in {"args", "env", "headers", "query"}:
                if key == "args" and stripped_item == []:
                    continue
                if key != "args" and stripped_item == {}:
                    continue
            sanitized[key] = stripped_item
        return sanitized
    if isinstance(value, list):
        return [_strip_forbidden_fields(item) for item in value]
    return value


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


def _strip_literal_scalars(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _strip_literal_scalars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip_literal_scalars(item) for item in value]
    if isinstance(value, str):
        return str(value)
    return value


def _dump_manifest_yaml(manifest: dict[str, object]) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    yaml.dump(manifest, stream)
    return stream.getvalue()


__all__ = [
    "WorkflowPackageManifestDecompileResult",
    "WorkflowPackageManifestDecompilerError",
    "decompile_workflow_package_definition",
    "decompile_workflow_package_manifest",
]
