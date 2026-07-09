from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.boundaries import (
    DefaultMcpConnectionTester,
    McpClientBoundary,
    McpClientConfigError,
    build_mcp_client_boundary_from_config,
)
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
    build_package_private_mcp_tool_descriptor,
    convert_mcp_input_schema,
    execution_tool_descriptor_to_payload,
    normalize_mcp_openai_function_name,
)
from app.agents.runtime_tools.types import RuntimeToolError
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


def _input_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
        "additionalProperties": False,
    }


def _package_private_exa_ref(**overrides: object) -> dict[str, object]:
    descriptor = build_package_private_mcp_tool_descriptor(
        server_key="exa",
        original_tool_name="web_search_exa",
        owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    )
    ref: dict[str, object] = {
        "packagePrivate": True,
        "key": "exa",
        "name": "Exa Web Search",
        "transport": "http-sse",
        "url": "https://example.com/mcp?tools=web_search_exa",
        "toolKeys": ["web_search_exa"],
        "toolDescriptors": [execution_tool_descriptor_to_payload(descriptor)],
    }
    ref.update(overrides)
    return ref


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


def test_mcp_runtime_rejects_global_server_refs(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[{"mcpServerKey": "external_data", "mcpServerVersion": 1}],
            enabled=True,
        )

    assert exc_info.value.code == "mcp_global_server_ref_removed"


def test_mcp_runtime_resolves_package_private_exa_tool(
    session_factory: sessionmaker[Session],
) -> None:
    client = _FakeMcpToolClient(
        {
            "content": "Bearer secret-token sk-live-secret-123456",
            "metadata": {"exaApiKey": "json-secret-value-123456"},
        }
    )
    dispatcher = McpRuntimeResolver(session_factory).build_dispatcher(
        mcp_server_refs=[
            _package_private_exa_ref(
                headers={" Authorization ": " Bearer package-token "},
                query={" exaApiKey ": " secret-token ", "locale": " en-US "},
            )
        ],
        client=cast(McpToolClient, client),
        timeout_seconds=2.5,
        enabled=True,
    )

    descriptors = dispatcher.list_execution_descriptors()
    assert len(descriptors) == 1
    assert descriptors[0].tool_key == "exa@1:mcp_exa_web_search_exa"
    assert descriptors[0].openai_function_name == "mcp_exa_web_search_exa"
    assert descriptors[0].redaction_policy == "mcp.output.redact_text"
    assert descriptors[0].owner_extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert descriptors[0].original_tool_name == "web_search_exa"

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
    assert boundary.url == (
        "https://example.com/mcp?tools=web_search_exa&exaApiKey=secret-token&locale=en-US"
    )
    assert boundary.headers == {"Authorization": "Bearer package-token"}
    assert boundary.query == {"exaApiKey": "secret-token", "locale": "en-US"}
    assert call["tool_name"] == "web_search_exa"
    assert call["arguments"] == {"query": "AAPL latest company news"}
    assert call["timeout_seconds"] == 2.5
    output_payload = json.dumps(output)
    assert "secret-token" not in output_payload
    assert "sk-live-secret" not in output_payload
    assert "json-secret-value" not in output_payload
    assert "[REDACTED]" in output_payload


def test_mcp_runtime_disabled_with_package_private_refs_exposes_no_tools(
    session_factory: sessionmaker[Session],
) -> None:
    client = _FakeMcpToolClient({"content": "unused"})
    dispatcher = McpRuntimeResolver(session_factory).build_dispatcher(
        mcp_server_refs=[_package_private_exa_ref()],
        client=cast(McpToolClient, client),
        enabled=False,
    )

    assert dispatcher.get_openai_tools() == []
    assert dispatcher.list_execution_descriptors() == ()
    assert dispatcher.list_tool_declarations() == ()
    with pytest.raises(RuntimeToolError) as exc_info:
        dispatcher.dispatch(name="mcp_exa_web_search_exa", arguments_json="{}")
    assert exc_info.value.code == "mcp_tool_call_unsupported"
    assert client.calls == []


def test_mcp_runtime_rejects_package_private_exa_without_descriptor(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeToolError) as exc_info:
        McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[_package_private_exa_ref(toolDescriptors=[])],
            enabled=True,
        )

    assert exc_info.value.code == "mcp_tool_descriptor_missing"


def test_mcp_runtime_rejects_package_private_exa_with_drifted_descriptor_hash(
    session_factory: sessionmaker[Session],
) -> None:
    ref = _package_private_exa_ref()
    descriptors = cast(list[dict[str, object]], ref["toolDescriptors"])
    descriptors[0] = {**descriptors[0], "schemaHash": "sha256:" + "a" * 64}

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[ref],
            enabled=True,
        )

    assert exc_info.value.code == "mcp_tool_descriptor_invalid"


def test_mcp_runtime_rejects_package_private_exa_malformed_descriptor_without_secret_leak(
    session_factory: sessionmaker[Session],
) -> None:
    ref = _package_private_exa_ref(
        headers={"Authorization": "Bearer package-token"},
        query={"exaApiKey": "secret-token"},
    )
    descriptors = cast(list[dict[str, object]], ref["toolDescriptors"])
    descriptors[0] = {**descriptors[0], "ownerExtensionKey": ""}

    with pytest.raises(RuntimeToolError) as exc_info:
        _ = McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[ref],
            enabled=True,
        )

    error_payload = json.dumps(
        {"code": exc_info.value.code, "message": exc_info.value.message},
        sort_keys=True,
    )
    assert exc_info.value.code == "mcp_tool_descriptor_invalid"
    assert "secret-token" not in error_payload
    assert "package-token" not in error_payload


def test_mcp_runtime_rejects_package_private_exa_malformed_config_without_secret_leak(
    session_factory: sessionmaker[Session],
) -> None:
    ref = _package_private_exa_ref(
        url=None,
        headers={"Authorization": "Bearer package-token"},
        query={"exaApiKey": "secret-token"},
    )

    with pytest.raises(McpClientConfigError) as exc_info:
        _ = McpRuntimeResolver(session_factory).build_dispatcher(
            mcp_server_refs=[ref],
            enabled=True,
        )

    details_json = json.dumps(exc_info.value.details, sort_keys=True)
    assert exc_info.value.details == [
        {"field": "url", "issue": "HTTP/SSE transport requires a URL"}
    ]
    assert "secret-token" not in details_json
    assert "package-token" not in details_json


def test_mcp_boundary_scopes_secret_query_names_to_package_private_query_map() -> None:
    config = {
        "transport": "http-sse",
        "url": "https://example.com/mcp?tools=web_search_exa",
        "query": {"exaApiKey": "secret-token"},
    }

    boundary = build_mcp_client_boundary_from_config(
        config,
        server_id=None,
        key="exa",
        version=1,
        name="Exa Web Search",
        enabled=True,
        allow_secret_query_names=True,
    )

    assert boundary.url == ("https://example.com/mcp?tools=web_search_exa&exaApiKey=secret-token")
    assert boundary.query == {"exaApiKey": "secret-token"}
    with pytest.raises(McpClientConfigError) as exc_info:
        build_mcp_client_boundary_from_config(
            config,
            server_id=1,
            key="exa",
            version=1,
            name="Exa Web Search",
            enabled=True,
        )
    assert exc_info.value.details == [
        {
            "field": "transport",
            "issue": "MCP HTTP/SSE URLs cannot include secret-bearing query parameters",
        }
    ]


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
    assert (
        validate_http_sse_url(
            "https://safe.example/mcp?tools=web_search_exa&exaApiKey=secret-token",
            resolved_hosts={"safe.example": ["93.184.216.34"]},
            allowed_secret_query_param_names={"exaApiKey"},
        )
        == "https://safe.example/mcp?tools=web_search_exa&exaApiKey=secret-token"
    )
    with pytest.raises(McpSecurityError, match="secret-bearing query"):
        validate_http_sse_url(
            "https://safe.example/mcp?exaApiKey=secret-token&accessToken=other-token",
            resolved_hosts={"safe.example": ["93.184.216.34"]},
            allowed_secret_query_param_names={"exaApiKey"},
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
