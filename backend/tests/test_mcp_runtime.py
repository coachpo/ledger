from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import DefaultMcpConnectionTester, McpClientBoundary
from app.agents.mcp.runtime import McpRuntimeResolver, McpToolClient
from app.agents.mcp.security import (
    McpSecurityError,
    redact_mcp_text,
    validate_http_redirect_chain,
    validate_http_sse_url,
    validate_stdio_command,
)
from app.agents.mcp.tool_adapter import (
    McpToolAdapterError,
    build_mcp_tool_snapshot,
    convert_mcp_input_schema,
    normalize_mcp_openai_function_name,
)
from app.agents.runtime_tools.types import RuntimeToolError
from app.models.mcp_server import McpServer


def _input_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
        "additionalProperties": False,
    }


def _snapshot(*, server_key: str = "external_data", version: int = 1) -> dict[str, object]:
    snapshot = build_mcp_tool_snapshot(
        server_key=server_key,
        server_version=version,
        original_tool_name="vendor.lookup",
        input_schema=_input_schema(),
    )
    return snapshot.model_dump(by_alias=True, mode="json")


def _package_private_exa_ref(**overrides: object) -> dict[str, object]:
    ref: dict[str, object] = {
        "packagePrivate": True,
        "key": "exa",
        "name": "Exa Web Search",
        "transport": "http-sse",
        "url": "https://example.com/mcp?tools=web_search_exa",
        "toolKeys": ["web_search_exa"],
    }
    ref.update(overrides)
    return ref


def _server(
    *,
    key: str = "external_data",
    version: int = 1,
    status: str = "published",
    enabled: bool = True,
    snapshots: list[dict[str, object]] | None = None,
) -> McpServer:
    return McpServer(
        key=key,
        version=version,
        status=status,
        config={
            "name": f"{key}-{version}",
            "description": "External MCP server",
            "enabled": enabled,
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@vendor/server"],
            "env": {"API_TOKEN": "secret-token"},
            "toolSnapshots": (
                snapshots if snapshots is not None else [_snapshot(server_key=key, version=version)]
            ),
        },
    )


class _FakeMcpToolClient:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def call_tool(
        self,
        *,
        boundary: McpClientBoundary,
        tool_name: str,
        arguments: dict[str, object],
        timeout_seconds: float,
    ) -> object:
        self.calls.append(
            {
                "boundary": boundary,
                "tool_name": tool_name,
                "arguments": arguments,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.result


def test_mcp_runtime_resolves_exact_published_pin_and_redacts_output(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        server = _server()
        session.add(server)
        session.commit()

    client = _FakeMcpToolClient(
        {
            "content": "Bearer secret-token sk-live-secret-123456",
            "metadata": {"exaApiKey": "json-secret-value-123456"},
        }
    )
    dispatcher = McpRuntimeResolver(session_factory).build_dispatcher(
        mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
        client=cast(McpToolClient, client),
        timeout_seconds=1.25,
        enabled=True,
    )

    tools = dispatcher.get_openai_tools()
    assert [tool["name"] for tool in tools] == ["mcp_external_data_vendor_lookup"]
    output = dispatcher.dispatch(
        name="mcp_external_data_vendor_lookup",
        arguments_json=json.dumps({"ticker": "NVDA"}),
    )

    assert output["originalToolName"] == "vendor.lookup"
    assert "secret-token" not in json.dumps(output)
    assert "sk-live-secret" not in json.dumps(output)
    assert "json-secret-value" not in json.dumps(output)
    assert "[REDACTED]" in json.dumps(output)
    assert client.calls[0]["tool_name"] == "vendor.lookup"
    assert client.calls[0]["timeout_seconds"] == 1.25


def test_mcp_runtime_resolves_package_private_exa_tool(
    session_factory: sessionmaker[Session],
) -> None:
    client = _FakeMcpToolClient(
        {"content": "Exa result", "metadata": {"exaApiKey": "json-secret-value-123456"}}
    )
    dispatcher = McpRuntimeResolver(session_factory).build_dispatcher(
        mcp_server_refs=[_package_private_exa_ref()],
        client=cast(McpToolClient, client),
        timeout_seconds=2.5,
        enabled=True,
    )

    tools = dispatcher.get_openai_tools()
    assert [tool["name"] for tool in tools] == ["mcp_exa_web_search_exa"]
    assert tools[0]["parameters"] == {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for the MCP tool."}
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    output = dispatcher.dispatch(
        name="mcp_exa_web_search_exa",
        arguments_json=json.dumps({"query": "AAPL latest company news"}),
    )

    call = client.calls[0]
    boundary = cast(McpClientBoundary, call["boundary"])
    assert boundary.server_id is None
    assert boundary.key == "exa"
    assert boundary.version == 1
    assert boundary.url == "https://example.com/mcp?tools=web_search_exa"
    assert call["tool_name"] == "web_search_exa"
    assert call["arguments"] == {"query": "AAPL latest company news"}
    assert call["timeout_seconds"] == 2.5
    assert "json-secret-value" not in json.dumps(output)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"key": ""}, "mcp_server_pin_invalid"),
        ({"toolKeys": []}, "mcp_tool_snapshots_missing"),
        ({"toolKeys": ["web_fetch_exa"]}, "mcp_tool_schema_missing"),
    ],
)
def test_mcp_runtime_rejects_invalid_package_private_refs(
    session_factory: sessionmaker[Session],
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[_package_private_exa_ref(**overrides)],
            enabled=True,
        )

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize("status", ["draft"])
def test_mcp_runtime_rejects_non_runtime_statuses(
    session_factory: sessionmaker[Session],
    status: str,
) -> None:
    with session_factory() as session:
        session.add(_server(status=status))
        session.commit()

    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
            enabled=True,
        )

    assert exc_info.value.code == "mcp_server_status_invalid"


def test_mcp_runtime_permits_pinned_deprecated_enabled_version(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_server(status="deprecated"))
        session.commit()

    dispatcher = McpRuntimeResolver(session_factory).build_dispatcher(
        mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
        enabled=True,
    )

    assert [tool["name"] for tool in dispatcher.get_openai_tools()] == [
        "mcp_external_data_vendor_lookup"
    ]


def test_mcp_runtime_rejects_disabled_and_implicit_pins(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(_server(enabled=False))
        session.commit()

    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[{"mcpServerKey": "external_data"}],
            enabled=True,
        )
    assert exc_info.value.code == "mcp_server_pin_invalid"

    with pytest.raises(RuntimeToolError) as disabled_exc:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
            enabled=True,
        )
    assert disabled_exc.value.code == "mcp_server_disabled"


def test_mcp_runtime_rejects_drifted_snapshot_hash(
    session_factory: sessionmaker[Session],
) -> None:
    drifted = _snapshot()
    drifted["schemaHash"] = "sha256:" + "a" * 64
    with session_factory() as session:
        session.add(_server(snapshots=[drifted]))
        session.commit()

    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
            enabled=True,
        )

    assert exc_info.value.code == "mcp_tool_snapshot_drift"


def test_mcp_tool_adapter_rejects_function_collisions_and_unsupported_schema() -> None:
    with pytest.raises(McpToolAdapterError):
        normalize_mcp_openai_function_name(
            server_key="external_data",
            original_tool_name="vendor.lookup",
            reserved_function_names={"mcp_external_data_vendor_lookup"},
        )

    with pytest.raises(McpToolAdapterError):
        convert_mcp_input_schema({"type": "object", "$ref": "#/defs/Input"})


def test_mcp_security_blocks_ssrf_redirects_shells_and_truncates_output() -> None:
    with pytest.raises(McpSecurityError):
        validate_http_sse_url(
            "https://metadata.google.internal/mcp",
            resolved_hosts={"metadata.google.internal": ["169.254.169.254"]},
        )
    with pytest.raises(McpSecurityError):
        validate_http_redirect_chain(
            ["https://safe.example/mcp", "https://internal.example/mcp"],
            resolved_hosts={"safe.example": ["93.184.216.34"], "internal.example": ["10.0.0.5"]},
        )
    with pytest.raises(McpSecurityError):
        validate_stdio_command(("bash", "-c", "echo $TOKEN"), allowed_commands={"bash"})
    with pytest.raises(McpSecurityError):
        validate_stdio_command(("python", "-c", "print('x')"), allowed_commands={"python"})
    with pytest.raises(McpSecurityError, match="secret-bearing query"):
        validate_http_sse_url(
            "https://safe.example/mcp?exaApiKey=secret-token",
            resolved_hosts={"safe.example": ["93.184.216.34"]},
        )

    redacted = redact_mcp_text("token=secret-token " + ("x" * 20), max_length=24)
    assert "secret-token" not in redacted
    assert redacted.endswith("...[truncated]")


class _RedirectResponse:
    status_code = 302

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False


class _RedirectClient:
    follow_redirects: bool | None = None
    requested_url: str | None = None

    def __init__(self, *, timeout: float, follow_redirects: bool) -> None:
        del timeout
        type(self).follow_redirects = follow_redirects

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def stream(self, method: str, url: str, *, headers: dict[str, str]):
        del method, headers
        type(self).requested_url = url
        return _RedirectResponse()


def test_default_mcp_connection_tester_test_disables_automatic_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.agents.mcp.boundaries.httpx.Client", _RedirectClient)
    boundary = McpClientBoundary(
        server_id=1,
        key="external_data",
        version=1,
        name="External Data",
        transport="http-sse",
        enabled=True,
        url="https://safe.example/mcp",
    )

    result = DefaultMcpConnectionTester(timeout_seconds=1.0).test(boundary)

    assert _RedirectClient.follow_redirects is False
    assert _RedirectClient.requested_url == "https://safe.example/mcp"
    assert result.ok is False
    assert result.status_code == 302
    assert result.message == "MCP HTTP/SSE redirects are not followed"


def test_default_mcp_connection_tester_fails_closed_on_http_redirect() -> None:
    def handler(request):
        assert request.url == "https://safe.example/mcp"
        return httpx.Response(
            302,
            headers={"Location": "https://169.254.169.254/latest/meta-data"},
        )

    boundary = McpClientBoundary(
        server_id=1,
        key="external_data",
        version=1,
        name="External Data",
        transport="http-sse",
        enabled=True,
        url="https://safe.example/mcp",
        headers={"Authorization": "Bearer secret-token"},
    )
    tester = DefaultMcpConnectionTester(timeout_seconds=1.0)
    transport = httpx.MockTransport(handler)

    with httpx.Client(transport=transport, follow_redirects=False) as client:
        result = tester._test_http_sse_with_client(boundary, client)

    assert result.ok is False
    assert result.status_code == 302
    assert result.message == "MCP HTTP/SSE redirects are not followed"
