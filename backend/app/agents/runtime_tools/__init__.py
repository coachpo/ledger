from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.agents.runtime_tools.declarations import (
    SignalDeckToolDeclaration,
    runtime_model_name_for_tool_key,
)
from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec

if TYPE_CHECKING:
    RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...]


def _load_runtime_tool_specs() -> tuple[RuntimeToolSpec, ...]:
    from app.extensions.registry import INSTALLED_EXTENSIONS

    return tuple(
        spec for extension in INSTALLED_EXTENSIONS for spec in extension.runtime_tool_specs
    )


@lru_cache
def get_default_runtime_tool_registry() -> RuntimeToolRegistry:
    return RuntimeToolRegistry(_load_runtime_tool_specs())


def __getattr__(name: str) -> object:
    if name == "RUNTIME_TOOL_SPECS":
        return _load_runtime_tool_specs()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RUNTIME_TOOL_SPECS",
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolRegistry",
    "RuntimeToolSpec",
    "SignalDeckToolDeclaration",
    "get_default_runtime_tool_registry",
    "runtime_model_name_for_tool_key",
]
