from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.agents import ToolCatalog


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
    ) -> None:
        self.tool_catalog = tool_catalog or ToolCatalog()

    def infer_compiled_plan_dependencies(
        self,
        compiled_plan: Mapping[str, Any],
    ) -> tuple[ExtensionDependency, ...]:
        dependencies: dict[str, dict[str, set[str]]] = {}
        tool_specs = {tool.key: tool for tool in self.tool_catalog.list_known_tools()}
        for profile in self._compiled_section(compiled_plan, "capabilityProfiles"):
            profile_key = str(profile.get("key") or "")
            raw_tool_keys = profile.get("toolKeys") or []
            if not isinstance(raw_tool_keys, list):
                continue
            for index, raw_tool_key in enumerate(raw_tool_keys):
                tool_key = str(raw_tool_key).strip().lower()
                tool_spec = tool_specs.get(tool_key)
                if tool_spec is None or tool_spec.owner_extension_key is None:
                    continue
                self._record_dependency(
                    dependencies,
                    extension_key=tool_spec.owner_extension_key,
                    surface=f"tool.{tool_spec.key}",
                    field=f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]",
                )
        return self._dependency_tuple(dependencies)

    def dependency_payloads(
        self,
        dependencies: tuple[ExtensionDependency, ...],
    ) -> list[dict[str, Any]]:
        return [self._dependency_payload(dependency) for dependency in dependencies]

    def compiled_plan_dependency_payloads(
        self,
        compiled_plan: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return self.dependency_payloads(self.infer_compiled_plan_dependencies(compiled_plan))

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
    def _record_dependency(
        dependencies: dict[str, dict[str, set[str]]],
        *,
        extension_key: str,
        surface: str,
        field: str,
    ) -> None:
        entry = dependencies.setdefault(
            extension_key,
            {"surfaces": set(), "fields": set()},
        )
        entry["surfaces"].add(surface)
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

        normalized: list[dict[str, Any]] = []
        for raw_dependency in raw_dependencies:
            if not isinstance(raw_dependency, Mapping):
                continue
            extension_key = str(raw_dependency.get("extensionKey") or "").strip()
            if not extension_key:
                continue
            normalized.append(
                {
                    "extensionKey": extension_key,
                    "surfaces": ExtensionDependencyService._string_list(
                        raw_dependency.get("surfaces")
                    ),
                    "fields": ExtensionDependencyService._string_list(raw_dependency.get("fields")),
                }
            )
        return normalized

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
        return [str(raw_value) for raw_value in raw_values if isinstance(raw_value, str)]


__all__ = ["ExtensionDependency", "ExtensionDependencyService"]
