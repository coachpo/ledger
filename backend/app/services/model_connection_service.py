from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import openai
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.errors import not_found_error
from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.schemas.model_connection import (
    ModelConnectionConnectionTestRead,
    ModelConnectionCreate,
    ModelConnectionListItemRead,
    ModelConnectionListRead,
    ModelConnectionRead,
    ModelConnectionStatus,
    ModelConnectionUpdate,
)


@dataclass(frozen=True)
class _ModelConnectionTestResult:
    ok: bool
    message: str
    tested_at: datetime


class ModelConnectionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ModelConnectionRepository(session)

    def list_connections(
        self,
        *,
        status_filter: ModelConnectionStatus | None = None,
    ) -> ModelConnectionListRead:
        items = self.repository.list_connections(
            status=status_filter.value if status_filter is not None else None
        )
        return ModelConnectionListRead(
            items=[ModelConnectionListItemRead.model_validate(item) for item in items]
        )

    def get_connection(self, connection_id: int) -> ModelConnectionRead:
        return ModelConnectionRead.model_validate(self._get_model(connection_id))

    def create_connection(self, payload: ModelConnectionCreate) -> ModelConnectionRead:
        connection = ModelConnection(
            status=ModelConnectionStatus.ACTIVE.value,
            name=payload.name,
            description=payload.description,
            base_url=payload.base_url,
            organization=payload.organization,
            project=payload.project,
            model_id=payload.model_id,
            reasoning_effort=payload.reasoning_effort.value,
            timeout_seconds=payload.timeout_seconds,
        )
        self._set_api_key(connection, payload.api_key)

        try:
            self.repository.add(connection)
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
        if "base_url" in payload.model_fields_set and payload.base_url is not None:
            connection.base_url = payload.base_url
        if "organization" in payload.model_fields_set:
            connection.organization = payload.organization
        if "project" in payload.model_fields_set:
            connection.project = payload.project
        if "model_id" in payload.model_fields_set and payload.model_id is not None:
            connection.model_id = payload.model_id
        if "reasoning_effort" in payload.model_fields_set and payload.reasoning_effort is not None:
            connection.reasoning_effort = payload.reasoning_effort.value
        if "timeout_seconds" in payload.model_fields_set and payload.timeout_seconds is not None:
            connection.timeout_seconds = payload.timeout_seconds
        if "api_key" in payload.model_fields_set:
            self._set_api_key(connection, payload.api_key)

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

    def archive_connection(self, connection_id: int) -> ModelConnectionRead:
        connection = self._get_model(connection_id)
        if connection.status == ModelConnectionStatus.ARCHIVED.value:
            return ModelConnectionRead.model_validate(connection)

        try:
            connection.status = ModelConnectionStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(connection)
        except Exception:
            self.session.rollback()
            raise
        return ModelConnectionRead.model_validate(connection)

    def _get_model(self, connection_id: int) -> ModelConnection:
        connection = self.repository.get(connection_id)
        if connection is None:
            raise not_found_error("Model connection")
        return connection

    def _run_connection_test(self, connection: ModelConnection) -> _ModelConnectionTestResult:
        tested_at = utcnow()
        api_key = self._get_api_key(connection)
        if api_key is None:
            return _ModelConnectionTestResult(
                ok=False,
                message="API key is not configured.",
                tested_at=tested_at,
            )

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": connection.base_url,
            "timeout": float(connection.timeout_seconds),
            "max_retries": 0,
        }
        if connection.organization:
            client_kwargs["organization"] = connection.organization
        if connection.project:
            client_kwargs["project"] = connection.project

        try:
            with OpenAI(**client_kwargs) as client:
                response = client.responses.create(
                    model=connection.model_id,
                    instructions="Reply with the single word OK.",
                    input="Connection test.",
                    reasoning=cast(Any, {"effort": connection.reasoning_effort}),
                )
            request_id = getattr(response, "_request_id", None)
            message = "Connection test succeeded."
            if isinstance(request_id, str) and request_id.strip():
                message = f"Connection test succeeded (request {request_id.strip()})."
            return _ModelConnectionTestResult(ok=True, message=message, tested_at=tested_at)
        except openai.APITimeoutError:
            return _ModelConnectionTestResult(
                ok=False,
                message="Connection test timed out.",
                tested_at=tested_at,
            )
        except openai.APIConnectionError:
            return _ModelConnectionTestResult(
                ok=False,
                message="Connection test could not reach the OpenAI API.",
                tested_at=tested_at,
            )
        except openai.APIStatusError as exc:
            return _ModelConnectionTestResult(
                ok=False,
                message=self._format_api_status_error(exc, api_key=api_key),
                tested_at=tested_at,
            )
        except openai.APIError as exc:
            return _ModelConnectionTestResult(
                ok=False,
                message=self._normalize_test_message(str(exc), api_key=api_key),
                tested_at=tested_at,
            )
        except Exception as exc:
            return _ModelConnectionTestResult(
                ok=False,
                message=self._normalize_test_message(
                    f"Unexpected connection test failure: {exc}",
                    api_key=api_key,
                ),
                tested_at=tested_at,
            )

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
        connection.has_api_key = bool(api_key)
        connection.api_key_last4 = api_key[-4:] if api_key else None

    def _format_api_status_error(
        self,
        exc: openai.APIStatusError,
        *,
        api_key: str,
    ) -> str:
        message = self._extract_api_status_message(exc)
        request_id = getattr(exc, "request_id", None)
        if isinstance(request_id, str) and request_id.strip():
            message = f"{message} requestId={request_id.strip()}"
        return self._normalize_test_message(message, api_key=api_key)

    @staticmethod
    def _extract_api_status_message(exc: openai.APIStatusError) -> str:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            raw_error = body.get("error")
            if isinstance(raw_error, dict):
                raw_message = raw_error.get("message")
                if isinstance(raw_message, str) and raw_message.strip():
                    return raw_message.strip()
            raw_message = body.get("message")
            if isinstance(raw_message, str) and raw_message.strip():
                return raw_message.strip()

        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int):
            return f"OpenAI request failed with status {status_code}."
        return "OpenAI request failed."

    @staticmethod
    def _normalize_test_message(message: str, *, api_key: str | None) -> str:
        normalized = " ".join(message.split()).strip()
        if api_key:
            normalized = normalized.replace(api_key, "[REDACTED]")
        if len(normalized) > 500:
            return f"{normalized[:497]}..."
        return normalized or "Connection test failed."


__all__ = ["ModelConnectionService"]
