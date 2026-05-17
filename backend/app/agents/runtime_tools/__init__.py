from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec


def _load_runtime_tool_specs() -> tuple[RuntimeToolSpec, ...]:
    from app.extensions.registry import get_bundled_extension_registry

    return get_bundled_extension_registry().list_runtime_tool_contributions()


@lru_cache
def get_default_runtime_tool_registry() -> RuntimeToolRegistry:
    return RuntimeToolRegistry(_load_runtime_tool_specs())


def __getattr__(name: str) -> Any:
    if name == "RUNTIME_TOOL_SPECS":
        return _load_runtime_tool_specs()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RUNTIME_TOOL_SPECS",
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolRegistry",
    "RuntimeToolSpec",
    "get_default_runtime_tool_registry",
]
