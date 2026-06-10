from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.agents.mcp.security import McpSecurityError, validate_http_sse_url, validate_stdio_command
from app.core.config import get_settings


@dataclass(frozen=True)
class McpClientBoundary:
    server_id: int | None
    key: str
    version: int
    name: str
    transport: str
    enabled: bool
    command: tuple[str, ...] | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class McpConnectionTestResult:
    ok: bool
    message: str
    status_code: int | None = None


class McpServerConfigLike(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def key(self) -> str: ...

    @property
    def version(self) -> int: ...

    @property
    def name(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    @property
    def flat_config(self) -> Mapping[str, Any]: ...


class McpConnectionTester(Protocol):
    def test(self, boundary: McpClientBoundary) -> McpConnectionTestResult: ...


class McpClientConfigError(ValueError):
    def __init__(self, details: Sequence[dict[str, str]]) -> None:
        super().__init__("MCP client configuration is invalid")
        self.details = list(details)


class DefaultMcpConnectionTester:
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def test(self, boundary: McpClientBoundary) -> McpConnectionTestResult:
        if boundary.transport == "stdio":
            return self._test_stdio(boundary)
        return self._test_http_sse(boundary)

    def _test_stdio(self, boundary: McpClientBoundary) -> McpConnectionTestResult:
        if boundary.command is None or not boundary.command:
            return McpConnectionTestResult(ok=False, message="No stdio command was configured")
        executable = boundary.command[0]
        resolved_path = self._resolve_executable_path(executable)
        if resolved_path is None:
            return McpConnectionTestResult(
                ok=False,
                message=f"Configured stdio executable {executable!r} was not found",
            )
        return McpConnectionTestResult(
            ok=True,
            message=f"Resolved stdio executable at {resolved_path}",
        )

    def _test_http_sse(self, boundary: McpClientBoundary) -> McpConnectionTestResult:
        if boundary.url is None:
            return McpConnectionTestResult(ok=False, message="No HTTP/SSE URL was configured")
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                return self._test_http_sse_with_client(boundary, client)
        except httpx.HTTPError as exc:
            return McpConnectionTestResult(ok=False, message=str(exc))

    @staticmethod
    def _test_http_sse_with_client(
        boundary: McpClientBoundary,
        client: httpx.Client,
    ) -> McpConnectionTestResult:
        if boundary.url is None:
            return McpConnectionTestResult(ok=False, message="No HTTP/SSE URL was configured")
        headers = {"accept": "text/event-stream", **boundary.headers}
        with client.stream("GET", boundary.url, headers=headers) as response:
            if 300 <= response.status_code < 400:
                return McpConnectionTestResult(
                    ok=False,
                    message="MCP HTTP/SSE redirects are not followed",
                    status_code=response.status_code,
                )
            if 200 <= response.status_code < 300:
                return McpConnectionTestResult(
                    ok=True,
                    message=f"Received HTTP {response.status_code} from MCP endpoint",
                    status_code=response.status_code,
                )
            return McpConnectionTestResult(
                ok=False,
                message=f"Received HTTP {response.status_code} from MCP endpoint",
                status_code=response.status_code,
            )

    @staticmethod
    def _resolve_executable_path(executable: str) -> str | None:
        executable_path = Path(executable)
        if executable_path.is_absolute() or executable.startswith("."):
            return str(executable_path) if executable_path.exists() else None
        return shutil.which(executable)


def build_mcp_client_boundary(server: McpServerConfigLike) -> McpClientBoundary:
    return build_mcp_client_boundary_from_config(
        server.flat_config,
        server_id=server.id,
        key=server.key,
        version=server.version,
        name=server.name,
        enabled=server.enabled,
    )


def build_mcp_client_boundary_from_config(
    config: Mapping[str, Any],
    *,
    server_id: int | None,
    key: str,
    version: int,
    name: str,
    enabled: bool,
    allow_secret_query_names: bool = False,
) -> McpClientBoundary:
    details: list[dict[str, str]] = []
    transport = _normalize_transport(config.get("transport"), details)
    command = _normalize_command(config, transport, details)
    base_url = _normalize_url(config, transport, details)
    headers = _normalize_headers(config, transport, details)
    query = _normalize_query(config, transport, details)
    env = _normalize_env(config, transport, details)
    url = _merge_http_sse_query(base_url, query)

    if not details:
        _validate_transport_security(
            transport=transport,
            command=command,
            url=url,
            allowed_secret_query_param_names=(set(query) if allow_secret_query_names else set()),
            details=details,
        )
    if details:
        raise McpClientConfigError(details)

    return McpClientBoundary(
        server_id=server_id,
        key=key,
        version=version,
        name=name,
        transport=transport,
        enabled=enabled,
        command=command,
        url=url,
        headers=headers,
        query=query,
        env=env,
    )


def _normalize_transport(raw_transport: object, details: list[dict[str, str]]) -> str:
    normalized_transport = str(raw_transport).strip() if raw_transport is not None else ""
    if normalized_transport not in {"stdio", "http-sse"}:
        details.append(
            {
                "field": "transport",
                "issue": "Server transport must be either 'stdio' or 'http-sse'",
            }
        )
    return normalized_transport


def _normalize_command(
    config: Mapping[str, Any],
    transport: str,
    details: list[dict[str, str]],
) -> tuple[str, ...] | None:
    if transport != "stdio":
        if "command" in config:
            details.append({"field": "command", "issue": "command is only supported for stdio"})
        if "args" in config:
            details.append({"field": "args", "issue": "args is only supported for stdio"})
        return None

    normalized_command = (
        str(config.get("command")).strip() if config.get("command") is not None else ""
    )
    if not normalized_command:
        details.append({"field": "command", "issue": "Stdio transport requires a command"})
        return None

    raw_args = config.get("args")
    if not isinstance(raw_args, list):
        details.append({"field": "args", "issue": "Stdio transport requires args[]"})
        return None

    normalized_args: list[str] = []
    for index, entry in enumerate(raw_args):
        normalized_entry = str(entry).strip() if entry is not None else ""
        if not normalized_entry:
            details.append({"field": f"args.{index}", "issue": "Args must be non-empty strings"})
            continue
        normalized_args.append(normalized_entry)

    if not normalized_args:
        details.append({"field": "args", "issue": "Stdio transport requires args[]"})
        return None
    return (normalized_command, *normalized_args)


def _normalize_url(
    config: Mapping[str, Any],
    transport: str,
    details: list[dict[str, str]],
) -> str | None:
    if transport != "http-sse":
        if "url" in config:
            details.append({"field": "url", "issue": "url is only supported for http-sse"})
        return None
    normalized_url = str(config.get("url")).strip() if config.get("url") is not None else ""
    if not normalized_url:
        details.append({"field": "url", "issue": "HTTP/SSE transport requires a URL"})
        return None
    return normalized_url


def _normalize_headers(
    config: Mapping[str, Any],
    transport: str,
    details: list[dict[str, str]],
) -> dict[str, str]:
    if transport != "http-sse":
        if "headers" in config:
            details.append({"field": "headers", "issue": "headers is only supported for http-sse"})
        return {}
    return _normalize_string_mapping(config.get("headers"), field_name="headers", details=details)


def _normalize_query(
    config: Mapping[str, Any],
    transport: str,
    details: list[dict[str, str]],
) -> dict[str, str]:
    if transport != "http-sse":
        if "query" in config:
            details.append({"field": "query", "issue": "query is only supported for http-sse"})
        return {}
    return _normalize_string_mapping(config.get("query"), field_name="query", details=details)


def _normalize_env(
    config: Mapping[str, Any],
    transport: str,
    details: list[dict[str, str]],
) -> dict[str, str]:
    if transport != "stdio":
        if "env" in config:
            details.append({"field": "env", "issue": "env is only supported for stdio"})
        return {}
    return _normalize_string_mapping(config.get("env"), field_name="env", details=details)


def _merge_http_sse_query(url: str | None, query: Mapping[str, str]) -> str | None:
    if url is None or not query:
        return url
    parsed = urlsplit(url)
    query_names = set(query)
    base_pairs = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name not in query_names
    ]
    merged_query = urlencode([*base_pairs, *query.items()])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, merged_query, parsed.fragment))


def _validate_transport_security(
    *,
    transport: str,
    command: tuple[str, ...] | None,
    url: str | None,
    allowed_secret_query_param_names: set[str],
    details: list[dict[str, str]],
) -> None:
    try:
        if transport == "stdio":
            validate_stdio_command(
                command or (),
                allowed_commands=get_settings().mcp_stdio_allowed_commands,
            )
        elif transport == "http-sse":
            validate_http_sse_url(
                url or "",
                allowed_secret_query_param_names=allowed_secret_query_param_names,
            )
    except McpSecurityError as exc:
        details.append({"field": "transport", "issue": str(exc)})


def _normalize_string_mapping(
    raw_mapping: object,
    *,
    field_name: str,
    details: list[dict[str, str]],
) -> dict[str, str]:
    if raw_mapping is None:
        return {}
    if not isinstance(raw_mapping, Mapping):
        details.append({"field": field_name, "issue": "Expected an object"})
        return {}

    normalized: dict[str, str] = {}
    for key, value in raw_mapping.items():
        normalized_key = str(key).strip()
        normalized_value = str(value).strip() if value is not None else ""
        if not normalized_key:
            details.append({"field": field_name, "issue": "Keys must be non-empty strings"})
            continue
        if not normalized_value:
            details.append(
                {
                    "field": f"{field_name}.{normalized_key}",
                    "issue": "Values must be non-empty strings",
                }
            )
            continue
        normalized[normalized_key] = normalized_value
    return normalized


__all__ = [
    "DefaultMcpConnectionTester",
    "McpClientBoundary",
    "McpClientConfigError",
    "McpConnectionTestResult",
    "McpConnectionTester",
    "build_mcp_client_boundary",
]
