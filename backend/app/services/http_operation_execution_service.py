from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.repositories.run_operation_invocation import redact_operation_request_metadata
from app.repositories.workflow_package_secret_binding import WorkflowPackageSecretBindingRepository
from app.services.execution_plan import (
    ExecutionPlanOperation,
    PackageExecutionOwnership,
    PackageLocalOutputSchemaSpec,
)
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    PackageOutputSchemaCandidate,
    package_output_schema_candidate,
)

_HTTP_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_HTTP_JSON_CONTENT_TYPES = ("application/json", "+json")
_ALLOWED_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "location",
    "retry-after",
    "x-correlation-id",
    "x-request-id",
}
_SENSITIVE_NAME_PARTS = (
    "authorization",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)


@dataclass(frozen=True)
class _ResolvedValue:
    value: Any
    metadata: Any


@dataclass(frozen=True)
class _ResolvedRequestContext:
    method: str
    url: str
    headers: dict[str, str]
    query: dict[str, str]
    body: Any
    body_bytes: bytes | None
    request_metadata: dict[str, Any]


@dataclass(frozen=True)
class _HttpResponseContext:
    status_code: int
    headers: httpx.Headers
    url: str
    encoding: str | None
    body_bytes: bytes
    redirects: list[dict[str, Any]]


@dataclass
class HttpOperationExecutionError(Exception):
    code: str
    message: str
    details: list[dict[str, Any]] = field(default_factory=list)
    request_metadata: dict[str, Any] | None = None
    response_metadata: dict[str, Any] | None = None
    status_code: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


@dataclass
class HttpOperationExecutionResult:
    output: Any | None
    request_metadata: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    status_code: int | None = None
    error: HttpOperationExecutionError | None = None


class HttpOperationExecutionService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        settings: Settings | None = None,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
        client_kwargs: Mapping[str, Any] | None = None,
        resolved_hosts: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.client_factory = client_factory
        self.client_kwargs = dict(client_kwargs or {})
        self.resolved_hosts = {
            str(key): tuple(str(item) for item in value)
            for key, value in (resolved_hosts or {}).items()
        }
        self._output_schema_compiler = OutputSchemaCompiler() if session is not None else None
        self._secret_binding_repository = (
            WorkflowPackageSecretBindingRepository(session) if session is not None else None
        )

    async def invoke(
        self,
        *,
        operation: ExecutionPlanOperation,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any] | None = None,
        package_ownership: PackageExecutionOwnership | None = None,
        secret_values: Mapping[str, Any] | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> HttpOperationExecutionResult:
        return await asyncio.to_thread(
            self.execute,
            operation=operation,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            package_ownership=package_ownership,
            secret_values=secret_values,
            output_model=output_model,
        )

    def execute(
        self,
        *,
        operation: ExecutionPlanOperation,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any] | None = None,
        package_ownership: PackageExecutionOwnership | None = None,
        secret_values: Mapping[str, Any] | None = None,
        output_model: type[BaseModel] | None = None,
    ) -> HttpOperationExecutionResult:
        started = time.monotonic()
        try:
            return self._execute_once(
                operation=operation,
                initial_input=initial_input,
                slot_outputs=slot_outputs or {},
                package_ownership=package_ownership,
                secret_values=secret_values or {},
                output_model=output_model,
                started_at=started,
            )
        except HttpOperationExecutionError as exc:
            if not operation.optional:
                raise
            return HttpOperationExecutionResult(
                output=None,
                request_metadata=deepcopy(exc.request_metadata or {}),
                response_metadata=deepcopy(exc.response_metadata or {}),
                duration_ms=self._duration_ms(started, exc.duration_ms),
                status_code=exc.status_code,
                error=exc,
            )

    def _execute_once(
        self,
        *,
        operation: ExecutionPlanOperation,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any],
        package_ownership: PackageExecutionOwnership | None,
        secret_values: Mapping[str, Any],
        output_model: type[BaseModel] | None,
        started_at: float,
    ) -> HttpOperationExecutionResult:
        if operation.operation_kind != "http":
            self._raise_error(
                code="http_operation_kind_unsupported",
                message=f"Operation {operation.operation_key!r} is not an HTTP operation",
                started_at=started_at,
            )

        resolved_operation = operation.package_runtime_operation
        request_payload = deepcopy(
            resolved_operation.request if resolved_operation is not None else operation.request
        )
        method = self._normalize_method(
            resolved_operation.method if resolved_operation is not None else operation.method,
            started_at=started_at,
        )
        if method not in self._allowed_methods():
            self._raise_error(
                code="http_operation_method_not_allowed",
                message=f"HTTP method {method!r} is not allowed",
                details=[{"field": "method", "issue": "HTTP method is not allowed"}],
                started_at=started_at,
            )
        timeout_seconds = self._normalize_timeout(
            (
                resolved_operation.timeout_seconds
                if resolved_operation is not None
                else operation.timeout_seconds
            ),
            started_at=started_at,
        )
        output_model_type = self._resolve_output_model(
            operation=operation,
            output_model=output_model,
            started_at=started_at,
        )

        request_context = self._resolve_request_context(
            request_payload,
            method=method,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            secret_values=secret_values,
            package_ownership=package_ownership,
            started_at=started_at,
        )
        request_body_bytes = request_context.body_bytes
        if (
            request_body_bytes is not None
            and len(request_body_bytes) > self.settings.http_operation_request_max_bytes
        ):
            self._raise_error(
                code="http_operation_request_body_too_large",
                message="HTTP request body exceeds the configured maximum size",
                request_metadata=request_context.request_metadata,
                started_at=started_at,
            )

        self._validate_request_url(request_context.url, started_at=started_at)
        self._validate_request_headers(request_context.headers, started_at=started_at)

        try:
            response_context = self._send_request(
                method=method,
                url=request_context.url,
                headers=request_context.headers,
                body_bytes=request_body_bytes,
                timeout_seconds=timeout_seconds,
                started_at=started_at,
            )
        except HttpOperationExecutionError:
            raise
        except httpx.TimeoutException as exc:
            self._raise_error(
                code="http_operation_timeout_exceeded",
                message="HTTP request timed out",
                request_metadata=request_context.request_metadata,
                started_at=started_at,
                details=[{"field": "timeoutSeconds", "issue": str(exc)}],
            )
        except httpx.HTTPError as exc:
            self._raise_error(
                code="http_operation_request_failed",
                message=str(exc),
                request_metadata=request_context.request_metadata,
                started_at=started_at,
            )

        response_metadata, parsed_body = self._parse_response(
            response_context,
            request_metadata=request_context.request_metadata,
            started_at=started_at,
        )
        status_code = int(response_metadata.get("statusCode", response_context.status_code))
        if not 200 <= status_code < 300:
            self._raise_error(
                code="http_operation_status_failed",
                message=f"HTTP request failed with status {status_code}",
                request_metadata=request_context.request_metadata,
                response_metadata=response_metadata,
                status_code=status_code,
                started_at=started_at,
            )

        try:
            validated_output = output_model_type.model_validate(parsed_body)
        except ValidationError as exc:
            self._raise_error(
                code="http_operation_output_validation_failed",
                message="HTTP response failed schema validation",
                request_metadata=request_context.request_metadata,
                response_metadata=response_metadata,
                status_code=status_code,
                details=self._validation_details_from_pydantic_error(exc),
                started_at=started_at,
            )

        output = validated_output.model_dump(mode="json")
        return HttpOperationExecutionResult(
            output=output,
            request_metadata=deepcopy(request_context.request_metadata),
            response_metadata=deepcopy(response_metadata),
            duration_ms=self._duration_ms(started_at),
            status_code=status_code,
            error=None,
        )

    def _send_request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body_bytes: bytes | None,
        timeout_seconds: int,
        started_at: float,
    ) -> _HttpResponseContext:
        redirects: list[dict[str, Any]] = []
        current_method = method
        current_url = url
        current_body = body_bytes
        timeout = float(timeout_seconds)
        with self.client_factory(
            timeout=timeout,
            follow_redirects=False,
            **self.client_kwargs,
        ) as client:
            while True:
                request_kwargs: dict[str, Any] = {"headers": headers}
                if current_body is not None:
                    request_kwargs["content"] = current_body
                with client.stream(current_method, current_url, **request_kwargs) as response:
                    if response.status_code in _HTTP_REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        response_metadata: dict[str, Any] = {
                            "statusCode": response.status_code,
                            "headers": self._response_headers_metadata(response.headers),
                            "redirects": deepcopy(redirects),
                        }
                        if location:
                            response_metadata["location"] = self._redact_url(
                                urljoin(current_url, location)
                            )
                        self._raise_error(
                            code="http_operation_redirect_blocked",
                            message="HTTP redirects are not followed",
                            request_metadata={
                                "method": current_method,
                                "url": self._redact_url(current_url),
                            },
                            response_metadata=response_metadata,
                            status_code=response.status_code,
                            started_at=started_at,
                        )
                    body_bytes = self._read_response_bytes(response, started_at=started_at)
                    return _HttpResponseContext(
                        status_code=response.status_code,
                        headers=httpx.Headers(response.headers),
                        url=str(response.url),
                        encoding=response.encoding,
                        body_bytes=body_bytes,
                        redirects=deepcopy(redirects),
                    )

    def _parse_response(
        self,
        response_context: _HttpResponseContext,
        *,
        request_metadata: dict[str, Any],
        started_at: float,
    ) -> tuple[dict[str, Any], Any]:
        content_type = response_context.headers.get("content-type")
        normalized_content_type = (
            content_type.strip().lower() if isinstance(content_type, str) else ""
        )
        if not normalized_content_type:
            self._raise_error(
                code="http_operation_content_type_unsupported",
                message="HTTP response did not include a supported Content-Type header",
                request_metadata=request_metadata,
                response_metadata={
                    "statusCode": response_context.status_code,
                    "headers": self._response_headers_metadata(response_context.headers),
                },
                status_code=response_context.status_code,
                started_at=started_at,
            )
        if not self._is_supported_content_type(normalized_content_type):
            self._raise_error(
                code="http_operation_content_type_unsupported",
                message=f"HTTP response Content-Type {content_type!r} is not supported",
                request_metadata=request_metadata,
                response_metadata={
                    "statusCode": response_context.status_code,
                    "headers": self._response_headers_metadata(response_context.headers),
                    "contentType": content_type,
                },
                status_code=response_context.status_code,
                started_at=started_at,
            )

        body_bytes = response_context.body_bytes
        body_sha256 = hashlib.sha256(body_bytes).hexdigest()
        response_body = self._decode_response_body(
            body_bytes,
            content_type=normalized_content_type,
            encoding=response_context.encoding,
            started_at=started_at,
            status_code=response_context.status_code,
            headers=response_context.headers,
        )
        response_metadata = {
            "statusCode": response_context.status_code,
            "headers": self._response_headers_metadata(response_context.headers),
            "contentType": content_type,
            "body": response_body,
            "bodyBytes": len(body_bytes),
            "bodySha256": body_sha256,
            "truncated": False,
            "url": self._redact_url(response_context.url),
            "redirects": deepcopy(response_context.redirects),
        }
        return response_metadata, response_body

    def _read_response_bytes(self, response: httpx.Response, *, started_at: float) -> bytes:
        response_bytes = bytearray()
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            response_bytes.extend(chunk)
            if len(response_bytes) > self.settings.http_operation_response_max_bytes:
                self._raise_error(
                    code="http_operation_response_body_too_large",
                    message="HTTP response body exceeds the configured maximum size",
                    request_metadata={"url": self._redact_url(str(response.request.url))},
                    response_metadata={
                        "statusCode": response.status_code,
                        "headers": self._response_headers_metadata(response.headers),
                        "bodyBytes": len(response_bytes),
                    },
                    status_code=response.status_code,
                    started_at=started_at,
                )
        return bytes(response_bytes)

    def _decode_response_body(
        self,
        response_bytes: bytes,
        *,
        content_type: str,
        encoding: str | None,
        started_at: float,
        status_code: int,
        headers: httpx.Headers,
    ) -> Any:
        if any(marker in content_type for marker in _HTTP_JSON_CONTENT_TYPES):
            text = response_bytes.decode(encoding or "utf-8")
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                self._raise_error(
                    code="http_operation_response_parse_failed",
                    message="HTTP JSON response could not be parsed",
                    response_metadata={
                        "statusCode": status_code,
                        "headers": self._response_headers_metadata(headers),
                        "contentType": headers.get("content-type"),
                    },
                    status_code=status_code,
                    details=[{"field": "response.body", "issue": str(exc)}],
                    started_at=started_at,
                )
        text = response_bytes.decode(encoding or "utf-8")
        return text

    def _resolve_request_context(
        self,
        request_payload: Mapping[str, Any],
        *,
        method: str,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any],
        secret_values: Mapping[str, Any],
        package_ownership: PackageExecutionOwnership | None,
        started_at: float,
    ) -> _ResolvedRequestContext:
        resolved_url = self._coerce_text_value(
            self._resolve_request_value(
                request_payload.get("url"),
                initial_input=initial_input,
                slot_outputs=slot_outputs,
                secret_values=secret_values,
                package_ownership=package_ownership,
            ).value,
            field="url",
        )
        headers_value = (
            request_payload.get("headers") if isinstance(request_payload, dict) else None
        )
        query_value = request_payload.get("query") if isinstance(request_payload, dict) else None
        body_value = request_payload.get("body") if isinstance(request_payload, dict) else None

        resolved_headers, header_metadata = self._resolve_string_mapping(
            headers_value,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            secret_values=secret_values,
            package_ownership=package_ownership,
            field_name="headers",
        )
        resolved_query, query_metadata = self._resolve_string_mapping(
            query_value,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            secret_values=secret_values,
            package_ownership=package_ownership,
            field_name="query",
        )
        resolved_body = self._resolve_request_value(
            body_value,
            initial_input=initial_input,
            slot_outputs=slot_outputs,
            secret_values=secret_values,
            package_ownership=package_ownership,
        )

        final_url = self._merge_query_params(resolved_url, resolved_query)
        redacted_request = redact_operation_request_metadata(
            {
                "method": method,
                "url": self._redact_url(final_url),
                "headers": header_metadata,
                "query": query_metadata,
                "body": resolved_body.metadata,
                "bodyBytes": self._body_bytes_length(resolved_body.value),
                "bodySha256": self._body_sha256(resolved_body.value),
            }
        )
        request_body_bytes = self._encode_body(resolved_body.value, request_payload=request_payload)
        if (
            request_body_bytes is not None
            and len(request_body_bytes) > self.settings.http_operation_request_max_bytes
        ):
            self._raise_error(
                code="http_operation_request_body_too_large",
                message="HTTP request body exceeds the configured maximum size",
                request_metadata=cast(dict[str, Any], redacted_request),
                started_at=started_at,
            )
        request_metadata = cast(dict[str, Any], redacted_request)
        request_metadata["url"] = self._redact_url(final_url)
        request_metadata["headers"] = header_metadata
        request_metadata["query"] = query_metadata
        request_metadata["body"] = resolved_body.metadata
        request_metadata["bodyBytes"] = self._body_bytes_length(resolved_body.value)
        body_sha256 = self._body_sha256(resolved_body.value)
        if body_sha256 is not None:
            request_metadata["bodySha256"] = body_sha256
        request_metadata = cast(
            dict[str, Any],
            redact_operation_request_metadata(request_metadata),
        )
        return _ResolvedRequestContext(
            method=method,
            url=final_url,
            headers=resolved_headers,
            query=resolved_query,
            body=resolved_body.value,
            body_bytes=request_body_bytes,
            request_metadata=request_metadata,
        )

    def _resolve_string_mapping(
        self,
        value: object,
        *,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any],
        secret_values: Mapping[str, Any],
        package_ownership: PackageExecutionOwnership | None,
        field_name: str,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        if value is None:
            return {}, {}
        if not isinstance(value, dict):
            self._raise_error(
                code="http_operation_request_value_invalid",
                message=f"HTTP {field_name} must be an object of string values",
                details=[{"field": field_name, "issue": "HTTP request field must be an object"}],
            )
        resolved: dict[str, str] = {}
        metadata: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key:
                self._raise_error(
                    code="http_operation_request_value_invalid",
                    message=f"HTTP {field_name} keys must be non-empty strings",
                    details=[{"field": field_name, "issue": "HTTP request keys must be non-empty"}],
                )
            resolved_value = self._resolve_request_value(
                raw_value,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
                secret_values=secret_values,
                package_ownership=package_ownership,
            )
            resolved[key] = self._coerce_text_value(
                resolved_value.value, field=f"{field_name}.{key}"
            )
            metadata[key] = resolved_value.metadata
        return resolved, metadata

    def _resolve_request_value(
        self,
        value: object,
        *,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any],
        secret_values: Mapping[str, Any],
        package_ownership: PackageExecutionOwnership | None,
    ) -> _ResolvedValue:
        source_kind = self._source_kind(value)
        if source_kind is not None:
            if source_kind == "secret":
                if not isinstance(value, dict):
                    self._raise_error(
                        code="http_operation_request_value_invalid",
                        message="HTTP secret reference must be an object",
                        details=[
                            {"field": "secrets", "issue": "Secret reference must be an object"}
                        ],
                    )
                key = self._required_text(
                    value.get("key"),
                    key_name="key",
                    field_name="secret reference",
                )
                secret_value = self._resolve_secret_value(
                    key,
                    secret_values=secret_values,
                    package_ownership=package_ownership,
                )
                return _ResolvedValue(
                    value=secret_value,
                    metadata={"from": "secret", "key": key, "redacted": True},
                )
            source_value = self._resolve_source_reference_value(
                value,
                initial_input=initial_input,
                slot_outputs=slot_outputs,
            )
            metadata = self._source_metadata(value, source_kind)
            return _ResolvedValue(value=source_value, metadata=metadata)

        if isinstance(value, dict):
            resolved: dict[str, Any] = {}
            resolved_metadata: dict[str, Any] = {}
            for key, item in value.items():
                child = self._resolve_request_value(
                    item,
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                    secret_values=secret_values,
                    package_ownership=package_ownership,
                )
                resolved[str(key)] = child.value
                resolved_metadata[str(key)] = child.metadata
            return _ResolvedValue(value=resolved, metadata=resolved_metadata)

        if isinstance(value, list):
            resolved_items: list[Any] = []
            metadata_items: list[Any] = []
            for item in value:
                child = self._resolve_request_value(
                    item,
                    initial_input=initial_input,
                    slot_outputs=slot_outputs,
                    secret_values=secret_values,
                    package_ownership=package_ownership,
                )
                resolved_items.append(child.value)
                metadata_items.append(child.metadata)
            return _ResolvedValue(value=resolved_items, metadata=metadata_items)

        return _ResolvedValue(value=value, metadata=value)

    def _resolve_source_reference_value(
        self,
        value: object,
        *,
        initial_input: Mapping[str, Any],
        slot_outputs: Mapping[tuple[int, str], Any],
    ) -> Any:
        if not isinstance(value, dict):
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP request source reference must be an object",
                details=[
                    {"field": "request", "issue": "HTTP request source reference must be an object"}
                ],
            )
        source = str(value.get("from", value.get("source", ""))).strip().lower()
        if source == "input":
            path = value.get("path")
            return self._resolve_path(initial_input, path=path, field="request.input")
        if source == "step":
            step_index = value.get("stepIndex")
            slot = value.get("slot")
            if step_index is None or slot is None:
                self._raise_error(
                    code="http_operation_request_value_invalid",
                    message="HTTP step references require stepIndex and slot",
                    details=[{"field": "request", "issue": "Step reference is incomplete"}],
                )
            key = (int(step_index), str(slot))
            if key not in slot_outputs:
                self._raise_error(
                    code="http_operation_source_missing",
                    message=(
                        f"HTTP source slot {slot!r} from step {int(step_index)} was not available"
                    ),
                    details=[
                        {
                            "field": f"step.{int(step_index)}.{slot}",
                            "issue": "Referenced step output is not available",
                        }
                    ],
                )
            source_value = slot_outputs[key]
            path = value.get("path")
            if path is None:
                return source_value
            if source_value is None:
                return None
            return self._resolve_path(
                source_value, path=path, field=f"step.{int(step_index)}.{slot}"
            )
        self._raise_error(
            code="http_operation_request_value_invalid",
            message="HTTP request source reference is invalid",
            details=[{"field": "request", "issue": "Source reference must use input or step"}],
        )

    def _resolve_path(self, value: Any, *, path: object, field: str) -> Any:
        if path is None:
            return value
        if not isinstance(path, str) or not path.strip():
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP request path must be a non-empty string",
                details=[{"field": field, "issue": "Request path is invalid"}],
            )
        current = value
        for segment in path.split("."):
            if not isinstance(current, dict) or segment not in current:
                self._raise_error(
                    code="http_operation_source_missing",
                    message=f"Resolved path {path!r} was not present in the source payload",
                    details=[{"field": field, "issue": "Referenced path was not present"}],
                )
            current = current[segment]
        return current

    def _source_kind(self, value: object) -> str | None:
        if not isinstance(value, dict):
            return None
        raw_source = value.get("from", value.get("source"))
        if not isinstance(raw_source, str):
            return None
        normalized = raw_source.strip().lower()
        if normalized in {"input", "step", "secret", "secrets"}:
            return "secret" if normalized == "secrets" else normalized
        return None

    def _source_metadata(self, value: object, source_kind: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {"from": source_kind, "value": value}
        if source_kind == "input":
            metadata: dict[str, Any] = {"from": "input"}
            if value.get("path") is not None:
                metadata["path"] = value["path"]
            return metadata
        metadata = {
            "from": "step",
            "stepIndex": value.get("stepIndex"),
            "slot": value.get("slot"),
        }
        if value.get("path") is not None:
            metadata["path"] = value["path"]
        return metadata

    def _resolve_secret_value(
        self,
        key: str,
        *,
        secret_values: Mapping[str, Any],
        package_ownership: PackageExecutionOwnership | None,
    ) -> str:
        if key in secret_values:
            value = self._required_text(secret_values[key], key_name=key, field_name="secret value")
            return value
        if self._secret_binding_repository is None or package_ownership is None:
            self._raise_error(
                code="http_operation_secret_session_missing",
                message=(
                    f"HTTP secret binding {key!r} could not be resolved without a package session"
                ),
                details=[{"field": "secrets", "issue": "Secret binding session is required"}],
            )
        binding = self._secret_binding_repository.get_by_key(package_ownership.package_id, key)
        if binding is None:
            self._raise_error(
                code="http_operation_secret_missing",
                message=f"HTTP secret binding {key!r} was not found",
                details=[{"field": f"secrets.{key}", "issue": "Secret binding was not found"}],
            )
        payload = binding.secret_payload if isinstance(binding.secret_payload, dict) else {}
        payload_value = payload.get("value")
        normalized = self._required_text(payload_value, key_name=key, field_name="secret value")
        return normalized

    def _validate_request_url(self, url: str, *, started_at: float) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            self._raise_error(
                code="http_operation_url_invalid",
                message=f"HTTP url scheme {parsed.scheme!r} is not supported",
                details=[{"field": "url", "issue": "URL scheme must be http or https"}],
                started_at=started_at,
            )
        if parsed.scheme == "http" and not self.settings.http_operation_allow_insecure_http:
            self._raise_error(
                code="http_operation_insecure_http_blocked",
                message="HTTP URLs are blocked by configuration",
                details=[{"field": "url", "issue": "Insecure HTTP is disabled"}],
                started_at=started_at,
            )
        if parsed.username or parsed.password:
            self._raise_error(
                code="http_operation_url_invalid",
                message="HTTP URLs cannot include credentials",
                details=[{"field": "url", "issue": "URL credentials are not allowed"}],
                started_at=started_at,
            )
        host = parsed.hostname
        if host is None or not host.strip():
            self._raise_error(
                code="http_operation_url_invalid",
                message="HTTP URL must include a host",
                details=[{"field": "url", "issue": "URL host is required"}],
                started_at=started_at,
            )
        if self.settings.http_operation_block_private_networks:
            for address in self._resolve_host_addresses(host):
                if self._is_disallowed_ip_address(address):
                    self._raise_error(
                        code="http_operation_private_network_blocked",
                        message=f"HTTP host {host!r} resolves to a blocked address",
                        details=[
                            {"field": "url", "issue": "Private or loopback targets are blocked"}
                        ],
                        started_at=started_at,
                    )

    def _validate_request_headers(self, headers: dict[str, str], *, started_at: float) -> None:
        del started_at
        for key, value in headers.items():
            if not key.strip():
                self._raise_error(
                    code="http_operation_request_value_invalid",
                    message="HTTP header names must be non-empty",
                    details=[{"field": "headers", "issue": "Header names must be non-empty"}],
                )
            if not value.strip():
                self._raise_error(
                    code="http_operation_request_value_invalid",
                    message=f"HTTP header {key!r} must not be empty",
                    details=[
                        {"field": f"headers.{key}", "issue": "Header values must be non-empty"}
                    ],
                )

    def _normalize_method(self, method: str | None, *, started_at: float) -> str:
        normalized = self._required_text(method, key_name="method", field_name="method").upper()
        if not normalized.isalpha():
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP method must contain only letters",
                details=[{"field": "method", "issue": "HTTP method is invalid"}],
                started_at=started_at,
            )
        return normalized

    def _normalize_timeout(self, timeout_seconds: int | None, *, started_at: float) -> int:
        if timeout_seconds is None:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP timeout is required",
                details=[{"field": "timeoutSeconds", "issue": "HTTP timeout is required"}],
                started_at=started_at,
            )
        normalized = int(timeout_seconds)
        if normalized > self.settings.http_operation_timeout_max_seconds:
            self._raise_error(
                code="http_operation_timeout_exceeded",
                message="HTTP timeout exceeds the configured maximum",
                details=[
                    {"field": "timeoutSeconds", "issue": "Timeout exceeds the configured maximum"}
                ],
                started_at=started_at,
            )
        if normalized <= 0:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP timeout must be positive",
                details=[{"field": "timeoutSeconds", "issue": "Timeout must be positive"}],
                started_at=started_at,
            )
        return normalized

    def _resolve_output_model(
        self,
        *,
        operation: ExecutionPlanOperation,
        output_model: type[BaseModel] | None,
        started_at: float,
    ) -> type[BaseModel]:
        if output_model is not None:
            return output_model
        if operation.package_runtime_operation is None:
            self._raise_error(
                code="http_operation_output_schema_missing",
                message="HTTP operation output schema is not available",
                started_at=started_at,
            )
        if self._output_schema_compiler is None:
            self._raise_error(
                code="http_operation_output_schema_missing",
                message="HTTP operation output schema cannot be compiled without a session",
                started_at=started_at,
            )
        candidate = self._output_schema_candidate(operation.package_runtime_operation.output_schema)
        try:
            return self._output_schema_compiler.build_runtime_model(candidate)
        except (OutputSchemaCompilerError, ValidationError) as exc:
            self._raise_error(
                code="http_operation_output_schema_invalid",
                message=str(exc),
                started_at=started_at,
            )

    @staticmethod
    def _output_schema_candidate(
        output_schema: PackageLocalOutputSchemaSpec,
    ) -> PackageOutputSchemaCandidate:
        return package_output_schema_candidate(
            key=output_schema.key,
            name=output_schema.name,
            description=output_schema.description,
            json_schema=output_schema.json_schema,
        )

    def _merge_query_params(self, url: str, query: Mapping[str, str]) -> str:
        if not query:
            return url
        parsed = urlsplit(url)
        base_pairs = [
            (name, value)
            for name, value in parse_qsl(parsed.query, keep_blank_values=True)
            if name not in query
        ]
        merged_query = urlencode([*base_pairs, *query.items()])
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, merged_query, parsed.fragment)
        )

    def _body_bytes_length(self, body: Any) -> int:
        if body is None:
            return 0
        if isinstance(body, str):
            return len(body.encode("utf-8"))
        return len(self._json_body_bytes(body))

    def _body_sha256(self, body: Any) -> str | None:
        if body is None:
            return None
        if isinstance(body, str):
            return hashlib.sha256(body.encode("utf-8")).hexdigest()
        return hashlib.sha256(self._json_body_bytes(body)).hexdigest()

    def _encode_body(self, body: Any, *, request_payload: Mapping[str, Any]) -> bytes | None:
        del request_payload
        if body is None:
            return None
        if isinstance(body, str):
            return body.encode("utf-8")
        return self._json_body_bytes(body)

    def _json_body_bytes(self, body: Any) -> bytes:
        try:
            serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except TypeError as exc:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message="HTTP request body is not JSON serializable",
                details=[{"field": "body", "issue": str(exc)}],
            )
        return serialized.encode("utf-8")

    @staticmethod
    def _is_supported_content_type(content_type: str) -> bool:
        if content_type.startswith("text/"):
            return True
        return any(marker in content_type for marker in _HTTP_JSON_CONTENT_TYPES)

    def _response_headers_metadata(self, headers: httpx.Headers) -> dict[str, str]:
        selected: dict[str, str] = {}
        for key, value in headers.items():
            normalized_key = key.strip().lower()
            if normalized_key in _ALLOWED_RESPONSE_HEADERS:
                selected[normalized_key] = value
        return selected

    def _redact_url(self, url: str) -> str:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        query_pairs = []
        for name, value in parse_qsl(parsed.query, keep_blank_values=True):
            if self._is_sensitive_name(name):
                query_pairs.append((name, "[REDACTED]"))
            else:
                query_pairs.append((name, value))
        return urlunsplit(
            (parsed.scheme, host, parsed.path, urlencode(query_pairs), parsed.fragment)
        )

    def _required_text(self, value: object, *, key_name: str, field_name: str) -> str:
        if value is None:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message=f"HTTP {field_name} {key_name!r} is required",
                details=[{"field": field_name, "issue": "Value is required"}],
            )
        normalized = str(value).strip()
        if not normalized:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message=f"HTTP {field_name} {key_name!r} is required",
                details=[{"field": field_name, "issue": "Value is required"}],
            )
        return normalized

    def _coerce_text_value(self, value: Any, *, field: str) -> str:
        if value is None:
            self._raise_error(
                code="http_operation_request_value_invalid",
                message=f"HTTP {field} cannot be null",
                details=[{"field": field, "issue": "Value cannot be null"}],
            )
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                self._raise_error(
                    code="http_operation_request_value_invalid",
                    message=f"HTTP {field} cannot be empty",
                    details=[{"field": field, "issue": "Value cannot be empty"}],
                )
            return normalized
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        self._raise_error(
            code="http_operation_request_value_invalid",
            message=f"HTTP {field} must resolve to a string value",
            details=[{"field": field, "issue": "Value must resolve to a string"}],
        )

    def _resolve_host_addresses(self, host: str) -> list[str]:
        if host in self.resolved_hosts:
            return [str(item) for item in self.resolved_hosts[host]]
        try:
            return [str(item[4][0]) for item in socket.getaddrinfo(host, None)]
        except socket.gaierror:
            return []

    @staticmethod
    def _is_disallowed_ip_address(address: str) -> bool:
        try:
            ip_address = ipaddress.ip_address(address)
        except ValueError:
            return True
        return (
            ip_address.is_loopback
            or ip_address.is_private
            or ip_address.is_link_local
            or ip_address.is_multicast
            or ip_address.is_reserved
            or ip_address.is_unspecified
        )

    @staticmethod
    def _duration_ms(started_at: float, fallback: int | None = None) -> int:
        if fallback is not None:
            return fallback
        return max(0, int((time.monotonic() - started_at) * 1000))

    def _raise_error(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        request_metadata: dict[str, Any] | None = None,
        response_metadata: dict[str, Any] | None = None,
        status_code: int | None = None,
        started_at: float | None = None,
    ) -> NoReturn:
        raise HttpOperationExecutionError(
            code=code,
            message=message,
            details=list(details or []),
            request_metadata=deepcopy(request_metadata) if request_metadata is not None else None,
            response_metadata=(
                deepcopy(response_metadata) if response_metadata is not None else None
            ),
            status_code=status_code,
            duration_ms=None if started_at is None else self._duration_ms(started_at),
        )

    @staticmethod
    def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, str]]:
        details: list[dict[str, str]] = []
        for error in exc.errors():
            location = error.get("loc", ())
            field = ".".join(str(part) for part in location) if location else "output"
            details.append(
                {"field": field or "output", "issue": str(error.get("msg", "Invalid value"))}
            )
        return details

    def _allowed_methods(self) -> set[str]:
        return set(self.settings.http_operation_allowed_methods)

    @staticmethod
    def _normalize_url_result(url: str) -> str:
        return url.strip()

    def _is_sensitive_name(self, value: object) -> bool:
        normalized = str(value).replace("-", "_").replace(" ", "_").lower()
        return any(part in normalized for part in _SENSITIVE_NAME_PARTS)


__all__ = [
    "HttpOperationExecutionError",
    "HttpOperationExecutionResult",
    "HttpOperationExecutionService",
]
