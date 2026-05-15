from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

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
from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.repositories.model_connection import ModelConnectionRepository
from app.services.capability_service import CapabilityService, RuntimeToolGrantError
from app.services.execution_plan import PackageRuntimeAgentSpec
from app.services.quote_provider import QuoteProvider
from app.services.social_sentiment_provider import (
    SocialSentimentSourceAdapter,
    create_default_social_sentiment_adapters,
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
    duration_ms: int | None = None
    trace_span_id: str | None = None


RuntimeAgentSpec = Agent | PackageRuntimeAgentSpec


@dataclass(frozen=True)
class _ResolvedModelConnectionConfig:
    id: int
    name: str
    connection_kind: str
    base_url: str
    model_id: str
    reasoning_effort: str | None
    api_style: str
    timeout_seconds: int
    api_key: str | None


@dataclass(frozen=True)
class _PendingToolCall:
    name: str
    arguments_json: str
    call_id: str


_MAX_SERVER_TOOL_CALL_ROUNDS = 5


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
        duration_ms=None if duration_raw is None else int(duration_raw),
        trace_span_id=None if trace_span_raw is None else str(trace_span_raw),
    )


class AgentExecutionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        quote_provider: QuoteProvider | None = None,
        social_sentiment_adapters: Sequence[SocialSentimentSourceAdapter] | None = None,
        openai_client_factory: type[Any] = OpenAI,
        mcp_tool_client: McpToolClient | None = None,
    ) -> None:
        self.session_factory: sessionmaker[Session] = session_factory
        self.quote_provider: QuoteProvider | None = quote_provider
        self.social_sentiment_adapters: tuple[SocialSentimentSourceAdapter, ...] = (
            tuple(social_sentiment_adapters)
            if social_sentiment_adapters is not None
            else create_default_social_sentiment_adapters(
                timeout=get_settings().quote_provider_timeout_seconds
            )
        )
        self.openai_client_factory: type[Any] = openai_client_factory
        self.mcp_tool_client: McpToolClient | None = mcp_tool_client

    async def invoke(
        self,
        *,
        agent: RuntimeAgentSpec,
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
        agent: RuntimeAgentSpec,
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
            capability_references = self._runtime_capability_references(session, agent)
            granted_tool_keys = self._runtime_granted_tool_keys(session, agent)
            mcp_server_refs = self._runtime_mcp_server_refs(agent)
        try:
            return self._invoke_saved_model_connection_agent(
                agent=agent,
                model_connection=model_connection,
                resolved_input=resolved_input,
                output_model=output_model,
                openai_client_factory=openai_client_factory,
                capability_references=capability_references,
                granted_tool_keys=granted_tool_keys,
                mcp_server_refs=mcp_server_refs,
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
        agent: RuntimeAgentSpec,
    ) -> _ResolvedModelConnectionConfig:
        repository = ModelConnectionRepository(session)
        if isinstance(agent, PackageRuntimeAgentSpec):
            if agent.model_binding is None:
                raise RunExecutionError(
                    code="run_agent_model_connection_missing",
                    message=f"Package agent {agent.key!r} is missing its model connection",
                )
            connection = repository.get_by_key(agent.model_binding.key)
            if connection is None:
                raise RunExecutionError(
                    code="run_agent_model_connection_missing",
                    message=(
                        f"Package agent {agent.key!r} references missing model connection "
                        f"{agent.model_binding.key!r}"
                    ),
                )
            return self._to_runtime_model_connection(connection)

        if agent.model_connection_id is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=f"Agent {agent.key!r} is missing its saved model connection",
            )
        connection = repository.get(agent.model_connection_id)
        if connection is None:
            raise RunExecutionError(
                code="run_agent_model_connection_missing",
                message=(
                    f"Agent {agent.key!r} references missing model connection "
                    f"{agent.model_connection_id}"
                ),
            )
        return self._to_runtime_model_connection(connection)

    def _to_runtime_model_connection(
        self,
        connection: ModelConnection,
    ) -> _ResolvedModelConnectionConfig:
        return _ResolvedModelConnectionConfig(
            id=connection.id,
            name=connection.name,
            connection_kind=connection.connection_kind,
            base_url=connection.base_url,
            model_id=connection.model_id,
            reasoning_effort=connection.reasoning_effort,
            api_style=connection.api_style,
            timeout_seconds=connection.timeout_seconds,
            api_key=self._extract_model_connection_api_key(connection),
        )

    def _runtime_granted_tool_keys(
        self,
        session: Session,
        agent: RuntimeAgentSpec,
    ) -> set[str]:
        if isinstance(agent, PackageRuntimeAgentSpec):
            return {
                tool_key for profile in agent.capability_profiles for tool_key in profile.tool_keys
            }
        return CapabilityService(
            session,
            get_default_tool_catalog(),
        ).resolve_granted_tool_keys(agent.capabilities)

    @staticmethod
    def _runtime_capability_references(
        session: Session,
        agent: RuntimeAgentSpec,
    ) -> list[dict[str, object]]:
        del session
        if isinstance(agent, PackageRuntimeAgentSpec):
            return [
                {
                    "packageCapabilityKey": profile.key,
                    "toolKeys": list(profile.tool_keys),
                }
                for profile in agent.capability_profiles
            ]
        return list(agent.capabilities)

    @staticmethod
    def _runtime_mcp_server_refs(agent: RuntimeAgentSpec) -> Sequence[Mapping[str, object]]:
        if isinstance(agent, PackageRuntimeAgentSpec):
            return [
                {
                    "packagePrivate": True,
                    "key": server.key,
                    "name": server.name,
                    "description": server.description,
                    "transport": server.transport,
                    "command": server.command,
                    "args": list(server.args),
                    "url": server.url,
                    "env": dict(server.env),
                    "headers": dict(server.headers),
                    "query": dict(server.query),
                    "toolKeys": list(server.tool_keys),
                }
                for server in agent.mcp_servers
            ]
        return agent.mcp_servers

    @staticmethod
    def _runtime_agent_version(agent: RuntimeAgentSpec) -> int:
        if isinstance(agent, PackageRuntimeAgentSpec):
            return 1
        return agent.version

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
        agent: RuntimeAgentSpec,
        model_connection: _ResolvedModelConnectionConfig,
        resolved_input: dict[str, Any],
        output_model: type[BaseModel],
        openai_client_factory: type[Any],
        capability_references: list[dict[str, object]],
        granted_tool_keys: set[str],
        mcp_server_refs: Sequence[Mapping[str, object]],
        run_id: int | None,
        workflow_key: str | None,
        workflow_version: int | None,
        step_id: str | None,
        slot: str,
        trace_id: str | None,
    ) -> RunAgentInvocationResult:
        if model_connection.connection_kind == "deterministic_smoke":
            return RunAgentInvocationResult(
                output=self._deterministic_output_for_schema(output_model),
                tokens=1,
                duration_ms=0,
            )
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
            mcp_server_refs=mcp_server_refs,
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
            social_sentiment_adapters=self.social_sentiment_adapters,
            run_id=run_id,
            agent_key=agent.key,
            agent_version=self._runtime_agent_version(agent),
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
        response_input = self._build_openai_input(resolved_input)
        text_format = self._build_responses_text_format(output_model)
        started_at = time.monotonic()
        client_kwargs: dict[str, Any] = {
            "api_key": model_connection.api_key,
            "base_url": model_connection.base_url,
            "timeout": float(model_connection.timeout_seconds),
        }

        try:
            with openai_client_factory(**client_kwargs) as client:
                if model_connection.api_style == "responses":
                    return self._invoke_responses_agent(
                        client=client,
                        model_connection=model_connection,
                        instructions=instructions,
                        response_input=response_input,
                        text_format=text_format,
                        available_tools=available_tools,
                        granted_tool_keys=granted_tool_keys,
                        runtime_tool_registry=runtime_tool_registry,
                        runtime_tool_context=runtime_tool_context,
                        mcp_dispatcher=mcp_dispatcher,
                        started_at=started_at,
                    )
                if model_connection.api_style == "chat_completions":
                    return self._invoke_chat_completions_agent(
                        client=client,
                        model_connection=model_connection,
                        instructions=instructions,
                        response_input=response_input,
                        output_model=output_model,
                        available_tools=available_tools,
                        granted_tool_keys=granted_tool_keys,
                        runtime_tool_registry=runtime_tool_registry,
                        runtime_tool_context=runtime_tool_context,
                        mcp_dispatcher=mcp_dispatcher,
                        started_at=started_at,
                    )
                raise RunExecutionError(
                    code="agent_model_connection_api_style_unsupported",
                    message=(
                        f"Agent {agent.key!r} cannot run because model connection "
                        f"{model_connection.name!r} uses unsupported API style "
                        f"{model_connection.api_style!r}."
                    ),
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

    def _invoke_responses_agent(
        self,
        *,
        client: Any,
        model_connection: _ResolvedModelConnectionConfig,
        instructions: str,
        response_input: str | list[dict[str, str]],
        text_format: dict[str, Any],
        available_tools: list[dict[str, Any]],
        granted_tool_keys: set[str],
        runtime_tool_registry: RuntimeToolRegistry,
        runtime_tool_context: RuntimeToolContext,
        mcp_dispatcher: McpRuntimeDispatcher,
        started_at: float,
    ) -> RunAgentInvocationResult:
        previous_response_id: str | None = None
        previous_tool_calls: list[_PendingToolCall] | None = None
        manual_replay_mode = False
        total_tokens = 0
        for _ in range(_MAX_SERVER_TOOL_CALL_ROUNDS):
            request_kwargs: dict[str, Any] = {
                "model": model_connection.model_id,
                "instructions": instructions,
                "input": response_input,
                "text": text_format,
            }
            if model_connection.reasoning_effort is not None:
                request_kwargs["reasoning"] = {"effort": model_connection.reasoning_effort}
            if previous_response_id is not None:
                request_kwargs["previous_response_id"] = previous_response_id
            if available_tools:
                request_kwargs["tools"] = available_tools
            response, manual_replay_mode = self._create_response_with_manual_replay_fallback(
                client=client,
                request_kwargs=request_kwargs,
                previous_response_id=previous_response_id,
                previous_tool_calls=previous_tool_calls,
                function_call_outputs=response_input,
                manual_replay_mode=manual_replay_mode,
            )
            total_tokens += self._extract_total_tokens(response)
            pending_tool_calls = self._extract_pending_tool_calls(response)
            if not pending_tool_calls:
                duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
                response_text = self._extract_response_text(response)
                return RunAgentInvocationResult(
                    output=self._parse_response_output(response_text),
                    tokens=total_tokens,
                    duration_ms=duration_ms,
                )
            previous_response_id = self._extract_response_id(response)
            previous_tool_calls = pending_tool_calls
            response_input = self._build_function_call_outputs(
                pending_tool_calls=pending_tool_calls,
                granted_tool_keys=granted_tool_keys,
                runtime_tool_registry=runtime_tool_registry,
                runtime_tool_context=runtime_tool_context,
                mcp_dispatcher=mcp_dispatcher,
            )

        raise RunExecutionError(
            code="agent_tool_round_limit_exceeded",
            message="Agent exceeded the supported server tool call round limit.",
        )

    def _invoke_chat_completions_agent(
        self,
        *,
        client: Any,
        model_connection: _ResolvedModelConnectionConfig,
        instructions: str,
        response_input: str | list[dict[str, str]],
        output_model: type[BaseModel],
        available_tools: list[dict[str, Any]],
        granted_tool_keys: set[str],
        runtime_tool_registry: RuntimeToolRegistry,
        runtime_tool_context: RuntimeToolContext,
        mcp_dispatcher: McpRuntimeDispatcher,
        started_at: float,
    ) -> RunAgentInvocationResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": response_input},
        ]
        chat_tools = self._convert_responses_tools_to_chat_tools(available_tools)
        response_format = self._build_chat_response_format(output_model)
        total_tokens = 0

        for _ in range(_MAX_SERVER_TOOL_CALL_ROUNDS):
            request_kwargs: dict[str, Any] = {
                "model": model_connection.model_id,
                "messages": messages,
                "response_format": response_format,
            }
            if model_connection.reasoning_effort is not None:
                request_kwargs["reasoning_effort"] = model_connection.reasoning_effort
            if chat_tools:
                request_kwargs["tools"] = chat_tools
            response = client.chat.completions.create(**request_kwargs)
            total_tokens += self._extract_total_tokens(response)
            message = self._extract_first_chat_choice_message(response)
            pending_tool_calls = self._extract_pending_chat_tool_calls(message)
            if not pending_tool_calls:
                duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
                response_text = self._extract_chat_message_content(message)
                return RunAgentInvocationResult(
                    output=self._parse_response_output(response_text),
                    tokens=total_tokens,
                    duration_ms=duration_ms,
                )

            messages.append(
                self._build_chat_assistant_tool_call_message(
                    message=message,
                    pending_tool_calls=pending_tool_calls,
                )
            )
            messages.extend(
                self._build_chat_tool_result_messages(
                    pending_tool_calls=pending_tool_calls,
                    granted_tool_keys=granted_tool_keys,
                    runtime_tool_registry=runtime_tool_registry,
                    runtime_tool_context=runtime_tool_context,
                    mcp_dispatcher=mcp_dispatcher,
                )
            )

        raise RunExecutionError(
            code="agent_tool_round_limit_exceeded",
            message="Agent exceeded the supported server tool call round limit.",
        )

    @classmethod
    def _deterministic_output_for_schema(cls, output_model: type[BaseModel]) -> Any:
        schema = output_model.model_json_schema()
        return cls._deterministic_json_value(schema, name="output", root_schema=schema)

    @classmethod
    def _deterministic_json_value(
        cls,
        schema: Mapping[str, Any],
        *,
        name: str,
        root_schema: Mapping[str, Any],
    ) -> Any:
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            defs = root_schema.get("$defs")
            target = defs.get(ref.removeprefix("#/$defs/")) if isinstance(defs, Mapping) else None
            if isinstance(target, Mapping):
                return cls._deterministic_json_value(target, name=name, root_schema=root_schema)
        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties")
            if not isinstance(properties, Mapping):
                return {}
            required = schema.get("required")
            required_names = required if isinstance(required, list) else list(properties.keys())
            return {
                str(key): cls._deterministic_json_value(
                    value if isinstance(value, Mapping) else {},
                    name=str(key),
                    root_schema=root_schema,
                )
                for key, value in properties.items()
                if key in required_names
            }
        if schema_type == "array":
            items = schema.get("items")
            item_schema = items if isinstance(items, Mapping) else {}
            return [
                cls._deterministic_json_value(
                    item_schema,
                    name=name,
                    root_schema=root_schema,
                )
            ]
        if schema_type in {"integer", "number"}:
            return 1
        if schema_type == "boolean":
            return True
        if (
            isinstance(schema.get("properties"), Mapping)
            or schema.get("additionalProperties") is True
        ):
            return {}
        return f"deterministic {name}"

    @staticmethod
    def _build_responses_text_format(output_model: type[BaseModel]) -> dict[str, Any]:
        return {
            "format": {
                "type": "json_schema",
                "name": output_model.__name__,
                "schema": output_model.model_json_schema(),
            }
        }

    @staticmethod
    def _build_chat_response_format(output_model: type[BaseModel]) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": output_model.__name__,
                "schema": output_model.model_json_schema(),
            },
        }

    @staticmethod
    def _convert_responses_tools_to_chat_tools(
        available_tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        chat_tools: list[dict[str, Any]] = []
        for tool in available_tools:
            chat_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("parameters"),
                        "strict": tool.get("strict", True),
                    },
                }
            )
        return chat_tools

    @classmethod
    def _extract_first_chat_choice_message(cls, response: Any) -> Any:
        choices = cls._read_field(response, "choices")
        if not isinstance(choices, list) or not choices:
            raise RunExecutionError(
                code="agent_provider_response_empty",
                message="OpenAI chat response did not include a choice message.",
            )
        message = cls._read_field(choices[0], "message")
        if message is None:
            raise RunExecutionError(
                code="agent_provider_response_empty",
                message="OpenAI chat response did not include a choice message.",
            )
        return message

    @classmethod
    def _extract_pending_chat_tool_calls(cls, message: Any) -> list[_PendingToolCall]:
        raw_tool_calls = cls._read_field(message, "tool_calls")
        if raw_tool_calls is None:
            return []
        if not isinstance(raw_tool_calls, list):
            raw_tool_calls = [raw_tool_calls]

        pending: list[_PendingToolCall] = []
        for raw_tool_call in raw_tool_calls:
            call_id = cls._read_field(raw_tool_call, "id")
            function = cls._read_field(raw_tool_call, "function")
            name = cls._read_field(function, "name") if function is not None else None
            arguments = cls._read_field(function, "arguments") if function is not None else None
            if not isinstance(name, str) or not name.strip():
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message="OpenAI chat response requested a server tool without a valid name.",
                )
            if not isinstance(arguments, str):
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message=(
                        f"OpenAI chat response requested server tool {name!r} "
                        "without JSON arguments."
                    ),
                )
            if not isinstance(call_id, str) or not call_id.strip():
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message=(
                        f"OpenAI chat response requested server tool {name!r} without a call id."
                    ),
                )
            pending.append(
                _PendingToolCall(
                    name=name.strip(),
                    arguments_json=arguments,
                    call_id=call_id.strip(),
                )
            )
        return pending

    @classmethod
    def _build_chat_assistant_tool_call_message(
        cls,
        *,
        message: Any,
        pending_tool_calls: list[_PendingToolCall],
    ) -> dict[str, Any]:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call.call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments_json,
                    },
                }
                for tool_call in pending_tool_calls
            ],
        }
        content = cls._read_field(message, "content")
        if content is not None:
            assistant_message["content"] = content
        return assistant_message

    def _build_chat_tool_result_messages(
        self,
        *,
        pending_tool_calls: list[_PendingToolCall],
        granted_tool_keys: set[str],
        runtime_tool_registry: RuntimeToolRegistry,
        runtime_tool_context: RuntimeToolContext,
        mcp_dispatcher: McpRuntimeDispatcher,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for tool_call in pending_tool_calls:
            output_payload = self._dispatch_function_call(
                tool_call=tool_call,
                granted_tool_keys=granted_tool_keys,
                runtime_tool_registry=runtime_tool_registry,
                runtime_tool_context=runtime_tool_context,
                mcp_dispatcher=mcp_dispatcher,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.call_id,
                    "content": json.dumps(output_payload, ensure_ascii=False, sort_keys=True),
                }
            )
        return messages

    @classmethod
    def _extract_chat_message_content(cls, message: Any) -> str:
        content = cls._read_field(message, "content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        fragments = cls._collect_response_text_fragments(content)
        normalized = "\n".join(
            fragment.strip() for fragment in fragments if fragment.strip()
        ).strip()
        if normalized:
            return normalized
        raise RunExecutionError(
            code="agent_provider_response_empty",
            message="OpenAI chat response did not contain text output.",
        )

    @staticmethod
    def _read_field(value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)

    @staticmethod
    def _build_openai_instructions(
        agent: RuntimeAgentSpec,
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
                        f"OpenAI response requested server tool {name!r} without JSON arguments."
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

    def _create_response_with_manual_replay_fallback(
        self,
        *,
        client: Any,
        request_kwargs: dict[str, Any],
        previous_response_id: str | None,
        previous_tool_calls: list[_PendingToolCall] | None,
        function_call_outputs: str | list[dict[str, str]],
        manual_replay_mode: bool,
    ) -> tuple[Any, bool]:
        effective_request_kwargs = dict(request_kwargs)
        if manual_replay_mode:
            if previous_tool_calls is None or not isinstance(function_call_outputs, list):
                raise RunExecutionError(
                    code="agent_tool_call_invalid",
                    message="Responses manual replay could not reconstruct prior tool call state.",
                )
            effective_request_kwargs.pop("previous_response_id", None)
            effective_request_kwargs["input"] = self._build_manual_replay_input(
                pending_tool_calls=previous_tool_calls,
                function_call_outputs=function_call_outputs,
            )
        try:
            return client.responses.create(**effective_request_kwargs), manual_replay_mode
        except openai.APIStatusError as exc:
            if (
                manual_replay_mode
                or previous_response_id is None
                or previous_tool_calls is None
                or not isinstance(function_call_outputs, list)
                or not self._is_missing_tool_call_for_function_output(exc)
            ):
                raise
            replay_request_kwargs = dict(request_kwargs)
            replay_request_kwargs.pop("previous_response_id", None)
            replay_request_kwargs["input"] = self._build_manual_replay_input(
                pending_tool_calls=previous_tool_calls,
                function_call_outputs=function_call_outputs,
            )
            return client.responses.create(**replay_request_kwargs), True

    @staticmethod
    def _is_missing_tool_call_for_function_output(exc: openai.APIStatusError) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code != 400:
            return False
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            raw_error = body.get("error")
            if isinstance(raw_error, dict):
                raw_message = raw_error.get("message")
                if isinstance(raw_message, str):
                    return "no tool call found for function call output" in raw_message.lower()
            raw_message = body.get("message")
            if isinstance(raw_message, str):
                return "no tool call found for function call output" in raw_message.lower()
        return False

    @staticmethod
    def _build_manual_replay_input(
        *,
        pending_tool_calls: list[_PendingToolCall],
        function_call_outputs: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return [
            *[
                {
                    "type": "function_call",
                    "name": tool_call.name,
                    "arguments": tool_call.arguments_json,
                    "call_id": tool_call.call_id,
                }
                for tool_call in pending_tool_calls
            ],
            *function_call_outputs,
        ]

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
