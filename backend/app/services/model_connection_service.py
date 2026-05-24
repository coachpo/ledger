from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
    ModelConnectionUpdate,
    api_style_for_model_connection_protocol_profile,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
    normalize_model_connection_key,
)
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_dto import ModelConnectionTestRequest, ModelGatewayConnectionConfig
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


@dataclass(frozen=True)
class PackageModelConnectionBinding:
    key: str
    name: str
    connection_kind: str
    protocol_profile: str
    base_url: str
    model_id: str
    reasoning_effort: str | None
    capabilities: dict[str, object]
    output_strategy_policy: str
    parallel_tool_calls_policy: str
    reasoning_policy: str
    streaming_policy: str
    probe_cache_ttl_seconds: int
    api_style: str
    timeout_seconds: int
    has_api_key: bool


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
        self.model_gateway = model_gateway or ModelExecutionGateway(
            OpenAIProtocolAdapter(client_factory=OpenAI)
        )

    def list_connections(self) -> ModelConnectionListRead:
        items = self.repository.list_connections()
        return ModelConnectionListRead(
            items=[ModelConnectionListItemRead.model_validate(item) for item in items]
        )

    def get_connection(self, connection_id: int) -> ModelConnectionRead:
        return ModelConnectionRead.model_validate(self._get_model(connection_id))

    def resolve_connection_by_key(self, key: str) -> ModelConnection:
        return self._resolve_connection_by_key(
            key,
            path="modelConnection",
            message="Model connection validation failed",
        )

    def lookup_package_model_connection_binding(
        self,
        key: str,
    ) -> PackageModelConnectionBinding | None:
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
    ) -> PackageModelConnectionBinding:
        connection = self._resolve_connection_by_key(
            key,
            path=path,
            message="Package model connection validation failed",
        )
        if require_api_key and self._get_api_key(connection) is None:
            raise validation_error(
                "Package model connection validation failed",
                [{"field": path, "issue": "API key is not configured"}],
            )
        return self._to_package_binding(connection)

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
            capabilities=dump_model_connection_capabilities(payload.capabilities),
            output_strategy_policy=payload.output_strategy_policy.value,
            parallel_tool_calls_policy=payload.parallel_tool_calls_policy.value,
            reasoning_policy=payload.reasoning_policy.value,
            streaming_policy=payload.streaming_policy.value,
            probe_cache_ttl_seconds=payload.probe_cache_ttl_seconds,
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
        return ModelConnectionRead.model_validate(connection)

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
            reset_connection_test_result = True
            reset_probe_cache = True
            if "capabilities" not in payload.model_fields_set:
                connection.capabilities = dump_model_connection_capabilities(
                    default_model_connection_capabilities(connection.protocol_profile),
                )
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
        if "capabilities" in payload.model_fields_set and payload.capabilities is not None:
            connection.capabilities = dump_model_connection_capabilities(payload.capabilities)
            reset_probe_cache = True
        if (
            "output_strategy_policy" in payload.model_fields_set
            and payload.output_strategy_policy is not None
        ):
            connection.output_strategy_policy = payload.output_strategy_policy.value
            reset_probe_cache = True
        if (
            "parallel_tool_calls_policy" in payload.model_fields_set
            and payload.parallel_tool_calls_policy is not None
        ):
            connection.parallel_tool_calls_policy = payload.parallel_tool_calls_policy.value
            reset_probe_cache = True
        if "reasoning_policy" in payload.model_fields_set and payload.reasoning_policy is not None:
            connection.reasoning_policy = payload.reasoning_policy.value
            reset_probe_cache = True
        if "streaming_policy" in payload.model_fields_set and payload.streaming_policy is not None:
            connection.streaming_policy = payload.streaming_policy.value
            reset_probe_cache = True
        if (
            "probe_cache_ttl_seconds" in payload.model_fields_set
            and payload.probe_cache_ttl_seconds is not None
        ):
            connection.probe_cache_ttl_seconds = payload.probe_cache_ttl_seconds
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
        return ModelConnectionRead.model_validate(connection)

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

    @classmethod
    def _to_package_binding(cls, connection: ModelConnection) -> PackageModelConnectionBinding:
        return PackageModelConnectionBinding(
            key=connection.key,
            name=connection.name,
            connection_kind=connection.connection_kind,
            protocol_profile=connection.protocol_profile,
            base_url=connection.base_url,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            capabilities=cls._capabilities_payload(connection),
            output_strategy_policy=connection.output_strategy_policy,
            parallel_tool_calls_policy=connection.parallel_tool_calls_policy,
            reasoning_policy=connection.reasoning_policy,
            streaming_policy=connection.streaming_policy,
            probe_cache_ttl_seconds=connection.probe_cache_ttl_seconds,
            api_style=api_style_for_model_connection_protocol_profile(connection.protocol_profile),
            timeout_seconds=connection.timeout_seconds,
            has_api_key=cls._get_api_key(connection) is not None,
        )

    def _run_connection_test(self, connection: ModelConnection) -> _ModelConnectionTestResult:
        tested_at = utcnow()
        result = self.model_gateway.test_connection(
            ModelConnectionTestRequest(
                connection=self._to_gateway_connection(connection),
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
    def _to_gateway_connection(cls, connection: ModelConnection) -> ModelGatewayConnectionConfig:
        return ModelGatewayConnectionConfig(
            id=connection.id,
            name=connection.name,
            connection_kind=connection.connection_kind,
            base_url=connection.base_url,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            api_style=api_style_for_model_connection_protocol_profile(connection.protocol_profile),
            timeout_seconds=connection.timeout_seconds,
            api_key=cls._get_api_key(connection),
            capabilities=cls._capabilities_payload(connection),
            output_strategy_policy=connection.output_strategy_policy,
            parallel_tool_calls_policy=connection.parallel_tool_calls_policy,
            reasoning_policy=connection.reasoning_policy,
            streaming_policy=connection.streaming_policy,
        )

    @staticmethod
    def _capabilities_payload(connection: ModelConnection) -> dict[str, object]:
        try:
            capabilities = ModelConnectionCapabilities.model_validate(connection.capabilities)
        except ValidationError:
            capabilities = default_model_connection_capabilities(connection.protocol_profile)
        return dump_model_connection_capabilities(capabilities)

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


__all__ = ["ModelConnectionService", "PackageModelConnectionBinding"]
