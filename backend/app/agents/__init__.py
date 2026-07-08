from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.tool_catalog import (
        ResolvedCapabilityToolset,
        ResolvedTool,
        ToolCatalog,
        ToolCatalogValidationError,
        get_default_tool_catalog,
    )

__all__ = [
    "ResolvedCapabilityToolset",
    "ResolvedTool",
    "ToolCatalog",
    "ToolCatalogValidationError",
    "get_default_tool_catalog",
]

_TOOL_CATALOG_EXPORTS = set(__all__)


def __getattr__(name: str) -> Any:
    if name in _TOOL_CATALOG_EXPORTS:
        from app.agents import tool_catalog

        return getattr(tool_catalog, name)
    raise AttributeError(name)
