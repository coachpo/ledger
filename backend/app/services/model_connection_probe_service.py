from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import not_found_error
from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.schemas.common import to_camel
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionCapabilityProbeRead,
    ModelConnectionCapabilityProbeRequest,
    ModelConnectionCapabilityStatus,
    api_style_for_model_connection_protocol_profile,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
    normalize_model_connection_capability_key,
)
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_dto import ModelCapabilityProbeRequest, ModelGatewayConnectionConfig
from app.services.model_gateway_openai import (
    DEFAULT_OPENAI_CLIENT_FACTORY as OpenAI,
)
from app.services.model_gateway_openai import OpenAIProtocolAdapter


class ModelConnectionProbeService:
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

    def probe_connection_capabilities(
        self,
        connection_id: int,
        payload: ModelConnectionCapabilityProbeRequest | None = None,
    ) -> ModelConnectionCapabilityProbeRead:
        request = payload or ModelConnectionCapabilityProbeRequest()
        connection = self._get_model(connection_id)
        capabilities = self._capabilities_payload(connection)
        requested_capability_fields = self._requested_capability_fields(request)
        cached = not request.refresh and self._is_cache_fresh(
            capabilities,
            requested_capability_fields,
            ttl_seconds=connection.probe_cache_ttl_seconds,
        )
        if cached:
            probed_at = self._latest_probe_timestamp(
                connection=connection,
                capabilities=capabilities,
                requested_capability_fields=requested_capability_fields,
            )
        else:
            probe_result = self.model_gateway.probe_capabilities(
                ModelCapabilityProbeRequest(
                    connection=self._to_gateway_connection(connection),
                    capability_keys=requested_capability_fields,
                )
            )
            probed_at = utcnow()
            for field_name in requested_capability_fields:
                state = getattr(capabilities, field_name)
                outcome = probe_result.capabilities.get(field_name)
                if outcome is not None:
                    state.status = ModelConnectionCapabilityStatus(outcome.status)
                    state.detail = outcome.detail
                state.last_probed_at = probed_at
            connection.capabilities = dump_model_connection_capabilities(capabilities)
            connection.last_probed_at = probed_at
            try:
                self.session.commit()
                self.session.refresh(connection)
            except Exception:
                self.session.rollback()
                raise
            capabilities = self._capabilities_payload(connection)
        return ModelConnectionCapabilityProbeRead.model_validate(
            {
                "modelConnectionId": connection.id,
                "requestedCapabilityKeys": [
                    to_camel(field_name) for field_name in requested_capability_fields
                ],
                "cached": cached,
                "lastProbedAt": probed_at,
                "probeCacheTtlSeconds": connection.probe_cache_ttl_seconds,
                "capabilities": dump_model_connection_capabilities(capabilities),
            }
        )

    def _get_model(self, connection_id: int) -> ModelConnection:
        connection = self.repository.get(connection_id)
        if connection is None:
            raise not_found_error("Model connection")
        return connection

    @staticmethod
    def _requested_capability_fields(
        request: ModelConnectionCapabilityProbeRequest,
    ) -> tuple[str, ...]:
        if not request.capability_keys:
            return tuple(ModelConnectionCapabilities.model_fields)
        return tuple(
            normalize_model_connection_capability_key(capability_key)
            for capability_key in request.capability_keys
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
            api_style=api_style_for_model_connection_protocol_profile(
                connection.protocol_profile,
            ),
            timeout_seconds=connection.timeout_seconds,
            api_key=cls._get_api_key(connection),
            capabilities=dump_model_connection_capabilities(cls._capabilities_payload(connection)),
            output_strategy_policy=connection.output_strategy_policy,
            parallel_tool_calls_policy=connection.parallel_tool_calls_policy,
            reasoning_policy=connection.reasoning_policy,
            streaming_policy=connection.streaming_policy,
        )

    @staticmethod
    def _capabilities_payload(connection: ModelConnection) -> ModelConnectionCapabilities:
        try:
            return ModelConnectionCapabilities.model_validate(connection.capabilities)
        except ValidationError:
            return default_model_connection_capabilities(connection.protocol_profile)

    @staticmethod
    def _get_api_key(connection: ModelConnection) -> str | None:
        payload = connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
        raw_api_key = payload.get("apiKey")
        if raw_api_key is None:
            return None
        normalized = str(raw_api_key).strip()
        return normalized or None

    def _is_cache_fresh(
        self,
        capabilities: ModelConnectionCapabilities,
        requested_capability_fields: tuple[str, ...],
        *,
        ttl_seconds: int,
    ) -> bool:
        current_time = utcnow()
        ttl = timedelta(seconds=ttl_seconds)
        for field_name in requested_capability_fields:
            last_probed_at = getattr(capabilities, field_name).last_probed_at
            if last_probed_at is None:
                return False
            if current_time - last_probed_at > ttl:
                return False
        return True

    @staticmethod
    def _latest_probe_timestamp(
        *,
        connection: ModelConnection,
        capabilities: ModelConnectionCapabilities,
        requested_capability_fields: tuple[str, ...],
    ) -> datetime:
        timestamps = [connection.last_probed_at]
        timestamps.extend(
            getattr(capabilities, field_name).last_probed_at
            for field_name in requested_capability_fields
        )
        latest = max((timestamp for timestamp in timestamps if timestamp is not None), default=None)
        if latest is None:
            return utcnow()
        return latest


__all__ = ["ModelConnectionProbeService"]
