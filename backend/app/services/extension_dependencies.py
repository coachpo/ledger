from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.agents import ToolCatalog
from app.extensions.registry import (
    package_private_mcp_tool_owners,
    runtime_dependency_surfaces_for_extensions,
)


@dataclass(frozen=True, slots=True)
class ExtensionDependency:
    extension_key: str
    surfaces: tuple[str, ...]
    fields: tuple[str, ...]


def compiled_plan_extension_dependency_payloads(
    compiled_plan: Mapping[str, Any],
    *,
    tool_catalog: ToolCatalog,
) -> list[dict[str, Any]]:
    dependencies: dict[str, dict[str, set[str]]] = {}
    _collect_native_tool_dependencies(compiled_plan, dependencies, tool_catalog=tool_catalog)
    _collect_package_private_mcp_dependencies(compiled_plan, dependencies)
    _record_runtime_dependency_surfaces(dependencies)
    return [_dependency_payload(dependency) for dependency in _dependency_tuple(dependencies)]


def normalize_extension_dependency_payloads(raw_dependencies: object) -> list[dict[str, Any]]:
    if not isinstance(raw_dependencies, list):
        return []

    dependencies: dict[str, dict[str, set[str]]] = {}
    for raw_dependency in raw_dependencies:
        if not isinstance(raw_dependency, Mapping):
            continue
        extension_key = str(raw_dependency.get("extensionKey") or "").strip()
        if not extension_key:
            continue
        for surface in _string_list(raw_dependency.get("surfaces")):
            _record_dependency(dependencies, extension_key=extension_key, surface=surface)
        for field in _string_list(raw_dependency.get("fields")):
            entry = dependencies.setdefault(
                extension_key,
                {"surfaces": set(), "fields": set()},
            )
            entry["fields"].add(field)
    return [_dependency_payload(dependency) for dependency in _dependency_tuple(dependencies)]


def _collect_native_tool_dependencies(
    compiled_plan: Mapping[str, Any],
    dependencies: dict[str, dict[str, set[str]]],
    *,
    tool_catalog: ToolCatalog,
) -> None:
    tool_specs = {tool.key: tool for tool in tool_catalog.list_known_tools()}
    runtime_specs = _runtime_tool_specs_by_key()
    for profile in _compiled_section(compiled_plan, "capabilityProfiles"):
        profile_key = str(profile.get("key") or "")
        raw_tool_keys = profile.get("toolKeys") or []
        if not isinstance(raw_tool_keys, list):
            continue
        for index, raw_tool_key in enumerate(raw_tool_keys):
            tool_key = str(raw_tool_key).strip().lower()
            field = f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
            tool_spec = tool_specs.get(tool_key)
            if tool_spec is not None and tool_spec.owner_extension_key is not None:
                _record_dependency(
                    dependencies,
                    extension_key=tool_spec.owner_extension_key,
                    surface=f"tool.{tool_spec.key}",
                    field=field,
                )
            runtime_spec = runtime_specs.get(tool_key)
            if runtime_spec is not None and runtime_spec.owner_extension_key is not None:
                _record_dependency(
                    dependencies,
                    extension_key=runtime_spec.owner_extension_key,
                    surface=f"runtime.tool.{runtime_spec.key}",
                    field=field,
                )


def _collect_package_private_mcp_dependencies(
    compiled_plan: Mapping[str, Any],
    dependencies: dict[str, dict[str, set[str]]],
) -> None:
    mcp_tool_owners = package_private_mcp_tool_owners()
    used_server_keys = _agent_mcp_server_keys(compiled_plan)
    for server in _compiled_section(compiled_plan, "mcpServers"):
        server_key = str(server.get("key") or "")
        if server_key not in used_server_keys:
            continue
        raw_tool_keys = server.get("toolKeys") or []
        if not isinstance(raw_tool_keys, list):
            continue
        frozen_tool_owners = _package_private_mcp_descriptor_owners(server)
        for index, raw_tool_key in enumerate(raw_tool_keys):
            tool_key = str(raw_tool_key).strip().lower()
            extension_key = frozen_tool_owners.get(tool_key) or mcp_tool_owners.get(tool_key)
            if extension_key is None:
                continue
            _record_dependency(
                dependencies,
                extension_key=extension_key,
                surface=f"mcp.packagePrivate.{tool_key}",
                field=f"spec.mcpServers.{server_key}.toolKeys[{index}]",
            )


def _record_runtime_dependency_surfaces(
    dependencies: dict[str, dict[str, set[str]]],
) -> None:
    for extension_key in tuple(dependencies):
        for surface in runtime_dependency_surfaces_for_extensions((extension_key,)):
            _record_dependency(dependencies, extension_key=extension_key, surface=surface)


def _package_private_mcp_descriptor_owners(server: Mapping[str, Any]) -> dict[str, str]:
    raw_descriptors = server.get("toolDescriptors") or []
    if not isinstance(raw_descriptors, list):
        return {}
    owners: dict[str, str] = {}
    for raw_descriptor in raw_descriptors:
        if not isinstance(raw_descriptor, Mapping):
            continue
        original_tool_name = str(raw_descriptor.get("originalToolName") or "").strip().lower()
        owner_extension_key = str(raw_descriptor.get("ownerExtensionKey") or "").strip()
        if original_tool_name and owner_extension_key:
            owners[original_tool_name] = owner_extension_key
    return owners


def _compiled_section(compiled_plan: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    raw_items = compiled_plan.get(name) or []
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def _agent_mcp_server_keys(compiled_plan: Mapping[str, Any]) -> set[str]:
    server_keys: set[str] = set()
    for agent in _compiled_section(compiled_plan, "agents"):
        raw_server_keys = agent.get("mcpServers") or []
        if isinstance(raw_server_keys, list):
            server_keys.update(str(server_key) for server_key in raw_server_keys)
    return server_keys


def _runtime_tool_specs_by_key() -> dict[str, Any]:
    from app.agents.runtime_tools import RUNTIME_TOOL_SPECS

    return {spec.key: spec for spec in RUNTIME_TOOL_SPECS}


def _record_dependency(
    dependencies: dict[str, dict[str, set[str]]],
    *,
    extension_key: str,
    surface: str,
    field: str | None = None,
) -> None:
    normalized_extension_key = extension_key.strip()
    normalized_surface = surface.strip()
    if not normalized_extension_key or not normalized_surface:
        return
    entry = dependencies.setdefault(
        normalized_extension_key,
        {"surfaces": set(), "fields": set()},
    )
    entry["surfaces"].add(normalized_surface)
    if field:
        entry["fields"].add(field)


def _dependency_tuple(
    dependencies: dict[str, dict[str, set[str]]],
) -> tuple[ExtensionDependency, ...]:
    return tuple(
        ExtensionDependency(
            extension_key=extension_key,
            surfaces=tuple(sorted(values["surfaces"])),
            fields=tuple(sorted(values["fields"])),
        )
        for extension_key, values in sorted(dependencies.items())
    )


def _dependency_payload(dependency: ExtensionDependency) -> dict[str, Any]:
    return {
        "extensionKey": dependency.extension_key,
        "surfaces": list(dependency.surfaces),
        "fields": list(dependency.fields),
    }


def _string_list(raw_values: object) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    return [
        raw_value.strip()
        for raw_value in raw_values
        if isinstance(raw_value, str) and raw_value.strip()
    ]


__all__ = [
    "ExtensionDependency",
    "compiled_plan_extension_dependency_payloads",
    "normalize_extension_dependency_payloads",
]
