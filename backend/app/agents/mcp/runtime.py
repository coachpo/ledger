from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import McpClientBoundary, build_mcp_client_boundary
from app.agents.mcp.security import redact_mcp_text
from app.agents.mcp.tool_adapter import hash_strict_schema, snapshot_to_openai_tool
from app.agents.runtime_tools.types import RuntimeToolError
from app.models.mcp_server import McpServer
from app.repositories.mcp_server import McpServerRepository
from app.schemas.mcp_server import McpToolSnapshot

_ALLOWED_RUNTIME_STATUSES = {"published", "deprecated"}
_MAX_MCP_OUTPUT_LENGTH = 16_384


@dataclass(frozen=True)
class McpRuntimeTool:
    boundary: McpClientBoundary
    snapshot: McpToolSnapshot


class McpToolClient(Protocol):
    def call_tool(
        self,
        *,
        boundary: McpClientBoundary,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object: ...


class DefaultMcpToolClient:
    def call_tool(
        self,
        *,
        boundary: McpClientBoundary,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        del boundary, tool_name, arguments, timeout_seconds
        raise RuntimeToolError(
            code="mcp_runtime_transport_unavailable",
            message="MCP runtime transport is not configured for this server tool.",
        )


class McpRuntimeDispatcher:
    def __init__(
        self,
        *,
        tools: Sequence[McpRuntimeTool],
        client: McpToolClient | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._tools_by_function_name = {tool.snapshot.openai_function_name: tool for tool in tools}
        self._client = client or DefaultMcpToolClient()
        self._timeout_seconds = timeout_seconds
        if len(self._tools_by_function_name) != len(tools):
            raise RuntimeToolError(
                code="mcp_tool_name_collision",
                message="MCP tool snapshots contain duplicate OpenAI function names.",
            )

    def get_openai_tools(self) -> list[dict[str, object]]:
        return [
            snapshot_to_openai_tool(tool.snapshot) for tool in self._tools_by_function_name.values()
        ]

    def dispatch(self, *, name: str, arguments_json: str) -> dict[str, object]:
        tool = self._tools_by_function_name.get(name)
        if tool is None:
            raise RuntimeToolError(
                code="mcp_tool_call_unsupported",
                message=f"Agent requested unsupported MCP server tool {name!r}.",
            )
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            raise RuntimeToolError(
                code="mcp_tool_arguments_invalid",
                message="MCP tool arguments must be valid JSON.",
            ) from exc
        if not isinstance(arguments, dict):
            raise RuntimeToolError(
                code="mcp_tool_arguments_invalid",
                message="MCP tool arguments must be a JSON object.",
            )
        result = self._client.call_tool(
            boundary=tool.boundary,
            tool_name=tool.snapshot.original_tool_name,
            arguments=cast(dict[str, object], arguments),
            timeout_seconds=self._timeout_seconds,
        )
        return _safe_mcp_tool_output(tool.snapshot, result)


class McpRuntimeResolver:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def build_dispatcher(
        self,
        *,
        mcp_server_refs: Sequence[Mapping[str, object]],
        client: McpToolClient | None = None,
        timeout_seconds: float = 5.0,
        enabled: bool,
    ) -> McpRuntimeDispatcher:
        if not enabled or not mcp_server_refs:
            return McpRuntimeDispatcher(tools=[], client=client, timeout_seconds=timeout_seconds)
        with self.session_factory() as session:
            repository = McpServerRepository(session)
            tools: list[McpRuntimeTool] = []
            seen_functions: set[str] = set()
            for ref in mcp_server_refs:
                server = _resolve_exact_runtime_server(repository, ref)
                boundary = build_mcp_client_boundary(server)
                for snapshot in _snapshots_from_server(server):
                    if snapshot.openai_function_name in seen_functions:
                        raise RuntimeToolError(
                            code="mcp_tool_name_collision",
                            message="MCP tool snapshots contain duplicate OpenAI function names.",
                        )
                    seen_functions.add(snapshot.openai_function_name)
                    tools.append(McpRuntimeTool(boundary=boundary, snapshot=snapshot))
        return McpRuntimeDispatcher(tools=tools, client=client, timeout_seconds=timeout_seconds)


def _resolve_exact_runtime_server(
    repository: McpServerRepository,
    ref: Mapping[str, object],
) -> McpServer:
    key = str(ref.get("mcpServerKey") or "").strip().lower()
    version = ref.get("mcpServerVersion")
    if not key or not isinstance(version, int):
        raise RuntimeToolError(
            code="mcp_server_pin_invalid",
            message="MCP runtime requires exact numeric server version pins.",
        )
    server = repository.get_by_key_version(key, version)
    if server is None:
        raise RuntimeToolError(
            code="mcp_server_missing",
            message=f"MCP server {key!r} version {version} was not found.",
        )
    if server.status not in _ALLOWED_RUNTIME_STATUSES:
        raise RuntimeToolError(
            code="mcp_server_status_invalid",
            message="MCP runtime only permits published or deprecated server versions.",
        )
    if not server.enabled:
        raise RuntimeToolError(
            code="mcp_server_disabled",
            message="MCP runtime only permits enabled server versions.",
        )
    return server


def _snapshots_from_server(server: McpServer) -> tuple[McpToolSnapshot, ...]:
    raw_snapshots = server.flat_config.get("toolSnapshots", [])
    if not isinstance(raw_snapshots, list):
        raise RuntimeToolError(
            code="mcp_tool_snapshots_invalid",
            message="MCP server tool snapshots must be a list.",
        )
    snapshots = tuple(McpToolSnapshot.model_validate(item) for item in raw_snapshots)
    if not snapshots:
        raise RuntimeToolError(
            code="mcp_tool_snapshots_missing",
            message="MCP runtime requires frozen publish-time tool snapshots.",
        )
    for snapshot in snapshots:
        if snapshot.mcp_server_key != server.key or snapshot.mcp_server_version != server.version:
            raise RuntimeToolError(
                code="mcp_tool_snapshot_drift",
                message="MCP tool snapshot identity does not match the pinned server version.",
            )
        if hash_strict_schema(snapshot.strict_schema) != snapshot.schema_hash:
            raise RuntimeToolError(
                code="mcp_tool_snapshot_drift",
                message="MCP tool snapshot schema hash does not match the frozen schema.",
            )
    return snapshots


def _safe_mcp_tool_output(snapshot: McpToolSnapshot, result: object) -> dict[str, object]:
    if isinstance(result, Mapping):
        payload: object = dict(result)
    else:
        payload = {"content": redact_mcp_text(result, max_length=_MAX_MCP_OUTPUT_LENGTH)}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    redacted = redact_mcp_text(serialized, max_length=_MAX_MCP_OUTPUT_LENGTH)
    return {
        "toolKey": snapshot.frozen_tool_key,
        "mcpServerKey": snapshot.mcp_server_key,
        "mcpServerVersion": snapshot.mcp_server_version,
        "originalToolName": snapshot.original_tool_name,
        "output": json.loads(redacted),
    }


__all__ = [
    "DefaultMcpToolClient",
    "McpRuntimeDispatcher",
    "McpRuntimeResolver",
    "McpRuntimeTool",
    "McpToolClient",
]
