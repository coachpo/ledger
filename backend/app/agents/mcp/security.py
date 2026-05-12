from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, urlparse

_SECRET_FIELD_PATTERN = r"[A-Za-z0-9_]*(?:token|secret|api[_-]?key)[A-Za-z0-9_]*"
_SECRET_VALUE_RE = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+|"
    + r"(sk-[A-Za-z0-9_-]{8,})|"
    + rf"({_SECRET_FIELD_PATTERN}=)[^\s,;]+|"
    + rf"((?:\"{_SECRET_FIELD_PATTERN}\"|'{_SECRET_FIELD_PATTERN}'|{_SECRET_FIELD_PATTERN})"
    + r"\s*:\s*(?:\"|'))[^\"']+((?:\"|'))"
)
_SECRET_QUERY_PARAM_RE = re.compile(r"(?i)(?:token|secret|api[_-]?key)")
_SHELL_EXECUTABLES = {"bash", "sh", "zsh", "fish", "cmd", "powershell", "pwsh"}
_MAX_REDACTED_TEXT_LENGTH = 16_384


class McpSecurityError(ValueError):
    pass


def redact_mcp_text(value: object, *, max_length: int = _MAX_REDACTED_TEXT_LENGTH) -> str:
    text = str(value)
    redacted = _SECRET_VALUE_RE.sub(lambda match: _redaction_replacement(match), text)
    if len(redacted) <= max_length:
        return redacted
    return redacted[:max_length] + "...[truncated]"


def _redaction_replacement(match: re.Match[str]) -> str:
    if match.group(1):
        return f"{match.group(1)}[REDACTED]"
    if match.group(3):
        return f"{match.group(3)}[REDACTED]"
    if match.group(4):
        return f"{match.group(4)}[REDACTED]{match.group(5)}"
    return "[REDACTED]"


def validate_http_sse_url(
    url: str,
    *,
    resolved_hosts: dict[str, Sequence[str]] | None = None,
    allowed_secret_query_param_names: Iterable[str] | None = None,
) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise McpSecurityError("MCP HTTP/SSE URLs must use https")
    if parsed.username or parsed.password:
        raise McpSecurityError("MCP HTTP/SSE URLs cannot include credentials")
    allowed_secret_names = {
        str(name).strip()
        for name in (allowed_secret_query_param_names or ())
        if str(name).strip()
    }
    for name, _value in parse_qsl(parsed.query, keep_blank_values=True):
        if _SECRET_QUERY_PARAM_RE.search(name) and name not in allowed_secret_names:
            raise McpSecurityError(
                "MCP HTTP/SSE URLs cannot include secret-bearing query parameters"
            )
    host = parsed.hostname
    if host is None:
        raise McpSecurityError("MCP HTTP/SSE URL must include a host")
    addresses = _resolve_host_addresses(host, resolved_hosts=resolved_hosts)
    if not addresses:
        raise McpSecurityError("MCP HTTP/SSE host did not resolve")
    for address in addresses:
        _validate_public_ip_address(address)
    return url


def validate_http_redirect_chain(
    urls: Sequence[str],
    *,
    resolved_hosts: dict[str, Sequence[str]] | None = None,
) -> tuple[str, ...]:
    if not urls:
        raise McpSecurityError("MCP redirect chain cannot be empty")
    return tuple(validate_http_sse_url(url, resolved_hosts=resolved_hosts) for url in urls)


def validate_stdio_command(
    command: Sequence[str],
    *,
    allowed_commands: Iterable[str],
) -> tuple[str, ...]:
    normalized = tuple(str(part).strip() for part in command if str(part).strip())
    if not normalized:
        raise McpSecurityError("MCP stdio command cannot be empty")
    executable = normalized[0].rsplit("/", 1)[-1]
    allowed = {item.strip() for item in allowed_commands if item.strip()}
    if executable in _SHELL_EXECUTABLES:
        raise McpSecurityError("MCP stdio shell executables are not allowed")
    if executable not in allowed:
        raise McpSecurityError("MCP stdio executable is not allowlisted")
    if any(part in {"-c", "/c"} for part in normalized[1:]):
        raise McpSecurityError("MCP stdio inline shell commands are not allowed")
    return normalized


def _resolve_host_addresses(
    host: str,
    *,
    resolved_hosts: dict[str, Sequence[str]] | None,
) -> list[str]:
    if resolved_hosts is not None:
        return [str(item) for item in resolved_hosts.get(host, ())]
    try:
        return [str(item[4][0]) for item in socket.getaddrinfo(host, None)]
    except socket.gaierror as exc:
        raise McpSecurityError("MCP HTTP/SSE host did not resolve") from exc


def _validate_public_ip_address(value: str) -> None:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise McpSecurityError("MCP HTTP/SSE host resolved to an invalid IP address") from exc
    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise McpSecurityError("MCP HTTP/SSE host resolved to a disallowed IP address")


__all__ = [
    "McpSecurityError",
    "redact_mcp_text",
    "validate_http_redirect_chain",
    "validate_http_sse_url",
    "validate_stdio_command",
]
