from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.agents.tool_catalog.server_declared import (
    SERVER_DECLARED_TOOL_REGISTRY,
    ServerDeclaredToolSpec,
)
from app.models.capability import Capability

_SERVER_DECLARED_TOOL_KEY_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,119}(?:\.[a-z][a-z0-9_]{0,119})+$"
)


@dataclass(frozen=True)
class ResolvedTool:
    key: str
    display_name: str
    description: str
    module: str
    owner_extension_key: str | None = None


@dataclass(frozen=True)
class ResolvedCapabilityToolset:
    capability_id: int
    capability_key: str
    capability_version: int
    name: str
    description: str
    tools: tuple[ResolvedTool, ...]


class ToolCatalogValidationError(ValueError):
    def __init__(self, details: Sequence[dict[str, object]]) -> None:
        super().__init__("Tool catalog validation failed")
        self.details: list[dict[str, object]] = [dict(detail) for detail in details]


class ToolCatalog:
    def __init__(
        self,
        tool_registry: Mapping[str, ServerDeclaredToolSpec] | None = None,
        *,
        enabled_extension_keys: Collection[str] | None = None,
    ) -> None:
        self.tool_registry: dict[str, ServerDeclaredToolSpec] = dict(
            tool_registry or SERVER_DECLARED_TOOL_REGISTRY
        )
        self.enabled_extension_keys: frozenset[str] | None = (
            None if enabled_extension_keys is None else frozenset(enabled_extension_keys)
        )

    def list_registered_tools(self) -> tuple[ResolvedTool, ...]:
        return tuple(
            self._to_resolved_tool(tool)
            for tool in sorted(self.tool_registry.values(), key=lambda item: item.key)
            if self._is_enabled_tool(tool)
        )

    def list_known_tools(self) -> tuple[ResolvedTool, ...]:
        return tuple(
            self._to_resolved_tool(tool)
            for tool in sorted(self.tool_registry.values(), key=lambda item: item.key)
        )

    def resolve_tool_keys(self, tool_keys: Sequence[object]) -> tuple[ResolvedTool, ...]:
        resolved_tools: list[ResolvedTool] = []
        seen_keys: set[str] = set()
        details: list[dict[str, object]] = []

        for index, raw_tool_key in enumerate(tool_keys):
            tool_key = self._normalize_tool_key_value(raw_tool_key, index=index, details=details)
            if tool_key is None:
                continue
            if tool_key in seen_keys:
                details.append(
                    {
                        "field": f"toolKeys.{index}",
                        "issue": f"Duplicate tool key {tool_key!r} is not allowed",
                    }
                )
                continue
            tool_spec = self.tool_registry.get(tool_key)
            if tool_spec is None:
                details.append(
                    {
                        "field": f"toolKeys.{index}",
                        "issue": f"Unknown server-declared tool {tool_key!r}",
                    }
                )
                continue
            if not self._is_enabled_tool(tool_spec):
                details.append(
                    self._disabled_tool_detail(field=f"toolKeys.{index}", tool_spec=tool_spec)
                )
                continue
            resolved_tools.append(self._to_resolved_tool(tool_spec))
            seen_keys.add(tool_key)

        if details:
            raise ToolCatalogValidationError(details)
        return tuple(resolved_tools)

    def resolve_tool_grants(
        self,
        tool_grants: Sequence[dict[str, Any]],
    ) -> tuple[ResolvedTool, ...]:
        resolved_tools: list[ResolvedTool] = []
        seen_keys: set[str] = set()
        details: list[dict[str, object]] = []

        for index, raw_grant in enumerate(tool_grants):
            tool_key = self._normalize_tool_key(raw_grant, index=index, details=details)
            if tool_key is None:
                continue
            if tool_key in seen_keys:
                details.append(
                    {
                        "field": f"toolGrants.{index}.tool",
                        "issue": f"Duplicate tool reference {tool_key!r} is not allowed",
                    }
                )
                continue
            tool_spec = self.tool_registry.get(tool_key)
            if tool_spec is None:
                details.append(
                    {
                        "field": f"toolGrants.{index}.tool",
                        "issue": f"Unknown server-declared tool {tool_key!r}",
                    }
                )
                continue
            if not self._is_enabled_tool(tool_spec):
                details.append(
                    self._disabled_tool_detail(
                        field=f"toolGrants.{index}.tool",
                        tool_spec=tool_spec,
                    )
                )
                continue
            resolved_tools.append(self._to_resolved_tool(tool_spec))
            seen_keys.add(tool_key)

        if details:
            raise ToolCatalogValidationError(details)
        return tuple(resolved_tools)

    def resolve_capability(self, capability: Capability) -> ResolvedCapabilityToolset:
        resolved_tools = self.resolve_tool_keys(capability.tool_keys)
        return ResolvedCapabilityToolset(
            capability_id=capability.id,
            capability_key=capability.key,
            capability_version=capability.version,
            name=capability.name,
            description=capability.description,
            tools=resolved_tools,
        )

    @staticmethod
    def _normalize_tool_key(
        raw_grant: dict[str, Any],
        *,
        index: int,
        details: list[dict[str, object]],
    ) -> str | None:
        if not isinstance(raw_grant, dict):
            details.append(
                {
                    "field": f"toolGrants.{index}",
                    "issue": "Tool grants must be objects",
                }
            )
            return None
        raw_tool_key = raw_grant.get("tool")
        normalized_tool_key = str(raw_tool_key).strip().lower() if raw_tool_key is not None else ""
        if not normalized_tool_key:
            details.append(
                {
                    "field": f"toolGrants.{index}.tool",
                    "issue": "Tool key is required",
                }
            )
            return None
        return normalized_tool_key

    @staticmethod
    def _normalize_tool_key_value(
        raw_tool_key: object,
        *,
        index: int,
        details: list[dict[str, object]],
    ) -> str | None:
        if not isinstance(raw_tool_key, str):
            details.append(
                {
                    "field": f"toolKeys.{index}",
                    "issue": "Tool key must be a string",
                }
            )
            return None
        normalized_tool_key = raw_tool_key.strip().lower()
        if not normalized_tool_key:
            details.append(
                {
                    "field": f"toolKeys.{index}",
                    "issue": "Tool key is required",
                }
            )
            return None
        if _SERVER_DECLARED_TOOL_KEY_PATTERN.fullmatch(normalized_tool_key) is None:
            details.append(
                {
                    "field": f"toolKeys.{index}",
                    "issue": "Tool key must use dot-separated lowercase identifiers",
                }
            )
            return None
        return normalized_tool_key

    def _is_enabled_tool(self, tool_spec: ServerDeclaredToolSpec) -> bool:
        if self.enabled_extension_keys is None or tool_spec.owner_extension_key is None:
            return True
        return tool_spec.owner_extension_key in self.enabled_extension_keys

    @staticmethod
    def _disabled_tool_detail(
        *,
        field: str,
        tool_spec: ServerDeclaredToolSpec,
    ) -> dict[str, object]:
        extension_key = tool_spec.owner_extension_key or "unknown"
        return {
            "field": field,
            "issue": (
                f"Server-declared tool {tool_spec.key!r} is disabled because extension "
                f"{extension_key!r} is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": extension_key,
            "surface": f"tool.{tool_spec.key}",
        }

    @staticmethod
    def _to_resolved_tool(tool_spec: ServerDeclaredToolSpec) -> ResolvedTool:
        return ResolvedTool(
            key=tool_spec.key,
            display_name=tool_spec.display_name,
            description=tool_spec.description,
            module=tool_spec.module,
            owner_extension_key=tool_spec.owner_extension_key,
        )


@lru_cache
def get_default_tool_catalog() -> ToolCatalog:
    return ToolCatalog()


__all__ = [
    "ResolvedCapabilityToolset",
    "ResolvedTool",
    "ToolCatalog",
    "ToolCatalogValidationError",
    "get_default_tool_catalog",
]
