from __future__ import annotations

import shlex
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.models.mcp_server import McpServer


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
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class McpConnectionTestResult:
    ok: bool
    message: str
    status_code: int | None = None


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
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                headers = {"accept": "text/event-stream", **boundary.headers}
                with client.stream("GET", boundary.url, headers=headers) as response:
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
        except httpx.HTTPError as exc:
            return McpConnectionTestResult(ok=False, message=str(exc))

    @staticmethod
    def _resolve_executable_path(executable: str) -> str | None:
        executable_path = Path(executable)
        if executable_path.is_absolute() or executable.startswith("."):
            return str(executable_path) if executable_path.exists() else None
        return shutil.which(executable)


def build_mcp_client_boundary(server: McpServer) -> McpClientBoundary:
    details: list[dict[str, str]] = []
    headers: dict[str, str] = {}
    env: dict[str, str] = {}

    command = _normalize_command(server.command, server.transport, details)
    url = _normalize_url(server.url, server.transport, details)
    auth_payload = server.auth if isinstance(server.auth, dict) else {}
    _normalize_auth(auth_payload, headers=headers, env=env, details=details)

    if details:
        raise McpClientConfigError(details)

    return McpClientBoundary(
        server_id=server.id,
        key=server.key,
        version=server.version,
        name=server.name,
        transport=server.transport,
        enabled=server.enabled,
        command=command,
        url=url,
        headers=headers,
        env=env,
    )


def _normalize_command(
    raw_command: str | None,
    transport: str,
    details: list[dict[str, str]],
) -> tuple[str, ...] | None:
    if transport != "stdio":
        return None
    normalized_command = str(raw_command).strip() if raw_command is not None else ""
    if not normalized_command:
        details.append({"field": "command", "issue": "Stdio transport requires a command"})
        return None
    try:
        command_parts = tuple(shlex.split(normalized_command))
    except ValueError as exc:
        details.append({"field": "command", "issue": str(exc)})
        return None
    if not command_parts:
        details.append({"field": "command", "issue": "Stdio command cannot be empty"})
        return None
    return command_parts


def _normalize_url(
    raw_url: str | None,
    transport: str,
    details: list[dict[str, str]],
) -> str | None:
    if transport != "http-sse":
        return None
    normalized_url = str(raw_url).strip() if raw_url is not None else ""
    if not normalized_url:
        details.append({"field": "url", "issue": "HTTP/SSE transport requires a URL"})
        return None
    return normalized_url


def _normalize_auth(
    auth_payload: Mapping[str, Any],
    *,
    headers: dict[str, str],
    env: dict[str, str],
    details: list[dict[str, str]],
) -> None:
    allowed_keys = {"apiKey", "env", "header", "headers", "value"}
    for key in sorted(set(auth_payload) - allowed_keys):
        details.append({"field": f"auth.{key}", "issue": "Unsupported auth field"})

    if not auth_payload:
        return

    raw_headers = auth_payload.get("headers")
    if raw_headers is not None:
        _merge_string_mapping(
            raw_headers,
            target=headers,
            field_prefix="auth.headers",
            details=details,
        )

    raw_env = auth_payload.get("env")
    if raw_env is not None:
        _merge_string_mapping(raw_env, target=env, field_prefix="auth.env", details=details)

    if any(key in auth_payload for key in {"apiKey", "header", "value"}):
        raw_header_name = auth_payload.get("header")
        header_name = str(raw_header_name).strip() if raw_header_name is not None else ""
        header_value = auth_payload.get("value")
        if header_value is None:
            header_value = auth_payload.get("apiKey")
        normalized_value = str(header_value).strip() if header_value is not None else ""
        if not header_name:
            details.append(
                {"field": "auth.header", "issue": "Header auth requires a non-empty header name"}
            )
        if not normalized_value:
            details.append(
                {
                    "field": "auth.apiKey",
                    "issue": "Header auth requires a non-empty apiKey or value",
                }
            )
        if header_name and normalized_value:
            if header_name in headers:
                details.append(
                    {
                        "field": "auth.header",
                        "issue": f"Header {header_name!r} is defined more than once",
                    }
                )
            else:
                headers[header_name] = normalized_value


def _merge_string_mapping(
    raw_mapping: object,
    *,
    target: dict[str, str],
    field_prefix: str,
    details: list[dict[str, str]],
) -> None:
    if not isinstance(raw_mapping, Mapping):
        details.append({"field": field_prefix, "issue": "Expected an object"})
        return
    for key, value in raw_mapping.items():
        normalized_key = str(key).strip()
        normalized_value = str(value).strip() if value is not None else ""
        if not normalized_key:
            details.append({"field": field_prefix, "issue": "Keys must be non-empty strings"})
            continue
        if not normalized_value:
            details.append(
                {
                    "field": f"{field_prefix}.{normalized_key}",
                    "issue": "Values must be non-empty strings",
                }
            )
            continue
        target[normalized_key] = normalized_value


__all__ = [
    "DefaultMcpConnectionTester",
    "McpClientBoundary",
    "McpClientConfigError",
    "McpConnectionTestResult",
    "McpConnectionTester",
    "build_mcp_client_boundary",
]
