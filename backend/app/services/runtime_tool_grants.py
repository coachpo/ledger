from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from app.agents import ResolvedTool, ToolCatalog, ToolCatalogValidationError


@dataclass(frozen=True, slots=True)
class RuntimeToolGrantPolicy:
    tool_key: str
    denied_code: str
    denied_message: str


class RuntimeToolGrantError(Exception):
    code: str
    message: str
    details: list[dict[str, str]]

    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])


class RuntimeToolGrantService:
    tool_catalog: ToolCatalog

    def __init__(self, tool_catalog: ToolCatalog) -> None:
        self.tool_catalog = tool_catalog

    def resolve_granted_tool_keys(
        self,
        capability_references: Sequence[dict[str, object]],
    ) -> set[str]:
        granted_tool_keys: set[str] = set()
        for reference in capability_references:
            package_tool_keys = reference.get("toolKeys")
            if not isinstance(package_tool_keys, list):
                raise RuntimeToolGrantError(
                    code="capability_reference_removed",
                    message="Global capability references are not supported at runtime.",
                )
            for package_tool_key in cast(list[object], package_tool_keys):
                if isinstance(package_tool_key, str):
                    granted_tool_keys.add(package_tool_key)
        return {tool.key for tool in self._validate_tool_keys(granted_tool_keys)}

    def require_runtime_tool_grant(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
    ) -> None:
        granted_tool_keys = self.resolve_granted_tool_keys(capability_references)
        if grant_policy.tool_key not in granted_tool_keys:
            raise RuntimeToolGrantError(
                code=grant_policy.denied_code,
                message=grant_policy.denied_message,
            )

    def _validate_tool_keys(self, tool_keys: set[str]) -> tuple[ResolvedTool, ...]:
        try:
            return self.tool_catalog.resolve_tool_keys(sorted(tool_keys))
        except ToolCatalogValidationError as exc:
            raise RuntimeToolGrantError(
                code="capability_tool_keys_invalid",
                message="Capability contains stale or invalid tool keys.",
                details=[
                    {
                        "field": str(detail.get("field", "toolKeys")),
                        "issue": str(detail.get("issue", "Invalid tool key")),
                    }
                    for detail in exc.details
                ],
            ) from exc


__all__ = [
    "RuntimeToolGrantError",
    "RuntimeToolGrantPolicy",
    "RuntimeToolGrantService",
]
