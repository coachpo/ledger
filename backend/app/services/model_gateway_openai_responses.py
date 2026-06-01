from __future__ import annotations

import json
import time
from typing import Any

import openai

from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.types import RuntimeToolError
from app.services.model_gateway_dto import (
    ModelExecutionRequest,
    ModelExecutionResult,
    ModelExecutionUsage,
    ModelGatewayError,
    ModelToolCall,
    ModelToolExecutor,
)
from app.services.model_gateway_output_validation import (
    exhausted_validation_error,
    select_output_strategy,
    validate_model_output,
    validation_failed_error,
    validation_retry_input,
)
from app.services.model_gateway_policy_strategy import select_model_execution_strategies
from app.services.model_gateway_tool_retry import (
    ModelToolCallRetryState,
    is_retryable_tool_call_failure,
)
from app.services.model_gateway_tool_strategy import build_model_tool_call, select_tool_strategy

_MAX_SERVER_TOOL_CALL_ROUNDS = 5


class OpenAIResponsesAdapter:
    def invoke_with_client(
        self,
        *,
        client: Any,
        request: ModelExecutionRequest,
        tool_executor: ModelToolExecutor,
        started_at: float,
    ) -> ModelExecutionResult:
        response_input: str | list[dict[str, str]] = request.input_text
        previous_response_id: str | None = None
        previous_tool_calls: list[ModelToolCall] | None = None
        manual_replay_mode = False
        usage = ModelExecutionUsage()
        tool_strategy = select_tool_strategy(request)
        tools = self._tools_from_declarations(request.tools)
        output_strategy = select_output_strategy(request)
        selected_strategies = select_model_execution_strategies(
            request,
            output_strategy=output_strategy.strategy,
            has_tools=tool_strategy.has_tools,
            allow_parallel_tool_calls=tool_strategy.allow_parallel_tool_calls,
        )
        text_format = self._build_text_format(request, output_strategy.strategy)
        validation_attempt = 0
        tool_retry_state = ModelToolCallRetryState()
        for _ in range(_MAX_SERVER_TOOL_CALL_ROUNDS + output_strategy.max_validation_attempts - 1):
            request_kwargs: dict[str, Any] = {
                "model": request.connection.model_id,
                "instructions": request.instructions,
                "input": response_input,
            }
            if text_format is not None:
                request_kwargs["text"] = text_format
            if selected_strategies.reasoning_effort is not None:
                request_kwargs["reasoning"] = {"effort": selected_strategies.reasoning_effort}
            if previous_response_id is not None:
                request_kwargs["previous_response_id"] = previous_response_id
            if tools:
                request_kwargs["tools"] = tools
                request_kwargs["parallel_tool_calls"] = tool_strategy.allow_parallel_tool_calls
            response, manual_replay_mode = self._create_with_manual_replay_fallback(
                client=client,
                request_kwargs=request_kwargs,
                previous_response_id=previous_response_id,
                previous_tool_calls=previous_tool_calls,
                function_call_outputs=response_input,
                manual_replay_mode=manual_replay_mode,
            )
            usage = self._merge_usage(usage, self._extract_usage(response))
            try:
                pending_tool_calls = self._extract_pending_tool_calls(response)
            except ModelGatewayError as exc:
                if tool_retry_state.can_retry(exc):
                    response_input = self._tool_retry_input(
                        request.input_text,
                        tool_retry_state.record_retry(exc),
                    )
                    previous_response_id = None
                    previous_tool_calls = None
                    manual_replay_mode = False
                    continue
                if is_retryable_tool_call_failure(exc):
                    raise tool_retry_state.exhausted_error(exc) from exc
                raise
            if not pending_tool_calls:
                duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
                response_text = self._extract_text(response)
                try:
                    output = (
                        response_text
                        if output_strategy.strategy == "plainText"
                        else self._parse_output(response_text)
                    )
                except ModelGatewayError as exc:
                    if exc.code != "model_output_validation_failed":
                        raise
                    validation_attempt += 1
                    if validation_attempt >= output_strategy.max_validation_attempts:
                        if output_strategy.strategy == "jsonObjectWithValidation":
                            raise exhausted_validation_error(exc.details) from exc
                        raise
                    response_input = validation_retry_input(
                        original_input=request.input_text,
                        validation_details=exc.details,
                    )
                    previous_response_id = None
                    previous_tool_calls = None
                    manual_replay_mode = False
                    continue
                validation = validate_model_output(request, output)
                if validation.details is None:
                    return ModelExecutionResult(
                        output=validation.output,
                        usage=usage,
                        selected_strategies=selected_strategies,
                        duration_ms=duration_ms,
                        tool_retry_metadata=tool_retry_state.metadata(),
                    )
                validation_attempt += 1
                if validation_attempt >= output_strategy.max_validation_attempts:
                    if output_strategy.strategy == "jsonObjectWithValidation":
                        raise exhausted_validation_error(validation.details)
                    raise validation_failed_error(validation.details)
                response_input = validation_retry_input(
                    original_input=request.input_text,
                    validation_details=validation.details,
                )
                previous_response_id = None
                previous_tool_calls = None
                manual_replay_mode = False
                continue
            function_call_outputs, retry_feedback = self._build_function_call_outputs(
                pending_tool_calls=pending_tool_calls,
                tool_executor=tool_executor,
                tool_retry_state=tool_retry_state,
            )
            if retry_feedback is not None:
                response_input = self._tool_retry_input(request.input_text, retry_feedback)
                previous_response_id = None
                previous_tool_calls = None
                manual_replay_mode = False
                continue
            previous_response_id = self._extract_response_id(response)
            previous_tool_calls = pending_tool_calls
            response_input = function_call_outputs
        raise ModelGatewayError(
            code="agent_tool_round_limit_exceeded",
            message="Agent exceeded the supported server tool call round limit.",
        )

    @staticmethod
    def _tool_retry_input(original_input: str, retry_feedback: str) -> str:
        return "\n\n".join((original_input, retry_feedback))

    def create_connection_test_response(
        self,
        *,
        client: Any,
        request: Any,
    ) -> Any:
        request_kwargs: dict[str, Any] = {
            "model": request.connection.model_id,
            "instructions": request.instructions,
            "input": request.input_text,
        }
        if request.connection.reasoning_effort is not None:
            request_kwargs["reasoning"] = {"effort": request.connection.reasoning_effort}
        return client.responses.create(**request_kwargs)

    @staticmethod
    def build_text_format(request: ModelExecutionRequest) -> dict[str, Any] | None:
        return OpenAIResponsesAdapter._build_text_format(request, "strictJsonSchema")

    @staticmethod
    def _build_text_format(
        request: ModelExecutionRequest,
        strategy: str,
    ) -> dict[str, Any] | None:
        if strategy == "plainText":
            return None
        if strategy == "jsonObjectWithValidation":
            return {"format": {"type": "json_object"}}
        return {
            "format": {
                "type": "json_schema",
                "name": request.output_schema.name,
                "strict": True,
                "schema": dict(request.output_schema.schema),
            }
        }

    @staticmethod
    def _tools_from_declarations(
        tools: tuple[SignalDeckToolDeclaration, ...],
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": tool.model_name,
                "description": tool.description,
                "strict": tool.strict,
                "parameters": dict(tool.input_schema),
            }
            for tool in tools
        ]

    @classmethod
    def _extract_pending_tool_calls(cls, response: Any) -> list[ModelToolCall]:
        output_items = cls._read_field(response, "output")
        if output_items is None:
            return []
        if not isinstance(output_items, list):
            output_items = [output_items]
        pending: list[ModelToolCall] = []
        for item in output_items:
            item_type = cls._read_field(item, "type")
            if item_type != "function_call":
                continue
            pending.append(
                cls._build_pending_tool_call(
                    name=cls._read_field(item, "name"),
                    arguments=cls._read_field(item, "arguments"),
                    call_id=cls._read_field(item, "call_id"),
                    context="OpenAI response",
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

    def _create_with_manual_replay_fallback(
        self,
        *,
        client: Any,
        request_kwargs: dict[str, Any],
        previous_response_id: str | None,
        previous_tool_calls: list[ModelToolCall] | None,
        function_call_outputs: str | list[dict[str, str]],
        manual_replay_mode: bool,
    ) -> tuple[Any, bool]:
        effective_request_kwargs = dict(request_kwargs)
        if manual_replay_mode:
            if previous_tool_calls is None or not isinstance(function_call_outputs, list):
                raise ModelGatewayError(
                    code="model_tool_call_payload_invalid",
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
        pending_tool_calls: list[ModelToolCall],
        function_call_outputs: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return [
            *[
                {
                    "type": "function_call",
                    "name": tool_call.tool_name,
                    "arguments": tool_call.arguments_json,
                    "call_id": tool_call.call_id,
                }
                for tool_call in pending_tool_calls
            ],
            *function_call_outputs,
        ]

    @classmethod
    def _extract_response_id(cls, response: Any) -> str:
        response_id = cls._read_field(response, "id")
        if isinstance(response_id, str) and response_id.strip():
            return response_id.strip()
        raise ModelGatewayError(
            code="model_tool_call_payload_invalid",
            message="OpenAI response did not include a response id for tool continuation.",
        )

    def _build_function_call_outputs(
        self,
        *,
        pending_tool_calls: list[ModelToolCall],
        tool_executor: ModelToolExecutor,
        tool_retry_state: ModelToolCallRetryState,
    ) -> tuple[list[dict[str, str]], str | None]:
        items: list[dict[str, str]] = []
        for tool_call in pending_tool_calls:
            try:
                tool_result = tool_executor(tool_call)
            except RuntimeToolError as exc:
                if tool_retry_state.can_retry(
                    exc,
                    prior_successful_tool_results=len(items),
                ):
                    return [], tool_retry_state.record_retry(exc, tool_call=tool_call)
                if is_retryable_tool_call_failure(exc):
                    raise tool_retry_state.exhausted_error(exc, tool_call=tool_call) from exc
                raise
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": tool_result.call_id,
                    "output": json.dumps(
                        tool_result.output,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        return items, None

    @classmethod
    def _extract_text(cls, response: Any) -> str:
        direct_text = cls._read_field(response, "output_text") or cls._read_field(
            response,
            "outputText",
        )
        output_payload = cls._read_field(response, "output")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()
        fragments = cls._collect_text_fragments(output_payload)
        normalized = "\n".join(
            fragment.strip() for fragment in fragments if fragment.strip()
        ).strip()
        if normalized:
            return normalized
        raise ModelGatewayError(
            code="agent_provider_response_empty",
            message="OpenAI response did not contain text output.",
        )

    @classmethod
    def _collect_text_fragments(cls, value: Any) -> list[str]:
        fragments: list[str] = []
        if value is None:
            return fragments
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            for item in value:
                fragments.extend(cls._collect_text_fragments(item))
            return fragments
        if isinstance(value, dict):
            text_value = value.get("text")
            if isinstance(text_value, str) and text_value.strip():
                fragments.append(text_value)
            for key in ("content", "output"):
                nested = value.get(key)
                if nested is not None:
                    fragments.extend(cls._collect_text_fragments(nested))
            return fragments
        text_attr = getattr(value, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            fragments.append(text_attr)
        for attr in ("content", "output"):
            nested = getattr(value, attr, None)
            if nested is not None:
                fragments.extend(cls._collect_text_fragments(nested))
        return fragments

    def _parse_output(self, response_text: str) -> Any:
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
        usage = cls._read_field(response, "usage")
        return ModelExecutionUsage(
            input_tokens=cls._read_usage_int(usage, "input_tokens", "prompt_tokens"),
            output_tokens=cls._read_usage_int(usage, "output_tokens", "completion_tokens"),
            total_tokens=cls._read_usage_int(usage, "total_tokens", "totalTokens"),
            raw=usage if isinstance(usage, dict) else None,
        )

    @classmethod
    def _read_usage_int(cls, usage: Any, *fields: str) -> int | None:
        for field in fields:
            raw_value = cls._read_field(usage, field)
            try:
                if raw_value is not None:
                    return int(raw_value)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _read_field(value: Any, field: str) -> Any:
        if isinstance(value, dict):
            return value.get(field)
        return getattr(value, field, None)


__all__ = ["OpenAIResponsesAdapter"]
