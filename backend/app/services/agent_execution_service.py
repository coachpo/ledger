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

from app.agents import get_default_tool_catalog
from app.agents.mcp import McpRuntimeDispatcher, McpRuntimeResolver, McpToolClient
from app.agents.runtime_tools import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolRegistry,
    get_default_runtime_tool_registry,
)
from app.core.config import get_settings
from app.core.formatting import parse_decimal_string
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.services.capability_service import CapabilityService, RuntimeToolGrantError
from app.services.model_connection_snapshot import parse_model_connection_runtime_snapshot
from app.services.quote_provider import QuoteProvider


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


@dataclass(frozen=True)
class _PendingToolCall:
    name: str
    arguments_json: str
    call_id: str


_MAX_SERVER_TOOL_CALL_ROUNDS = 5


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
        quote_provider: QuoteProvider | None = None,
        openai_client_factory: type[Any] = OpenAI,
        mcp_tool_client: McpToolClient | None = None,
    ) -> None:
        self.session_factory: sessionmaker[Session] = session_factory
        self.quote_provider: QuoteProvider | None = quote_provider
        self.openai_client_factory: type[Any] = openai_client_factory
        self.mcp_tool_client: McpToolClient | None = mcp_tool_client

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
        run_id: int | None = None,
        workflow_key: str | None = None,
        workflow_version: int | None = None,
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
            run_id,
            workflow_key,
            workflow_version,
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
        run_id: int | None,
        workflow_key: str | None,
        workflow_version: int | None,
    ) -> RunAgentInvocationResult:
        step_id = f"step_{step_index}"
        with self.session_factory() as session:
            model_connection = self._resolve_runtime_model_connection(session, agent)
            granted_tool_keys = CapabilityService(
                session,
                get_default_tool_catalog(),
            ).resolve_granted_tool_keys(agent.capabilities)
        try:
            return self._invoke_saved_model_connection_agent(
                agent=agent,
                model_connection=model_connection,
                resolved_input=resolved_input,
                output_model=output_model,
                openai_client_factory=openai_client_factory,
                capability_references=agent.capabilities,
                granted_tool_keys=granted_tool_keys,
                run_id=run_id,
                workflow_key=workflow_key,
                workflow_version=workflow_version,
                step_id=step_id,
                slot=slot,
                trace_id=trace_id,
            )
        except RuntimeToolGrantError as exc:
            raise RunExecutionError(
                code=exc.code,
                message=exc.message,
                details=list(exc.details or []),
            ) from exc

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
        try:
            snapshot = parse_model_connection_runtime_snapshot(agent.model_connection_snapshot)
        except ValueError as exc:
            raise RunExecutionError(
                code="run_agent_model_connection_snapshot_invalid",
                message=f"Agent {agent.key!r} has an invalid saved model connection snapshot",
            ) from exc

        return _ResolvedModelConnectionConfig(
            id=connection.id,
            name=connection.name,
            base_url=snapshot.base_url,
            organization=snapshot.organization,
            project=snapshot.project,
            model_id=snapshot.model_id,
            reasoning_effort=snapshot.reasoning_effort,
            timeout_seconds=snapshot.timeout_seconds,
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
        capability_references: list[dict[str, Any]],
        granted_tool_keys: set[str],
        run_id: int | None,
        workflow_key: str | None,
        workflow_version: int | None,
        step_id: str | None,
        slot: str,
        trace_id: str | None,
    ) -> RunAgentInvocationResult:
        if model_connection.api_key is None:
            raise RunExecutionError(
                code="agent_model_connection_api_key_missing",
                message=(
                    f"Agent {agent.key!r} cannot run because model connection "
                    f"{model_connection.name!r} is missing an API key"
                ),
            )

        runtime_tool_registry = get_default_runtime_tool_registry()
        settings = get_settings()
        mcp_dispatcher = McpRuntimeResolver(self.session_factory).build_dispatcher(
            mcp_server_refs=agent.mcp_servers,
            client=self.mcp_tool_client,
            timeout_seconds=settings.mcp_runtime_timeout_seconds,
            enabled=settings.mcp_runtime_enabled,
        )
        available_tools = runtime_tool_registry.get_openai_tools(granted_tool_keys)
        available_tools.extend(mcp_dispatcher.get_openai_tools())
        runtime_tool_context = RuntimeToolContext(
            session_factory=self.session_factory,
            capability_references=capability_references,
            quote_provider=self.quote_provider,
            run_id=run_id,
            agent_key=agent.key,
            agent_version=agent.version,
            agent_name=agent.name,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
            step_id=step_id,
            slot=slot,
            trace_id=trace_id,
        )
        instructions = self._build_openai_instructions(
            agent,
            output_model,
            runtime_tool_guidance=runtime_tool_registry.get_guidance(granted_tool_keys),
        )
        response_input: str | list[dict[str, str]] = self._build_openai_input(resolved_input)
        previous_response_id: str | None = None
        total_tokens = 0
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
                for _ in range(_MAX_SERVER_TOOL_CALL_ROUNDS):
                    request_kwargs: dict[str, Any] = {
                        "model": model_connection.model_id,
                        "instructions": instructions,
                        "input": response_input,
                        "reasoning": cast(Any, {"effort": model_connection.reasoning_effort}),
                    }
                    if previous_response_id is not None:
                        request_kwargs["previous_response_id"] = previous_response_id
                    if available_tools:
                        request_kwargs["tools"] = available_tools
                    response = client.responses.create(**request_kwargs)
                    total_tokens += self._extract_total_tokens(response)
                    pending_tool_calls = self._extract_pending_tool_calls(response)
                    if not pending_tool_calls:
                        duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
                        response_text = self._extract_response_text(response)
                        return RunAgentInvocationResult(
                            output=self._parse_response_output(response_text),
                            tokens=total_tokens,
                            cost_usd=Decimal("0"),
                            duration_ms=duration_ms,
                        )
                    previous_response_id = self._extract_response_id(response)
                    response_input = self._build_function_call_outputs(
                        pending_tool_calls=pending_tool_calls,
                        granted_tool_keys=granted_tool_keys,
                        runtime_tool_registry=runtime_tool_registry,
                        runtime_tool_context=runtime_tool_context,
                        mcp_dispatcher=mcp_dispatcher,
                    )
        except RuntimeToolError as exc:
            raise self._runtime_tool_error_to_run_execution_error(exc) from exc
        except (RuntimeToolGrantError, RunExecutionError):
            raise
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

        raise RunExecutionError(
            code="agent_tool_round_limit_exceeded",
            message="Agent exceeded the supported server tool call round limit.",
        )

    @staticmethod
    def _build_openai_instructions(
        agent: Agent,
        output_model: type[BaseModel],
        *,
        runtime_tool_guidance: str,
    ) -> str:
        schema_text = json.dumps(output_model.model_json_schema(), indent=2, sort_keys=True)
        normalized_tool_guidance = runtime_tool_guidance.strip()
        tool_guidance = f"\n\n{normalized_tool_guidance}" if normalized_tool_guidance else ""
        return (
            f"{agent.system_prompt.strip()}{tool_guidance}\n\n"
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
    def _extract_pending_tool_calls(cls, response: Any) -> list[_PendingToolCall]:
        output_items = (
            response.get("output")
            if isinstance(response, dict)
            else getattr(response, "output", None)
        )
        if output_items is None:
            return []
        if not isinstance(output_items, list):
            output_items = [output_items]

        pending: list[_PendingToolCall] = []
        for item in output_items:
            item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
            if item_type != "function_call":
                continue
            name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            arguments = (
                item.get("arguments")
                if isinstance(item, dict)
                else getattr(item, "arguments", None)
            )
            call_id = (
                item.get("call_id") if isinstance(item, dict) else getattr(item, "call_id", None)
            )
            if not isinstance(name, str) or not name.strip():
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message="OpenAI response requested a server tool without a valid name.",
                )
            if not isinstance(arguments, str):
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message=(
                        f"OpenAI response requested server tool {name!r} " "without JSON arguments."
                    ),
                )
            if not isinstance(call_id, str) or not call_id.strip():
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message=f"OpenAI response requested server tool {name!r} without a call id.",
                )
            pending.append(
                _PendingToolCall(
                    name=name.strip(),
                    arguments_json=arguments,
                    call_id=call_id.strip(),
                )
            )
        return pending

    @staticmethod
    def _extract_response_id(response: Any) -> str:
        response_id = (
            response.get("id") if isinstance(response, dict) else getattr(response, "id", None)
        )
        if isinstance(response_id, str) and response_id.strip():
            return response_id.strip()
        raise RunExecutionError(
            code="agent_tool_call_invalid",
            message="OpenAI response did not include a response id for tool continuation.",
        )

    def _build_function_call_outputs(
        self,
        *,
        pending_tool_calls: list[_PendingToolCall],
        granted_tool_keys: set[str],
        runtime_tool_registry: RuntimeToolRegistry,
        runtime_tool_context: RuntimeToolContext,
        mcp_dispatcher: McpRuntimeDispatcher,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for tool_call in pending_tool_calls:
            output_payload = self._dispatch_function_call(
                tool_call=tool_call,
                granted_tool_keys=granted_tool_keys,
                runtime_tool_registry=runtime_tool_registry,
                runtime_tool_context=runtime_tool_context,
                mcp_dispatcher=mcp_dispatcher,
            )
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(output_payload, ensure_ascii=False, sort_keys=True),
                }
            )
        return items

    @staticmethod
    def _dispatch_function_call(
        *,
        tool_call: _PendingToolCall,
        granted_tool_keys: set[str],
        runtime_tool_registry: RuntimeToolRegistry,
        runtime_tool_context: RuntimeToolContext,
        mcp_dispatcher: McpRuntimeDispatcher,
    ) -> dict[str, object]:
        try:
            return runtime_tool_registry.dispatch(
                name=tool_call.name,
                arguments_json=tool_call.arguments_json,
                granted_tool_keys=granted_tool_keys,
                context=runtime_tool_context,
            )
        except RuntimeToolError as exc:
            if exc.code != "agent_tool_call_unsupported":
                raise
        return mcp_dispatcher.dispatch(
            name=tool_call.name,
            arguments_json=tool_call.arguments_json,
        )

    @staticmethod
    def _runtime_tool_error_to_run_execution_error(exc: RuntimeToolError) -> RunExecutionError:
        return RunExecutionError(
            code=exc.code,
            message=exc.message,
            details=[dict(detail) for detail in exc.details],
        )

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
