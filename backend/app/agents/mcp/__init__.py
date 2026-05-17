from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.mcp.boundaries import (
    DefaultMcpConnectionTester,
    McpClientBoundary,
    McpClientConfigError,
    McpConnectionTester,
    McpConnectionTestResult,
    build_mcp_client_boundary,
)

if TYPE_CHECKING:
    from app.agents.mcp.runtime import (
        DefaultMcpToolClient,
        McpRuntimeDispatcher,
        McpRuntimeResolver,
        McpToolClient,
    )

_RUNTIME_EXPORTS = {
    "DefaultMcpToolClient",
    "McpRuntimeDispatcher",
    "McpRuntimeResolver",
    "McpToolClient",
}


def __getattr__(name: str) -> Any:
    if name not in _RUNTIME_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from app.agents.mcp.runtime import (
        DefaultMcpToolClient,
        McpRuntimeDispatcher,
        McpRuntimeResolver,
        McpToolClient,
    )

    runtime_exports: dict[str, Any] = {
        "DefaultMcpToolClient": DefaultMcpToolClient,
        "McpRuntimeDispatcher": McpRuntimeDispatcher,
        "McpRuntimeResolver": McpRuntimeResolver,
        "McpToolClient": McpToolClient,
    }
    return runtime_exports[name]


__all__ = [
    "DefaultMcpConnectionTester",
    "DefaultMcpToolClient",
    "McpClientBoundary",
    "McpClientConfigError",
    "McpConnectionTestResult",
    "McpConnectionTester",
    "McpRuntimeDispatcher",
    "McpRuntimeResolver",
    "McpToolClient",
    "build_mcp_client_boundary",
]
