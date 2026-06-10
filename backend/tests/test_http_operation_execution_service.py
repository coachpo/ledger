# pyright: reportExplicitAny=false
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.services.execution_plan import ExecutionPlanOperation
from app.services.http_operation_execution_service import (
    HttpOperationExecutionError,
    HttpOperationExecutionService,
)


class WebhookResponse(BaseModel):
    ok: bool
    id: str


class _CapturingTransport(httpx.MockTransport):
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if isinstance(response, Exception):
                raise response
            return response

        super().__init__(handler)


class _ChunkedStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks

    def close(self) -> None:
        return None


def _settings(**overrides: Any) -> Settings:
    return Settings(**overrides)


def _operation(
    *,
    request: dict[str, Any] | None = None,
    method: str = "POST",
    timeout_seconds: int = 5,
    optional: bool = False,
) -> ExecutionPlanOperation:
    return ExecutionPlanOperation(
        slot="webhook_result",
        operation_key="notify_webhook",
        operation_kind="http",
        output_schema_id=1,
        output_schema_version=1,
        request=request
        or {
            "url": {"from": "input", "path": "url"},
            "headers": {"Authorization": {"from": "secret", "key": "webhook_token"}},
            "query": {"ticker": {"from": "input", "path": "ticker"}},
            "body": {"message": {"from": "input", "path": "message"}},
        },
        method=method,
        timeout_seconds=timeout_seconds,
        optional=optional,
    )


def _service(
    transport: _CapturingTransport,
    *,
    settings: Settings | None = None,
    resolved_hosts: dict[str, tuple[str, ...]] | None = None,
) -> HttpOperationExecutionService:
    def client_factory(**kwargs: Any) -> httpx.Client:
        return httpx.Client(transport=transport, **kwargs)

    return HttpOperationExecutionService(
        settings=settings
        or _settings(
            http_operation_allow_insecure_http=False,
            http_operation_block_private_networks=True,
        ),
        client_factory=client_factory,
        resolved_hosts=resolved_hosts or {"api.example.test": ("93.184.216.34",)},
    )


def _execute(
    service: HttpOperationExecutionService,
    operation: ExecutionPlanOperation | None = None,
    *,
    initial_input: dict[str, Any] | None = None,
    secret_values: dict[str, str] | None = None,
) -> Any:
    return service.execute(
        operation=operation or _operation(),
        initial_input=initial_input
        or {
            "url": "https://api.example.test/hooks?api_key=visible-secret",
            "ticker": "AAPL",
            "message": "hello",
        },
        secret_values=secret_values or {"webhook_token": "super-secret"},
        output_model=WebhookResponse,
    )


def test_successful_post_builds_request_and_redacts_audit_metadata() -> None:
    transport = _CapturingTransport(
        httpx.Response(
            200, json={"ok": True, "id": "evt_123"}, headers={"content-type": "application/json"}
        )
    )
    service = _service(transport)

    result = _execute(service)

    assert result.output == {"ok": True, "id": "evt_123"}
    assert result.status_code == 200
    assert result.response_metadata["bodySha256"]
    request = transport.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.example.test/hooks?api_key=visible-secret&ticker=AAPL"
    assert request.headers["Authorization"] == "super-secret"
    assert json.loads(request.content.decode("utf-8")) == {"message": "hello"}
    assert (
        result.request_metadata["url"]
        == "https://api.example.test/hooks?api_key=%5BREDACTED%5D&ticker=AAPL"
    )
    assert result.request_metadata["headers"]["Authorization"] == {
        "from": "secret",
        "key": "webhook_token",
        "redacted": True,
    }
    assert result.request_metadata["body"] == {"message": {"from": "input", "path": "message"}}


def test_unsupported_method_is_rejected_before_request() -> None:
    transport = _CapturingTransport(httpx.Response(200, json={"ok": True, "id": "evt_123"}))
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service, _operation(method="DELETE"))

    assert exc_info.value.code == "http_operation_method_not_allowed"
    assert transport.requests == []


def test_insecure_public_http_url_is_rejected_before_request() -> None:
    transport = _CapturingTransport(httpx.Response(200, json={"ok": True, "id": "evt_123"}))
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(
            service,
            initial_input={
                "url": "http://api.example.test/hooks",
                "ticker": "AAPL",
                "message": "hello",
            },
        )

    assert exc_info.value.code == "http_operation_insecure_http_blocked"
    assert transport.requests == []


def test_oversize_request_body_is_rejected_before_request() -> None:
    transport = _CapturingTransport(httpx.Response(200, json={"ok": True, "id": "evt_123"}))
    service = _service(
        transport,
        settings=_settings(
            http_operation_allow_insecure_http=False,
            http_operation_block_private_networks=True,
            http_operation_request_max_bytes=8,
        ),
    )

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(
            service,
            initial_input={
                "url": "https://api.example.test/hooks",
                "ticker": "AAPL",
                "message": "payload larger than limit",
            },
        )

    assert exc_info.value.code == "http_operation_request_body_too_large"
    assert transport.requests == []


def test_unsupported_response_content_type_is_rejected() -> None:
    transport = _CapturingTransport(
        httpx.Response(200, content=b"<ok />", headers={"content-type": "application/xml"})
    )
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_content_type_unsupported"
    assert exc_info.value.status_code == 200


def test_invalid_json_response_is_rejected() -> None:
    transport = _CapturingTransport(
        httpx.Response(200, content=b'{"ok":', headers={"content-type": "application/json"})
    )
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_response_parse_failed"
    assert exc_info.value.status_code == 200


def test_redirect_is_blocked_even_when_redirect_limit_is_configured() -> None:
    transport = _CapturingTransport(
        httpx.Response(
            301, headers={"location": "https://api.example.test/next", "content-type": "text/plain"}
        )
    )
    service = _service(
        transport,
        settings=_settings(
            http_operation_allow_insecure_http=False,
            http_operation_block_private_networks=True,
            http_operation_max_redirects=3,
        ),
    )

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_redirect_blocked"
    assert exc_info.value.status_code == 301
    assert len(transport.requests) == 1
    assert str(transport.requests[0].url) == (
        "https://api.example.test/hooks?api_key=visible-secret&ticker=AAPL"
    )


def test_ssrf_blocks_private_resolved_address() -> None:
    transport = _CapturingTransport(httpx.Response(200, json={"ok": True, "id": "evt_123"}))
    service = _service(transport, resolved_hosts={"metadata.example.test": ("169.254.169.254",)})
    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(
            service,
            initial_input={
                "url": "https://metadata.example.test/latest",
                "ticker": "AAPL",
                "message": "hello",
            },
        )

    assert exc_info.value.code == "http_operation_private_network_blocked"
    assert transport.requests == []


def test_timeout_is_reported_as_http_operation_error() -> None:
    transport = _CapturingTransport(httpx.TimeoutException("timed out"))
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_timeout_exceeded"
    assert exc_info.value.request_metadata is not None


def test_oversize_response_body_is_rejected() -> None:
    transport = _CapturingTransport(
        httpx.Response(
            200,
            stream=_ChunkedStream([b'{"ok":true,', b'"id":"evt_123"}']),
            headers={"content-type": "application/json"},
        )
    )
    service = _service(
        transport,
        settings=_settings(http_operation_response_max_bytes=4),
    )

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_response_body_too_large"
    assert exc_info.value.status_code == 200


def test_redirect_is_blocked_by_default() -> None:
    transport = _CapturingTransport(
        httpx.Response(
            302, headers={"location": "https://api.example.test/next", "content-type": "text/plain"}
        )
    )
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_redirect_blocked"
    assert exc_info.value.status_code == 302
    assert exc_info.value.response_metadata is not None
    assert exc_info.value.response_metadata["location"] == "https://api.example.test/next"


def test_schema_failure_raises_for_required_and_returns_error_for_optional() -> None:
    transport = _CapturingTransport(
        httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    service = _service(transport)

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(service)

    assert exc_info.value.code == "http_operation_output_validation_failed"

    optional_transport = _CapturingTransport(
        httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    optional_result = _execute(_service(optional_transport), _operation(optional=True))

    assert optional_result.output is None
    assert optional_result.error is not None
    assert optional_result.error.code == "http_operation_output_validation_failed"
    assert optional_result.status_code == 200


def test_dev_override_allows_insecure_http_and_private_networks() -> None:
    transport = _CapturingTransport(
        httpx.Response(
            200, json={"ok": True, "id": "evt_123"}, headers={"content-type": "application/json"}
        )
    )
    service = _service(
        transport,
        settings=_settings(
            http_operation_allow_insecure_http=True,
            http_operation_block_private_networks=False,
        ),
        resolved_hosts={"localhost": ("127.0.0.1",)},
    )

    result = _execute(
        service,
        initial_input={"url": "http://localhost/hooks", "ticker": "AAPL", "message": "hello"},
    )

    assert result.output == {"ok": True, "id": "evt_123"}
    assert str(transport.requests[0].url) == "http://localhost/hooks?ticker=AAPL"


def test_localhost_blocking_uses_strict_defaults() -> None:
    transport = _CapturingTransport(httpx.Response(200, json={"ok": True, "id": "evt_123"}))
    service = _service(transport, resolved_hosts={"localhost": ("127.0.0.1",)})

    with pytest.raises(HttpOperationExecutionError) as exc_info:
        _execute(
            service,
            initial_input={"url": "http://localhost/hooks", "ticker": "AAPL", "message": "hello"},
        )

    assert exc_info.value.code == "http_operation_insecure_http_blocked"
    assert transport.requests == []
