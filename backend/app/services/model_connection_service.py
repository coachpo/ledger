from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import openai
from fastapi import status
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error, validation_error
from app.core.formatting import utcnow
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.schemas.model_connection import (
    ModelConnectionConnectionTestRead,
    ModelConnectionCreate,
    ModelConnectionListItemRead,
    ModelConnectionListRead,
    ModelConnectionRead,
    ModelConnectionUpdate,
    normalize_model_connection_key,
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
    base_url: str
    model_id: str
    reasoning_effort: str | None
    api_style: str
    timeout_seconds: int
    has_api_key: bool


class ModelConnectionService:
    session: Session
    repository: ModelConnectionRepository

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ModelConnectionRepository(session)

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
            name=payload.name,
            description=payload.description,
            api_style=payload.api_style.value,
            base_url=payload.base_url,
            model_id=payload.model_id,
            reasoning_effort=payload.reasoning_effort,
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

        if "connection_kind" in payload.model_fields_set and payload.connection_kind is not None:
            connection.connection_kind = payload.connection_kind.value
            reset_connection_test_result = True
        if "api_style" in payload.model_fields_set and payload.api_style is not None:
            connection.api_style = payload.api_style.value
            reset_connection_test_result = True
        if "base_url" in payload.model_fields_set and payload.base_url is not None:
            connection.base_url = payload.base_url
            reset_connection_test_result = True
        if "model_id" in payload.model_fields_set and payload.model_id is not None:
            connection.model_id = payload.model_id
            reset_connection_test_result = True
        if "reasoning_effort" in payload.model_fields_set:
            connection.reasoning_effort = payload.reasoning_effort
            reset_connection_test_result = True
        if "timeout_seconds" in payload.model_fields_set and payload.timeout_seconds is not None:
            connection.timeout_seconds = payload.timeout_seconds
            reset_connection_test_result = True
        if "api_key" in payload.model_fields_set:
            self._set_api_key(connection, payload.api_key)
            reset_connection_test_result = True

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
            base_url=connection.base_url,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            api_style=connection.api_style,
            timeout_seconds=connection.timeout_seconds,
            has_api_key=cls._get_api_key(connection) is not None,
        )

    def _run_connection_test(self, connection: ModelConnection) -> _ModelConnectionTestResult:
        tested_at = utcnow()
        if connection.connection_kind == "deterministic_smoke":
            return _ModelConnectionTestResult(
                ok=True,
                message="Deterministic smoke test succeeded.",
                tested_at=tested_at,
            )

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

        try:
            if connection.api_style == "responses":
                return self._run_responses_connection_test(
                    connection,
                    client_kwargs,
                    tested_at,
                )
            if connection.api_style == "chat_completions":
                return self._run_chat_completions_connection_test(
                    connection,
                    client_kwargs,
                    tested_at,
                )
            api_style = connection.api_style
            unsupported_api_style_message = (
                f"Model connection validation failed: unsupported API style {api_style!r}."
            )
            return _ModelConnectionTestResult(
                ok=False,
                message=self._normalize_test_message(
                    unsupported_api_style_message,
                    api_key=api_key,
                ),
                tested_at=tested_at,
            )
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

    def _run_responses_connection_test(
        self,
        connection: ModelConnection,
        client_kwargs: dict[str, Any],
        tested_at: datetime,
    ) -> _ModelConnectionTestResult:
        request_kwargs: dict[str, Any] = {
            "model": connection.model_id,
            "instructions": "Reply with the single word OK.",
            "input": "Connection test.",
        }
        if connection.reasoning_effort is not None:
            request_kwargs["reasoning"] = {"effort": connection.reasoning_effort}
        with OpenAI(**client_kwargs) as client:
            response = client.responses.create(**request_kwargs)
        return _ModelConnectionTestResult(
            ok=True,
            message=self._success_message(response),
            tested_at=tested_at,
        )

    def _run_chat_completions_connection_test(
        self,
        connection: ModelConnection,
        client_kwargs: dict[str, Any],
        tested_at: datetime,
    ) -> _ModelConnectionTestResult:
        request_kwargs: dict[str, Any] = {
            "model": connection.model_id,
            "messages": [
                {"role": "system", "content": "Reply with the single word OK."},
                {"role": "user", "content": "Connection test."},
            ],
        }
        if connection.reasoning_effort is not None:
            request_kwargs["reasoning_effort"] = connection.reasoning_effort

        with OpenAI(**client_kwargs) as client:
            response = client.chat.completions.create(**request_kwargs)
        return _ModelConnectionTestResult(
            ok=True,
            message=self._success_message(response),
            tested_at=tested_at,
        )

    @staticmethod
    def _success_message(response: Any) -> str:
        request_id = getattr(response, "_request_id", None)
        message = "Connection test succeeded."
        if isinstance(request_id, str) and request_id.strip():
            message = f"Connection test succeeded (request {request_id.strip()})."
        return message

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


__all__ = ["ModelConnectionService", "PackageModelConnectionBinding"]
