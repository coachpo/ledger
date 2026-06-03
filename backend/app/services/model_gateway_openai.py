from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import openai
from openai import OpenAI

from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.failure_taxonomy import (
    PROVIDER_NETWORK_FAILURE,
    PROVIDER_TRANSPORT_FAILURE,
    provider_status_failure_classification,
)
from app.agents.runtime_tools.types import RuntimeToolError
from app.services.model_gateway_dto import (
    ModelCapabilityProbeOutcome,
    ModelCapabilityProbeRequest,
    ModelCapabilityProbeResult,
    ModelConnectionTestRequest,
    ModelConnectionTestResult,
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelExecutionStrategies,
    ModelExecutionUsage,
    ModelGatewayConnectionConfig,
    ModelGatewayError,
    ModelToolCall,
    ModelToolExecutor,
)
from app.services.model_gateway_openai_responses import OpenAIResponsesAdapter
from app.services.model_gateway_output_validation import (
    exhausted_validation_error,
    select_output_strategy,
    validate_model_output,
    validation_failed_error,
    validation_retry_input,
)
from app.services.model_gateway_policy_strategy import select_model_execution_strategies
from app.services.model_gateway_provider_retry import (
    ProviderRetryRecorder,
    call_with_provider_retry,
)
from app.services.model_gateway_tool_retry import (
    ModelToolCallRetryState,
    is_retryable_tool_call_failure,
)
from app.services.model_gateway_tool_strategy import build_model_tool_call, select_tool_strategy

DEFAULT_OPENAI_CLIENT_FACTORY = OpenAI
_MAX_SERVER_TOOL_CALL_ROUNDS = 5
_CAPABILITY_PROBE_INSTRUCTIONS = "Reply with the single word OK."
_CAPABILITY_PROBE_INPUT = "Capability probe."
_CAPABILITY_PROBE_JSON_INSTRUCTIONS = "Reply with one JSON object only."
_CAPABILITY_PROBE_JSON_INPUT = 'Capability probe. Return JSON exactly as {"ok": true}.'
_CAPABILITY_PROBE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}
_CAPABILITY_PROBE_TOOL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
}
_CAPABILITY_PROBE_TOOL = SignalDeckToolDeclaration(
    kind="native_runtime",
    tool_key="signaldeck.capability_probe.echo",
    model_name="signaldeck_capability_probe_echo",
    description="Echo a probe value for capability detection.",
    input_schema=_CAPABILITY_PROBE_TOOL_SCHEMA,
    schema_hash="capability-probe-echo/v1",
)
_CAPABILITY_PROBE_SECOND_TOOL = SignalDeckToolDeclaration(
    kind="native_runtime",
    tool_key="signaldeck.capability_probe.second_echo",
    model_name="signaldeck_capability_probe_second_echo",
    description="Echo a second probe value for parallel capability detection.",
    input_schema=_CAPABILITY_PROBE_TOOL_SCHEMA,
    schema_hash="capability-probe-second-echo/v1",
)
_CAPABILITY_PROBE_LABELS = {
    "text_generation": "text generation",
    "chat_completions": "Chat Completions protocol",
    "responses_api": "Responses protocol",
    "streaming": "streaming",
    "native_tool_calls": "native tool calls",
    "parallel_tool_calls": "parallel tool calls",
    "json_object_output": "JSON object output",
    "strict_json_schema_output": "strict JSON schema output",
    "reasoning_hints": "reasoning hints",
    "usage_reporting": "usage reporting",
    "system_messages": "system messages",
}
_UNSUPPORTED_PROBE_MESSAGE_MARKERS = (
    "unsupported",
    "not supported",
    "does not support",
    "disabled",
    "invalid request",
    "invalid_request_error",
    "unknown parameter",
    "unrecognized request argument",
    "unknown field",
    "not allowed",
    "response_format type is unavailable",
)


class OpenAIProtocolAdapter:
    def __init__(self, client_factory: type[Any] = DEFAULT_OPENAI_CLIENT_FACTORY) -> None:
        self._client_factory = client_factory

    def invoke(
        self,
        request: ModelExecutionRequest,
        *,
        tool_executor: ModelToolExecutor,
    ) -> ModelExecutionResult:
        started_at = time.monotonic()
        selected_strategies: ModelExecutionStrategies | None = None
        provider_retry_recorder: ProviderRetryRecorder | None = None
        try:
            tool_strategy = select_tool_strategy(request)
            output_strategy = select_output_strategy(request)
            selected_strategies = self._selected_strategies(
                request,
                output_strategy=output_strategy.strategy,
                has_tools=tool_strategy.has_tools,
                allow_parallel_tool_calls=tool_strategy.allow_parallel_tool_calls,
            )
            client_kwargs = self._client_kwargs(
                request.connection,
                max_retries=0,
            )
            with self._client_factory(**client_kwargs) as client:
                if request.connection.api_style == "responses":
                    return OpenAIResponsesAdapter().invoke_with_client(
                        client=client,
                        request=request,
                        tool_executor=tool_executor,
                        started_at=started_at,
                    )
                if request.connection.api_style == "chat_completions":
                    provider_retry_recorder = ProviderRetryRecorder()
                    return self._invoke_chat_completions_agent(
                        client=client,
                        request=request,
                        tool_executor=tool_executor,
                        started_at=started_at,
                        provider_retry_recorder=provider_retry_recorder,
                    )
                raise ModelGatewayError(
                    code="agent_model_connection_api_style_unsupported",
                    message=(
                        "Model connection uses unsupported API style "
                        f"{request.connection.api_style!r}."
                    ),
                    selected_strategies=selected_strategies,
                )
        except ModelGatewayError as exc:
            duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
            raise exc.with_execution_context(
                usage=getattr(exc, "usage", None),
                selected_strategies=getattr(exc, "selected_strategies", None)
                or selected_strategies,
                duration_ms=duration_ms,
                provider_retry_metadata=self._provider_retry_metadata(provider_retry_recorder),
            ) from exc
        except openai.APITimeoutError as exc:
            raise ModelGatewayError(
                code="agent_provider_timeout",
                message="OpenAI request timed out.",
                selected_strategies=selected_strategies,
                failure_classification=PROVIDER_NETWORK_FAILURE,
                provider_retry_metadata=self._provider_retry_metadata(provider_retry_recorder),
            ) from exc
        except openai.APIConnectionError as exc:
            raise ModelGatewayError(
                code="agent_provider_connection_error",
                message="OpenAI request could not reach the API.",
                selected_strategies=selected_strategies,
                failure_classification=PROVIDER_NETWORK_FAILURE,
                provider_retry_metadata=self._provider_retry_metadata(provider_retry_recorder),
            ) from exc
        except openai.APIStatusError as exc:
            status_code = getattr(exc, "status_code", None)
            raise ModelGatewayError(
                code="agent_provider_status_error",
                message=self._format_api_status_error(
                    exc,
                    api_key=request.connection.api_key,
                ),
                selected_strategies=selected_strategies,
                failure_classification=provider_status_failure_classification(
                    status_code if isinstance(status_code, int) else None
                ),
                provider_retry_metadata=self._provider_retry_metadata(provider_retry_recorder),
            ) from exc
        except openai.APIError as exc:
            raise ModelGatewayError(
                code="agent_provider_error",
                message=self._normalize_provider_message(
                    str(exc),
                    api_key=request.connection.api_key,
                ),
                selected_strategies=selected_strategies,
                failure_classification=PROVIDER_TRANSPORT_FAILURE,
                provider_retry_metadata=self._provider_retry_metadata(provider_retry_recorder),
            ) from exc

    def test_connection(
        self,
        request: ModelConnectionTestRequest,
    ) -> ModelConnectionTestResult:
        try:
            with self._client_factory(
                **self._client_kwargs(request.connection, max_retries=0)
            ) as client:
                response = self._create_connection_test_response(
                    client=client,
                    request=request,
                )
            return ModelConnectionTestResult(
                ok=True,
                message=self._success_message(response),
            )
        except openai.APITimeoutError:
            return ModelConnectionTestResult(ok=False, message="Connection test timed out.")
        except openai.APIConnectionError:
            return ModelConnectionTestResult(
                ok=False,
                message="Connection test could not reach the OpenAI API.",
            )
        except openai.APIStatusError as exc:
            return ModelConnectionTestResult(
                ok=False,
                message=self._format_api_status_error(exc, api_key=request.connection.api_key),
            )
        except openai.APIError as exc:
            return ModelConnectionTestResult(
                ok=False,
                message=self._normalize_provider_message(
                    str(exc),
                    api_key=request.connection.api_key,
                ),
            )
        except Exception as exc:
            return ModelConnectionTestResult(
                ok=False,
                message=self._normalize_provider_message(
                    f"Unexpected connection test failure: {exc}",
                    api_key=request.connection.api_key,
                ),
            )

    def probe_capabilities(
        self,
        request: ModelCapabilityProbeRequest,
    ) -> ModelCapabilityProbeResult:
        outcomes: dict[str, ModelCapabilityProbeOutcome] = {}
        try:
            with self._client_factory(
                **self._client_kwargs(request.connection, max_retries=0)
            ) as client:
                self._probe_capabilities_with_client(
                    client=client,
                    request=request,
                    outcomes=outcomes,
                )
        except Exception as exc:
            outcome = self._failure_probe_outcome(
                label="capability",
                exc=exc,
                api_key=request.connection.api_key,
            )
            for capability_key in request.capability_keys:
                outcomes.setdefault(capability_key, outcome)
        return ModelCapabilityProbeResult(capabilities=outcomes)

    def _probe_capabilities_with_client(
        self,
        *,
        client: Any,
        request: ModelCapabilityProbeRequest,
        outcomes: dict[str, ModelCapabilityProbeOutcome],
    ) -> None:
        base_response: Any | None = None
        base_outcome: ModelCapabilityProbeOutcome | None = None

        def base_probe() -> tuple[ModelCapabilityProbeOutcome, Any | None]:
            nonlocal base_response, base_outcome
            if base_outcome is None:
                base_outcome, base_response = self._run_probe_call(
                    label="text generation",
                    api_key=request.connection.api_key,
                    call=lambda: self._create_basic_probe_response(client, request.connection),
                )
            return base_outcome, base_response

        for capability_key in request.capability_keys:
            if capability_key in {"text_generation", "system_messages"}:
                outcomes[capability_key] = base_probe()[0]
            elif capability_key == "chat_completions":
                outcomes[capability_key] = self._protocol_probe_outcome(
                    request,
                    expected_api_style="chat_completions",
                    base_probe=base_probe,
                )
            elif capability_key == "responses_api":
                outcomes[capability_key] = self._protocol_probe_outcome(
                    request,
                    expected_api_style="responses",
                    base_probe=base_probe,
                )
            elif capability_key == "usage_reporting":
                outcomes[capability_key] = self._usage_probe_outcome(base_probe())
            elif capability_key == "json_object_output":
                outcomes[capability_key] = self._run_probe_call(
                    label=_CAPABILITY_PROBE_LABELS[capability_key],
                    api_key=request.connection.api_key,
                    call=lambda: self._create_json_object_probe_response(
                        client,
                        request.connection,
                    ),
                )[0]
            elif capability_key == "strict_json_schema_output":
                outcomes[capability_key] = self._run_probe_call(
                    label=_CAPABILITY_PROBE_LABELS[capability_key],
                    api_key=request.connection.api_key,
                    call=lambda: self._create_strict_schema_probe_response(
                        client,
                        request.connection,
                    ),
                )[0]
            elif capability_key == "native_tool_calls":
                outcomes[capability_key] = self._run_probe_call(
                    label=_CAPABILITY_PROBE_LABELS[capability_key],
                    api_key=request.connection.api_key,
                    call=lambda: self._create_tool_probe_response(
                        client,
                        request.connection,
                        parallel=False,
                    ),
                )[0]
            elif capability_key == "parallel_tool_calls":
                outcomes[capability_key] = self._run_probe_call(
                    label=_CAPABILITY_PROBE_LABELS[capability_key],
                    api_key=request.connection.api_key,
                    call=lambda: self._create_tool_probe_response(
                        client,
                        request.connection,
                        parallel=True,
                    ),
                )[0]
            elif capability_key == "reasoning_hints":
                if request.connection.reasoning_effort is None:
                    outcomes[capability_key] = ModelCapabilityProbeOutcome(
                        status="unknown",
                        detail="Reasoning effort is not configured for this connection.",
                    )
                else:
                    outcomes[capability_key] = self._run_probe_call(
                        label=_CAPABILITY_PROBE_LABELS[capability_key],
                        api_key=request.connection.api_key,
                        call=lambda: self._create_reasoning_probe_response(
                            client,
                            request.connection,
                        ),
                    )[0]
            elif capability_key == "streaming":
                outcomes[capability_key] = self._run_probe_call(
                    label=_CAPABILITY_PROBE_LABELS[capability_key],
                    api_key=request.connection.api_key,
                    call=lambda: self._create_streaming_probe_response(
                        client,
                        request.connection,
                    ),
                )[0]
            else:
                outcomes[capability_key] = ModelCapabilityProbeOutcome(
                    status="unknown",
                    detail="Capability probe is not defined for this capability key.",
                )

    def _create_connection_test_response(
        self,
        *,
        client: Any,
        request: ModelConnectionTestRequest,
    ) -> Any:
        if request.connection.api_style == "responses":
            return OpenAIResponsesAdapter().create_connection_test_response(
                client=client,
                request=request,
            )
        if request.connection.api_style == "chat_completions":
            request_kwargs = {
                "model": request.connection.model_id,
                "messages": [
                    {"role": "system", "content": request.instructions},
                    {"role": "user", "content": request.input_text},
                ],
            }
            if request.connection.reasoning_effort is not None:
                request_kwargs["reasoning_effort"] = request.connection.reasoning_effort
            return client.chat.completions.create(**request_kwargs)
        raise ModelGatewayError(
            code="agent_model_connection_api_style_unsupported",
            message=(
                f"Model connection uses unsupported API style {request.connection.api_style!r}."
            ),
        )

    def _create_basic_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
    ) -> Any:
        if connection.api_style == "responses":
            return client.responses.create(**self._responses_probe_kwargs(connection))
        if connection.api_style == "chat_completions":
            return client.chat.completions.create(**self._chat_probe_kwargs(connection))
        raise self._probe_api_style_error(connection)

    def _create_json_object_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
    ) -> Any:
        if connection.api_style == "responses":
            request_kwargs = self._responses_probe_kwargs(
                connection,
                instructions=_CAPABILITY_PROBE_JSON_INSTRUCTIONS,
                input_text=_CAPABILITY_PROBE_JSON_INPUT,
            )
            request_kwargs["text"] = {"format": {"type": "json_object"}}
            return client.responses.create(**request_kwargs)
        if connection.api_style == "chat_completions":
            request_kwargs = self._chat_probe_kwargs(
                connection,
                instructions=_CAPABILITY_PROBE_JSON_INSTRUCTIONS,
                input_text=_CAPABILITY_PROBE_JSON_INPUT,
            )
            request_kwargs["response_format"] = {"type": "json_object"}
            return client.chat.completions.create(**request_kwargs)
        raise self._probe_api_style_error(connection)

    def _create_strict_schema_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
    ) -> Any:
        if connection.api_style == "responses":
            request_kwargs = self._responses_probe_kwargs(connection)
            request_kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "CapabilityProbe",
                    "strict": True,
                    "schema": dict(_CAPABILITY_PROBE_JSON_SCHEMA),
                }
            }
            return client.responses.create(**request_kwargs)
        if connection.api_style == "chat_completions":
            request_kwargs = self._chat_probe_kwargs(connection)
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "CapabilityProbe",
                    "strict": True,
                    "schema": dict(_CAPABILITY_PROBE_JSON_SCHEMA),
                },
            }
            return client.chat.completions.create(**request_kwargs)
        raise self._probe_api_style_error(connection)

    def _create_tool_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
        *,
        parallel: bool,
    ) -> Any:
        tools = (
            (_CAPABILITY_PROBE_TOOL, _CAPABILITY_PROBE_SECOND_TOOL)
            if parallel
            else (_CAPABILITY_PROBE_TOOL,)
        )
        if connection.api_style == "responses":
            request_kwargs = self._responses_probe_kwargs(connection)
            request_kwargs["tools"] = OpenAIResponsesAdapter._tools_from_declarations(tools)
            if parallel:
                request_kwargs["parallel_tool_calls"] = True
            return client.responses.create(**request_kwargs)
        if connection.api_style == "chat_completions":
            request_kwargs = self._chat_probe_kwargs(connection)
            request_kwargs["tools"] = self._chat_tools_from_declarations(tools)
            if parallel:
                request_kwargs["parallel_tool_calls"] = True
            return client.chat.completions.create(**request_kwargs)
        raise self._probe_api_style_error(connection)

    def _create_reasoning_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
    ) -> Any:
        if connection.api_style == "responses":
            return client.responses.create(
                **self._responses_probe_kwargs(connection, include_reasoning=True)
            )
        if connection.api_style == "chat_completions":
            return client.chat.completions.create(
                **self._chat_probe_kwargs(connection, include_reasoning=True)
            )
        raise self._probe_api_style_error(connection)

    def _create_streaming_probe_response(
        self,
        client: Any,
        connection: ModelGatewayConnectionConfig,
    ) -> Any:
        if connection.api_style == "responses":
            request_kwargs = self._responses_probe_kwargs(connection)
            request_kwargs["stream"] = True
            stream = client.responses.create(**request_kwargs)
            self._close_probe_stream(stream)
            return stream
        if connection.api_style == "chat_completions":
            request_kwargs = self._chat_probe_kwargs(connection)
            request_kwargs["stream"] = True
            stream = client.chat.completions.create(**request_kwargs)
            self._close_probe_stream(stream)
            return stream
        raise self._probe_api_style_error(connection)

    @staticmethod
    def _responses_probe_kwargs(
        connection: ModelGatewayConnectionConfig,
        *,
        include_reasoning: bool = False,
        instructions: str = _CAPABILITY_PROBE_INSTRUCTIONS,
        input_text: str = _CAPABILITY_PROBE_INPUT,
    ) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = {
            "model": connection.model_id,
            "instructions": instructions,
            "input": input_text,
        }
        if include_reasoning and connection.reasoning_effort is not None:
            request_kwargs["reasoning"] = {"effort": connection.reasoning_effort}
        return request_kwargs

    @staticmethod
    def _chat_probe_kwargs(
        connection: ModelGatewayConnectionConfig,
        *,
        include_reasoning: bool = False,
        instructions: str = _CAPABILITY_PROBE_INSTRUCTIONS,
        input_text: str = _CAPABILITY_PROBE_INPUT,
    ) -> dict[str, Any]:
        request_kwargs: dict[str, Any] = {
            "model": connection.model_id,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
        }
        if include_reasoning and connection.reasoning_effort is not None:
            request_kwargs["reasoning_effort"] = connection.reasoning_effort
        return request_kwargs

    def _protocol_probe_outcome(
        self,
        request: ModelCapabilityProbeRequest,
        *,
        expected_api_style: str,
        base_probe: Callable[[], tuple[ModelCapabilityProbeOutcome, Any | None]],
    ) -> ModelCapabilityProbeOutcome:
        if request.connection.api_style != expected_api_style:
            return ModelCapabilityProbeOutcome(
                status="notApplicable",
                detail="Capability is not applicable to the selected protocol profile.",
            )
        base_outcome, _ = base_probe()
        if base_outcome.status != "supported":
            return base_outcome
        label = _CAPABILITY_PROBE_LABELS[
            "responses_api" if expected_api_style == "responses" else "chat_completions"
        ]
        return self._success_probe_outcome(label)

    def _usage_probe_outcome(
        self,
        probe_result: tuple[ModelCapabilityProbeOutcome, Any | None],
    ) -> ModelCapabilityProbeOutcome:
        base_outcome, response = probe_result
        if base_outcome.status != "supported" or response is None:
            return base_outcome
        usage = self._extract_usage(response)
        has_usage = (
            usage.input_tokens is not None
            or usage.output_tokens is not None
            or usage.total_tokens is not None
        )
        if has_usage:
            return ModelCapabilityProbeOutcome(
                status="supported",
                detail="Provider returned usage metadata during the probe.",
            )
        return ModelCapabilityProbeOutcome(
            status="unsupported",
            detail="Provider response did not include usage metadata during the probe.",
        )

    def _run_probe_call(
        self,
        *,
        label: str,
        api_key: str | None,
        call: Callable[[], Any],
    ) -> tuple[ModelCapabilityProbeOutcome, Any | None]:
        try:
            response = call()
        except Exception as exc:
            return self._failure_probe_outcome(label=label, exc=exc, api_key=api_key), None
        return self._success_probe_outcome(label), response

    @staticmethod
    def _success_probe_outcome(label: str) -> ModelCapabilityProbeOutcome:
        return ModelCapabilityProbeOutcome(
            status="supported",
            detail=f"Provider accepted {label} probe.",
        )

    def _failure_probe_outcome(
        self,
        *,
        label: str,
        exc: Exception,
        api_key: str | None,
    ) -> ModelCapabilityProbeOutcome:
        if isinstance(exc, openai.APITimeoutError):
            message = "OpenAI request timed out."
            return self._inconclusive_probe_outcome(label=label, message=message)
        if isinstance(exc, openai.APIConnectionError):
            message = "OpenAI request could not reach the API."
            return self._inconclusive_probe_outcome(label=label, message=message)
        if isinstance(exc, openai.APIStatusError):
            message = self._format_api_status_error(exc, api_key=api_key)
        elif isinstance(exc, openai.APIError):
            message = self._normalize_provider_message(str(exc), api_key=api_key)
        elif isinstance(exc, ModelGatewayError):
            message = self._normalize_provider_message(exc.message, api_key=api_key)
        else:
            message = self._normalize_provider_message(
                f"Unexpected capability probe failure: {exc}",
                api_key=api_key,
            )
        if self._is_unsupported_probe_failure(message):
            return ModelCapabilityProbeOutcome(
                status="unsupported",
                detail=f"Provider rejected {label} probe: {message}",
            )
        return self._inconclusive_probe_outcome(label=label, message=message)

    @staticmethod
    def _is_unsupported_probe_failure(message: str) -> bool:
        normalized = message.lower()
        return any(marker in normalized for marker in _UNSUPPORTED_PROBE_MESSAGE_MARKERS)

    @staticmethod
    def _inconclusive_probe_outcome(
        *,
        label: str,
        message: str,
    ) -> ModelCapabilityProbeOutcome:
        return ModelCapabilityProbeOutcome(
            status="unknown",
            detail=f"Capability probe for {label} was inconclusive: {message}",
        )

    @staticmethod
    def _probe_api_style_error(connection: ModelGatewayConnectionConfig) -> ModelGatewayError:
        return ModelGatewayError(
            code="agent_model_connection_api_style_unsupported",
            message=(f"Model connection uses unsupported API style {connection.api_style!r}."),
        )

    @staticmethod
    def _close_probe_stream(stream: Any) -> None:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _selected_strategies(
        request: ModelExecutionRequest,
        *,
        output_strategy: str,
        has_tools: bool,
        allow_parallel_tool_calls: bool,
    ) -> ModelExecutionStrategies:
        return select_model_execution_strategies(
            request,
            output_strategy=output_strategy,
            has_tools=has_tools,
            allow_parallel_tool_calls=allow_parallel_tool_calls,
        )

    def _invoke_chat_completions_agent(
        self,
        *,
        client: Any,
        request: ModelExecutionRequest,
        tool_executor: ModelToolExecutor,
        started_at: float,
        provider_retry_recorder: ProviderRetryRecorder,
    ) -> ModelExecutionResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.instructions},
            {"role": "user", "content": request.input_text},
        ]
        tool_strategy = select_tool_strategy(request)
        chat_tools = self._chat_tools_from_declarations(request.tools)
        output_strategy = select_output_strategy(request)
        selected_strategies = self._selected_strategies(
            request,
            output_strategy=output_strategy.strategy,
            has_tools=tool_strategy.has_tools,
            allow_parallel_tool_calls=tool_strategy.allow_parallel_tool_calls,
        )
        response_format = self._build_chat_response_format(request, output_strategy.strategy)
        usage = ModelExecutionUsage()
        validation_attempt = 0
        tool_retry_state = ModelToolCallRetryState()
        for _ in range(_MAX_SERVER_TOOL_CALL_ROUNDS + output_strategy.max_validation_attempts - 1):
            request_kwargs: dict[str, Any] = {
                "model": request.connection.model_id,
                "messages": list(messages),
            }
            if response_format is not None:
                request_kwargs["response_format"] = response_format
            if selected_strategies.reasoning_effort is not None:
                request_kwargs["reasoning_effort"] = selected_strategies.reasoning_effort
            if chat_tools:
                request_kwargs["tools"] = chat_tools
                request_kwargs["parallel_tool_calls"] = tool_strategy.allow_parallel_tool_calls
            request_payload = dict(request_kwargs)

            def create_chat_completion(
                request_payload: dict[str, Any] = request_payload,
            ) -> Any:
                return client.chat.completions.create(**request_payload)

            response = call_with_provider_retry(
                create_chat_completion,
                recorder=provider_retry_recorder,
            )
            usage = self._merge_usage(usage, self._extract_usage(response))
            message = self._extract_first_chat_choice_message(response)
            try:
                pending_tool_calls = self._extract_pending_chat_tool_calls(message)
            except ModelGatewayError as exc:
                if tool_retry_state.can_retry(exc):
                    messages.append({"role": "user", "content": tool_retry_state.record_retry(exc)})
                    continue
                if is_retryable_tool_call_failure(exc):
                    raise tool_retry_state.exhausted_error(exc) from exc
                raise
            if not pending_tool_calls:
                duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
                response_text = self._extract_chat_message_content(message)
                try:
                    output = (
                        response_text
                        if output_strategy.strategy == "plainText"
                        else self._parse_response_output(response_text)
                    )
                except ModelGatewayError as exc:
                    if exc.code != "model_output_validation_failed":
                        raise
                    validation_attempt += 1
                    if validation_attempt >= output_strategy.max_validation_attempts:
                        if output_strategy.max_validation_attempts > 1:
                            raise exhausted_validation_error(exc.details) from exc
                        raise
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append(
                        {
                            "role": "user",
                            "content": validation_retry_input(
                                original_input=request.input_text,
                                validation_details=exc.details,
                            ),
                        }
                    )
                    continue
                validation = validate_model_output(request, output)
                if validation.details is None:
                    return ModelExecutionResult(
                        output=validation.output,
                        usage=usage,
                        selected_strategies=selected_strategies,
                        duration_ms=duration_ms,
                        tool_retry_metadata=tool_retry_state.metadata(),
                        provider_retry_metadata=provider_retry_recorder.success_metadata(),
                    )
                validation_attempt += 1
                if validation_attempt >= output_strategy.max_validation_attempts:
                    if output_strategy.max_validation_attempts > 1:
                        raise exhausted_validation_error(validation.details)
                    raise validation_failed_error(validation.details)
                messages.append({"role": "assistant", "content": response_text})
                messages.append(
                    {
                        "role": "user",
                        "content": validation_retry_input(
                            original_input=request.input_text,
                            validation_details=validation.details,
                        ),
                    }
                )
                continue
            tool_result_messages, retry_feedback = self._build_chat_tool_result_messages(
                pending_tool_calls=pending_tool_calls,
                tool_executor=tool_executor,
                tool_retry_state=tool_retry_state,
            )
            if retry_feedback is not None:
                messages.append({"role": "user", "content": retry_feedback})
                continue
            messages.append(
                self._build_chat_assistant_tool_call_message(
                    message=message,
                    pending_tool_calls=pending_tool_calls,
                )
            )
            messages.extend(tool_result_messages)
        raise ModelGatewayError(
            code="agent_tool_round_limit_exceeded",
            message="Agent exceeded the supported server tool call round limit.",
        )

    @staticmethod
    def _provider_retry_metadata(
        recorder: ProviderRetryRecorder | None,
    ) -> dict[str, Any] | None:
        if recorder is None or not recorder.attempts:
            return None
        if recorder.attempts[-1].outcome == "exhausted":
            return recorder.exhausted_metadata()
        return recorder.success_metadata()

    @staticmethod
    def _client_kwargs(
        connection: ModelGatewayConnectionConfig,
        *,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "api_key": connection.api_key,
            "base_url": connection.base_url,
            "timeout": float(connection.timeout_seconds),
        }
        if max_retries is not None:
            kwargs["max_retries"] = max_retries
        return kwargs

    @staticmethod
    def _build_chat_response_format(
        request: ModelExecutionRequest,
        strategy: str,
    ) -> dict[str, Any] | None:
        if strategy == "plainText":
            return None
        if strategy == "jsonObjectWithValidation":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": request.output_schema.name,
                "strict": True,
                "schema": dict(request.output_schema.schema),
            },
        }

    @staticmethod
    def _chat_tools_from_declarations(
        tools: tuple[SignalDeckToolDeclaration, ...],
    ) -> list[dict[str, Any]]:
        chat_tools: list[dict[str, Any]] = []
        for tool in tools:
            chat_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.model_name,
                        "description": tool.description,
                        "parameters": dict(tool.input_schema),
                        "strict": tool.strict,
                    },
                }
            )
        return chat_tools

    @classmethod
    def _extract_first_chat_choice_message(cls, response: Any) -> Any:
        choices = cls._read_field(response, "choices")
        if not isinstance(choices, list) or not choices:
            raise ModelGatewayError(
                code="agent_provider_response_empty",
                message="OpenAI chat response did not include a choice message.",
            )
        message = cls._read_field(choices[0], "message")
        if message is None:
            raise ModelGatewayError(
                code="agent_provider_response_empty",
                message="OpenAI chat response did not include a choice message.",
            )
        return message

    @classmethod
    def _extract_pending_chat_tool_calls(cls, message: Any) -> list[ModelToolCall]:
        raw_tool_calls = cls._read_field(message, "tool_calls")
        if raw_tool_calls is None:
            return []
        if not isinstance(raw_tool_calls, list):
            raw_tool_calls = [raw_tool_calls]
        pending: list[ModelToolCall] = []
        for raw_tool_call in raw_tool_calls:
            call_id = cls._read_field(raw_tool_call, "id")
            function = cls._read_field(raw_tool_call, "function")
            name = cls._read_field(function, "name") if function is not None else None
            arguments = cls._read_field(function, "arguments") if function is not None else None
            pending.append(
                cls._build_pending_tool_call(
                    name=name,
                    arguments=arguments,
                    call_id=call_id,
                    context="OpenAI chat response",
                )
            )
        return pending

    @classmethod
    def _build_pending_tool_call(
        cls,
        *,
        name: Any,
        arguments: Any,
        call_id: Any,
        context: str,
    ) -> ModelToolCall:
        return build_model_tool_call(
            name=name,
            arguments=arguments,
            call_id=call_id,
            context=context,
        )

    @classmethod
    def _build_chat_assistant_tool_call_message(
        cls,
        *,
        message: Any,
        pending_tool_calls: list[ModelToolCall],
    ) -> dict[str, Any]:
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call.call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.tool_name,
                        "arguments": tool_call.arguments_json,
                    },
                }
                for tool_call in pending_tool_calls
            ],
        }
        content = cls._read_field(message, "content")
        if content is not None:
            assistant_message["content"] = content
        reasoning_content = cls._read_field(message, "reasoning_content")
        if reasoning_content is not None:
            assistant_message["reasoning_content"] = reasoning_content
        return assistant_message

    def _build_chat_tool_result_messages(
        self,
        *,
        pending_tool_calls: list[ModelToolCall],
        tool_executor: ModelToolExecutor,
        tool_retry_state: ModelToolCallRetryState,
    ) -> tuple[list[dict[str, str]], str | None]:
        messages: list[dict[str, str]] = []
        for tool_call in pending_tool_calls:
            try:
                tool_result = tool_executor(tool_call)
            except RuntimeToolError as exc:
                if tool_retry_state.can_retry(
                    exc,
                    prior_successful_tool_results=len(messages),
                ):
                    return [], tool_retry_state.record_retry(exc, tool_call=tool_call)
                if is_retryable_tool_call_failure(exc):
                    raise tool_retry_state.exhausted_error(exc, tool_call=tool_call) from exc
                raise
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_result.call_id,
                    "content": json.dumps(
                        tool_result.output,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        return messages, None

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
        raise ModelGatewayError(
            code="agent_provider_response_empty",
            message="OpenAI chat response did not contain text output.",
        )

    @staticmethod
    def _read_field(value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)

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
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ModelGatewayError(
                code="model_output_validation_failed",
                message=(
                    "Model response did not return valid JSON for the selected output strategy."
                ),
                details=[{"field": "output", "issue": "Response body is not valid JSON"}],
            ) from exc

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

    @classmethod
    def _merge_usage(
        cls,
        current: ModelExecutionUsage,
        next_usage: ModelExecutionUsage,
    ) -> ModelExecutionUsage:
        return ModelExecutionUsage(
            input_tokens=cls._sum_usage_values(current.input_tokens, next_usage.input_tokens),
            output_tokens=cls._sum_usage_values(current.output_tokens, next_usage.output_tokens),
            total_tokens=cls._sum_usage_values(current.total_tokens, next_usage.total_tokens),
        )

    @staticmethod
    def _sum_usage_values(*values: int | None) -> int | None:
        normalized = [int(value) for value in values if value is not None]
        return sum(normalized) if normalized else None

    @classmethod
    def _extract_usage(cls, response: Any) -> ModelExecutionUsage:
        if isinstance(response, dict):
            usage = response.get("usage")
        else:
            usage = getattr(response, "usage", None)
        return ModelExecutionUsage(
            input_tokens=cls._read_usage_int(usage, "input_tokens", "prompt_tokens"),
            output_tokens=cls._read_usage_int(usage, "output_tokens", "completion_tokens"),
            total_tokens=cls._read_usage_int(usage, "total_tokens", "totalTokens"),
            raw=usage if isinstance(usage, dict) else None,
        )

    @classmethod
    def _read_usage_int(cls, usage: Any, *fields: str) -> int | None:
        for field in fields:
            if isinstance(usage, dict):
                raw_value = usage.get(field)
            else:
                raw_value = getattr(usage, field, None)
            try:
                if raw_value is not None:
                    return int(raw_value)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _success_message(response: Any) -> str:
        request_id = getattr(response, "_request_id", None)
        message = "Connection test succeeded."
        if isinstance(request_id, str) and request_id.strip():
            message = f"Connection test succeeded (request {request_id.strip()})."
        return message

    def _format_api_status_error(
        self,
        exc: openai.APIStatusError,
        *,
        api_key: str | None,
    ) -> str:
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
    "DEFAULT_OPENAI_CLIENT_FACTORY",
    "OpenAIProtocolAdapter",
]
