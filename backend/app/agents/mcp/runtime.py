from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import McpClientBoundary, build_mcp_client_boundary_from_config
from app.agents.mcp.security import redact_mcp_text
from app.agents.mcp.tool_adapter import (
    PACKAGE_PRIVATE_MCP_VERSION,
    SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS,
    ExecutionToolDescriptor,
    McpToolAdapterError,
    execution_tool_descriptor_from_payload,
    execution_tool_descriptor_to_openai_tool,
    execution_tool_descriptor_to_signaldeck_tool_declaration,
    mcp_tool_snapshot_from_descriptor,
    package_private_mcp_tool_input_schema,
)
from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.failure_taxonomy import (
    MCP_TOOL_ARGUMENT_JSON_INVALID,
    MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
    MCP_TRANSPORT_FAILURE,
)
from app.agents.runtime_tools.types import RuntimeToolError
from app.core.errors import ApiError
from app.schemas.mcp_server import McpToolSnapshot
from app.services.extension_service import ExtensionService

_MAX_MCP_OUTPUT_LENGTH = 16_384


@dataclass(frozen=True)
class McpRuntimeTool:
    boundary: McpClientBoundary
    snapshot: McpToolSnapshot
    descriptor: ExecutionToolDescriptor


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
            execution_tool_descriptor_to_openai_tool(tool.descriptor)
            for tool in self._tools_by_function_name.values()
        ]

    def list_execution_descriptors(self) -> tuple[ExecutionToolDescriptor, ...]:
        return tuple(tool.descriptor for tool in self._tools_by_function_name.values())

    def list_tool_declarations(self) -> tuple[SignalDeckToolDeclaration, ...]:
        return tuple(
            execution_tool_descriptor_to_signaldeck_tool_declaration(tool.descriptor)
            for tool in self._tools_by_function_name.values()
        )

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
                failure_classification=MCP_TOOL_ARGUMENT_JSON_INVALID,
            ) from exc
        if not isinstance(arguments, dict):
            raise RuntimeToolError(
                code="mcp_tool_arguments_invalid",
                message="MCP tool arguments must be a JSON object.",
                failure_classification=MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
            )
        normalized_arguments = cast(dict[str, object], arguments)
        _validate_mcp_arguments_schema(tool, normalized_arguments)
        try:
            result = self._client.call_tool(
                boundary=tool.boundary,
                tool_name=tool.snapshot.original_tool_name,
                arguments=normalized_arguments,
                timeout_seconds=self._timeout_seconds,
            )
        except RuntimeToolError:
            raise
        except Exception as exc:
            raise RuntimeToolError(
                code="mcp_runtime_transport_error",
                message="MCP runtime transport failed while calling a server tool.",
                details=[
                    {
                        "field": "mcpTransport",
                        "issue": "Transport raised an exception",
                        "exceptionType": type(exc).__name__,
                    }
                ],
                failure_classification=MCP_TRANSPORT_FAILURE,
            ) from exc
        return _safe_mcp_tool_output(tool, result)


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
        reserved_function_names: Collection[str] | None = None,
    ) -> McpRuntimeDispatcher:
        if not enabled or not mcp_server_refs:
            return McpRuntimeDispatcher(tools=[], client=client, timeout_seconds=timeout_seconds)
        with self.session_factory() as session:
            extension_service = ExtensionService(session)
            tools: list[McpRuntimeTool] = []
            seen_functions: set[str] = set(reserved_function_names or ())
            for ref in mcp_server_refs:
                if not _is_package_private_ref(ref):
                    raise RuntimeToolError(
                        code="mcp_global_server_ref_removed",
                        message="Global MCP server references are not supported at runtime.",
                    )
                tools.extend(
                    _package_private_tools_from_ref(
                        ref,
                        seen_functions=seen_functions,
                        extension_service=extension_service,
                    )
                )
        return McpRuntimeDispatcher(tools=tools, client=client, timeout_seconds=timeout_seconds)


def _is_package_private_ref(ref: Mapping[str, object]) -> bool:
    return ref.get("packagePrivate") is True


def _package_private_tools_from_ref(
    ref: Mapping[str, object],
    *,
    seen_functions: set[str],
    extension_service: ExtensionService,
) -> list[McpRuntimeTool]:
    key = str(ref.get("key") or "").strip().lower()
    if not key:
        raise RuntimeToolError(
            code="mcp_server_pin_invalid",
            message="Package-private MCP runtime requires a server key.",
        )
    tool_names = _string_list(ref.get("toolKeys"))
    if not tool_names:
        raise RuntimeToolError(
            code="mcp_tool_snapshots_missing",
            message="Package-private MCP runtime requires declared tool keys.",
        )
    descriptors = _package_private_descriptors_from_ref(ref, server_key=key)
    config: dict[str, object] = {"transport": ref.get("transport")}
    if ref.get("command") is not None:
        config["command"] = ref.get("command")
    args = _string_list(ref.get("args"))
    if args:
        config["args"] = args
    if ref.get("url") is not None:
        config["url"] = ref.get("url")
    if ref.get("env"):
        config["env"] = ref.get("env")
    if ref.get("headers"):
        config["headers"] = ref.get("headers")
    if ref.get("query"):
        config["query"] = ref.get("query")
    boundary = build_mcp_client_boundary_from_config(
        config,
        server_id=None,
        key=key,
        version=PACKAGE_PRIVATE_MCP_VERSION,
        name=str(ref.get("name") or key),
        enabled=True,
        allow_secret_query_names=True,
    )
    tools: list[McpRuntimeTool] = []
    for tool_name in tool_names:
        descriptor = _package_private_descriptor_for_tool(
            tool_name,
            descriptors=descriptors,
            extension_service=extension_service,
        )
        _remember_openai_function(descriptor.openai_function_name, seen_functions)
        snapshot = _snapshot_from_descriptor(descriptor)
        tools.append(
            McpRuntimeTool(
                boundary=boundary,
                snapshot=snapshot,
                descriptor=descriptor,
            )
        )
    return tools


def _package_private_descriptors_from_ref(
    ref: Mapping[str, object],
    *,
    server_key: str,
) -> dict[str, ExecutionToolDescriptor]:
    raw_descriptors = ref.get("toolDescriptors")
    if not isinstance(raw_descriptors, Sequence) or isinstance(
        raw_descriptors,
        (str, bytes, bytearray),
    ):
        return {}
    descriptors: dict[str, ExecutionToolDescriptor] = {}
    for index, raw_descriptor in enumerate(raw_descriptors):
        if not isinstance(raw_descriptor, Mapping):
            raise RuntimeToolError(
                code="mcp_tool_descriptor_invalid",
                message=f"Package-private MCP tool descriptor {index} must be an object.",
            )
        try:
            descriptor = execution_tool_descriptor_from_payload(raw_descriptor)
        except McpToolAdapterError as exc:
            raise RuntimeToolError(
                code="mcp_tool_descriptor_invalid",
                message=str(exc),
            ) from exc
        _validate_package_private_descriptor(descriptor, server_key=server_key)
        original_tool_name = descriptor.original_tool_name or ""
        if original_tool_name in descriptors:
            raise RuntimeToolError(
                code="mcp_tool_name_collision",
                message="MCP tool snapshots contain duplicate OpenAI function names.",
            )
        descriptors[original_tool_name] = descriptor
    return descriptors


def _validate_package_private_descriptor(
    descriptor: ExecutionToolDescriptor,
    *,
    server_key: str,
) -> None:
    if descriptor.kind != "mcp" or descriptor.mcp_server_key != server_key:
        raise RuntimeToolError(
            code="mcp_tool_descriptor_invalid",
            message="Package-private MCP tool descriptor server identity is invalid.",
        )
    if descriptor.mcp_server_version != PACKAGE_PRIVATE_MCP_VERSION:
        raise RuntimeToolError(
            code="mcp_tool_descriptor_invalid",
            message="Package-private MCP tool descriptor version is invalid.",
        )


def _package_private_descriptor_for_tool(
    tool_name: str,
    *,
    descriptors: Mapping[str, ExecutionToolDescriptor],
    extension_service: ExtensionService,
) -> ExecutionToolDescriptor:
    normalized_tool_name = tool_name.strip().lower()
    try:
        _ = package_private_mcp_tool_input_schema(normalized_tool_name)
    except McpToolAdapterError as exc:
        raise RuntimeToolError(code="mcp_tool_schema_missing", message=str(exc)) from exc
    descriptor = descriptors.get(normalized_tool_name)
    if descriptor is None:
        raise RuntimeToolError(
            code="mcp_tool_descriptor_missing",
            message=f"Package-private MCP tool {normalized_tool_name!r} is missing its descriptor.",
        )
    _require_package_private_descriptor_owner(
        descriptor,
        extension_service=extension_service,
        tool_name=normalized_tool_name,
    )
    return descriptor


def _require_package_private_descriptor_owner(
    descriptor: ExecutionToolDescriptor,
    *,
    extension_service: ExtensionService,
    tool_name: str,
) -> None:
    owner_extension_key = descriptor.owner_extension_key
    if owner_extension_key is None:
        raise RuntimeToolError(
            code="mcp_tool_owner_missing",
            message=f"Package-private MCP tool {tool_name!r} is missing extension ownership.",
        )
    try:
        _ = extension_service.require_enabled(
            owner_extension_key,
            surface=f"mcp.packagePrivate.{tool_name}",
        )
    except ApiError as exc:
        raise RuntimeToolError(
            code=exc.code,
            message=exc.message,
            details=[dict(detail) for detail in exc.details],
        ) from exc


def _snapshot_from_descriptor(descriptor: ExecutionToolDescriptor) -> McpToolSnapshot:
    try:
        return mcp_tool_snapshot_from_descriptor(descriptor)
    except McpToolAdapterError as exc:
        raise RuntimeToolError(code="mcp_tool_descriptor_invalid", message=str(exc)) from exc


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _remember_openai_function(function_name: str, seen_functions: set[str]) -> None:
    if function_name in seen_functions:
        raise RuntimeToolError(
            code="mcp_tool_name_collision",
            message="MCP tool snapshots contain duplicate OpenAI function names.",
        )
    seen_functions.add(function_name)


def _validate_mcp_arguments_schema(
    tool: McpRuntimeTool,
    arguments: dict[str, object],
) -> None:
    schema = tool.descriptor.strict_schema
    required = schema.get("required")
    if isinstance(required, list):
        missing = [item for item in required if isinstance(item, str) and item not in arguments]
        if missing:
            raise RuntimeToolError(
                code="mcp_tool_arguments_invalid",
                message="MCP tool arguments are missing required fields.",
                details=[
                    {"field": field, "issue": "Required field is missing"} for field in missing
                ],
                failure_classification=MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
            )
    properties = schema.get("properties")
    if isinstance(properties, dict):
        unknown = sorted(set(arguments) - {str(key) for key in properties})
        if unknown:
            raise RuntimeToolError(
                code="mcp_tool_arguments_invalid",
                message="MCP tool arguments include unsupported fields.",
                details=[{"field": field, "issue": "Unsupported field"} for field in unknown],
                failure_classification=MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
            )


def _safe_mcp_tool_output(tool: McpRuntimeTool, result: object) -> dict[str, object]:
    if isinstance(result, Mapping):
        payload: object = dict(result)
    else:
        payload = {"content": redact_mcp_text(result, max_length=_MAX_MCP_OUTPUT_LENGTH)}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    redacted = redact_mcp_text(serialized, max_length=_MAX_MCP_OUTPUT_LENGTH)
    return {
        "toolKey": tool.descriptor.tool_key,
        "mcpServerKey": tool.snapshot.mcp_server_key,
        "mcpServerVersion": tool.snapshot.mcp_server_version,
        "originalToolName": tool.snapshot.original_tool_name,
        "output": json.loads(redacted),
    }


__all__ = [
    "DefaultMcpToolClient",
    "McpRuntimeDispatcher",
    "McpRuntimeResolver",
    "McpRuntimeTool",
    "McpToolClient",
    "SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS",
]
