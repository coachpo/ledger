from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.agents import ToolCatalog
from app.extensions.registry import BundledExtensionRegistry, get_bundled_extension_registry


@dataclass(frozen=True, slots=True)
class ExtensionDependency:
    extension_key: str
    surfaces: tuple[str, ...]
    fields: tuple[str, ...]


class ExtensionDependencyService:
    def __init__(
        self,
        *,
        tool_catalog: ToolCatalog | None = None,
        registry: BundledExtensionRegistry | None = None,
    ) -> None:
        self.tool_catalog = tool_catalog or ToolCatalog()
        self.registry = registry or get_bundled_extension_registry()

    def collect_compiled_plan_dependencies(
        self,
        compiled_plan: Mapping[str, Any],
    ) -> tuple[ExtensionDependency, ...]:
        dependencies: dict[str, dict[str, set[str]]] = {}
        self._collect_native_tool_dependencies(compiled_plan, dependencies)
        self._collect_package_private_mcp_dependencies(compiled_plan, dependencies)
        self._record_runtime_dependency_surfaces(dependencies)
        return self._dependency_tuple(dependencies)

    def infer_compiled_plan_dependencies(
        self,
        compiled_plan: Mapping[str, Any],
    ) -> tuple[ExtensionDependency, ...]:
        return self.collect_compiled_plan_dependencies(compiled_plan)

    def dependency_payloads(
        self,
        dependencies: tuple[ExtensionDependency, ...],
    ) -> list[dict[str, Any]]:
        return [self._dependency_payload(dependency) for dependency in dependencies]

    def compiled_plan_dependency_payloads(
        self,
        compiled_plan: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.dependency_payloads(self.collect_compiled_plan_dependencies(compiled_plan))

    def _collect_native_tool_dependencies(
        self,
        compiled_plan: Mapping[str, Any],
        dependencies: dict[str, dict[str, set[str]]],
    ) -> None:
        tool_specs = {tool.key: tool for tool in self.tool_catalog.list_known_tools()}
        runtime_specs = self._runtime_tool_specs_by_key()
        for profile in self._compiled_section(compiled_plan, "capabilityProfiles"):
            profile_key = str(profile.get("key") or "")
            raw_tool_keys = profile.get("toolKeys") or []
            if not isinstance(raw_tool_keys, list):
                continue
            for index, raw_tool_key in enumerate(raw_tool_keys):
                tool_key = str(raw_tool_key).strip().lower()
                field = f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
                tool_spec = tool_specs.get(tool_key)
                if tool_spec is not None and tool_spec.owner_extension_key is not None:
                    self._record_dependency(
                        dependencies,
                        extension_key=tool_spec.owner_extension_key,
                        surface=self._owner_qualified_tool_surface(tool_spec.key),
                        field=field,
                    )
                runtime_spec = runtime_specs.get(tool_key)
                if runtime_spec is not None and runtime_spec.owner_extension_key is not None:
                    self._record_dependency(
                        dependencies,
                        extension_key=runtime_spec.owner_extension_key,
                        surface=self._owner_qualified_runtime_tool_surface(
                            runtime_spec.key,
                        ),
                        field=field,
                    )

    def _collect_package_private_mcp_dependencies(
        self,
        compiled_plan: Mapping[str, Any],
        dependencies: dict[str, dict[str, set[str]]],
    ) -> None:
        mcp_tool_owners = self.registry.package_private_mcp_tool_owners()
        used_server_keys = self._agent_mcp_server_keys(compiled_plan)
        for server in self._compiled_section(compiled_plan, "mcpServers"):
            server_key = str(server.get("key") or "")
            if server_key not in used_server_keys:
                continue
            raw_tool_keys = server.get("toolKeys") or []
            if not isinstance(raw_tool_keys, list):
                continue
            frozen_tool_owners = self._package_private_mcp_descriptor_owners(server)
            for index, raw_tool_key in enumerate(raw_tool_keys):
                tool_key = str(raw_tool_key).strip().lower()
                extension_key = frozen_tool_owners.get(tool_key) or mcp_tool_owners.get(tool_key)
                if extension_key is None:
                    continue
                self._record_dependency(
                    dependencies,
                    extension_key=extension_key,
                    surface=f"mcp.packagePrivate.{tool_key}",
                    field=f"spec.mcpServers.{server_key}.toolKeys[{index}]",
                )

    def _record_runtime_dependency_surfaces(
        self,
        dependencies: dict[str, dict[str, set[str]]],
    ) -> None:
        for extension_key in tuple(dependencies):
            for surface in self.registry.runtime_dependency_surfaces_for_extensions(
                (extension_key,)
            ):
                self._record_dependency(
                    dependencies,
                    extension_key=extension_key,
                    surface=surface,
                )

    @staticmethod
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

    @staticmethod
    def _compiled_section(
        compiled_plan: Mapping[str, Any],
        name: str,
    ) -> list[dict[str, Any]]:
        raw_items = compiled_plan.get(name) or []
        return (
            [item for item in raw_items if isinstance(item, dict)]
            if isinstance(raw_items, list)
            else []
        )

    @staticmethod
    def _agent_mcp_server_keys(compiled_plan: Mapping[str, Any]) -> set[str]:
        server_keys: set[str] = set()
        for agent in ExtensionDependencyService._compiled_section(compiled_plan, "agents"):
            raw_server_keys = agent.get("mcpServers") or []
            if not isinstance(raw_server_keys, list):
                continue
            server_keys.update(str(server_key) for server_key in raw_server_keys)
        return server_keys

    @staticmethod
    def _runtime_tool_specs_by_key() -> dict[str, Any]:
        from app.agents.runtime_tools import RUNTIME_TOOL_SPECS

        return {spec.key: spec for spec in RUNTIME_TOOL_SPECS}

    @staticmethod
    def _owner_qualified_tool_surface(tool_key: str) -> str:
        return f"tool.{tool_key}"

    @staticmethod
    def _owner_qualified_runtime_tool_surface(tool_key: str) -> str:
        return f"runtime.tool.{tool_key}"

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def normalize_dependency_payloads(raw_dependencies: object) -> list[dict[str, Any]]:
        if not isinstance(raw_dependencies, list):
            return []

        dependencies: dict[str, dict[str, set[str]]] = {}
        for raw_dependency in raw_dependencies:
            if not isinstance(raw_dependency, Mapping):
                continue
            extension_key = str(raw_dependency.get("extensionKey") or "").strip()
            if not extension_key:
                continue
            for surface in ExtensionDependencyService._string_list(raw_dependency.get("surfaces")):
                ExtensionDependencyService._record_dependency(
                    dependencies,
                    extension_key=extension_key,
                    surface=surface,
                )
            for field in ExtensionDependencyService._string_list(raw_dependency.get("fields")):
                entry = dependencies.setdefault(
                    extension_key,
                    {"surfaces": set(), "fields": set()},
                )
                entry["fields"].add(field)
        return [
            ExtensionDependencyService._dependency_payload(dependency)
            for dependency in ExtensionDependencyService._dependency_tuple(dependencies)
        ]

    @staticmethod
    def _dependency_payload(dependency: ExtensionDependency) -> dict[str, Any]:
        return {
            "extensionKey": dependency.extension_key,
            "surfaces": list(dependency.surfaces),
            "fields": list(dependency.fields),
        }

    @staticmethod
    def _string_list(raw_values: object) -> list[str]:
        if not isinstance(raw_values, list):
            return []
        return [
            raw_value.strip()
            for raw_value in raw_values
            if isinstance(raw_value, str) and raw_value.strip()
        ]


__all__ = ["ExtensionDependency", "ExtensionDependencyService"]
