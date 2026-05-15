from __future__ import annotations

import json
import time
from typing import Any

import httpx
from openai import BadRequestError
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.agents.mcp.runtime import McpRuntimeDispatcher
from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolSpec
from app.services.agent_execution_service import (
    AgentExecutionService,
    _ResolvedModelConnectionConfig,
)


class _SummaryOutput(BaseModel):
    summary: str


class _DispatchRecorder:
    def __init__(self) -> None:
        self.dispatch_calls: list[dict[str, Any]] = []

    def executor(
        self, context: RuntimeToolContext, arguments: dict[str, object]
    ) -> dict[str, object]:
        tool_name = str(arguments.pop("__tool_name"))
        self.dispatch_calls.append(
            {
                "name": tool_name,
                "arguments": dict(arguments),
                "context_agent_key": context.agent_key,
            }
        )
        return {"tool": tool_name, "arguments": dict(arguments)}


def _build_runtime_tool_registry(recorder: _DispatchRecorder) -> RuntimeToolRegistry:
    def _build_spec(
        *,
        key: str,
        function_name: str,
        parameters_schema: dict[str, object],
        sort_order: int,
    ) -> RuntimeToolSpec:
        def _parser(arguments_json: str) -> dict[str, object]:
            parsed = json.loads(arguments_json)
            assert isinstance(parsed, dict)
            parsed["__tool_name"] = function_name
            return parsed

        return RuntimeToolSpec(
            key=key,
            openai_function_name=function_name,
            display_name=function_name,
            description=function_name,
            parameters_schema=parameters_schema,
            guidance="",
            sort_order=sort_order,
            denied_code="agent_execution_access_denied",
            denied_message="denied",
            parser=_parser,
            executor=recorder.executor,
        )

    return RuntimeToolRegistry(
        [
            _build_spec(
                key="ledger.market_data.quote_lookup",
                function_name="ledger_market_data_quote_lookup",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array"},
                        "baseCurrency": {"type": ["string", "null"]},
                    },
                    "required": ["symbols", "baseCurrency"],
                    "additionalProperties": False,
                },
                sort_order=1,
            ),
            _build_spec(
                key="ledger.market_data.history_lookup",
                function_name="ledger_market_data_history_lookup",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array"},
                        "range": {"type": ["string", "null"]},
                        "pointLimit": {"type": ["integer", "null"]},
                    },
                    "required": ["symbols", "range", "pointLimit"],
                    "additionalProperties": False,
                },
                sort_order=2,
            ),
        ]
    )


class _ManualReplayClient:
    def __init__(self) -> None:
        self.responses = self
        self.create_calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(kwargs)
        if len(self.create_calls) == 1:
            return {
                "id": "resp_initial",
                "output": [
                    {"type": "reasoning", "id": "rs_1", "summary": [], "status": "completed"},
                    {
                        "type": "function_call",
                        "name": "ledger_market_data_quote_lookup",
                        "arguments": json.dumps({"symbols": ["AAPL"], "baseCurrency": None}),
                        "call_id": "call_quote",
                    },
                ],
                "usage": {"total_tokens": 2},
            }
        if len(self.create_calls) == 2:
            request = httpx.Request("POST", "https://provider.example/v1/responses")
            response = httpx.Response(
                400,
                request=request,
                json={
                    "message": "No tool call found for function call output with call_id call_quote.",
                    "type": "invalid_request_error",
                    "param": "input",
                    "code": None,
                },
            )
            raise BadRequestError(
                "No tool call found for function call output with call_id call_quote.",
                response=response,
                body=response.json(),
            )
        if len(self.create_calls) == 3:
            assert "previous_response_id" not in kwargs
            assert kwargs["input"] == [
                {
                    "type": "function_call",
                    "name": "ledger_market_data_quote_lookup",
                    "arguments": json.dumps({"symbols": ["AAPL"], "baseCurrency": None}),
                    "call_id": "call_quote",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_quote",
                    "output": json.dumps(
                        {
                            "arguments": {"baseCurrency": None, "symbols": ["AAPL"]},
                            "tool": "ledger_market_data_quote_lookup",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ]
            return {
                "id": "resp_replayed",
                "output": [
                    {
                        "type": "function_call",
                        "name": "ledger_market_data_history_lookup",
                        "arguments": json.dumps(
                            {"symbols": ["AAPL"], "range": "1mo", "pointLimit": 5}
                        ),
                        "call_id": "call_history",
                    }
                ],
                "usage": {"total_tokens": 2},
            }
        if len(self.create_calls) == 4:
            assert "previous_response_id" not in kwargs
            assert kwargs["input"] == [
                {
                    "type": "function_call",
                    "name": "ledger_market_data_history_lookup",
                    "arguments": json.dumps({"symbols": ["AAPL"], "range": "1mo", "pointLimit": 5}),
                    "call_id": "call_history",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_history",
                    "output": json.dumps(
                        {
                            "arguments": {
                                "pointLimit": 5,
                                "range": "1mo",
                                "symbols": ["AAPL"],
                            },
                            "tool": "ledger_market_data_history_lookup",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ]
            return {
                "id": "resp_final",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"summary":"manual replay ok"}'}
                        ],
                    }
                ],
                "usage": {"total_tokens": 1},
            }
        raise AssertionError(f"Unexpected create call count: {len(self.create_calls)}")


def test_invoke_responses_agent_replays_manual_context_after_call_id_failure(
    session_factory: sessionmaker[Session],
) -> None:
    service = AgentExecutionService(session_factory)
    client = _ManualReplayClient()
    recorder = _DispatchRecorder()
    tool_registry = _build_runtime_tool_registry(recorder)
    result = service._invoke_responses_agent(
        client=client,
        model_connection=_ResolvedModelConnectionConfig(
            id=1,
            name="TradingAgents Primary Model",
            connection_kind="provider",
            base_url="http://provider.example/v1",
            model_id="gpt-5.4-mini",
            reasoning_effort="medium",
            api_style="responses",
            timeout_seconds=60,
            api_key="sk-test",
        ),
        instructions="Return only valid JSON.",
        response_input="Need tool usage first.",
        text_format=service._build_responses_text_format(_SummaryOutput),
        available_tools=tool_registry.get_openai_tools(
            {
                "ledger.market_data.quote_lookup",
                "ledger.market_data.history_lookup",
            }
        ),
        granted_tool_keys={
            "ledger.market_data.quote_lookup",
            "ledger.market_data.history_lookup",
        },
        runtime_tool_registry=tool_registry,
        runtime_tool_context=RuntimeToolContext(
            session_factory=session_factory,
            capability_references=[],
            agent_key="market_analyst",
        ),
        mcp_dispatcher=McpRuntimeDispatcher(tools=[]),
        started_at=time.monotonic(),
    )

    assert result.output == {"summary": "manual replay ok"}
    assert [call["name"] for call in recorder.dispatch_calls] == [
        "ledger_market_data_quote_lookup",
        "ledger_market_data_history_lookup",
    ]
    assert len(client.create_calls) == 4
    assert client.create_calls[1]["previous_response_id"] == "resp_initial"
    assert client.create_calls[1]["input"][0]["type"] == "function_call_output"
    assert "previous_response_id" not in client.create_calls[2]
    assert "previous_response_id" not in client.create_calls[3]
