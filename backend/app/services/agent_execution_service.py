from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import openai
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import parse_decimal_string
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.services.stock_analysis_reference import (
    StockAnalysisReferenceError,
    StockAnalysisReferenceService,
)


class RunExecutionError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        trace_span_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = list(details or [])
        self.trace_span_id = trace_span_id


@dataclass
class RunAgentInvocationResult:
    output: Any
    tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    duration_ms: int | None = None
    trace_span_id: str | None = None


@dataclass(frozen=True)
class _ResolvedModelConnectionConfig:
    id: int
    name: str
    base_url: str
    organization: str | None
    project: str | None
    model_id: str
    reasoning_effort: str
    timeout_seconds: int
    api_key: str | None


def _normalize_cost(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return parse_decimal_string(value)


def normalize_agent_invocation_result(raw_result: Any) -> RunAgentInvocationResult:
    if isinstance(raw_result, RunAgentInvocationResult):
        return raw_result
    if not isinstance(raw_result, dict):
        raise RunExecutionError(
            code="agent_result_invalid",
            message="Agent execution returned an unsupported result payload",
        )
    duration_raw = raw_result.get("duration_ms", raw_result.get("durationMs"))
    trace_span_raw = raw_result.get("trace_span_id", raw_result.get("traceSpanId"))
    return RunAgentInvocationResult(
        output=raw_result.get("output"),
        tokens=int(raw_result.get("tokens", 0) or 0),
        cost_usd=_normalize_cost(raw_result.get("cost_usd", raw_result.get("costUsd", "0"))),
        duration_ms=None if duration_raw is None else int(duration_raw),
        trace_span_id=None if trace_span_raw is None else str(trace_span_raw),
    )


class AgentExecutionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        openai_client_factory: type[Any] = OpenAI,
    ) -> None:
        self.session_factory = session_factory
        self.openai_client_factory = openai_client_factory

    async def invoke(
        self,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        step_index: int,
        slot: str,
        openai_client_factory: type[Any] | None = None,
    ) -> RunAgentInvocationResult:
        client_factory = openai_client_factory or self.openai_client_factory
        return await asyncio.to_thread(
            self._invoke_sync,
            agent,
            resolved_input,
            output_model,
            trace_id,
            step_index,
            slot,
            client_factory,
        )

    def _invoke_sync(
        self,
        agent: Agent,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        trace_id: str | None,
        step_index: int,
        slot: str,
        openai_client_factory: type[Any],
    ) -> RunAgentInvocationResult:
        del trace_id
        with self.session_factory() as session:
            reference_service = StockAnalysisReferenceService(session)
            try:
                reference_result = reference_service.maybe_invoke(
                    agent=agent,
                    resolved_input=resolved_input,
                    step_index=step_index,
                    slot=slot,
                )
            except StockAnalysisReferenceError as exc:
                raise RunExecutionError(
                    code=exc.code,
                    message=exc.message,
                    details=list(exc.details or []),
                ) from exc
            if reference_result is not None:
                return normalize_agent_invocation_result(reference_result)
            model_connection = self._resolve_runtime_model_connection(session, agent)
        return self._invoke_saved_model_connection_agent(
            agent=agent,
            model_connection=model_connection,
            resolved_input=resolved_input,
            output_model=output_model,
            openai_client_factory=openai_client_factory,
        )

    def _resolve_runtime_model_connection(
        self,
        session: Session,
        agent: Agent,
    ) -> _ResolvedModelConnectionConfig:
        if agent.model_connection_id is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=f"Agent {agent.key!r} is missing its saved model connection",
            )
        connection = ModelConnectionRepository(session).get(agent.model_connection_id)
        if connection is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=(
                    f"Agent {agent.key!r} references missing model connection "
                    f"{agent.model_connection_id}"
                ),
            )
        return _ResolvedModelConnectionConfig(
            id=connection.id,
            name=connection.name,
            base_url=connection.base_url,
            organization=connection.organization,
            project=connection.project,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            timeout_seconds=connection.timeout_seconds,
            api_key=self._extract_model_connection_api_key(connection),
        )

    @staticmethod
    def _extract_model_connection_api_key(connection: ModelConnection) -> str | None:
        payload = connection.secret_payload if isinstance(connection.secret_payload, dict) else {}
        raw_api_key = payload.get("apiKey")
        if raw_api_key is None:
            return None
        normalized = str(raw_api_key).strip()
        return normalized or None

    def _invoke_saved_model_connection_agent(
        self,
        *,
        agent: Agent,
        model_connection: _ResolvedModelConnectionConfig,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        openai_client_factory: type[Any],
    ) -> RunAgentInvocationResult:
        if model_connection.api_key is None:
            raise RunExecutionError(
                code="agent_model_connection_api_key_missing",
                message=(
                    f"Agent {agent.key!r} cannot run because model connection "
                    f"{model_connection.name!r} is missing an API key"
                ),
            )

        instructions = self._build_openai_instructions(agent, output_model)
        input_text = self._build_openai_input(resolved_input)
        started_at = time.monotonic()
        client_kwargs: dict[str, Any] = {
            "api_key": model_connection.api_key,
            "base_url": model_connection.base_url,
            "timeout": float(model_connection.timeout_seconds),
        }
        if model_connection.organization:
            client_kwargs["organization"] = model_connection.organization
        if model_connection.project:
            client_kwargs["project"] = model_connection.project

        try:
            with openai_client_factory(**client_kwargs) as client:
                response = client.responses.create(
                    model=model_connection.model_id,
                    instructions=instructions,
                    input=input_text,
                    reasoning=cast(Any, {"effort": model_connection.reasoning_effort}),
                )
        except openai.APITimeoutError as exc:
            raise RunExecutionError(
                code="agent_provider_timeout",
                message="OpenAI request timed out.",
            ) from exc
        except openai.APIConnectionError as exc:
            raise RunExecutionError(
                code="agent_provider_connection_error",
                message="OpenAI request could not reach the API.",
            ) from exc
        except openai.APIStatusError as exc:
            raise RunExecutionError(
                code="agent_provider_status_error",
                message=self._format_api_status_error(exc, api_key=model_connection.api_key),
            ) from exc
        except openai.APIError as exc:
            raise RunExecutionError(
                code="agent_provider_error",
                message=self._normalize_provider_message(
                    str(exc),
                    api_key=model_connection.api_key,
                ),
            ) from exc
        except Exception as exc:
            raise RunExecutionError(
                code="agent_provider_error",
                message=self._normalize_provider_message(
                    f"Unexpected OpenAI execution failure: {exc}",
                    api_key=model_connection.api_key,
                ),
            ) from exc

        duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
        response_text = self._extract_response_text(response)
        return RunAgentInvocationResult(
            output=self._parse_response_output(response_text),
            tokens=self._extract_total_tokens(response),
            cost_usd=Decimal("0"),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _build_openai_instructions(agent: Agent, output_model: type[BaseModel]) -> str:
        schema_text = json.dumps(output_model.model_json_schema(), indent=2, sort_keys=True)
        return (
            f"{agent.system_prompt.strip()}\n\n"
            "Return only valid JSON with no markdown fences or explanatory text. "
            "The JSON must satisfy this schema exactly:\n"
            f"{schema_text}"
        )

    @staticmethod
    def _build_openai_input(resolved_input: dict[str, Any]) -> str:
        serialized_input = json.dumps(
            resolved_input,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"Use this JSON object as the complete agent input:\n{serialized_input}"

    @classmethod
    def _extract_response_text(cls, response: Any) -> str:
        if isinstance(response, dict):
            direct_text = response.get("output_text") or response.get("outputText")
            output_payload = response.get("output")
        else:
            direct_text = getattr(response, "output_text", None)
            output_payload = getattr(response, "output", None)
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()
        fragments = cls._collect_response_text_fragments(output_payload)
        normalized = "\n".join(
            fragment.strip() for fragment in fragments if fragment.strip()
        ).strip()
        if normalized:
            return normalized
        raise RunExecutionError(
            code="agent_provider_response_empty",
            message="OpenAI response did not contain text output.",
        )

    @classmethod
    def _collect_response_text_fragments(cls, value: Any) -> list[str]:
        fragments: list[str] = []
        if value is None:
            return fragments
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            for item in value:
                fragments.extend(cls._collect_response_text_fragments(item))
            return fragments
        if isinstance(value, dict):
            text_value = value.get("text")
            if isinstance(text_value, str) and text_value.strip():
                fragments.append(text_value)
            for key in ("content", "output"):
                nested = value.get(key)
                if nested is not None:
                    fragments.extend(cls._collect_response_text_fragments(nested))
            return fragments

        text_attr = getattr(value, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            fragments.append(text_attr)
        for attr in ("content", "output"):
            nested = getattr(value, attr, None)
            if nested is not None:
                fragments.extend(cls._collect_response_text_fragments(nested))
        return fragments

    def _parse_response_output(self, response_text: str) -> Any:
        candidate = self._strip_markdown_code_fence(response_text)
        candidates = [candidate]
        embedded = self._extract_embedded_json_candidate(candidate)
        if embedded is not None and embedded != candidate:
            candidates.append(embedded)
        for raw_candidate in candidates:
            try:
                return json.loads(raw_candidate)
            except json.JSONDecodeError:
                continue
        raise RunExecutionError(
            code="agent_output_parse_failed",
            message="OpenAI response did not return valid JSON for the agent output schema.",
        )

    @staticmethod
    def _strip_markdown_code_fence(text: str) -> str:
        candidate = text.strip()
        if not candidate.startswith("```"):
            return candidate
        lines = candidate.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
            return "\n".join(lines[1:-1]).strip()
        return candidate

    @staticmethod
    def _extract_embedded_json_candidate(text: str) -> str | None:
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start != -1 and object_end > object_start:
            return text[object_start : object_end + 1].strip()
        array_start = text.find("[")
        array_end = text.rfind("]")
        if array_start != -1 and array_end > array_start:
            return text[array_start : array_end + 1].strip()
        return None

    @staticmethod
    def _extract_total_tokens(response: Any) -> int:
        if isinstance(response, dict):
            usage = response.get("usage")
        else:
            usage = getattr(response, "usage", None)
        if isinstance(usage, dict):
            raw_total = usage.get("total_tokens", usage.get("totalTokens"))
        else:
            raw_total = getattr(usage, "total_tokens", None)
            if raw_total is None:
                raw_total = getattr(usage, "totalTokens", None)
        try:
            return int(raw_total or 0)
        except (TypeError, ValueError):
            return 0

    def _format_api_status_error(self, exc: openai.APIStatusError, *, api_key: str) -> str:
        message = self._extract_api_status_message(exc)
        request_id = getattr(exc, "request_id", None)
        if isinstance(request_id, str) and request_id.strip():
            message = f"{message} requestId={request_id.strip()}"
        return self._normalize_provider_message(message, api_key=api_key)

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
    def _normalize_provider_message(message: str, *, api_key: str | None) -> str:
        normalized = " ".join(str(message).split()).strip()
        if api_key:
            normalized = normalized.replace(api_key, "[REDACTED]")
        if len(normalized) > 500:
            return f"{normalized[:497]}..."
        return normalized or "Agent execution failed."


__all__ = [
    "AgentExecutionService",
    "RunAgentInvocationResult",
    "RunExecutionError",
    "normalize_agent_invocation_result",
]
