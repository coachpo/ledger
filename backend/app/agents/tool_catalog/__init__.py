from __future__ import annotations

import re
from collections.abc import Sequence
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


@dataclass(frozen=True)
class ResolvedCapabilityToolset:
    capability_id: int
    capability_key: str
    capability_version: int
    name: str
    description: str
    tools: tuple[ResolvedTool, ...]


class ToolCatalogValidationError(ValueError):
    def __init__(self, details: Sequence[dict[str, str]]) -> None:
        super().__init__("Tool catalog validation failed")
        self.details = list(details)


class ToolCatalog:
    def __init__(self, tool_registry: dict[str, ServerDeclaredToolSpec] | None = None) -> None:
        self.tool_registry = dict(tool_registry or SERVER_DECLARED_TOOL_REGISTRY)

    def list_registered_tools(self) -> tuple[ResolvedTool, ...]:
        return tuple(
            ResolvedTool(
                key=tool.key,
                display_name=tool.display_name,
                description=tool.description,
                module=tool.module,
            )
            for tool in sorted(self.tool_registry.values(), key=lambda item: item.key)
        )

    def resolve_tool_keys(self, tool_keys: Sequence[object]) -> tuple[ResolvedTool, ...]:
        resolved_tools: list[ResolvedTool] = []
        seen_keys: set[str] = set()
        details: list[dict[str, str]] = []

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
        details: list[dict[str, str]] = []

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
        details: list[dict[str, str]],
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
        details: list[dict[str, str]],
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

    @staticmethod
    def _to_resolved_tool(tool_spec: ServerDeclaredToolSpec) -> ResolvedTool:
        return ResolvedTool(
            key=tool_spec.key,
            display_name=tool_spec.display_name,
            description=tool_spec.description,
            module=tool_spec.module,
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
