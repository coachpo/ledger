from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import (
    McpClientBoundary,
    build_mcp_client_boundary,
    build_mcp_client_boundary_from_config,
)
from app.agents.mcp.security import redact_mcp_text
from app.agents.mcp.tool_adapter import (
    PACKAGE_PRIVATE_MCP_VERSION,
    SUPPORTED_PACKAGE_PRIVATE_MCP_TOOL_KEYS,
    ExecutionToolDescriptor,
    McpToolAdapterError,
    execution_tool_descriptor_from_payload,
    execution_tool_descriptor_to_openai_tool,
    execution_tool_descriptor_to_signaldeck_tool_declaration,
    mcp_snapshot_to_execution_descriptor,
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
from app.models.mcp_server import McpServer
from app.repositories.mcp_server import McpServerRepository
from app.schemas.mcp_server import McpToolSnapshot
from app.services.extension_service import ExtensionService

_ALLOWED_RUNTIME_STATUSES = {"published", "deprecated"}
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
            repository = McpServerRepository(session)
            extension_service = ExtensionService(session)
            tools: list[McpRuntimeTool] = []
            seen_functions: set[str] = set(reserved_function_names or ())
            for ref in mcp_server_refs:
                if _is_package_private_ref(ref):
                    tools.extend(
                        _package_private_tools_from_ref(
                            ref,
                            seen_functions=seen_functions,
                            extension_service=extension_service,
                        )
                    )
                    continue
                server = _resolve_exact_runtime_server(repository, ref)
                boundary = build_mcp_client_boundary(server)
                for snapshot in _snapshots_from_server(server):
                    descriptor = _descriptor_from_saved_snapshot(snapshot)
                    _remember_openai_function(descriptor.openai_function_name, seen_functions)
                    tools.append(
                        McpRuntimeTool(
                            boundary=boundary,
                            snapshot=snapshot,
                            descriptor=descriptor,
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
        _ = _descriptor_from_saved_snapshot(snapshot)
    return snapshots


def _descriptor_from_saved_snapshot(snapshot: McpToolSnapshot) -> ExecutionToolDescriptor:
    try:
        return mcp_snapshot_to_execution_descriptor(snapshot, owner_extension_key=None)
    except McpToolAdapterError as exc:
        raise RuntimeToolError(
            code="mcp_tool_snapshot_drift",
            message=str(exc),
        ) from exc


def _validate_mcp_arguments_schema(
    tool: McpRuntimeTool,
    arguments: Mapping[str, object],
) -> None:
    schema = tool.descriptor.strict_schema
    if not schema:
        return
    details: list[dict[str, object]] = []
    _collect_schema_validation_details(arguments, schema, path="$", details=details)
    if details:
        raise RuntimeToolError(
            code="mcp_tool_arguments_invalid",
            message="MCP tool arguments failed schema validation.",
            details=details,
            failure_classification=MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
        )


def _collect_schema_validation_details(
    value: object,
    schema: Mapping[str, object],
    *,
    path: str,
    details: list[dict[str, object]],
) -> None:
    if len(details) >= 5:
        return
    type_values = _schema_type_values(schema.get("type"))
    if type_values and not any(_matches_schema_type(value, item) for item in type_values):
        expected = ", ".join(sorted(type_values))
        _add_schema_detail(details, path, f"Expected {expected} value")
        return
    if "const" in schema and value != schema["const"]:
        _add_schema_detail(details, path, "Value does not match required constant")
        return
    enum_values = schema.get("enum")
    if isinstance(enum_values, Sequence) and not isinstance(enum_values, (str, bytes, bytearray)):
        if value not in enum_values:
            _add_schema_detail(details, path, "Value is not in the allowed enum")
            return
    if isinstance(value, Mapping) and "object" in type_values:
        _collect_object_schema_details(value, schema, path=path, details=details)
    if isinstance(value, list) and "array" in type_values:
        items_schema = schema.get("items")
        if isinstance(items_schema, Mapping):
            for index, item in enumerate(value):
                _collect_schema_validation_details(
                    item,
                    items_schema,
                    path=f"{path}[{index}]",
                    details=details,
                )
                if len(details) >= 5:
                    return
    _collect_scalar_schema_details(value, schema, path=path, details=details)


def _collect_object_schema_details(
    value: Mapping[object, object],
    schema: Mapping[str, object],
    *,
    path: str,
    details: list[dict[str, object]],
) -> None:
    raw_properties = schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    required = _string_sequence(schema.get("required"))
    for field_name in required:
        if field_name not in value:
            _add_schema_detail(details, f"{path}.{field_name}", "Required field is missing")
    if schema.get("additionalProperties") is False:
        unexpected = sorted(str(key) for key in set(value) - set(properties))
        for field_name in unexpected:
            _add_schema_detail(details, f"{path}.{field_name}", "Field is not allowed")
    for field_name, field_schema in properties.items():
        if field_name in value and isinstance(field_schema, Mapping):
            _collect_schema_validation_details(
                value[field_name],
                field_schema,
                path=f"{path}.{field_name}",
                details=details,
            )
            if len(details) >= 5:
                return


def _collect_scalar_schema_details(
    value: object,
    schema: Mapping[str, object],
    *,
    path: str,
    details: list[dict[str, object]],
) -> None:
    if isinstance(value, str):
        min_length = _numeric_constraint(schema.get("minLength"))
        max_length = _numeric_constraint(schema.get("maxLength"))
        if min_length is not None and len(value) < min_length:
            _add_schema_detail(details, path, f"String length must be at least {int(min_length)}")
        if max_length is not None and len(value) > max_length:
            _add_schema_detail(details, path, f"String length must be at most {int(max_length)}")
    if _is_json_number(value):
        minimum = _numeric_constraint(schema.get("minimum"))
        maximum = _numeric_constraint(schema.get("maximum"))
        number_value = cast(int | float, value)
        if minimum is not None and number_value < minimum:
            _add_schema_detail(details, path, f"Value must be at least {minimum:g}")
        if maximum is not None and number_value > maximum:
            _add_schema_detail(details, path, f"Value must be at most {maximum:g}")


def _schema_type_values(raw_type: object) -> set[str]:
    if isinstance(raw_type, str):
        return {raw_type}
    if isinstance(raw_type, Sequence) and not isinstance(raw_type, (str, bytes, bytearray)):
        return {str(item) for item in raw_type}
    return set()


def _matches_schema_type(value: object, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, Mapping)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return _is_json_number(value)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _is_json_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_constraint(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str))


def _add_schema_detail(details: list[dict[str, object]], path: str, issue: str) -> None:
    if len(details) >= 5:
        return
    details.append({"field": _schema_detail_field(path), "issue": issue})


def _schema_detail_field(path: str) -> str:
    if path == "$":
        return "arguments"
    return "arguments" + path.removeprefix("$")


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
