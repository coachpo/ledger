from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from importlib import import_module
from typing import Any, Protocol, cast

from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec


class _RuntimeContributionRegistry(Protocol):
    def list_runtime_tool_contributions(self) -> tuple[RuntimeToolSpec, ...]: ...


def _load_runtime_tool_specs() -> tuple[RuntimeToolSpec, ...]:
    memory_module = import_module("app.agents.runtime_tools.memory")
    registry_module = import_module("app.extensions.registry")
    core_specs = cast(
        tuple[RuntimeToolSpec, ...],
        memory_module.__dict__["CORE_MEMORY_RUNTIME_TOOL_SPECS"],
    )
    get_registry = cast(
        Callable[[], _RuntimeContributionRegistry],
        registry_module.__dict__["get_bundled_extension_registry"],
    )
    return (
        *core_specs,
        *get_registry().list_runtime_tool_contributions(),
    )


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
    "SignalDeckToolDeclaration",
    "get_default_runtime_tool_registry",
]
