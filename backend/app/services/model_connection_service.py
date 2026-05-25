from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error, validation_error
from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionConnectionTestRead,
    ModelConnectionCreate,
    ModelConnectionListItemRead,
    ModelConnectionListRead,
    ModelConnectionRead,
    ModelConnectionOutputStrategyPolicy,
    ModelConnectionParallelToolCallsPolicy,
    ModelConnectionReasoningPolicy,
    ModelConnectionStreamingPolicy,
    ModelConnectionUpdate,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
    normalize_model_connection_key,
)
from app.services.execution_plan import PackageResolvedModelBinding
from app.services.model_connection_compatibility import CompatibilityResolutionService
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_dto import ModelConnectionTestRequest
from app.services.model_gateway_openai import (
    DEFAULT_OPENAI_CLIENT_FACTORY as OpenAI,
)
from app.services.model_gateway_openai import (
    OpenAIProtocolAdapter,
)


@dataclass(frozen=True)
class _ModelConnectionTestResult:
    ok: bool
    message: str
    tested_at: datetime


class ModelConnectionService:
    session: Session
    repository: ModelConnectionRepository

    def __init__(
        self,
        session: Session,
        model_gateway: ModelExecutionGateway | None = None,
    ) -> None:
        self.session = session
        self.repository = ModelConnectionRepository(session)
        self.compatibility_resolution_service = CompatibilityResolutionService()
        self.model_gateway = model_gateway or ModelExecutionGateway(
            OpenAIProtocolAdapter(client_factory=OpenAI)
        )

    def list_connections(self) -> ModelConnectionListRead:
        items = self.repository.list_connections()
        return ModelConnectionListRead(
            items=[self._to_list_item_read(item) for item in items]
        )

    def get_connection(self, connection_id: int) -> ModelConnectionRead:
        return self._to_read(self._get_model(connection_id))

    def resolve_connection_by_key(self, key: str) -> ModelConnection:
        return self._resolve_connection_by_key(
            key,
            path="modelConnection",
            message="Model connection validation failed",
        )

    def lookup_package_model_connection_binding(
        self,
        key: str,
    ) -> PackageResolvedModelBinding | None:
        normalized_key = self._normalize_key_for_resolver(
            key,
            path="modelConnection",
            message="Package model connection validation failed",
        )
        connection = self.repository.get_by_key(normalized_key)
        if connection is None:
            return None
        return self._to_package_binding(connection)

    def resolve_package_model_connection_binding(
        self,
        key: str,
        *,
        path: str = "modelConnection",
        require_api_key: bool = False,
    ) -> PackageResolvedModelBinding:
        connection = self._resolve_connection_by_key(
            key,
            path=path,
            message="Package model connection validation failed",
        )
        binding = self._to_package_binding(connection)
        if require_api_key and not binding.has_api_key:
            raise validation_error(
                "Package model connection validation failed",
                [{"field": path, "issue": "API key is not configured"}],
            )
        return binding

    def create_connection(self, payload: ModelConnectionCreate) -> ModelConnectionRead:
        if self.repository.get_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="model_connection_duplicate_key",
                message="A model connection with this key already exists",
            )

        connection = ModelConnection(
            key=payload.key,
            status="active",
            connection_kind=payload.connection_kind.value,
            protocol_profile=payload.protocol_profile.value,
            name=payload.name,
            description=payload.description,
            base_url=payload.base_url,
            model_id=payload.model_id,
            reasoning_effort=payload.reasoning_effort,
            capabilities=dump_model_connection_capabilities(
                default_model_connection_capabilities(payload.protocol_profile),
            ),
            output_strategy_policy=ModelConnectionOutputStrategyPolicy.PREFER_STRICT_SCHEMA.value,
            parallel_tool_calls_policy=ModelConnectionParallelToolCallsPolicy.SERIALIZE.value,
            reasoning_policy=ModelConnectionReasoningPolicy.ALLOW.value,
            streaming_policy=ModelConnectionStreamingPolicy.ALLOW.value,
            probe_cache_ttl_seconds=900,
            timeout_seconds=payload.timeout_seconds,
        )
        self._set_api_key(connection, payload.api_key)

        try:
            _ = self.repository.add(connection)
            self.session.commit()
            self.session.refresh(connection)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read(connection)

    def update_connection(
        self,
        connection_id: int,
        payload: ModelConnectionUpdate,
    ) -> ModelConnectionRead:
        connection = self._get_model(connection_id)

        if "name" in payload.model_fields_set and payload.name is not None:
            connection.name = payload.name
        if "description" in payload.model_fields_set:
            connection.description = payload.description or ""
        reset_connection_test_result = False

        reset_probe_cache = True
        if "connection_kind" in payload.model_fields_set and payload.connection_kind is not None:
            connection.connection_kind = payload.connection_kind.value
            reset_connection_test_result = True
            reset_probe_cache = True
        if "protocol_profile" in payload.model_fields_set and payload.protocol_profile is not None:
            connection.protocol_profile = payload.protocol_profile.value
            connection.capabilities = dump_model_connection_capabilities(
                default_model_connection_capabilities(connection.protocol_profile),
            )
            connection.output_strategy_policy = (
                ModelConnectionOutputStrategyPolicy.PREFER_STRICT_SCHEMA.value
            )
            connection.parallel_tool_calls_policy = (
                ModelConnectionParallelToolCallsPolicy.SERIALIZE.value
            )
            connection.reasoning_policy = ModelConnectionReasoningPolicy.ALLOW.value
            connection.streaming_policy = ModelConnectionStreamingPolicy.ALLOW.value
            connection.probe_cache_ttl_seconds = 900
            reset_connection_test_result = True
            reset_probe_cache = True
        if "base_url" in payload.model_fields_set and payload.base_url is not None:
            connection.base_url = payload.base_url
            reset_connection_test_result = True
            reset_probe_cache = True
        if "model_id" in payload.model_fields_set and payload.model_id is not None:
            connection.model_id = payload.model_id
            reset_connection_test_result = True
            reset_probe_cache = True
        if "reasoning_effort" in payload.model_fields_set:
            connection.reasoning_effort = payload.reasoning_effort
            reset_connection_test_result = True
            reset_probe_cache = True
        if "timeout_seconds" in payload.model_fields_set and payload.timeout_seconds is not None:
            connection.timeout_seconds = payload.timeout_seconds
            reset_connection_test_result = True
            reset_probe_cache = True
        if "api_key" in payload.model_fields_set:
            self._set_api_key(connection, payload.api_key)
            reset_connection_test_result = True
            reset_probe_cache = True

        if reset_probe_cache:
            self._clear_probe_cache(connection)
        if reset_connection_test_result:
            self._clear_connection_test_result(connection)

        try:
            self.session.commit()
            self.session.refresh(connection)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read(connection)

    def test_connection(self, connection_id: int) -> ModelConnectionConnectionTestRead:
        connection = self._get_model(connection_id)
        result = self._run_connection_test(connection)

        try:
            connection.last_tested_at = result.tested_at
            connection.last_test_ok = result.ok
            connection.last_test_message = result.message
            self._clear_probe_cache(connection)
            self.session.commit()
            self.session.refresh(connection)
        except Exception:
            self.session.rollback()
            raise

        return ModelConnectionConnectionTestRead.model_validate(
            {
                "modelConnectionId": connection.id,
                "ok": result.ok,
                "message": result.message,
                "lastTestedAt": result.tested_at,
            }
        )

    def delete_connection(self, connection_id: int) -> None:
        connection = self._get_model(connection_id)

        try:
            self.repository.delete(connection)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _get_model(self, connection_id: int) -> ModelConnection:
        connection = self.repository.get(connection_id)
        if connection is None:
            raise not_found_error("Model connection")
        return connection

    def _resolve_connection_by_key(
        self,
        key: str,
        *,
        path: str,
        message: str,
    ) -> ModelConnection:
        normalized_key = self._normalize_key_for_resolver(key, path=path, message=message)
        connection = self.repository.get_by_key(normalized_key)
        if connection is None:
            raise validation_error(
                message,
                [
                    {
                        "field": path,
                        "issue": f"Model connection {normalized_key!r} was not found",
                    }
                ],
            )
        return connection

    @staticmethod
    def _normalize_key_for_resolver(key: str, *, path: str, message: str) -> str:
        try:
            return normalize_model_connection_key(key)
        except ValueError as exc:
            raise validation_error(
                message,
                [{"field": path, "issue": str(exc)}],
            ) from exc

    def _to_list_item_read(self, connection: ModelConnection) -> ModelConnectionListItemRead:
        return ModelConnectionListItemRead.model_validate(self._read_payload(connection))

    def _to_read(self, connection: ModelConnection) -> ModelConnectionRead:
        return ModelConnectionRead.model_validate(
            {
                **self._read_payload(connection),
                "created_at": connection.created_at,
                "updated_at": connection.updated_at,
            }
        )

    def _read_payload(self, connection: ModelConnection) -> dict[str, Any]:
        resolution = self.compatibility_resolution_service.resolve_connection(connection)
        return {
            "id": connection.id,
            "key": resolution.key,
            "name": resolution.name,
            "description": connection.description,
            "connection_kind": resolution.connection_kind,
            "protocol_profile": resolution.protocol_profile,
            "base_url": resolution.base_url,
            "model_id": resolution.model_id,
            "reasoning_effort": resolution.reasoning_effort,
            "capabilities": resolution.capabilities,
            "output_strategy_policy": resolution.output_strategy_policy,
            "parallel_tool_calls_policy": resolution.parallel_tool_calls_policy,
            "reasoning_policy": resolution.reasoning_policy,
            "streaming_policy": resolution.streaming_policy,
            "last_probed_at": connection.last_probed_at,
            "probe_cache_ttl_seconds": resolution.probe_cache_ttl_seconds,
            "timeout_seconds": resolution.timeout_seconds,
            "last_tested_at": connection.last_tested_at,
            "last_test_ok": connection.last_test_ok,
            "last_test_message": connection.last_test_message,
        }

    def _to_package_binding(self, connection: ModelConnection) -> PackageResolvedModelBinding:
        resolution = self.compatibility_resolution_service.resolve_connection(connection)
        return self.compatibility_resolution_service.to_package_resolved_model_binding(
            resolution,
        )

    def _run_connection_test(self, connection: ModelConnection) -> _ModelConnectionTestResult:
        tested_at = utcnow()
        result = self.model_gateway.test_connection(
            ModelConnectionTestRequest(
                connection=self.compatibility_resolution_service.to_gateway_connection_config(
                    connection,
                ),
                instructions="Reply with the single word OK.",
                input_text="Connection test.",
            )
        )
        return _ModelConnectionTestResult(
            ok=result.ok,
            message=result.message,
            tested_at=tested_at,
        )

    @classmethod
    def _clear_probe_cache(cls, connection: ModelConnection) -> None:
        connection.last_probed_at = None
        try:
            capabilities = ModelConnectionCapabilities.model_validate(connection.capabilities)
        except ValidationError:
            capabilities = default_model_connection_capabilities(connection.protocol_profile)
        for field_name in type(capabilities).model_fields:
            getattr(capabilities, field_name).last_probed_at = None
        connection.capabilities = dump_model_connection_capabilities(capabilities)

    @staticmethod
    def _get_api_key(connection: ModelConnection) -> str | None:
        payload = connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
        raw_api_key = payload.get("apiKey")
        if raw_api_key is None:
            return None
        normalized = str(raw_api_key).strip()
        return normalized or None

    @staticmethod
    def _set_api_key(connection: ModelConnection, api_key: str | None) -> None:
        payload = (
            dict(connection.secret_payload) if isinstance(connection.secret_payload, dict) else {}
        )
        if api_key is None:
            payload.pop("apiKey", None)
        else:
            payload["apiKey"] = api_key
        connection.secret_payload = payload

    @staticmethod
    def _clear_connection_test_result(connection: ModelConnection) -> None:
        connection.last_tested_at = None
        connection.last_test_ok = None
        connection.last_test_message = None


__all__ = ["ModelConnectionService"]
