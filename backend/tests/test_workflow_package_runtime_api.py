from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, cast, override

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import ApiError, validation_error
from app.core.formatting import utcnow
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.model_connection import ModelConnection
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.workflow_package import WorkflowPackage
from app.models.workflow_package_schedule import (
    WorkflowPackageSchedule,
    WorkflowPackageScheduleFire,
)
from app.schemas.run import RunAgentInvocationRead, RunPackageProvenanceRead
from app.schemas.schedule import (
    DailyRecurrence,
    FireReason,
    FireStatus,
    IntervalRecurrence,
    IntervalUnit,
    MisfirePolicy,
    OverlapPolicy,
    ScheduleCreate,
)
from app.schemas.workflow_package import WorkflowPackageRead
from app.services.model_gateway import ModelExecutionGateway
from app.services.model_gateway_dto import (
    ModelCapabilityProbeRequest,
    ModelConnectionTestRequest,
    ModelExecutionResult,
    ModelGatewayConnectionConfig,
    ModelGatewayError,
)
from app.services.model_gateway_openai import (
    OPENAI_COMPATIBLE_USER_AGENT,
    ProviderRetryAttempt,
    ProviderRetryPolicy,
    ProviderRetryRecorder,
    _build_openai_compatible_user_agent,
    _call_with_provider_retry,
)
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_package_schedule_inputs import (
    RUNTIME_INPUT_PAYLOAD_MAX_BYTES,
    SCHEDULE_RENDER_VALIDATION_FAILED,
    SCHEDULE_TEMPLATE_INVALID_EXPRESSION,
    SCHEDULE_TEMPLATE_MISSING_VALUE,
    ScheduledInputLastRunContext,
    build_scheduled_input_template_context,
    render_scheduled_input_template,
)
from app.services.workflow_package_schedule_materializer import WorkflowPackageScheduleMaterializer
from app.services.workflow_package_schedule_service import WorkflowPackageScheduleService
from app.workers.run_scheduler import RunSchedulerWorker, scheduler_lease_owner
from tests.fake_openai_provider import run_fake_openai_provider

_DIGITAL_ORACLE_PHASE1_TOOL_KEYS = (
    "signaldeck.digital_oracle.prediction_markets.lookup",
    "signaldeck.digital_oracle.sec_filings.lookup",
    "signaldeck.digital_oracle.market_sentiment.lookup",
    "signaldeck.digital_oracle.macro_rates.lookup",
    "signaldeck.digital_oracle.crypto_derivatives.lookup",
    "signaldeck.digital_oracle.cftc_positioning.lookup",
    "signaldeck.digital_oracle.options.lookup",
)
_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_DIGITAL_ORACLE_PRESET_KEY = "digital_oracle_researcher"
_TRADINGAGENTS_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)
_TRADINGAGENTS_CANONICAL_SCHEDULES = (
    ("TradingAgents Advisory Research · 1h", "advisory_research"),
    ("TradingAgents Market Research · 1h", "market_research"),
    ("TradingAgents News Research · 1h", "news_research"),
    ("TradingAgents Fundamentals Research · 1h", "fundamentals_research"),
)


def _canonicalize_live_tool_keys(source: str) -> str:
    return source


_TRADINGAGENTS_CANONICAL_SCHEDULE_INPUT_TEMPLATES: dict[str, dict[str, object]] = {
    "advisory_research": {
        "ticker": "SPY",
        "asOfDate": "{{fire.scheduledLocalDate}}",
        "horizonDays": 30,
        "outputLanguage": "English",
        "benchmarkSymbol": "SPY",
        "maxRiskDebateRounds": 2,
        "maxInvestmentDebateRounds": 2,
    },
    "market_research": {
        "ticker": "SPY",
        "asOfDate": "{{fire.scheduledLocalDate}}",
        "horizonDays": 30,
        "outputLanguage": "English",
        "benchmarkSymbol": "SPY",
    },
    "news_research": {
        "ticker": "SPY",
        "asOfDate": "{{fire.scheduledLocalDate}}",
        "horizonDays": 30,
        "outputLanguage": "English",
    },
    "fundamentals_research": {
        "ticker": "SPY",
        "asOfDate": "{{fire.scheduledLocalDate}}",
        "horizonDays": 30,
        "outputLanguage": "English",
    },
}


class _RuntimeOpenAIUsage:
    def __init__(self, total_tokens: int) -> None:
        self.total_tokens = total_tokens


class _RuntimeOpenAIResponse:
    def __init__(self, *, output_text: str, total_tokens: int) -> None:
        self.output_text = output_text
        self.usage = _RuntimeOpenAIUsage(total_tokens)


class _RuntimeRecordingOpenAIClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    output_text = '{"summary": "package runtime output"}'
    output_texts: list[str] | None = None
    total_tokens = 23

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        output_texts = type(self).output_texts
        output_text = (
            output_texts[min(len(type(self).create_calls) - 1, len(output_texts) - 1)]
            if output_texts
            else type(self).output_text
        )
        return _RuntimeOpenAIResponse(
            output_text=output_text,
            total_tokens=type(self).total_tokens,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.output_text = '{"summary": "package runtime output"}'
        cls.output_texts = None
        cls.total_tokens = 23


class _RuntimeRecordingChatCompletionsClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []
    final_output_text = '{"summary": "package chat runtime output"}'
    final_output_texts: list[str] | None = None
    return_empty_choices = False
    malformed_tool_arguments = False
    failures: list[BaseException] | None = None
    tool_argument_sequence: list[str] | None = None
    tool_name_sequence: list[str] | None = None
    reasoning_content: str | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.chat = self
        self.completions = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        call_index = len(type(self).create_calls)
        failures = type(self).failures or []
        if call_index <= len(failures):
            raise failures[call_index - 1]
        if type(self).return_empty_choices:
            return {
                "choices": [],
                "usage": self._usage(prompt_tokens=1, completion_tokens=0),
            }
        tool_argument_sequence = type(self).tool_argument_sequence
        should_emit_tool_call = (
            call_index <= len(tool_argument_sequence)
            if tool_argument_sequence is not None
            else call_index == 1
        )
        if should_emit_tool_call:
            tool_name_sequence = type(self).tool_name_sequence or []
            tool_name = (
                tool_name_sequence[call_index - 1]
                if call_index <= len(tool_name_sequence)
                else "signaldeck_finance_reports_lookup"
            )
            arguments = (
                tool_argument_sequence[call_index - 1]
                if tool_argument_sequence is not None
                else (
                    "{" if type(self).malformed_tool_arguments else self._report_lookup_arguments()
                )
            )
            call_id = (
                "call_report_lookup"
                if (
                    tool_argument_sequence is None
                    and tool_name == "signaldeck_finance_reports_lookup"
                )
                else f"call_{call_index}"
            )
            message: dict[str, Any] = {
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": arguments},
                    }
                ],
            }
            if type(self).reasoning_content is not None:
                message["reasoning_content"] = type(self).reasoning_content
            return {
                "choices": [{"message": message}],
                "usage": self._usage(prompt_tokens=7, completion_tokens=2),
            }
        final_output_texts = type(self).final_output_texts
        final_output_text = (
            final_output_texts[min(call_index - 1, len(final_output_texts) - 1)]
            if final_output_texts
            else type(self).final_output_text
        )
        return {
            "choices": [{"message": {"content": final_output_text}}],
            "usage": self._usage(prompt_tokens=11, completion_tokens=8),
        }

    @staticmethod
    def _usage(*, prompt_tokens: int, completion_tokens: int) -> dict[str, int]:
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    @staticmethod
    def _report_lookup_arguments() -> str:
        return json.dumps(
            {
                "ticker": "NVDA",
                "tag": None,
                "reviewType": None,
                "source": None,
                "limit": 1,
                "offset": 0,
            },
            sort_keys=True,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.final_output_text = '{"summary": "package chat runtime output"}'
        cls.final_output_texts = None
        cls.return_empty_choices = False
        cls.malformed_tool_arguments = False
        cls.failures = None
        cls.tool_argument_sequence = None
        cls.tool_name_sequence = None
        cls.reasoning_content = None


class _RuntimeMalformedResponsesToolClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        return {
            "id": "resp_tool_invalid",
            "output": [
                {
                    "type": "function_call",
                    "name": "signaldeck_finance_reports_lookup",
                    "call_id": "call_report_lookup",
                    "arguments": "{",
                }
            ],
            "usage": {"total_tokens": 3},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


class _RuntimeRetryingResponsesToolClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        call_index = len(type(self).create_calls)
        if call_index == 1:
            arguments = "{"
        elif call_index == 2:
            arguments = _RuntimeRecordingChatCompletionsClient._report_lookup_arguments()
        else:
            return {"id": "resp_final", "output_text": '{"summary": "responses retry output"}'}
        return {
            "id": f"resp_tool_{call_index}",
            "output": [
                {
                    "type": "function_call",
                    "name": "signaldeck_finance_reports_lookup",
                    "call_id": f"call_{call_index}",
                    "arguments": arguments,
                }
            ],
            "usage": {"total_tokens": 3},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


class _RuntimeProviderRetryingResponsesClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        call_index = len(type(self).create_calls)
        if call_index == 1:
            return {
                "id": "resp_tool_1",
                "output": [
                    {
                        "type": "function_call",
                        "name": "signaldeck_finance_reports_lookup",
                        "call_id": "call_report_lookup",
                        "arguments": (
                            _RuntimeRecordingChatCompletionsClient._report_lookup_arguments()
                        ),
                    }
                ],
                "usage": {"total_tokens": 3},
            }
        if call_index == 2:
            raise _provider_status_error(503)
        if call_index == 3:
            return {
                "id": "resp_final",
                "output_text": '{"summary": "responses provider retry output"}',
                "usage": {"total_tokens": 5},
            }
        raise AssertionError(f"Unexpected create call count: {call_index}")

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []


class _RuntimeUsageLessResponsesClient:
    init_calls: list[dict[str, Any]] = []
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        return {
            "id": "resp_usage_missing",
            "output_text": '{"summary": "usage omitted"}',
        }

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []


class _RuntimeReasoningRejectingChatClient:
    create_calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        del kwargs
        self.chat = self
        self.completions = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> dict[str, Any]:
        type(self).create_calls.append(kwargs)
        if "reasoning_effort" in kwargs:
            raise ApiError(
                status_code=400,
                code="invalid_request_error",
                message="Unsupported reasoning fields were rejected by the provider.",
            )
        return {
            "choices": [{"message": {"content": '{"summary": "reasoning omitted"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = []


def _provider_retry_request() -> httpx.Request:
    return httpx.Request("POST", "https://provider-runtime.example.test/v1/responses")


def _provider_status_error(
    status_code: int,
    *,
    headers: dict[str, str] | None = None,
    body: object | None = None,
) -> openai.APIStatusError:
    request = _provider_retry_request()
    response = httpx.Response(status_code, request=request, headers=headers or {})
    return openai.APIStatusError(
        "Provider request failed.",
        response=response,
        body=(
            body
            if body is not None
            else {
                "error": {
                    "message": "provider said no",
                    "headers": {"Authorization": "Bearer secret"},
                }
            }
        ),
    )


def _package_source(*, package_key: str = "runtime_package") -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Runtime Package
  description: Runtime package fixture.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles: []
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      outputSchema: summary_output
      capabilityProfiles: []
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


def _package_source_with_report_lookup(*, package_key: str) -> str:
    source = _package_source(package_key=package_key)
    source = source.replace(
        "  capabilityProfiles: []\n  outputSchemas:",
        """  capabilityProfiles:
    - key: report_context_tools
      name: Memory Context Tools
      toolKeys:
        - signaldeck.finance.reports.lookup
  outputSchemas:""",
        1,
    )
    return source.replace(
        "      capabilityProfiles: []\n  workflows:",
        "      capabilityProfiles: [report_context_tools]\n  workflows:",
        1,
    )


def _package_source_with_digital_oracle_phase1_tools(*, package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Digital Oracle Runtime Fixture
  description: Runtime fixture for Digital Oracle phase-1 tool grants.
spec:
  inputs:
    type: object
    properties:
      researchQuestion:
        type: string
    required: [researchQuestion]
  capabilityProfiles:
    - key: digital_oracle_phase1_tools
      name: Digital Oracle Phase 1 Tools
      toolKeys:
        - signaldeck.digital_oracle.cftc_positioning.lookup
        - signaldeck.digital_oracle.crypto_derivatives.lookup
        - signaldeck.digital_oracle.macro_rates.lookup
        - signaldeck.digital_oracle.market_sentiment.lookup
        - signaldeck.digital_oracle.options.lookup
        - signaldeck.digital_oracle.prediction_markets.lookup
        - signaldeck.digital_oracle.sec_filings.lookup
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          researchQuestion:
            type: string
        required: [researchQuestion]
      outputSchema: summary_output
      capabilityProfiles: [digital_oracle_phase1_tools]
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          researchQuestion:
            type: string
        required: [researchQuestion]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          researchQuestion: ${{{{ inputs.researchQuestion }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


def _package_source_with_inline_private_mcp(*, package_key: str) -> str:
    return (
        _package_source(package_key=package_key)
        .replace(
            "  agents:\n",
            """  mcpServers:
    - key: exa
      name: Exa Web Search
      transport: http-sse
      url: https://mcp.exa.ai/mcp?tools=web_search_exa
      headers:
        Authorization: Bearer inline-header-secret
      query:
        exaApiKey: inline-query-secret
      toolKeys: [web_search_exa]
  agents:
""",
            1,
        )
        .replace(
            "      capabilityProfiles: []",
            "      capabilityProfiles: []\n      mcpServers: [exa]",
            1,
        )
    )


def _schema_aliases(schema: type[Any]) -> set[str]:
    return {field.alias or name for name, field in schema.model_fields.items()}


def _assert_package_read_is_artifact_inventory(body: dict[str, object]) -> None:
    assert set(body) == _schema_aliases(WorkflowPackageRead)


def _create_package(
    client: TestClient,
    *,
    package_key: str = "runtime_package",
) -> dict[str, object]:
    return _create_package_from_source(
        client,
        manifest_source=_package_source(package_key=package_key),
    )


def _create_package_from_source(
    client: TestClient,
    *,
    manifest_source: str,
) -> dict[str, object]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert response.status_code == 201, response.json()
    body = cast(dict[str, object], response.json())
    _assert_package_read_is_artifact_inventory(body)
    return body


def _seeded_package(client: TestClient, package_key: str) -> dict[str, Any]:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, Any]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] == package_key:
            return package
    raise AssertionError(f"Workflow package preset {package_key!r} was not seeded")


def _delete_existing_package(client: TestClient, package_key: str) -> None:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, object]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] != package_key:
            continue
        deleted = client.delete(f"/api/workflow-packages/{package['id']}")
        assert deleted.status_code == 204, deleted.text
        break


def _bind_package_secret(client: TestClient, package_id: int, key: str) -> None:
    response = client.put(
        f"/api/workflow-packages/{package_id}/secret-bindings/{key}",
        json={"value": f"{key}-test-value"},
    )
    assert response.status_code == 200, response.json()


def _create_canonical_fixture_package(
    client: TestClient,
    *,
    package_key: str,
    fixture: Path,
) -> dict[str, Any]:
    _delete_existing_package(client, package_key)
    body = _create_package_from_source(
        client,
        manifest_source=_canonicalize_live_tool_keys(fixture.read_text()),
    )
    return cast(dict[str, Any], body)


def _seeded_tradingagents_package(client: TestClient) -> dict[str, Any]:
    return _create_canonical_fixture_package(
        client,
        package_key=_TRADINGAGENTS_PRESET_KEY,
        fixture=_TRADINGAGENTS_FIXTURE,
    )


def _seeded_digital_oracle_package(client: TestClient) -> dict[str, Any]:
    return _create_canonical_fixture_package(
        client,
        package_key=_DIGITAL_ORACLE_PRESET_KEY,
        fixture=_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE,
    )


def _create_tradingagents_canonical_schedules(
    session_factory: sessionmaker[Session],
    *,
    package_id: int,
    next_fire_at: datetime,
) -> None:
    with session_factory() as session:
        service = WorkflowPackageScheduleService(session)
        for name, workflow_key in _TRADINGAGENTS_CANONICAL_SCHEDULES:
            _ = service.create_schedule(
                ScheduleCreate(
                    package_id=package_id,
                    workflow_key=workflow_key,
                    name=name,
                    timezone="UTC",
                    recurrence=IntervalRecurrence(every=1, unit=IntervalUnit.HOURS),
                    input_template=deepcopy(
                        _TRADINGAGENTS_CANONICAL_SCHEDULE_INPUT_TEMPLATES[workflow_key]
                    ),
                ),
                next_fire_at=next_fire_at,
            )


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    key: str = "package_runtime_model",
    name: str = "Package Runtime Model",
    description: str = "Package runtime model binding.",
    api_key: str | None = "test-api-key",
    base_url: str = "https://provider-runtime.example.test/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
    capabilities: dict[str, Any] | None = None,
    output_strategy_policy: str = "prefer_strict_schema",
    parallel_tool_calls_policy: str = "serialize",
    reasoning_policy: str = "allow",
    streaming_policy: str = "allow",
) -> None:
    with session_factory() as session:
        payload = {} if api_key is None else {"apiKey": api_key}
        session.add(
            ModelConnection(
                key=key,
                name=name,
                description=description,
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="high",
                api_style=api_style,
                capabilities=capabilities or {},
                output_strategy_policy=output_strategy_policy,
                parallel_tool_calls_policy=parallel_tool_calls_policy,
                reasoning_policy=reasoning_policy,
                streaming_policy=streaming_policy,
                timeout_seconds=31,
                secret_payload=payload,
            )
        )
        session.commit()


def _chat_model_gateway_connection_config(
    *,
    api_key: str | None = "test-api-key",
) -> ModelGatewayConnectionConfig:
    return ModelGatewayConnectionConfig(
        id=1,
        name="Chat Runtime Model",
        base_url="https://provider-runtime.example.test/v1",
        model_id="chat-runtime-model",
        reasoning_effort="high",
        api_style="chat_completions",
        timeout_seconds=31,
        api_key=api_key,
    )


def _drain_run_queue(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        drained = RunQueueService(session, session_factory).drain_once()
        assert drained is True


def _wait_for_run(client: TestClient, run_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 3.0
    last_body: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.json()
        body = response.json()
        last_body = cast(dict[str, Any], body)
        if body["status"] not in {"queued", "running"}:
            return last_body
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish in time: {last_body}")


def test_run_scheduler_locked_settings_defaults_and_lease_owner_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in (
        "RUN_SCHEDULER_MAX_ACTIVE_RUNS",
        "RUN_SCHEDULER_MAX_ACTIVE_PER_PACKAGE",
        "RUN_SCHEDULER_POLL_INTERVAL_SECONDS",
        "RUN_SCHEDULER_HEARTBEAT_SECONDS",
        "RUN_SCHEDULER_LEASE_TTL_SECONDS",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings.model_validate({})

    assert settings.run_scheduler_max_active_runs == 4
    assert settings.run_scheduler_max_active_per_package == 1
    assert settings.run_scheduler_poll_interval_seconds == 1.0
    assert settings.run_scheduler_heartbeat_seconds == 10.0
    assert settings.run_scheduler_lease_ttl_seconds == 60.0
    assert scheduler_lease_owner(hostname="test-host", pid=1234, slot=2) == (
        "scheduler:test-host:1234:2"
    )


def test_workflow_package_launch_enqueues_without_request_worker(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="enqueue_only_worker_boundary_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "queued"
        assert run.attempt_count == 0
        assert run.last_claimed_at is None
        assert run.lease_owner is None
        assert run.lease_expires_at is None
        assert run.heartbeat_at is None
    assert _RuntimeRecordingOpenAIClient.create_calls == []


def test_seeded_digital_oracle_launch_persists_question_input(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        key="digital_oracle_primary_model",
        name="Digital Oracle Primary Model",
        description="Preflight model binding.",
        api_style="chat_completions",
        capabilities={
            "nativeToolCalls": {"status": "supported"},
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "supported"},
            "parallelToolCalls": {"status": "supported"},
        },
    )
    package = _seeded_digital_oracle_package(client)
    _bind_package_secret(client, int(package["id"]), "fred_api_key")
    parameters = {"researchQuestion": "what is the sun?", "outputLanguage": "English"}

    launch = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={"workflowKey": "research", "parameters": parameters},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.workflow_package_key == _DIGITAL_ORACLE_PRESET_KEY
        assert run.workflow_package_workflow_key == "research"
        assert run.input == parameters
        assert snapshot.workflow_package_key == _DIGITAL_ORACLE_PRESET_KEY
        assert snapshot.workflow_key == "research"
        assert snapshot.launch_parameters == parameters


def test_seeded_digital_oracle_launch_records_parameters_and_expected_tools(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        key="digital_oracle_primary_model",
        name="Digital Oracle Primary Model",
        description="Preflight model binding.",
        api_style="chat_completions",
        capabilities={
            "nativeToolCalls": {"status": "supported"},
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "supported"},
            "parallelToolCalls": {"status": "supported"},
        },
    )
    package = _seeded_digital_oracle_package(client)
    _bind_package_secret(client, int(package["id"]), "fred_api_key")
    parameters = {"researchQuestion": "Will the Nasdaq go up?", "outputLanguage": "English"}

    launch = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={"workflowKey": "research", "parameters": parameters},
    )
    assert launch.status_code == 201, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    raw_run_id = launch_body["id"]
    assert isinstance(raw_run_id, int)
    run_id = raw_run_id

    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.status == "queued"
        assert run.input == parameters
        assert snapshot.launch_parameters == parameters
        serialized_snapshot = json.dumps(
            {
                "packageDefinition": snapshot.package_definition,
                "compiledPlan": snapshot.compiled_plan,
            },
            sort_keys=True,
        )

    assert "signaldeck.digital_oracle.macro_rates.lookup" in serialized_snapshot
    assert "web_research" in serialized_snapshot
    assert "ticker" in serialized_snapshot
    assert "secSubmissionsUrl" in serialized_snapshot


def test_run_queue_stale_lease_recovery_frees_serial_worker_lane(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="stale_lease_worker_lane_package")
    launch_payload = {"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}}
    first = client.post(f"/api/workflow-packages/{created['id']}/launches", json=launch_payload)
    second = client.post(f"/api/workflow-packages/{created['id']}/launches", json=launch_payload)
    assert first.status_code == 201, first.json()
    assert second.status_code == 201, second.json()
    first_run_id = int(first.json()["id"])
    second_run_id = int(second.json()["id"])

    first_worker = scheduler_lease_owner(hostname="test-host", pid=100, slot=1)
    second_worker = scheduler_lease_owner(hostname="test-host", pid=100, slot=2)

    with session_factory() as session:
        claimed_id = RunQueueService(
            session,
            session_factory,
            lease_owner=first_worker,
            lease_ttl_seconds=1.0,
        ).claim_next_run()
        assert claimed_id == first_run_id

    expired_at = utcnow() - timedelta(seconds=5)
    with session_factory() as session:
        blocked = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).claim_next_run()
        assert blocked is None
        running = session.get(Run, first_run_id)
        assert running is not None
        running.lease_expires_at = expired_at
        running.heartbeat_at = expired_at
        session.commit()

    recovered_at = utcnow()
    with session_factory() as session:
        recovered = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).recover_stale_leases(now=recovered_at)
        assert recovered == 1

    with session_factory() as session:
        next_claim = RunQueueService(
            session,
            session_factory,
            lease_owner=second_worker,
        ).claim_next_run()
        assert next_claim == second_run_id
        recovered_run = session.get(Run, first_run_id)
        assert recovered_run is not None
        assert recovered_run.status == "failed"
        assert recovered_run.lease_owner is None
        assert "scheduler lease expired" in str(recovered_run.error)


def test_stale_recovered_run_cannot_be_finalized_by_expired_executor(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    started = Event()
    resume = Event()

    class _BlockingRuntimeOpenAIClient(_RuntimeRecordingOpenAIClient):
        @override
        def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
            type(self).create_calls.append(kwargs)
            started.set()
            assert resume.wait(timeout=3.0)
            return _RuntimeOpenAIResponse(
                output_text='{"summary": "expired executor output"}',
                total_tokens=type(self).total_tokens,
            )

    _BlockingRuntimeOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _BlockingRuntimeOpenAIClient)
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="stale_terminal_write_package")
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    worker = scheduler_lease_owner(hostname="test-host", pid=101, slot=1)
    recovery_worker = scheduler_lease_owner(hostname="test-host", pid=102, slot=1)

    with session_factory() as session:
        claimed_id = RunQueueService(
            session,
            session_factory,
            lease_owner=worker,
            lease_ttl_seconds=0.1,
        ).claim_next_run()
        assert claimed_id == run_id

    def execute_stale_worker() -> None:
        with session_factory() as session:
            RunService(session, session_factory).execute_claimed_run(run_id, lease_owner=worker)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(execute_stale_worker)
        assert started.wait(timeout=3.0)
        expired_at = utcnow() - timedelta(seconds=5)
        with session_factory() as session:
            run = session.get(Run, run_id)
            assert run is not None
            run.lease_expires_at = expired_at
            run.heartbeat_at = expired_at
            session.commit()
        with session_factory() as session:
            recovered = RunQueueService(
                session,
                session_factory,
                lease_owner=recovery_worker,
            ).recover_stale_leases(now=utcnow())
            assert recovered == 1
        resume.set()
        future.result(timeout=3.0)

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.final_output is None
        assert run.lease_owner is None
        assert "scheduler lease expired" in str(run.error)


def test_runtime_input_registry_endpoints_are_removed_from_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.json()
    openapi = cast(dict[str, Any], response.json())
    paths = cast(dict[str, dict[str, Any]], openapi["paths"])

    registry_path = "/api/workflow-packages/{package_id}/runtime-input-registry"
    presets_path = "/api/workflow-packages/{package_id}/runtime-input-registry/presets"
    presets_item_path = f"{presets_path}/{{entry_id}}"
    assert registry_path not in paths
    assert presets_path not in paths
    assert presets_item_path not in paths


def test_workflow_package_read_contract_is_artifact_inventory_and_launch_keeps_live_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_read_contract_package")
    package_id = cast(int, created["id"])

    detail = client.get(f"/api/workflow-packages/{package_id}")
    assert detail.status_code == 200, detail.json()
    detail_body = cast(dict[str, object], detail.json())
    _assert_package_read_is_artifact_inventory(detail_body)

    package_list = client.get("/api/workflow-packages")
    assert package_list.status_code == 200, package_list.json()
    list_body = cast(dict[str, object], package_list.json())
    items = cast(list[dict[str, object]], list_body["items"])
    [listed] = [item for item in items if item["id"] == package_id]
    _assert_package_read_is_artifact_inventory(listed)

    launch = client.get(
        f"/api/workflow-packages/{package_id}/launch",
        params={"workflowKey": "runtime_workflow"},
    )
    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert {"ready", "blockingErrors", "warnings"} <= set(launch_body)

    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert {"ready", "blockingErrors", "warnings"} <= set(preflight_body)


def test_workflow_package_launch_rejects_unknown_root_parameter_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_unknown_root_package")

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "unexpected": True},
        },
    )
    assert preflight.status_code == 200, preflight.json()
    preflight_body = preflight.json()
    assert preflight_body["ready"] is False
    assert preflight_body["blockingErrors"] == [
        {"field": "unexpected", "issue": "Extra inputs are not permitted"}
    ]

    response = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "unexpected": True},
        },
    )

    assert response.status_code == 400, response.json()
    body = response.json()
    assert body["code"] == "run_invalid_input"
    assert body["details"] == [{"field": "unexpected", "issue": "Extra inputs are not permitted"}]
    with session_factory() as session:
        assert session.query(Run).count() == 0


def test_workflow_package_launch_rejects_unknown_nested_parameter_key(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    original_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    nested_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "          context:\n"
        "            type: object\n"
        "            properties:\n"
        "              sector:\n"
        "                type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    manifest_source = _package_source(package_key="runtime_unknown_nested_package").replace(
        original_input_schema,
        nested_input_schema,
        1,
    )
    created_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert created_response.status_code == 201, created_response.json()
    created = cast(dict[str, object], created_response.json())

    preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {
                "ticker": "MSFT",
                "context": {"sector": "semiconductors", "unexpected": True},
            },
        },
    )
    assert preflight.status_code == 200, preflight.json()
    preflight_body = preflight.json()
    assert preflight_body["ready"] is False
    assert preflight_body["blockingErrors"] == [
        {"field": "context.unexpected", "issue": "Extra inputs are not permitted"}
    ]

    response = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {
                "ticker": "MSFT",
                "context": {"sector": "semiconductors", "unexpected": True},
            },
        },
    )

    assert response.status_code == 400, response.json()
    body = response.json()
    assert body["code"] == "run_invalid_input"
    assert body["details"] == [
        {"field": "context.unexpected", "issue": "Extra inputs are not permitted"}
    ]
    with session_factory() as session:
        assert session.query(Run).count() == 0


def test_workflow_package_preflight_rejects_typed_parameter_errors_before_launch(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_runtime_input_default(
            package_key="runtime_preflight_invalid_typed_package"
        ),
    )
    package_id = cast(int, created["id"])

    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "horizonDays": "soon"},
        },
    )

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    details_by_field = {detail["field"]: detail["issue"] for detail in body["blockingErrors"]}
    assert "valid integer" in details_by_field["horizonDays"]
    with session_factory() as session:
        assert session.query(Run).count() == 0


def test_workflow_package_launch_executes_with_live_model_connection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package live runtime output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    gateway_calls: list[str] = []
    original_gateway_invoke = ModelExecutionGateway.invoke

    def _recording_gateway_invoke(
        self: ModelExecutionGateway,
        request: Any,
        *,
        tool_executor: Any,
    ) -> Any:
        gateway_calls.append(request.agent_key)
        return original_gateway_invoke(self, request, tool_executor=tool_executor)

    monkeypatch.setattr(
        "app.services.model_gateway.ModelExecutionGateway.invoke",
        _recording_gateway_invoke,
    )

    _seed_model_connection(session_factory)
    created = _create_package(client)
    package_id = cast(int, created["id"])

    with session_factory() as session:
        package_before_launch = session.get(WorkflowPackage, package_id)
        assert package_before_launch is not None
        package_updated_at_before_launch = package_before_launch.updated_at
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://model-gateway.example.com/v1"
        connection.model_id = "gpt-package-v2"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "test-api-key-rotated"}
        session.commit()

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        package_after_launch = session.get(WorkflowPackage, package_id)
        assert package_after_launch is not None
        assert package_after_launch.updated_at == package_updated_at_before_launch
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert snapshot is not None
        assert snapshot.workflow_package_key == "runtime_package"
        assert snapshot.workflow_key == "runtime_workflow"
        assert snapshot.launch_parameters == {"ticker": "MSFT"}

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["targetKind"] == "workflowPackage"
    assert detail["targetId"] == created["id"]
    assert detail["targetKey"] == "runtime_package"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert set(provenance) == _schema_aliases(RunPackageProvenanceRead)
    assert provenance["workflowPackageKey"] == "runtime_package"
    assert provenance["workflowKey"] == "runtime_workflow"
    assert provenance["launchSnapshot"]["parameters"] == {"ticker": "MSFT"}
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert set(invocation) == _schema_aliases(RunAgentInvocationRead)
    assert invocation["agentRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "package_analyst",
        "version": 1,
    }
    assert invocation["outputSchemaRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "summary_output",
        "version": 1,
    }
    assert detail["finalOutput"] == {"summary": "package live runtime output"}
    assert detail["executedTokens"] == 23
    assert gateway_calls == ["package_analyst"]
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["usage"] == {"totalTokens": 23}
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "enabled",
        "reasoningEffort": "low",
        "streamingStrategy": "disabled",
    }
    init_call = _RuntimeRecordingOpenAIClient.init_calls[-1]
    assert init_call["api_key"] == "test-api-key-rotated"
    assert init_call["base_url"] == "https://model-gateway.example.com/v1"
    assert init_call["timeout"] == 91.0
    create_call = _RuntimeRecordingOpenAIClient.create_calls[-1]
    assert create_call["model"] == "gpt-package-v2"
    assert create_call["reasoning"]["effort"] == "low"

    with session_factory() as session:
        run = session.get(Run, run_id)
        assert run is not None
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert snapshot is not None
        assert run.workflow_package_key == "runtime_package"
        assert run.workflow_package_workflow_key == "runtime_workflow"
        assert snapshot.manifest_hash == package.manifest_hash
        assert snapshot.compiled_hash == package.compiled_hash
        assert snapshot.workflow_key == "runtime_workflow"
        assert snapshot.launch_parameters == {"ticker": "MSFT"}
        assert snapshot.resolved_model_connections[0]["modelId"] == "gpt-package-v2"
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert invocation.agent_id == 1
        assert invocation.agent_key == "package_analyst"
        assert invocation.output_schema_id == 1
        assert invocation.output == {"summary": "package live runtime output"}


def test_workflow_package_runtime_strict_json_schema_strategy_sends_native_schema(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "strict schema output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_strict_schema_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "strict schema output"}
    text_format = _RuntimeRecordingOpenAIClient.create_calls[-1]["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    assert text_format["schema"]["properties"]["summary"]["type"] == "string"


def test_workflow_package_runtime_strict_json_schema_invalid_json_retries_twice_and_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        "not json",
        '{"notSummary": "invalid"}',
        '{"summary": "strict corrected output"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_strict_schema_retry_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "strict corrected output"}
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 3
    for create_call in _RuntimeRecordingOpenAIClient.create_calls:
        text_format = create_call["text"]["format"]
        assert text_format["type"] == "json_schema"
        assert text_format["strict"] is True
    first_retry_input = _RuntimeRecordingOpenAIClient.create_calls[1]["input"]
    second_retry_input = _RuntimeRecordingOpenAIClient.create_calls[2]["input"]
    assert "JSON/schema validation" in first_retry_input
    assert "Response body is not valid JSON" in first_retry_input
    assert "summary" in second_retry_input
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"]["outputStrategy"] == "strictJsonSchema"
    assert "providerRetries" not in gateway_metadata


def test_workflow_package_runtime_strict_json_schema_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        "not json",
        '{"notSummary": "invalid"}',
        '{"stillWrong": "invalid"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_strict_schema_exhausted_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "model_output_retry_exhausted"
    assert invocation["errorDetails"][0]["field"] == "summary"
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 3
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"]["outputStrategy"] == "strictJsonSchema"
    assert "providerRetries" not in gateway_metadata


def test_workflow_package_runtime_forbidden_reasoning_and_streaming_policies_record_metadata(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "policy output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        reasoning_policy="forbid",
        streaming_policy="forbid",
    )
    created = _create_package(client, package_key="runtime_policy_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "disabledByPolicy",
        "streamingStrategy": "disabledByPolicy",
    }
    assert gateway_metadata["usage"] == {"totalTokens": 23}
    assert "reasoning" not in _RuntimeRecordingOpenAIClient.create_calls[-1]
    assert detail["finalOutput"] == {"summary": "policy output"}


def test_workflow_package_runtime_reasoning_unsupported_is_normalized_before_provider_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeReasoningRejectingChatClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeReasoningRejectingChatClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        capabilities={
            "reasoningHints": {"status": "unsupported"},
        },
    )
    created = _create_package(client, package_key="runtime_reasoning_unsupported_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_reasoning_unsupported"
    assert invocation["errorDetails"][0]["field"] == "reasoningHints"
    assert _RuntimeReasoningRejectingChatClient.create_calls == []


def test_workflow_package_runtime_missing_usage_metadata_stays_secret_safe_and_successful(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeUsageLessResponsesClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeUsageLessResponsesClient)

    _seed_model_connection(session_factory)
    created = _create_package(client, package_key="runtime_usage_missing_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "usage omitted"}
    assert detail["executedTokens"] == 0
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["usage"] == {"totalTokens": 0}
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "enabled",
        "reasoningEffort": "high",
        "streamingStrategy": "disabled",
    }


def test_workflow_package_runtime_json_object_validation_retries_and_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        '{"notSummary": "invalid"}',
        '{"summary": "json fallback corrected output"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "unsupported"},
            "jsonObjectOutput": {"status": "supported"},
        },
        output_strategy_policy="allow_json_object_validation",
    )
    created = _create_package(client, package_key="runtime_json_validation_retry_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "json fallback corrected output"}
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 2
    first_create_call = _RuntimeRecordingOpenAIClient.create_calls[0]
    assert first_create_call["text"]["format"]["type"] == "json_object"
    assert "JSON/schema validation" in _RuntimeRecordingOpenAIClient.create_calls[1]["input"]


def test_workflow_package_runtime_json_object_validation_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_texts = [
        '{"notSummary": "invalid"}',
        '{"stillWrong": "invalid"}',
        '{"wrongAgain": "invalid"}',
    ]
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        capabilities={
            "strictJsonSchemaOutput": {"status": "unsupported"},
            "jsonObjectOutput": {"status": "supported"},
        },
        output_strategy_policy="allow_json_object_validation",
    )
    created = _create_package(client, package_key="runtime_json_validation_exhausted_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "model_output_retry_exhausted"
    assert invocation["errorDetails"][0]["field"] == "summary"
    assert (
        cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]["selectedStrategies"][
            "outputStrategy"
        ]
        == "jsonObjectWithValidation"
    )
    assert len(_RuntimeRecordingOpenAIClient.create_calls) == 3


def test_workflow_package_runtime_chat_completions_adapter_executes_tool_calls_and_usage(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.reasoning_content = "preserved thinking trace"
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        model_id="chat-runtime-model",
        api_style="chat_completions",
    )
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(package_key="runtime_chat_tool_package"),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded", detail
    assert detail["finalOutput"] == {"summary": "package chat runtime output"}
    assert detail["executedTokens"] == 28
    init_call = _RuntimeRecordingChatCompletionsClient.init_calls[-1]
    assert init_call["api_key"] == "test-api-key"
    assert init_call["base_url"] == "https://provider-runtime.example.test/v1"
    assert init_call["timeout"] == 31.0
    assert init_call["max_retries"] == 0
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 2

    first_call = _RuntimeRecordingChatCompletionsClient.create_calls[0]
    assert first_call["model"] == "chat-runtime-model"
    assert first_call["reasoning_effort"] == "high"
    assert first_call["messages"][0]["role"] == "system"
    assert first_call["messages"][1]["role"] == "user"
    assert first_call["response_format"]["type"] == "json_schema"
    assert first_call["parallel_tool_calls"] is False
    tool_names = [tool["function"]["name"] for tool in first_call["tools"]]
    assert "signaldeck_finance_reports_lookup" in tool_names

    second_call = _RuntimeRecordingChatCompletionsClient.create_calls[1]
    assistant_message = second_call["messages"][-2]
    tool_message = second_call["messages"][-1]
    assert assistant_message["role"] == "assistant"
    assert assistant_message["reasoning_content"] == "preserved thinking trace"
    assert assistant_message["tool_calls"] == [
        {
            "id": "call_report_lookup",
            "type": "function",
            "function": {
                "name": "signaldeck_finance_reports_lookup",
                "arguments": _RuntimeRecordingChatCompletionsClient._report_lookup_arguments(),
            },
        }
    ]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_report_lookup"
    tool_payload = json.loads(tool_message["content"])
    assert tool_payload["count"] == 0
    assert tool_payload["reports"] == []
    assert tool_payload["count"] == 0

    with session_factory() as session:
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run_id).one()
        assert invocation.status == "succeeded"
        assert invocation.tokens == 28
        assert invocation.output == {"summary": "package chat runtime output"}
        gateway_metadata = cast(dict[str, Any], invocation.graph_metadata)["modelGateway"]
        assert gateway_metadata["usage"] == {
            "inputTokens": 18,
            "outputTokens": 10,
            "totalTokens": 28,
        }
        assert gateway_metadata["selectedStrategies"] == {
            "outputStrategy": "strictJsonSchema",
            "toolCallStrategy": "serialize",
            "parallelToolCalls": False,
            "reasoningStrategy": "enabled",
            "reasoningEffort": "high",
            "streamingStrategy": "disabled",
        }
        assert "providerRetries" not in gateway_metadata


def test_workflow_package_runtime_chat_strict_json_schema_invalid_json_retries_twice_and_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = []
    _RuntimeRecordingChatCompletionsClient.final_output_texts = [
        "not json",
        '{"notSummary": "invalid"}',
        '{"summary": "chat strict corrected output"}',
    ]
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_chat_strict_schema_retry_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat strict corrected output"}
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    for create_call in _RuntimeRecordingChatCompletionsClient.create_calls:
        assert create_call["response_format"]["type"] == "json_schema"
    first_retry_messages = _RuntimeRecordingChatCompletionsClient.create_calls[1]["messages"]
    assert first_retry_messages[-2] == {"role": "assistant", "content": "not json"}
    assert "JSON/schema validation" in first_retry_messages[-1]["content"]
    assert "Response body is not valid JSON" in first_retry_messages[-1]["content"]
    second_retry_messages = _RuntimeRecordingChatCompletionsClient.create_calls[2]["messages"]
    assert "summary" in second_retry_messages[-1]["content"]
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"]["outputStrategy"] == "strictJsonSchema"
    assert "providerRetries" not in gateway_metadata


def test_workflow_package_runtime_chat_strict_json_schema_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = []
    _RuntimeRecordingChatCompletionsClient.final_output_texts = [
        "not json",
        '{"notSummary": "invalid"}',
        '{"stillWrong": "invalid"}',
    ]
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        capabilities={
            "strictJsonSchemaOutput": {"status": "supported"},
            "jsonObjectOutput": {"status": "unsupported"},
        },
        output_strategy_policy="require_strict_schema",
    )
    created = _create_package(client, package_key="runtime_chat_strict_schema_exhausted_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "model_output_retry_exhausted"
    assert invocation["errorDetails"][0]["field"] == "summary"
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["selectedStrategies"]["outputStrategy"] == "strictJsonSchema"
    assert "providerRetries" not in gateway_metadata


def test_workflow_package_runtime_chat_provider_retry_records_providerRetries_modelGateway(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.failures = [_provider_status_error(503)]
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = []
    _RuntimeRecordingChatCompletionsClient.final_output_text = (
        '{"summary": "chat provider retry output"}'
    )
    jitter_bounds: list[tuple[int, int]] = []

    def jitter_random_int(lower: int, upper: int) -> int:
        jitter_bounds.append((lower, upper))
        assert (lower, upper) == (0, 500)
        return 137

    monkeypatch.setattr(
        "app.services.model_gateway_openai.time.sleep",
        lambda _: None,
    )
    monkeypatch.setattr(
        "app.services.model_gateway_openai.random.randint",
        jitter_random_int,
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package(client, package_key="runtime_chat_provider_retry_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat provider retry output"}
    assert detail["executedTokens"] == 19
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 2
    init_call = _RuntimeRecordingChatCompletionsClient.init_calls[-1]
    assert init_call["api_key"] == "test-api-key"
    assert init_call["base_url"] == "https://provider-runtime.example.test/v1"
    assert init_call["timeout"] == 31.0
    assert init_call["max_retries"] == 0
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["usage"] == {
        "inputTokens": 11,
        "outputTokens": 8,
        "totalTokens": 19,
    }
    assert gateway_metadata["selectedStrategies"] == {
        "outputStrategy": "strictJsonSchema",
        "toolCallStrategy": "none",
        "parallelToolCalls": False,
        "reasoningStrategy": "enabled",
        "reasoningEffort": "high",
        "streamingStrategy": "disabled",
    }
    assert gateway_metadata["providerRetries"] == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 137,
            }
        ],
        "terminalOutcome": "succeededAfterRetry",
    }
    assert jitter_bounds == [(0, 500)]
    assert "toolCallRetries" not in gateway_metadata


def test_model_gateway_user_agent_reads_backend_version_file(tmp_path: Path) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("9.8.7\n", encoding="utf-8")

    assert _build_openai_compatible_user_agent(version_file) == "SignalDeck/9.8.7"


def test_model_gateway_user_agent_uses_fallback_when_version_file_is_missing(
    tmp_path: Path,
) -> None:
    assert _build_openai_compatible_user_agent(tmp_path / "missing") == "SignalDeck/0.1.0"


def test_model_gateway_connection_test_sets_signaldeck_user_agent_header() -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    gateway = ModelExecutionGateway(client_factory=_RuntimeRecordingChatCompletionsClient)

    result = gateway.test_connection(
        ModelConnectionTestRequest(
            connection=_chat_model_gateway_connection_config(),
            instructions="Reply with the single word OK.",
            input_text="Connection test.",
        )
    )

    assert result.ok is True
    init_call = _RuntimeRecordingChatCompletionsClient.init_calls[-1]
    assert init_call["default_headers"] == {"User-Agent": OPENAI_COMPATIBLE_USER_AGENT}
    assert init_call["api_key"] == "test-api-key"
    assert init_call["base_url"] == "https://provider-runtime.example.test/v1"
    assert init_call["timeout"] == 31.0
    assert init_call["max_retries"] == 0


def test_model_gateway_connection_test_chat_provider_retry_free_with_max_retries_zero() -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.failures = [_provider_status_error(503)]
    gateway = ModelExecutionGateway(client_factory=_RuntimeRecordingChatCompletionsClient)

    result = gateway.test_connection(
        ModelConnectionTestRequest(
            connection=_chat_model_gateway_connection_config(),
            instructions="Reply with the single word OK.",
            input_text="Connection test.",
        )
    )

    assert result.ok is False
    assert result.message == "provider said no"
    assert _RuntimeRecordingChatCompletionsClient.init_calls[-1]["max_retries"] == 0
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 1


def test_model_gateway_capability_probe_chat_provider_retry_free_with_max_retries_zero() -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.failures = [_provider_status_error(503)]
    gateway = ModelExecutionGateway(client_factory=_RuntimeRecordingChatCompletionsClient)

    result = gateway.probe_capabilities(
        ModelCapabilityProbeRequest(
            connection=_chat_model_gateway_connection_config(),
            capability_keys=("text_generation", "usage_reporting"),
        )
    )

    assert _RuntimeRecordingChatCompletionsClient.init_calls[-1]["max_retries"] == 0
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 1
    assert result.capabilities["text_generation"].status == "unknown"
    assert result.capabilities["usage_reporting"].status == "unknown"
    assert "provider said no" in cast(str, result.capabilities["text_generation"].detail)
    assert "provider said no" in cast(str, result.capabilities["usage_reporting"].detail)


def test_provider_retry_policy_classifies_retryable_provider_failures() -> None:
    policy = ProviderRetryPolicy()

    assert (
        _call_with_provider_retry(
            lambda: "provider seam ready",
            policy=policy,
            recorder=ProviderRetryRecorder(policy=policy),
        )
        == "provider seam ready"
    )

    retryable_failures = (
        openai.APITimeoutError(request=_provider_retry_request()),
        openai.APIConnectionError(request=_provider_retry_request()),
        _provider_status_error(408),
        _provider_status_error(409),
        _provider_status_error(429),
        _provider_status_error(500),
        _provider_status_error(503),
    )

    for failure in retryable_failures:
        assert policy.is_retryable(failure) is True


def test_provider_retry_policy_rejects_non_retryable_failures() -> None:
    policy = ProviderRetryPolicy()

    non_retryable_failures = (
        _provider_status_error(400),
        _provider_status_error(401),
        _provider_status_error(403),
        _provider_status_error(404),
        _provider_status_error(422),
        validation_error("Runtime input validation failed"),
        ModelGatewayError(
            code="agent_model_connection_api_key_missing",
            message="Model connection API key is required.",
        ),
        ModelGatewayError(
            code="agent_model_connection_api_style_unsupported",
            message="Model connection uses unsupported API style.",
        ),
    )

    for failure in non_retryable_failures:
        assert policy.is_retryable(failure) is False


def test_provider_retry_after_honors_only_allowed_statuses() -> None:
    policy = ProviderRetryPolicy()

    assert (
        policy.retry_after_delay_ms(_provider_status_error(429, headers={"retry-after": "3"}))
        == 3000
    )
    assert (
        policy.retry_after_delay_ms(_provider_status_error(503, headers={"retry-after-ms": "2500"}))
        == 2500
    )
    assert (
        policy.retry_after_delay_ms(_provider_status_error(503, headers={"retry-after": "10"}))
        == 10000
    )
    assert (
        policy.retry_after_delay_ms(_provider_status_error(429, headers={"retry-after": "10.1"}))
        is None
    )
    assert (
        policy.retry_after_delay_ms(_provider_status_error(500, headers={"retry-after": "3"}))
        is None
    )
    assert (
        policy.retry_after_delay_ms(_provider_status_error(429, headers={"retry-after": "0"}))
        is None
    )


def test_provider_retry_helper_retries_with_full_jitter_and_retry_after() -> None:
    failures = iter(
        [
            _provider_status_error(503),
            _provider_status_error(429, headers={"retry-after": "9"}),
        ]
    )
    recorder = ProviderRetryRecorder(policy=ProviderRetryPolicy())
    sleep_calls: list[float] = []
    jitter_bounds: list[tuple[int, int]] = []
    create_calls = 0

    def operation() -> str:
        nonlocal create_calls
        create_calls += 1
        failure = next(failures, None)
        if failure is not None:
            raise failure
        return "provider recovered"

    def jitter_random_int(lower: int, upper: int) -> int:
        jitter_bounds.append((lower, upper))
        assert (lower, upper) == (0, 500)
        return 137

    assert (
        _call_with_provider_retry(
            operation,
            recorder=recorder,
            sleep=sleep_calls.append,
            random_int=jitter_random_int,
        )
        == "provider recovered"
    )
    assert create_calls == 3
    assert jitter_bounds == [(0, 500)]
    assert sleep_calls == [0.137, 9.0]
    assert recorder.success_metadata() == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 137,
            },
            {
                "attempt": 2,
                "outcome": "retryAfterHonored",
                "errorCode": "agent_provider_status_error",
                "statusCode": 429,
                "failureClass": "provider_transport",
                "delayMs": 9000,
            },
        ],
        "terminalOutcome": "succeededAfterRetry",
    }


def test_provider_retry_helper_exhausts_after_max_attempts() -> None:
    recorder = ProviderRetryRecorder(policy=ProviderRetryPolicy())
    sleep_calls: list[float] = []
    jitter_bounds: list[tuple[int, int]] = []
    create_calls = 0

    def operation() -> str:
        nonlocal create_calls
        create_calls += 1
        raise _provider_status_error(503)

    def jitter_random_int(lower: int, upper: int) -> int:
        jitter_bounds.append((lower, upper))
        return {500: 137, 1000: 911}[upper]

    with pytest.raises(openai.APIStatusError):
        _call_with_provider_retry(
            operation,
            recorder=recorder,
            sleep=sleep_calls.append,
            random_int=jitter_random_int,
        )

    assert create_calls == 3
    assert jitter_bounds == [(0, 500), (0, 1000)]
    assert sleep_calls == [0.137, 0.911]
    assert recorder.exhausted_metadata() == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 137,
            },
            {
                "attempt": 2,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 911,
            },
            {
                "attempt": 3,
                "outcome": "exhausted",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
            },
        ],
        "terminalOutcome": "exhausted",
    }


def test_provider_retry_metadata_contract_success_after_retry_records_failed_attempts() -> None:
    policy = ProviderRetryPolicy()
    recorder = ProviderRetryRecorder(policy=policy)

    assert recorder.success_metadata() is None
    success_without_retries = ModelExecutionResult(
        output={"summary": "ok"},
        provider_retry_metadata=recorder.success_metadata(),
    )
    assert "providerRetries" not in success_without_retries.runtime_metadata()

    assert ProviderRetryAttempt(
        attempt=1,
        outcome="retryScheduled",
        error_code="agent_provider_status_error",
        status_code=503,
        failure_class="provider_transport",
        delay_ms=417,
    ).to_metadata() == {
        "attempt": 1,
        "outcome": "retryScheduled",
        "errorCode": "agent_provider_status_error",
        "statusCode": 503,
        "failureClass": "provider_transport",
        "delayMs": 417,
    }

    recorder.record_retry(_provider_status_error(503), delay_ms=417)
    recorder.record_retry(
        _provider_status_error(429, headers={"retry-after": "9"}),
        delay_ms=9000,
        retry_after_honored=True,
    )

    metadata = recorder.success_metadata()
    assert metadata == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 417,
            },
            {
                "attempt": 2,
                "outcome": "retryAfterHonored",
                "errorCode": "agent_provider_status_error",
                "statusCode": 429,
                "failureClass": "provider_transport",
                "delayMs": 9000,
            },
        ],
        "terminalOutcome": "succeededAfterRetry",
    }

    result = ModelExecutionResult(
        output={"summary": "ok"},
        tool_retry_metadata={
            "attemptsUsed": 1,
            "maxAttempts": 1,
            "failures": [{"code": "x"}],
        },
        provider_retry_metadata=metadata,
    )
    gateway_metadata = result.runtime_metadata()

    assert gateway_metadata["providerRetries"] == metadata
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert "exhausted" not in gateway_metadata["providerRetries"]
    assert len(gateway_metadata["providerRetries"]["attempts"]) == 2


def test_provider_retry_metadata_contract_exhaustion_and_non_retryable_omission() -> None:
    policy = ProviderRetryPolicy()

    first_non_retryable_failure = ModelGatewayError(
        code="agent_model_connection_api_key_missing",
        message="Model connection API key is required.",
    )
    assert policy.is_retryable(first_non_retryable_failure) is False
    assert "providerRetries" not in first_non_retryable_failure.runtime_metadata()

    recorder = ProviderRetryRecorder(policy=policy)
    recorder.record_retry(
        openai.APITimeoutError(request=_provider_retry_request()),
        delay_ms=250,
    )
    recorder.record_exhausted(openai.APIConnectionError(request=_provider_retry_request()))
    metadata = recorder.exhausted_metadata()
    assert metadata == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_timeout",
                "failureClass": "provider_network",
                "delayMs": 250,
            },
            {
                "attempt": 2,
                "outcome": "exhausted",
                "errorCode": "agent_provider_connection_error",
                "failureClass": "provider_network",
            },
        ],
        "terminalOutcome": "exhausted",
    }

    exhausted_failure = ModelGatewayError(
        code="agent_provider_connection_error",
        message="OpenAI request could not reach the API.",
        provider_retry_metadata=metadata,
    )
    gateway_metadata = exhausted_failure.runtime_metadata()

    assert gateway_metadata["providerRetries"] == metadata
    assert gateway_metadata["providerRetries"]["terminalOutcome"] == "exhausted"
    assert gateway_metadata["providerRetries"]["attempts"][-1]["outcome"] == "exhausted"
    assert "exhausted" not in gateway_metadata["providerRetries"]


def test_workflow_package_runtime_chat_tool_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = [
        "{",
        _RuntimeRecordingChatCompletionsClient._report_lookup_arguments(),
    ]
    _RuntimeRecordingChatCompletionsClient.final_output_text = (
        '{"summary": "chat parser retry output"}'
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_chat_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "chat parser retry output"}
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    retry_prompt = _RuntimeRecordingChatCompletionsClient.create_calls[1]["messages"][-1]
    assert retry_prompt["role"] == "user"
    assert "toolCallRetry" in retry_prompt["content"]
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["maxAttempts"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is False
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    assert retry_failure["failureTaxonomy"]["retryable"] is True


def test_workflow_package_runtime_native_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    invalid_arguments = json.loads(
        _RuntimeRecordingChatCompletionsClient._report_lookup_arguments()
    )
    invalid_arguments["limit"] = 0
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = [
        json.dumps(invalid_arguments, sort_keys=True),
        _RuntimeRecordingChatCompletionsClient._report_lookup_arguments(),
    ]
    _RuntimeRecordingChatCompletionsClient.final_output_text = (
        '{"summary": "native parser retry output"}'
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_native_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "native parser retry output"}
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 3
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == ("native_tool_argument_validation")
    assert retry_failure["toolName"] == "signaldeck_finance_reports_lookup"


def test_workflow_package_runtime_chat_tool_parser_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.tool_argument_sequence = ["{", "{"]
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_chat_malformed_tool_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_tool_call_retry_exhausted"
    assert invocation["errorDetails"][0]["lastFailureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["failureTaxonomy"]["failureClass"] == "retry_bound_exhausted"
    assert gateway_metadata["failureTaxonomy"]["retryable"] is False
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is True
    assert len(_RuntimeRecordingChatCompletionsClient.create_calls) == 2


def test_workflow_package_runtime_responses_provider_retry_records_providerRetries_modelGateway(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeProviderRetryingResponsesClient.reset()
    jitter_bounds: list[tuple[int, int]] = []

    def jitter_random_int(lower: int, upper: int) -> int:
        jitter_bounds.append((lower, upper))
        assert (lower, upper) == (0, 500)
        return 137

    monkeypatch.setattr(
        "app.services.model_gateway_openai.time.sleep",
        lambda _: None,
    )
    monkeypatch.setattr(
        "app.services.model_gateway_openai.random.randint",
        jitter_random_int,
    )
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeProviderRetryingResponsesClient,
    )

    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_responses_provider_retry_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "responses provider retry output"}
    assert len(_RuntimeProviderRetryingResponsesClient.create_calls) == 3
    init_call = _RuntimeProviderRetryingResponsesClient.init_calls[-1]
    assert init_call["api_key"] == "test-api-key"
    assert init_call["base_url"] == "https://provider-runtime.example.test/v1"
    assert init_call["timeout"] == 31.0
    assert init_call["max_retries"] == 0
    second_call = _RuntimeProviderRetryingResponsesClient.create_calls[1]
    third_call = _RuntimeProviderRetryingResponsesClient.create_calls[2]
    assert "previous_response_id" not in second_call
    assert "previous_response_id" not in third_call
    assert second_call["input"] == third_call["input"]
    assert second_call["input"][0]["type"] == "function_call"
    assert second_call["input"][1]["type"] == "function_call_output"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["providerRetries"] == {
        "policy": "transientProviderRetry/v1",
        "maxAttempts": 3,
        "attempts": [
            {
                "attempt": 1,
                "outcome": "retryScheduled",
                "errorCode": "agent_provider_status_error",
                "statusCode": 503,
                "failureClass": "provider_transport",
                "delayMs": 137,
            }
        ],
        "terminalOutcome": "succeededAfterRetry",
    }
    assert "toolCallRetries" not in gateway_metadata
    assert jitter_bounds == [(0, 500)]


def test_workflow_package_runtime_responses_tool_parser_retry_success_records_accounting(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRetryingResponsesToolClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRetryingResponsesToolClient,
    )

    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_responses_parser_retry_success_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "responses retry output"}
    assert len(_RuntimeRetryingResponsesToolClient.create_calls) == 3
    retry_input = _RuntimeRetryingResponsesToolClient.create_calls[1]["input"]
    assert isinstance(retry_input, str)
    assert "toolCallRetry" in retry_input
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    retry_failure = gateway_metadata["toolCallRetries"]["failures"][0]
    assert retry_failure["failureTaxonomy"]["failureClass"] == (
        "provider_tool_argument_json_invalid"
    )


def test_workflow_package_runtime_responses_tool_parser_retry_exhaustion_fails_stably(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeMalformedResponsesToolClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeMalformedResponsesToolClient,
    )

    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_responses_malformed_tool_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["errorCode"] == "model_tool_call_retry_exhausted"
    assert invocation["errorDetails"][0]["lastFailureClass"] == (
        "provider_tool_argument_json_invalid"
    )
    gateway_metadata = cast(dict[str, Any], invocation["graphMetadata"])["modelGateway"]
    assert gateway_metadata["failureTaxonomy"]["failureClass"] == "retry_bound_exhausted"
    assert gateway_metadata["toolCallRetries"]["attemptsUsed"] == 1
    assert gateway_metadata["toolCallRetries"]["exhausted"] is True
    assert len(_RuntimeMalformedResponsesToolClient.create_calls) == 2
    assert _RuntimeMalformedResponsesToolClient.create_calls[0]["parallel_tool_calls"] is False


def test_workflow_package_runtime_tool_policy_forbid_blocks_tool_dependent_package(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(
        session_factory,
        api_style="chat_completions",
        parallel_tool_calls_policy="forbid",
    )
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_report_lookup(
            package_key="runtime_tool_policy_forbid_package"
        ),
    )

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 422, launch.json()
    assert launch.json()["code"] == "validation_error"
    assert launch.json()["message"] == "Workflow package launch validation failed"
    assert {
        "field": "spec.capabilityProfiles.report_context_tools.toolKeys",
        "code": "model_capability_required_missing",
        "agentKey": "package_analyst",
        "modelConnectionKey": "package_runtime_model",
        "requirement": "nativeToolCalls",
        "issue": (
            "This workflow requires native tool calls, but the selected model connection "
            "forbids tool calls."
        ),
    } in launch.json()["details"]
    assert _RuntimeRecordingChatCompletionsClient.create_calls == []


def test_runtime_digital_oracle_toolKeys_dependency_snapshot(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package_from_source(
        client,
        manifest_source=_package_source_with_digital_oracle_phase1_tools(
            package_key="runtime_digital_oracle_dependency_package"
        ),
    )
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"researchQuestion": "Will rates fall this quarter?"},
        },
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200, detail.json()
    dependencies = cast(list[dict[str, object]], detail.json()["extensionDependencies"])
    assert len(dependencies) == 1
    dependency = dependencies[0]
    surfaces = set(cast(list[str], dependency["surfaces"]))
    assert dependency["extensionKey"] == DIGITAL_ORACLE_EXTENSION_KEY
    assert FINANCE_WORKSPACE_EXTENSION_KEY not in json.dumps(dependencies, sort_keys=True)
    assert set(cast(list[str], dependency["fields"])) == {
        f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]"
        for index in range(len(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
    }
    assert surfaces == {
        *[f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
        *[f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
    }


def test_workflow_package_runtime_chat_completions_adapter_normalizes_empty_response_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingChatCompletionsClient.reset()
    _RuntimeRecordingChatCompletionsClient.return_empty_choices = True
    monkeypatch.setattr(
        "app.services.run_service.OpenAI",
        _RuntimeRecordingChatCompletionsClient,
    )

    _seed_model_connection(session_factory, api_style="chat_completions")
    created = _create_package(client, package_key="runtime_chat_empty_response_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "failed"
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "agent_provider_response_empty"
    assert "choice message" in invocation["errorMessage"]
    assert invocation["tokens"] == 0
    assert detail["executedTokens"] == 0


def test_workflow_package_launch_blocks_secretless_provider_without_openai(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    class _UnexpectedOpenAIClient:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            raise AssertionError("OpenAI should not be used before provider API key validation")

    monkeypatch.setattr("app.services.run_service.OpenAI", _UnexpectedOpenAIClient)

    _seed_model_connection(
        session_factory,
        api_key=None,
        base_url="https://provider-key-required.example.test/v1",
        model_id="provider-runtime-model",
        api_style="chat_completions",
    )
    created = _create_package(client, package_key="runtime_provider_key_required_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AMD"}},
    )

    assert launch.status_code == 422, launch.json()
    body = cast(dict[str, Any], launch.json())
    assert body["code"] == "validation_error"
    assert body["details"] == [
        {"field": "spec.agents[0].modelConnection", "issue": "API key is not configured"}
    ]


def test_workflow_package_runtime_without_finance_dependencies_succeeds(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "provider no finance output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)

    _seed_model_connection(
        session_factory,
        base_url="https://provider-core-only.example.test/v1",
        model_id="provider-runtime-model",
    )
    created = _create_package(client, package_key="runtime_core_no_finance_package")
    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "AMD"},
        },
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "provider no finance output"}
    assert detail["extensionDependencies"] == []


def test_workflow_package_validation_redacts_and_reads_omit_inline_private_mcp_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _package_source_with_inline_private_mcp(
        package_key="runtime_private_mcp_projection_package"
    )

    validation = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": manifest_source},
    )
    assert validation.status_code == 200, validation.json()
    validation_body = cast(dict[str, Any], validation.json())
    validation_payload = json.dumps(validation_body, sort_keys=True)
    assert "inline-header-secret" not in validation_payload
    assert "inline-query-secret" not in validation_payload
    assert "[REDACTED]" in validation_payload
    validation_spec = cast(dict[str, Any], validation_body["packageDefinition"])["spec"]
    validation_mcp = cast(list[dict[str, Any]], validation_spec["mcpServers"])[0]
    assert validation_mcp["headers"] == {"Authorization": "[REDACTED]"}
    assert validation_mcp["query"] == {"exaApiKey": "[REDACTED]"}
    compiled_mcp = cast(list[dict[str, Any]], validation_body["compiledPlan"]["mcpServers"])[0]
    assert compiled_mcp["headers"] == {"Authorization": "[REDACTED]"}
    assert compiled_mcp["query"] == {"exaApiKey": "[REDACTED]"}
    descriptor = cast(list[dict[str, Any]], compiled_mcp["toolDescriptors"])[0]
    assert descriptor["ownerExtensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert descriptor["schemaHash"].startswith("sha256:")
    assert descriptor["redactionPolicy"] == "mcp.output.redact_text"

    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={"manifestSource": manifest_source},
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    manifest = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert manifest.status_code == 200, manifest.json()
    manifest_payload = json.dumps(manifest.json(), sort_keys=True)
    assert "headers" not in manifest_payload
    assert "query" not in manifest_payload
    assert "inline-header-secret" not in manifest_payload
    assert "inline-query-secret" not in manifest_payload
    exported = client.get(f"/api/workflow-packages/{package_id}/export")
    assert exported.status_code == 200, exported.text
    assert "headers" not in exported.text
    assert "query" not in exported.text
    assert "inline-header-secret" not in exported.text
    assert "inline-query-secret" not in exported.text


def test_workflow_package_runtime_uses_fake_provider_endpoint(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    request_log: list[dict[str, Any]] = []
    with run_fake_openai_provider(base_path="/codex/v1", request_log=request_log) as base_url:
        _seed_model_connection(session_factory, base_url=base_url)
        created = _create_package(client, package_key="runtime_fake_provider_package")

        launch = client.post(
            f"/api/workflow-packages/{created['id']}/launches",
            json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "NVDA"}},
        )
        assert launch.status_code == 201, launch.json()
        run_id = int(launch.json()["id"])

        _drain_run_queue(session_factory)
        detail = _wait_for_run(client, run_id)

    request_paths = [cast(str, entry["path"]) for entry in request_log]
    assert request_paths == ["/codex/v1/responses"]
    assert "/codex/v1/v1/responses" not in request_paths
    assert "/v1/responses" not in request_paths
    assert not any(path.endswith("/chat/completions") for path in request_paths)

    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "fake strict schema"}
    assert detail["executedTokens"] == 5


def test_workflow_package_runtime_passes_literal_trailing_slash_base_url_to_openai_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "runtime trailing slash output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    literal_base_url = "https://new.sharedchat.cc/codex/v1/"

    _seed_model_connection(session_factory, base_url=literal_base_url)
    created = _create_package(client, package_key="runtime_literal_base_url_package")

    launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "NVDA"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)

    assert detail["status"] == "succeeded"
    init_call = _RuntimeRecordingOpenAIClient.init_calls[-1]
    assert init_call["base_url"] == literal_base_url

    with session_factory() as session:
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert snapshot is not None
        profile = cast(dict[str, Any], snapshot.resolved_model_connections[0])
        assert profile["baseUrl"] == literal_base_url


def test_workflow_package_runtime_openai_style_control_root_avoids_duplicate_v1_path(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    request_log: list[dict[str, Any]] = []
    with run_fake_openai_provider(base_path="/v1", request_log=request_log) as base_url:
        _seed_model_connection(session_factory, base_url=base_url)
        created = _create_package(client, package_key="runtime_openai_style_control_root_package")

        launch = client.post(
            f"/api/workflow-packages/{created['id']}/launches",
            json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "NVDA"}},
        )
        assert launch.status_code == 201, launch.json()
        run_id = int(launch.json()["id"])

        _drain_run_queue(session_factory)
        detail = _wait_for_run(client, run_id)

    request_paths = [cast(str, entry["path"]) for entry in request_log]
    assert request_paths == ["/v1/responses"]
    assert "/v1/v1/responses" not in request_paths
    assert detail["status"] == "succeeded"
    assert detail["finalOutput"] == {"summary": "fake strict schema"}


def test_workflow_package_save_allows_missing_model_connection_and_launch_rejects_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key="runtime_missing_model_package")},
    )

    assert create.status_code == 201, create.json()
    package_id = int(create.json()["id"])
    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 422, launch.json()
    body = cast(dict[str, object], launch.json())
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package launch validation failed"
    details = cast(list[dict[str, object]], body["details"])
    assert {
        "field": "spec.agents[0].modelConnection",
        "issue": "Model connection 'package_runtime_model' was not found",
    } in details
    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert (
            session.query(WorkflowPackage).filter_by(key="runtime_missing_model_package").count()
            == 1
        )


def _package_source_with_runtime_input_default(*, package_key: str) -> str:
    original_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    defaulted_input_schema = (
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "          horizonDays:\n"
        "            type: integer\n"
        "            default: 14\n"
        "        required: [ticker]\n"
        "      flow:\n"
    )
    return _package_source(package_key=package_key).replace(
        original_input_schema,
        defaulted_input_schema,
        1,
    )


def _package_source_with_nullable_optional_input(*, package_key: str) -> str:
    return (
        _package_source_with_optional_wired_inputs(package_key=package_key)
        .replace(
            "      sector:\n        type: string\n",
            '      sector:\n        type: [string, "null"]\n',
            1,
        )
        .replace(
            "          sector:\n            type: string\n",
            '          sector:\n            type: [string, "null"]\n',
            2,
        )
    )


def _package_source_with_enum_optional_input(*, package_key: str, nullable: bool) -> str:
    sector_schema = (
        '      sector:\n        type: [string, "null"]\n        enum: [growth, value]\n'
        if nullable
        else "      sector:\n        type: string\n        enum: [growth, value]\n"
    )
    agent_sector_schema = (
        '          sector:\n            type: [string, "null"]\n            enum: [growth, value]\n'
        if nullable
        else "          sector:\n            type: string\n            enum: [growth, value]\n"
    )
    return (
        _package_source_with_optional_wired_inputs(package_key=package_key)
        .replace("      sector:\n        type: string\n", sector_schema, 1)
        .replace("          sector:\n            type: string\n", agent_sector_schema, 2)
    )


def _package_source_with_optional_wired_inputs(
    *, package_key: str, require_sector: bool = False
) -> str:
    agent_required = "[ticker, sector]" if require_sector else "[ticker]"
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Optional Input Runtime Package
  description: Runtime package fixture with optional wired inputs.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
      sector:
        type: string
      horizonDays:
        type: integer
    required: [ticker]
  capabilityProfiles: []
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
          sector:
            type: string
          horizonDays:
            type: integer
        required: {agent_required}
      outputSchema: summary_output
      capabilityProfiles: []
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
          sector:
            type: string
          horizonDays:
            type: integer
        required: [ticker]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
          sector: ${{{{ inputs.sector }}}}
          horizonDays: ${{{{ inputs.horizonDays }}}}
      output:
        from: ${{{{ nodes.package_analysis.outputs.analysis }}}}
"""


def test_workflow_package_launch_records_canonical_required_parameters(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_wired_inputs(
                package_key="optional_input_canonical_payload_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    expected_parameters = {"ticker": "MSFT"}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": expected_parameters},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_workflow_package_launch_materializes_defaulted_optional_input(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_runtime_input_default(
                package_key="defaulted_optional_input_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    expected_parameters = {"ticker": "MSFT", "horizonDays": 14}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_workflow_package_launch_preserves_explicit_empty_string(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_wired_inputs(
                package_key="explicit_empty_string_input_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    expected_parameters = {"ticker": "MSFT", "sector": ""}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": expected_parameters},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_workflow_package_launch_preserves_nullable_null_when_schema_allows_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_nullable_optional_input(
                package_key="nullable_optional_input_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    expected_parameters = {"ticker": "MSFT", "sector": None}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": expected_parameters},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_workflow_package_launch_preserves_nullable_null_for_enum_when_schema_allows_it(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_enum_optional_input(
                package_key="nullable_enum_optional_input_package",
                nullable=True,
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])
    expected_parameters = {"ticker": "MSFT", "sector": None}

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": expected_parameters},
    )

    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    with session_factory() as session:
        run = session.get(Run, run_id)
        snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert run is not None
        assert snapshot is not None
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_workflow_package_launch_rejects_explicit_null_for_non_nullable_optional_input_enum(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_enum_optional_input(
                package_key="non_nullable_enum_optional_input_package",
                nullable=False,
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT", "sector": None}},
    )

    assert launch.status_code == 400, launch.json()
    assert launch.json()["code"] == "run_invalid_input"
    assert any(detail["field"] == "sector" for detail in launch.json()["details"])


def test_workflow_package_launch_rejects_explicit_null_for_non_nullable_optional_input(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_wired_inputs(
                package_key="explicit_null_optional_input_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": "MSFT", "horizonDays": None},
        },
    )

    assert launch.status_code == 400, launch.json()
    assert launch.json()["code"] == "run_invalid_input"
    assert {
        "field": "horizonDays",
        "issue": "Input should be a valid integer",
    } in launch.json()["details"]


def test_workflow_package_wired_missing_optional_input_path_is_skipped(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "optional input output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_wired_inputs(
                package_key="optional_wired_missing_path_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])

    assert detail["status"] == "succeeded"
    assert detail["input"] == {"ticker": "MSFT"}
    assert invocation["resolvedInput"] == {"ticker": "MSFT"}


def test_workflow_package_wired_missing_required_input_path_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_wired_inputs(
                package_key="required_wired_missing_path_package",
                require_sector=True,
            )
        },
    )
    assert created.status_code == 201, created.json()
    package_id = int(created.json()["id"])

    launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "MSFT"}},
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])

    _drain_run_queue(session_factory)
    detail = _wait_for_run(client, run_id)
    invocation = cast(dict[str, Any], detail["steps"][0]["invocations"][0])

    assert detail["status"] == "failed"
    assert invocation["status"] == "failed"
    assert invocation["errorCode"] == "agent_input_required_source_missing"
    assert invocation["errorDetails"] == [
        {
            "field": "steps[0].agents.analysis.wiring.sector",
            "issue": "Required input field source is missing from the run input",
        }
    ]


def _assert_no_snake_case_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert "_" not in str(key)
            _assert_no_snake_case_keys(child)
    elif isinstance(value, list):
        for item in value:
            _assert_no_snake_case_keys(item)


def _schedule_api_payload(package_id: int, *, name: str = "Daily market brief") -> dict[str, Any]:
    return {
        "packageId": package_id,
        "workflowKey": "runtime_workflow",
        "name": name,
        "description": "Runs on a schedule",
        "status": "enabled",
        "timezone": "UTC",
        "recurrence": {"type": "interval", "every": 1, "unit": "hours"},
        "startsAt": "2099-06-01T12:00:00Z",
        "endsAt": None,
        "overlapPolicy": "skip",
        "misfirePolicy": "catchUpOne",
        "misfireGraceSeconds": 86400,
        "inputTemplate": {"ticker": "{{vars.ticker}}"},
        "templateVars": {"ticker": "MSFT"},
    }


def test_schedule_api_schedule_crud_contract_package_first_and_camelcase(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created_package = _create_package(client, package_key="schedule_api_crud_package")
    package_id = cast(int, created_package["id"])

    created = client.post("/api/schedules", json=_schedule_api_payload(package_id))

    assert created.status_code == 201, created.json()
    created_body = cast(dict[str, Any], created.json())
    schedule_id = int(created_body["id"])
    _assert_no_snake_case_keys(created_body)
    assert created_body["packageId"] == package_id
    assert created_body["packageKey"] == "schedule_api_crud_package"
    assert created_body["workflowKey"] == "runtime_workflow"
    assert created_body["status"] == "enabled"
    assert created_body["nextFireAt"] == "2099-06-01T13:00:00Z"
    assert created_body["latestFireId"] is None
    assert created_body["latestRunId"] is None
    assert created_body["latestStatus"] is None

    listed = client.get(
        "/api/schedules",
        params={"packageKey": "schedule_api_crud_package", "status": "enabled"},
    )
    assert listed.status_code == 200, listed.json()
    listed_body = cast(dict[str, Any], listed.json())
    _assert_no_snake_case_keys(listed_body)
    assert listed_body["totalCount"] == 1
    assert listed_body["items"][0]["id"] == schedule_id

    detail = client.get(f"/api/schedules/{schedule_id}")
    assert detail.status_code == 200, detail.json()
    assert detail.json()["packageId"] == package_id

    patched = client.patch(
        f"/api/schedules/{schedule_id}",
        json={
            "workflowKey": "runtime_workflow",
            "status": "paused",
            "description": None,
            "startsAt": None,
            "endsAt": None,
            "templateVars": {"ticker": "NVDA"},
        },
    )
    assert patched.status_code == 200, patched.json()
    patched_body = patched.json()
    assert patched_body["workflowKey"] == "runtime_workflow"
    assert patched_body["status"] == "paused"
    assert patched_body["description"] is None
    assert patched_body["startsAt"] is None
    assert patched_body["endsAt"] is None
    assert patched_body["name"] == "Daily market brief"
    assert patched_body["timezone"] == "UTC"
    assert patched_body["recurrence"] == {"type": "interval", "every": 1, "unit": "hours"}
    assert patched_body["overlapPolicy"] == "skip"
    assert patched_body["misfirePolicy"] == "catchUpOne"
    assert patched_body["misfireGraceSeconds"] == 86400

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={
            "idempotencyKey": "delete-contract-manual-fire",
            "scheduledFor": "2026-06-01T13:00:00Z",
        },
    )
    assert run_now.status_code == 201, run_now.json()
    run_now_body = cast(dict[str, Any], run_now.json())
    fire_id = int(cast(dict[str, Any], run_now_body["fire"])["id"])
    run_id = int(cast(dict[str, Any], run_now_body["run"])["id"])

    fire_history_before_delete = client.get(
        f"/api/schedules/{schedule_id}/fires",
        params={"limit": 10},
    )
    assert fire_history_before_delete.status_code == 200, fire_history_before_delete.json()
    assert fire_history_before_delete.json()["items"][0]["id"] == fire_id

    run_detail_before_delete = client.get(f"/api/runs/{run_id}")
    assert run_detail_before_delete.status_code == 200, run_detail_before_delete.json()
    assert run_detail_before_delete.json()["scheduleId"] == schedule_id
    assert run_detail_before_delete.json()["scheduleFireId"] == fire_id

    deleted = client.delete(f"/api/schedules/{schedule_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    repeated_delete = client.delete(f"/api/schedules/{schedule_id}")
    assert repeated_delete.status_code == 404, repeated_delete.json()

    deleted_fire_history = client.get(
        f"/api/schedules/{schedule_id}/fires",
        params={"limit": 10},
    )
    assert deleted_fire_history.status_code == 404, deleted_fire_history.json()

    linked_run_detail = client.get(f"/api/runs/{run_id}")
    assert linked_run_detail.status_code == 200, linked_run_detail.json()
    linked_run_body = cast(dict[str, Any], linked_run_detail.json())
    assert linked_run_body["id"] == run_id
    assert linked_run_body["scheduleId"] is None
    assert linked_run_body["scheduleFireId"] is None
    assert linked_run_body["scheduledFor"] == "2026-06-01T13:00:00Z"
    assert linked_run_body["scheduleReason"] == "manual"

    with session_factory() as session:
        retained_run = session.get(Run, run_id)
        remaining_fire_count = (
            session.query(WorkflowPackageScheduleFire)
            .filter(WorkflowPackageScheduleFire.schedule_id == schedule_id)
            .count()
        )
        assert retained_run is not None
        assert retained_run.schedule_id is None
        assert retained_run.schedule_fire_id is None
        assert retained_run.schedule_provenance is not None
        assert retained_run.schedule_provenance["scheduleId"] == schedule_id
        assert retained_run.schedule_provenance["scheduleFireId"] == fire_id
        assert retained_run.schedule_provenance["scheduleDeletedAt"] is not None
        assert remaining_fire_count == 0


def test_schedule_api_rejects_unknown_workflow_key_before_create_or_update_persistence(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_package = _create_package(client, package_key="schedule_api_workflow_key_guard_package")
    package_id = cast(int, created_package["id"])

    invalid_create_payload = _schedule_api_payload(package_id, name="Invalid workflow schedule")
    invalid_create_payload["workflowKey"] = "missing_workflow"
    invalid_create = client.post("/api/schedules", json=invalid_create_payload)

    assert invalid_create.status_code == 422, invalid_create.json()
    invalid_create_body = cast(dict[str, Any], invalid_create.json())
    assert invalid_create_body["code"] == "validation_error"
    assert invalid_create_body["message"] == "Schedule validation failed"
    assert invalid_create_body["details"] == [
        {
            "field": "workflowKey",
            "issue": (
                "Workflow key 'missing_workflow' is not present in workflow package "
                "'schedule_api_workflow_key_guard_package'"
            ),
        }
    ]
    with session_factory() as session:
        assert (
            session.query(WorkflowPackageSchedule)
            .filter(WorkflowPackageSchedule.package_id == package_id)
            .count()
            == 0
        )

    valid_create = client.post(
        "/api/schedules",
        json=_schedule_api_payload(package_id, name="Workflow key guard schedule"),
    )
    assert valid_create.status_code == 201, valid_create.json()
    schedule_id = int(valid_create.json()["id"])

    invalid_update = client.patch(
        f"/api/schedules/{schedule_id}",
        json={"workflowKey": "missing_workflow", "name": "Mutated name"},
    )

    assert invalid_update.status_code == 422, invalid_update.json()
    invalid_update_body = cast(dict[str, Any], invalid_update.json())
    assert invalid_update_body["code"] == "validation_error"
    assert invalid_update_body["message"] == "Schedule validation failed"
    assert invalid_update_body["details"][0]["field"] == "workflowKey"
    detail = client.get(f"/api/schedules/{schedule_id}")
    assert detail.status_code == 200, detail.json()
    detail_body = cast(dict[str, Any], detail.json())
    assert detail_body["workflowKey"] == "runtime_workflow"
    assert detail_body["name"] == "Workflow key guard schedule"
    with session_factory() as session:
        schedules = (
            session.query(WorkflowPackageSchedule)
            .filter(WorkflowPackageSchedule.package_id == package_id)
            .all()
        )
        assert len(schedules) == 1
        assert schedules[0].workflow_key == "runtime_workflow"
        assert schedules[0].name == "Workflow key guard schedule"


@pytest.mark.parametrize(
    ("field_name", "null_patch"),
    [
        ("workflowKey", {"workflowKey": None}),
        ("status", {"status": None}),
        ("name", {"name": None}),
        ("timezone", {"timezone": None}),
        ("recurrence", {"recurrence": None}),
        ("overlapPolicy", {"overlapPolicy": None}),
        ("misfirePolicy", {"misfirePolicy": None}),
        ("misfireGraceSeconds", {"misfireGraceSeconds": None}),
        ("inputTemplate", {"inputTemplate": None}),
        ("templateVars", {"templateVars": None}),
    ],
)
def test_schedule_api_patch_rejects_null_for_non_nullable_fields(
    client: TestClient,
    field_name: str,
    null_patch: dict[str, Any],
) -> None:
    created_package = _create_package(client, package_key=f"schedule_api_null_{field_name.lower()}")
    package_id = cast(int, created_package["id"])
    created = client.post(
        "/api/schedules",
        json=_schedule_api_payload(package_id, name="Null guard schedule"),
    )
    assert created.status_code == 201, created.json()
    schedule_id = int(created.json()["id"])

    rejected = client.patch(f"/api/schedules/{schedule_id}", json=null_patch)

    assert rejected.status_code == 422, rejected.json()
    rejected_body = cast(dict[str, Any], rejected.json())
    assert rejected_body["code"] == "validation_error"
    assert rejected_body["message"] == "Request validation failed"
    assert rejected_body["details"][0]["field"] == field_name
    assert "null" in rejected_body["details"][0]["issue"].lower()

    detail = client.get(f"/api/schedules/{schedule_id}")
    assert detail.status_code == 200, detail.json()
    detail_body = cast(dict[str, Any], detail.json())
    assert detail_body["name"] == "Null guard schedule"
    assert detail_body["status"] == "enabled"
    assert detail_body["timezone"] == "UTC"
    assert detail_body["recurrence"] == {"type": "interval", "every": 1, "unit": "hours"}
    assert detail_body["overlapPolicy"] == "skip"
    assert detail_body["misfirePolicy"] == "catchUpOne"
    assert detail_body["misfireGraceSeconds"] == 86400


def test_tradingagents_materializer_queues_canonical_schedules_without_provider_execution(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(
        session_factory,
        key="tradingagents_primary_model",
        name="TradingAgents Primary Model",
        description="Preflight model binding.",
        base_url="https://api.openai.com/v1",
        model_id="gpt-5.5-mini",
    )
    package = _seeded_tradingagents_package(client)
    package_id = cast(int, package["id"])
    materialized_at = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    _create_tradingagents_canonical_schedules(
        session_factory,
        package_id=package_id,
        next_fire_at=materialized_at,
    )

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(
        now=materialized_at
    )

    assert result.processed_count == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)
    assert result.queued_count == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)

    with session_factory() as session:
        schedules = (
            session.query(WorkflowPackageSchedule)
            .filter(WorkflowPackageSchedule.package_id == package_id)
            .order_by(WorkflowPackageSchedule.id)
            .all()
        )
        runs = (
            session.query(Run)
            .filter(Run.schedule_id.in_([schedule.id for schedule in schedules]))
            .order_by(Run.id)
            .all()
        )
        fires = (
            session.query(WorkflowPackageScheduleFire)
            .filter(
                WorkflowPackageScheduleFire.schedule_id.in_([schedule.id for schedule in schedules])
            )
            .order_by(WorkflowPackageScheduleFire.id)
            .all()
        )
        fires_by_schedule_id = {fire.schedule_id: fire for fire in fires}
        runs_by_schedule_id = {cast(int, run.schedule_id): run for run in runs}

        assert len(runs) == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)
        assert len(fires) == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)
        for schedule in schedules:
            fire = fires_by_schedule_id[schedule.id]
            run = runs_by_schedule_id[schedule.id]

            assert fire.status == FireStatus.QUEUED.value
            assert run.status == "queued"
            assert run.schedule_id == schedule.id
            assert run.schedule_fire_id == fire.id
            assert run.scheduled_for == materialized_at
            assert run.workflow_package_id == package_id
            assert run.workflow_package_workflow_key == schedule.workflow_key
            assert schedule.next_fire_at == materialized_at + timedelta(hours=1)

    assert _RuntimeRecordingOpenAIClient.init_calls == []
    assert _RuntimeRecordingOpenAIClient.create_calls == []


def test_schedule_api_run_now_persists_schedule_provenance_and_rerun_descendants(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    created_package = _create_package(client, package_key="schedule_api_run_now_package")
    package_id = cast(int, created_package["id"])
    scheduled_for = "2026-06-01T13:00:00Z"

    unsaved_preview = client.post(
        "/api/schedules/preview",
        json={
            "packageId": package_id,
            "workflowKey": "runtime_workflow",
            "timezone": "America/New_York",
            "recurrence": {"type": "daily", "atLocalTime": "09:00"},
            "scheduledFor": scheduled_for,
            "inputTemplate": {"ticker": "{{vars.ticker}}"},
            "templateVars": {"ticker": "MSFT"},
        },
    )
    assert unsaved_preview.status_code == 200, unsaved_preview.json()
    unsaved_body = cast(dict[str, Any], unsaved_preview.json())
    assert unsaved_body["scheduleId"] is None
    assert unsaved_body["scheduledFor"] == scheduled_for
    assert unsaved_body["renderedParameters"] == {"ticker": "MSFT"}
    assert unsaved_body["validationErrors"] == []
    assert unsaved_body["ready"] is True
    assert unsaved_body["templateContext"]["fire"]["scheduledLocalDate"] == "2026-06-01"
    assert unsaved_body["templateContext"]["fire"]["scheduledLocalTime"] == "09:00"

    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert session.query(WorkflowPackageScheduleFire).count() == 0

    created = client.post("/api/schedules", json=_schedule_api_payload(package_id))
    assert created.status_code == 201, created.json()
    schedule_id = int(created.json()["id"])

    saved_preview = client.post(
        f"/api/schedules/{schedule_id}/preview",
        json={"scheduledFor": scheduled_for},
    )
    assert saved_preview.status_code == 200, saved_preview.json()
    saved_body = cast(dict[str, Any], saved_preview.json())
    assert saved_body["scheduleId"] == schedule_id
    assert saved_body["renderedParameters"] == {"ticker": "MSFT"}
    assert saved_body["validationErrors"] == []
    assert saved_body["ready"] is True

    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert session.query(WorkflowPackageScheduleFire).count() == 0

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": "manual-fire-2026-06-01", "scheduledFor": scheduled_for},
    )
    assert run_now.status_code == 201, run_now.json()
    run_now_body = cast(dict[str, Any], run_now.json())
    fire_body = cast(dict[str, Any], run_now_body["fire"])
    run_body = cast(dict[str, Any], run_now_body["run"])
    assert run_now_body["scheduleId"] == schedule_id
    assert fire_body["reason"] == "manual"
    assert fire_body["status"] == "queued"
    assert fire_body["scheduledFor"] == scheduled_for
    assert fire_body["scheduledLocalDate"] == "2026-06-01"
    assert fire_body["scheduledLocalTime"] == "13:00"
    assert fire_body["renderedParameters"] == {"ticker": "MSFT"}
    assert run_body["status"] == "queued"
    assert run_body["workflowPackageId"] == package_id
    assert run_body["workflowPackageKey"] == "schedule_api_run_now_package"
    assert run_body["workflowKey"] == "runtime_workflow"

    run_list = client.get("/api/runs", params={"workflowPackageId": package_id})
    assert run_list.status_code == 200, run_list.json()
    run_list_items = cast(list[dict[str, Any]], run_list.json()["items"])
    run_list_item = next(item for item in run_list_items if item["id"] == run_body["id"])
    assert run_list_item["scheduleId"] == schedule_id
    assert run_list_item["scheduleFireId"] == fire_body["id"]
    assert run_list_item["scheduledFor"] == scheduled_for
    assert run_list_item["scheduleReason"] == "manual"

    run_detail = client.get(f"/api/runs/{run_body['id']}")
    assert run_detail.status_code == 200, run_detail.json()
    run_detail_body = cast(dict[str, Any], run_detail.json())
    assert run_detail_body["scheduleId"] == schedule_id
    assert run_detail_body["scheduleFireId"] == fire_body["id"]
    assert run_detail_body["scheduledFor"] == scheduled_for
    assert run_detail_body["scheduleReason"] == "manual"

    _drain_run_queue(session_factory)
    source_detail = _wait_for_run(client, int(run_body["id"]))
    assert source_detail["status"] == "succeeded"

    repeated = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": "manual-fire-2026-06-01", "scheduledFor": scheduled_for},
    )
    assert repeated.status_code == 201, repeated.json()
    assert repeated.json()["fire"]["id"] == fire_body["id"]
    assert repeated.json()["run"]["id"] == run_body["id"]

    fires = client.get(f"/api/schedules/{schedule_id}/fires", params={"limit": 10})
    assert fires.status_code == 200, fires.json()
    fire_history = cast(dict[str, Any], fires.json())
    assert fire_history["totalCount"] == 1
    assert fire_history["items"][0]["id"] == fire_body["id"]
    assert fire_history["items"][0]["runId"] == run_body["id"]

    rerun = client.post(
        f"/api/runs/{run_body['id']}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun.status_code == 201, rerun.json()
    rerun_id = int(rerun.json()["id"])

    with session_factory() as session:
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        fires_count = (
            session.query(WorkflowPackageScheduleFire)
            .filter(WorkflowPackageScheduleFire.schedule_id == schedule_id)
            .count()
        )
        source_run = session.get(Run, int(run_body["id"]))
        rerun_run = session.get(Run, rerun_id)
        schedule_row = session.get(WorkflowPackageSchedule, schedule_id)
        assert len(runs) == 1
        assert fires_count == 1
        assert source_run is not None
        assert rerun_run is not None
        assert schedule_row is not None
        assert source_run.schedule_reason == "manual"
        assert source_run.input == {"ticker": "MSFT"}
        assert source_run.schedule_provenance == {
            "scheduleId": schedule_id,
            "scheduleFireId": fire_body["id"],
            "scheduleName": schedule_row.name,
            "packageId": package_id,
            "packageKey": "schedule_api_run_now_package",
            "workflowKey": schedule_row.workflow_key,
            "timezone": schedule_row.timezone,
            "recurrence": deepcopy(schedule_row.recurrence),
            "fireKey": fire_body["fireKey"],
            "reason": "manual",
            "scheduledFor": scheduled_for,
            "scheduledLocalDate": fire_body["scheduledLocalDate"],
            "scheduledLocalTime": fire_body["scheduledLocalTime"],
            "scheduledLocalDateTime": fire_body["scheduledLocalDateTime"],
            "materializedAt": fire_body["materializedAt"],
            "scheduleDeletedAt": None,
        }
        assert rerun_run.schedule_id is None
        assert rerun_run.schedule_fire_id is None
        assert rerun_run.scheduled_for is None
        assert rerun_run.schedule_reason is None
        assert rerun_run.schedule_provenance is None


def test_scheduled_input_preview_returns_canonical_workflow_parameters(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created_package = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_runtime_input_default(
                package_key="scheduled_preview_canonical_package"
            )
        },
    )
    assert created_package.status_code == 201, created_package.json()
    package_id = int(created_package.json()["id"])
    scheduled_for = "2026-06-01T13:00:00Z"
    expected_parameters = {"ticker": "MSFT", "horizonDays": 14}
    preview_payload = {
        "packageId": package_id,
        "workflowKey": "runtime_workflow",
        "timezone": "UTC",
        "recurrence": {"type": "interval", "every": 1, "unit": "hours"},
        "scheduledFor": scheduled_for,
        "inputTemplate": {"ticker": "{{vars.ticker}}"},
        "templateVars": {"ticker": "MSFT"},
    }

    unsaved_preview = client.post("/api/schedules/preview", json=preview_payload)

    assert unsaved_preview.status_code == 200, unsaved_preview.json()
    unsaved_body = cast(dict[str, Any], unsaved_preview.json())
    assert unsaved_body["scheduleId"] is None
    assert unsaved_body["renderedParameters"] == expected_parameters
    assert unsaved_body["validationErrors"] == []
    assert unsaved_body["ready"] is True
    with session_factory() as session:
        assert session.query(Run).count() == 0
        assert session.query(WorkflowPackageScheduleFire).count() == 0

    schedule_payload = _schedule_api_payload(package_id, name="Canonical preview schedule")
    schedule_payload["inputTemplate"] = {"ticker": "{{vars.ticker}}"}
    schedule_payload["templateVars"] = {"ticker": "MSFT"}
    created_schedule = client.post("/api/schedules", json=schedule_payload)
    assert created_schedule.status_code == 201, created_schedule.json()
    schedule_id = int(created_schedule.json()["id"])

    saved_preview = client.post(
        f"/api/schedules/{schedule_id}/preview",
        json={"scheduledFor": scheduled_for},
    )

    assert saved_preview.status_code == 200, saved_preview.json()
    saved_body = cast(dict[str, Any], saved_preview.json())
    assert saved_body["scheduleId"] == schedule_id
    assert saved_body["renderedParameters"] == expected_parameters
    assert saved_body["validationErrors"] == []
    assert saved_body["ready"] is True


def test_scheduled_run_materializes_canonical_workflow_parameters(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created_package = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_runtime_input_default(
                package_key="scheduled_materialization_canonical_package"
            )
        },
    )
    assert created_package.status_code == 201, created_package.json()
    package_id = int(created_package.json()["id"])
    materialized_at = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    expected_parameters = {"ticker": "MSFT", "horizonDays": 14}
    with session_factory() as session:
        schedule = WorkflowPackageScheduleService(session).create_schedule(
            ScheduleCreate(
                package_id=package_id,
                workflow_key="runtime_workflow",
                name="Canonical materialization schedule",
                timezone="UTC",
                recurrence=IntervalRecurrence(every=1, unit=IntervalUnit.HOURS),
                input_template={"ticker": "{{vars.ticker}}"},
                template_vars={"ticker": "MSFT"},
            ),
            next_fire_at=materialized_at,
        )
        schedule_id = schedule.id

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(
        now=materialized_at
    )

    assert result.processed_count == 1
    assert result.queued_count == 1
    with session_factory() as session:
        fire = session.query(WorkflowPackageScheduleFire).filter_by(schedule_id=schedule_id).one()
        run = session.query(Run).filter_by(schedule_id=schedule_id).one()
        snapshot = session.get(RunWorkflowPackageSnapshot, run.id)
        assert snapshot is not None
        assert fire.status == FireStatus.QUEUED.value
        assert fire.rendered_parameters == expected_parameters
        assert run.status == "queued"
        assert run.input == expected_parameters
        assert snapshot.launch_parameters == expected_parameters


def test_schedule_api_run_now_blocks_secretless_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key=None)
    created_package = _create_package(client, package_key="schedule_api_run_now_blocked_package")
    package_id = cast(int, created_package["id"])
    created_schedule = client.post(
        "/api/schedules",
        json=_schedule_api_payload(package_id, name="Blocked run now schedule"),
    )
    assert created_schedule.status_code == 201, created_schedule.json()
    schedule_id = int(created_schedule.json()["id"])

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={
            "idempotencyKey": "blocked-run-now-2026-06-01",
            "scheduledFor": "2026-06-01T13:00:00Z",
        },
    )

    assert run_now.status_code == 422, run_now.json()
    body = cast(dict[str, Any], run_now.json())
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package launch validation failed"
    assert body["details"][0]["field"] == "spec.agents[0].modelConnection"
    assert body["details"][0]["issue"] == "API key is not configured"
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        assert len(fires) == 1
        assert fires[0].reason == FireReason.MANUAL
        assert fires[0].status == FireStatus.FAILED
        assert fires[0].error_code == "validation_error"
        assert fires[0].error_message == "Workflow package launch validation failed"
        assert runs == []


@pytest.mark.parametrize(
    ("case_name", "recurrence", "scheduled_for", "expected_window_start"),
    [
        (
            "daily",
            {"type": "daily", "atLocalTime": "09:00"},
            "2026-06-02T09:00:00Z",
            "2026-06-01T09:00:00Z",
        ),
        (
            "weekly",
            {"type": "weekly", "daysOfWeek": ["mon", "wed"], "atLocalTime": "09:00"},
            "2026-06-03T09:00:00Z",
            "2026-06-01T09:00:00Z",
        ),
        (
            "monthly",
            {"type": "monthly", "daysOfMonth": [1, 15], "atLocalTime": "09:00"},
            "2026-06-15T09:00:00Z",
            "2026-06-01T09:00:00Z",
        ),
    ],
)
def test_schedule_api_non_interval_window_start_for_preview_and_run_now(
    client: TestClient,
    session_factory: sessionmaker[Session],
    case_name: str,
    recurrence: dict[str, Any],
    scheduled_for: str,
    expected_window_start: str,
) -> None:
    _seed_model_connection(session_factory)
    package_key = f"schedule_api_window_start_{case_name}_package"
    created_package = _create_package(client, package_key=package_key)
    package_id = cast(int, created_package["id"])
    input_template = {"ticker": "{{window.start}}|{{window.startDate}}"}
    expected_ticker = f"{expected_window_start}|2026-06-01"

    unsaved_preview = client.post(
        "/api/schedules/preview",
        json={
            "packageId": package_id,
            "workflowKey": "runtime_workflow",
            "timezone": "UTC",
            "recurrence": recurrence,
            "scheduledFor": scheduled_for,
            "inputTemplate": input_template,
            "templateVars": {},
        },
    )

    assert unsaved_preview.status_code == 200, unsaved_preview.json()
    unsaved_body = cast(dict[str, Any], unsaved_preview.json())
    assert unsaved_body["templateContext"]["window"]["start"] == expected_window_start
    assert unsaved_body["templateContext"]["window"]["startDate"] == "2026-06-01"
    assert unsaved_body["renderedParameters"] == {"ticker": expected_ticker}
    assert unsaved_body["ready"] is True

    payload = _schedule_api_payload(package_id, name=f"{case_name.title()} window start")
    payload["timezone"] = "UTC"
    payload["recurrence"] = recurrence
    payload["inputTemplate"] = input_template
    payload["templateVars"] = {}
    created = client.post("/api/schedules", json=payload)
    assert created.status_code == 201, created.json()
    schedule_id = int(created.json()["id"])

    saved_preview = client.post(
        f"/api/schedules/{schedule_id}/preview",
        json={"scheduledFor": scheduled_for},
    )

    assert saved_preview.status_code == 200, saved_preview.json()
    saved_body = cast(dict[str, Any], saved_preview.json())
    assert saved_body["templateContext"]["window"]["start"] == expected_window_start
    assert saved_body["templateContext"]["window"]["startDate"] == "2026-06-01"
    assert saved_body["renderedParameters"] == {"ticker": expected_ticker}
    assert saved_body["ready"] is True

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": f"{case_name}-window-start", "scheduledFor": scheduled_for},
    )

    assert run_now.status_code == 201, run_now.json()
    run_now_body = cast(dict[str, Any], run_now.json())
    assert run_now_body["fire"]["renderedParameters"] == {"ticker": expected_ticker}
    with session_factory() as session:
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        assert len(runs) == 1
        assert runs[0].input == {"ticker": expected_ticker}


def test_schedule_api_run_now_idempotency_scope_and_paused_schedule(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created_package = _create_package(client, package_key="schedule_api_run_now_scope_package")
    package_id = cast(int, created_package["id"])
    payload = _schedule_api_payload(package_id, name="Paused manual schedule")
    payload["status"] = "paused"
    created = client.post("/api/schedules", json=payload)
    assert created.status_code == 201, created.json()
    schedule_id = int(created.json()["id"])
    assert created.json()["status"] == "paused"

    first = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": "manual-retry", "scheduledFor": "2026-06-01T13:00:00Z"},
    )
    repeated = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": "manual-retry", "scheduledFor": "2026-06-01T13:00:00Z"},
    )
    second_time = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={"idempotencyKey": "manual-retry", "scheduledFor": "2026-06-01T14:00:00Z"},
    )

    assert first.status_code == 201, first.json()
    assert repeated.status_code == 201, repeated.json()
    assert second_time.status_code == 201, second_time.json()
    assert repeated.json()["fire"]["id"] == first.json()["fire"]["id"]
    assert repeated.json()["run"]["id"] == first.json()["run"]["id"]
    assert second_time.json()["fire"]["id"] != first.json()["fire"]["id"]
    assert second_time.json()["run"]["id"] != first.json()["run"]["id"]

    detail = client.get(f"/api/schedules/{schedule_id}")
    fires = client.get(f"/api/schedules/{schedule_id}/fires", params={"limit": 10})
    assert detail.status_code == 200, detail.json()
    assert fires.status_code == 200, fires.json()
    assert detail.json()["status"] == "paused"
    assert fires.json()["totalCount"] == 2
    with session_factory() as session:
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        assert len(runs) == 2
        assert {run.schedule_reason for run in runs} == {"manual"}


def test_schedule_api_preview_reports_render_and_schema_validation_failures(
    client: TestClient,
) -> None:
    created_package = _create_package(client, package_key="schedule_api_preview_invalid_package")
    package_id = cast(int, created_package["id"])
    base_payload: dict[str, Any] = {
        "packageId": package_id,
        "workflowKey": "runtime_workflow",
        "timezone": "America/New_York",
        "recurrence": {"type": "daily", "atLocalTime": "09:00"},
        "scheduledFor": "2026-06-01T13:00:00Z",
    }

    missing_placeholder = client.post(
        "/api/schedules/preview",
        json={
            **base_payload,
            "inputTemplate": {"ticker": "{{vars.missingTicker}}"},
            "templateVars": {},
        },
    )
    schema_invalid = client.post(
        "/api/schedules/preview",
        json={
            **base_payload,
            "inputTemplate": {},
            "templateVars": {},
        },
    )

    assert missing_placeholder.status_code == 200, missing_placeholder.json()
    missing_body = missing_placeholder.json()
    assert missing_body["ready"] is False
    assert missing_body["renderedParameters"] == {}
    assert missing_body["validationErrors"] == [
        {
            "field": "inputTemplate.ticker",
            "issue": "Missing scheduled input placeholder value for 'vars.missingTicker'",
        }
    ]

    assert schema_invalid.status_code == 200, schema_invalid.json()
    schema_body = schema_invalid.json()
    assert schema_body["ready"] is False
    assert schema_body["renderedParameters"] == {}
    assert schema_body["validationErrors"][0]["field"] == "ticker"
    assert "Field required" in schema_body["validationErrors"][0]["issue"]


def test_schedule_api_stale_workflow_preview_and_materializer_fail_deterministically(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    created_package = _create_package(client, package_key="schedule_api_stale_workflow_package")
    package_id = cast(int, created_package["id"])
    with session_factory() as session:
        schedule = WorkflowPackageScheduleService(session).create_schedule(
            ScheduleCreate(
                package_id=package_id,
                workflow_key="runtime_workflow",
                name="Stale workflow schedule",
                timezone="UTC",
                recurrence=IntervalRecurrence(every=1, unit=IntervalUnit.HOURS),
                input_template={"ticker": "{{vars.ticker}}"},
                template_vars={"ticker": "MSFT"},
            ),
            next_fire_at=now,
        )
        schedule_id = schedule.id
        package = session.get(WorkflowPackage, package_id)
        assert package is not None
        package.compiled_plan = {"workflows": []}
        package.compiled_hash = "e" * 64
        session.commit()

    preview = client.post(
        f"/api/schedules/{schedule_id}/preview",
        json={"scheduledFor": "2026-06-01T13:00:00Z"},
    )
    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert preview.status_code == 200, preview.json()
    preview_body = preview.json()
    assert preview_body["ready"] is False
    assert preview_body["validationErrors"] == [
        {
            "field": "workflowKey",
            "issue": "Schedule workflow is no longer present in the current package",
        }
    ]
    assert result.failed_count == 1
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        assert len(fires) == 1
        assert fires[0].status == FireStatus.FAILED
        assert fires[0].error_code == SCHEDULE_RENDER_VALIDATION_FAILED
        assert fires[0].error_message == "Scheduled input template validation failed"
        assert runs == []


def test_schedule_api_run_now_records_failed_fire_for_missing_render_placeholder(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_package = _create_package(
        client,
        package_key="schedule_run_now_missing_placeholder_package",
    )
    package_id = cast(int, created_package["id"])
    payload = _schedule_api_payload(package_id, name="Missing placeholder run-now schedule")
    payload["inputTemplate"] = {"ticker": "{{vars.missingTicker}}"}
    payload["templateVars"] = {}
    created_schedule = client.post("/api/schedules", json=payload)
    assert created_schedule.status_code == 201, created_schedule.json()
    schedule_id = int(created_schedule.json()["id"])

    run_now = client.post(
        f"/api/schedules/{schedule_id}/run-now",
        json={
            "idempotencyKey": "missing-placeholder-run-now",
            "scheduledFor": "2026-06-01T13:00:00Z",
        },
    )

    assert run_now.status_code == 400, run_now.json()
    body = cast(dict[str, Any], run_now.json())
    assert body["code"] == SCHEDULE_TEMPLATE_MISSING_VALUE
    assert body["message"] == "Scheduled input template validation failed"
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        schedule = WorkflowPackageScheduleService(session).get_schedule(schedule_id)
        assert len(fires) == 1
        assert fires[0].reason == FireReason.MANUAL
        assert fires[0].status == FireStatus.FAILED
        assert fires[0].error_code == SCHEDULE_TEMPLATE_MISSING_VALUE
        assert fires[0].error_message == "Scheduled input template validation failed"
        schedule_body = schedule.model_dump(mode="json", by_alias=True)
        assert schedule_body["nextFireAt"] == created_schedule.json()["nextFireAt"]
        assert runs == []


def test_schedule_materializer_records_failed_fire_for_missing_render_placeholder(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    _, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_missing_placeholder_package",
        next_fire_at=now,
        input_template={"ticker": "{{vars.missingTicker}}"},
        template_vars={},
    )

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert result.failed_count == 1
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        schedule = WorkflowPackageScheduleService(session).get_schedule(schedule_id)
        assert len(fires) == 1
        assert fires[0].status == FireStatus.FAILED
        assert fires[0].error_code == SCHEDULE_TEMPLATE_MISSING_VALUE
        assert fires[0].error_message == "Scheduled input template validation failed"
        assert schedule.next_fire_at == now + timedelta(hours=1)
        assert runs == []


def _schedule_template_render_context(
    *,
    vars_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scheduled_for = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    window_start = datetime(2026, 5, 31, 13, 0, tzinfo=UTC)
    completed_at = datetime(2026, 5, 31, 13, 30, tzinfo=UTC)
    return build_scheduled_input_template_context(
        schedule_id=44,
        schedule_name="Daily market brief",
        schedule_timezone="America/New_York",
        package_key="schedule_render_package",
        workflow_key="daily_research",
        fire_id=801,
        fire_reason="scheduled",
        scheduled_for=scheduled_for,
        scheduled_local_date="2026-06-01",
        scheduled_local_time="09:00",
        scheduled_local_datetime="2026-06-01T09:00:00",
        materialized_at=scheduled_for + timedelta(seconds=4),
        window_start=window_start,
        last_run=ScheduledInputLastRunContext(
            id=710,
            status="succeeded",
            completed_at=completed_at,
        ),
        template_vars=vars_payload or {},
    )


def test_schedule_template_render_exact_placeholder_type_preservation() -> None:
    context = _schedule_template_render_context(
        vars_payload={
            "lookbackDays": 5,
            "payload": {"symbols": ["NVDA"], "active": True},
        }
    )
    result = render_scheduled_input_template(
        {
            "lookbackDays": "{{vars.lookbackDays}}",
            "payload": "{{vars.payload}}",
            "scheduleId": "{{schedule.id}}",
            "lastRunId": "{{lastRun.id}}",
        },
        context,
    )

    assert result.validation_errors == []
    assert result.rendered_parameters["lookbackDays"] == 5
    assert isinstance(result.rendered_parameters["lookbackDays"], int)
    assert result.rendered_parameters["payload"] == {"symbols": ["NVDA"], "active": True}
    assert result.rendered_parameters["scheduleId"] == 44
    assert result.rendered_parameters["lastRunId"] == 710


def test_schedule_template_payload_limit_uses_compact_json_size() -> None:
    template = {"items": ["x" * 128 for _ in range(1000)]}
    compact_size = len(
        json.dumps(
            template,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    default_size = len(json.dumps(template, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    assert compact_size <= RUNTIME_INPUT_PAYLOAD_MAX_BYTES
    assert default_size > RUNTIME_INPUT_PAYLOAD_MAX_BYTES

    result = render_scheduled_input_template(
        template,
        _schedule_template_render_context(),
    )

    assert result.validation_errors == []
    assert result.rendered_parameters == template


def test_schedule_template_render_embedded_placeholders_are_strings() -> None:
    context = _schedule_template_render_context(
        vars_payload={
            "lookbackDays": 5,
            "payload": {"symbols": ["NVDA"], "active": True},
        }
    )
    result = render_scheduled_input_template(
        {
            "title": "Daily brief for {{fire.scheduledLocalDate}}",
            "window": "{{window.start}} to {{window.end}}",
            "lookback": "{{vars.lookbackDays}} days",
            "payloadText": "payload={{vars.payload}}",
            "literal": r"\{{notAPlaceholder\}}",
        },
        context,
    )

    assert result.validation_errors == []
    assert result.rendered_parameters == {
        "title": "Daily brief for 2026-06-01",
        "window": "2026-05-31T13:00:00Z to 2026-06-01T13:00:00Z",
        "lookback": "5 days",
        "payloadText": 'payload={"active":true,"symbols":["NVDA"]}',
        "literal": "{{notAPlaceholder}}",
    }


def test_schedule_template_render_missing_variable_fails_deterministically() -> None:
    result = render_scheduled_input_template(
        {"ticker": "{{vars.missingTicker}}"},
        _schedule_template_render_context(vars_payload={"ticker": "NVDA"}),
    )

    assert result.rendered_parameters == {}
    assert result.validation_errors == [
        {
            "field": "inputTemplate.ticker",
            "issue": "Missing scheduled input placeholder value for 'vars.missingTicker'",
            "code": SCHEDULE_TEMPLATE_MISSING_VALUE,
            "expression": "vars.missingTicker",
        }
    ]


def test_schedule_template_render_invalid_expression_fails_deterministically() -> None:
    context = _schedule_template_render_context(vars_payload={"items": ["NVDA"]})
    unsafe_templates = [
        "{{env.API_KEY}}",
        "{{vars.items[0]}}",
        "{{vars.items | first}}",
        "{{vars.items()}}",
        "{{vars.items + 1}}",
        "{% for item in vars.items %}{{item}}{% endfor %}",
    ]

    for expression in unsafe_templates:
        result = render_scheduled_input_template({"value": expression}, context)
        assert result.rendered_parameters == {}
        assert result.validation_errors[0]["field"] == "inputTemplate.value"
        assert result.validation_errors[0]["code"] == SCHEDULE_TEMPLATE_INVALID_EXPRESSION


def _create_schedule_materializer_schedule(
    client: TestClient,
    session_factory: sessionmaker[Session],
    *,
    package_key: str,
    next_fire_at: datetime,
    timezone_name: str = "UTC",
    recurrence: Any | None = None,
    overlap_policy: OverlapPolicy = OverlapPolicy.SKIP,
    misfire_policy: MisfirePolicy = MisfirePolicy.CATCH_UP_ONE,
    misfire_grace_seconds: int = 86400,
    input_template: dict[str, Any] | None = None,
    template_vars: dict[str, Any] | None = None,
) -> tuple[int, int]:
    with session_factory() as session:
        has_model = (
            session.query(ModelConnection)
            .filter(ModelConnection.key == "package_runtime_model")
            .first()
            is not None
        )
    if not has_model:
        _seed_model_connection(session_factory)
    created = _create_package(client, package_key=package_key)
    package_id = cast(int, created["id"])
    with session_factory() as session:
        schedule = WorkflowPackageScheduleService(session).create_schedule(
            ScheduleCreate(
                package_id=package_id,
                workflow_key="runtime_workflow",
                name=f"Schedule {package_key}",
                timezone=timezone_name,
                recurrence=recurrence or IntervalRecurrence(every=1, unit=IntervalUnit.HOURS),
                overlap_policy=overlap_policy,
                misfire_policy=misfire_policy,
                misfire_grace_seconds=misfire_grace_seconds,
                input_template=input_template or {"ticker": "{{vars.ticker}}"},
                template_vars=template_vars or {"ticker": "MSFT"},
            ),
            next_fire_at=next_fire_at,
        )
        return package_id, schedule.id


def test_schedule_materializer_due_schedule_creates_one_fire_and_queued_run(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    package_id, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_due_package",
        next_fire_at=now,
    )

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)
    repeat = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert result.processed_count == 1
    assert result.queued_count == 1
    assert repeat.changed_count == 0
    with session_factory() as session:
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        schedule = WorkflowPackageScheduleService(session).get_schedule(schedule_id)
        assert len(runs) == 1
        assert len(fires) == 1
        assert fires[0].status == FireStatus.QUEUED
        assert fires[0].rendered_parameters == {"ticker": "MSFT"}
        assert runs[0].workflow_package_id == package_id
        assert runs[0].schedule_fire_id == fires[0].id
        assert runs[0].scheduled_for == now
        assert runs[0].schedule_reason == "scheduled"
        assert runs[0].input == {"ticker": "MSFT"}
        assert schedule.next_fire_at == now + timedelta(hours=1)


def test_schedule_materializer_daily_dst_transitions_use_named_timezone(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    spring_gap_fire = datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    _, spring_schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_dst_spring_package",
        next_fire_at=spring_gap_fire,
        timezone_name="America/New_York",
        recurrence=DailyRecurrence(at_local_time="02:00"),
    )

    spring_result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(
        now=spring_gap_fire
    )

    assert spring_result.queued_count == 1
    with session_factory() as session:
        spring_schedule = WorkflowPackageScheduleService(session).get_schedule(spring_schedule_id)
        spring_fire = (
            WorkflowPackageScheduleService(session).list_fire_history(spring_schedule_id).items[0]
        )
        assert spring_fire.scheduled_for == spring_gap_fire
        assert spring_fire.scheduled_local_date == "2026-03-08"
        assert spring_fire.scheduled_local_time == "03:00"
        assert spring_fire.scheduled_local_datetime == "2026-03-08T03:00"
        assert spring_schedule.next_fire_at == datetime(2026, 3, 9, 6, 0, tzinfo=UTC)

    fall_back_fire = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    _, fall_schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_dst_fall_package",
        next_fire_at=fall_back_fire,
        timezone_name="America/New_York",
        recurrence=DailyRecurrence(at_local_time="01:30"),
    )

    fall_result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(
        now=fall_back_fire
    )

    assert fall_result.queued_count == 1
    with session_factory() as session:
        fall_schedule = WorkflowPackageScheduleService(session).get_schedule(fall_schedule_id)
        fall_fire = (
            WorkflowPackageScheduleService(session).list_fire_history(fall_schedule_id).items[0]
        )
        assert fall_fire.scheduled_for == fall_back_fire
        assert fall_fire.scheduled_local_date == "2026-11-01"
        assert fall_fire.scheduled_local_time == "01:30"
        assert fall_fire.scheduled_local_datetime == "2026-11-01T01:30"
        assert fall_schedule.next_fire_at == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_schedule_materializer_worker_materializes_before_claim(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    due_at = utcnow() - timedelta(hours=1)
    _, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_worker_order_package",
        next_fire_at=due_at,
    )

    executed_run_ids: list[int] = []

    def record_claimed_run(self: RunSchedulerWorker, scheduled_run: object) -> None:
        del self
        executed_run_ids.append(int(cast(Any, scheduled_run).run_id))

    monkeypatch.setattr(RunSchedulerWorker, "_execute_claimed_run", record_claimed_run)

    worker = RunSchedulerWorker(session_factory=session_factory)
    claimed = worker.run_once()

    assert claimed is True
    with session_factory() as session:
        run = session.query(Run).filter(Run.schedule_id == schedule_id).one()
        fire = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items[0]
        assert fire.status == FireStatus.QUEUED
        assert run.schedule_fire_id == fire.id
        assert run.status == "running"
        assert run.last_claimed_at is not None
        assert executed_run_ids == [run.id]


def test_schedule_materializer_overlap_skip_and_misfire_skip(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    overlap_package_id, overlap_schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_overlap_package",
        next_fire_at=now,
        overlap_policy=OverlapPolicy.SKIP,
    )
    with session_factory() as session:
        active_run = Run(
            target_kind="workflowPackage",
            target_id=overlap_package_id,
            target_key="schedule_materializer_overlap_package",
            target_version=1,
            workflow_package_id=overlap_package_id,
            workflow_package_key="schedule_materializer_overlap_package",
            workflow_package_workflow_key="runtime_workflow",
            schedule_id=overlap_schedule_id,
            input={},
            status="queued",
            queued_at=now - timedelta(minutes=5),
        )
        active_run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=overlap_package_id,
            workflow_package_key="schedule_materializer_overlap_package",
            workflow_package_name="schedule_materializer_overlap_package",
            workflow_package_description="",
            workflow_package_status="active",
            workflow_key="runtime_workflow",
            workflow_name="Runtime Workflow",
            workflow_description="",
            manifest_hash="a" * 64,
            compiled_hash="b" * 64,
            manifest_source=(
                "apiVersion: signaldeck.workflowPackage/v1\n"
                "key: schedule_materializer_overlap_package\n"
            ),
            package_definition={"metadata": {"key": "schedule_materializer_overlap_package"}},
            compiled_plan={"workflows": [{"key": "runtime_workflow"}]},
            extension_dependencies=[],
            local_resource_refs={"workflows": ["runtime_workflow"]},
            input_schema={},
            launch_parameters={},
            resolved_model_connections=[],
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(active_run)
        session.commit()

    overlap_result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert overlap_result.skipped_count == 1
    with session_factory() as session:
        overlap_fires = (
            WorkflowPackageScheduleService(session).list_fire_history(overlap_schedule_id).items
        )
        overlap_runs = session.query(Run).filter(Run.schedule_id == overlap_schedule_id).all()
        assert len(overlap_fires) == 1
        assert overlap_fires[0].status == FireStatus.SKIPPED
        assert overlap_fires[0].skip_reason == "schedule_overlap_active"
        assert len(overlap_runs) == 1

    _, misfire_schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_misfire_package",
        next_fire_at=now - timedelta(hours=3),
        misfire_policy=MisfirePolicy.SKIP,
    )
    misfire_result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert misfire_result.skipped_count == 1
    with session_factory() as session:
        misfire_fires = (
            WorkflowPackageScheduleService(session).list_fire_history(misfire_schedule_id).items
        )
        misfire_runs = session.query(Run).filter(Run.schedule_id == misfire_schedule_id).all()
        misfire_schedule = WorkflowPackageScheduleService(session).get_schedule(misfire_schedule_id)
        assert len(misfire_fires) == 1
        assert misfire_fires[0].status == FireStatus.SKIPPED
        assert misfire_fires[0].scheduled_for == now
        assert misfire_fires[0].skip_reason == "schedule_misfire_skipped"
        assert misfire_schedule.next_fire_at == now + timedelta(hours=1)
        assert misfire_runs == []


def test_schedule_materializer_catch_up_one_queues_latest_eligible_misfire(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 5, tzinfo=UTC)
    expected_fire = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    _, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_catch_up_one_package",
        next_fire_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
        misfire_policy=MisfirePolicy.CATCH_UP_ONE,
        misfire_grace_seconds=7200,
    )

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert result.queued_count == 1
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        schedule = WorkflowPackageScheduleService(session).get_schedule(schedule_id)
        assert len(fires) == 1
        assert len(runs) == 1
        assert fires[0].status == FireStatus.QUEUED
        assert fires[0].scheduled_for == expected_fire
        assert runs[0].scheduled_for == expected_fire
        assert schedule.next_fire_at == expected_fire + timedelta(hours=1)


def test_schedule_materializer_overlap_queue_creates_run_when_prior_run_active(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    package_id, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_overlap_queue_package",
        next_fire_at=now,
        overlap_policy=OverlapPolicy.QUEUE,
    )
    with session_factory() as session:
        active_run = Run(
            target_kind="workflowPackage",
            target_id=package_id,
            target_key="schedule_materializer_overlap_queue_package",
            target_version=1,
            workflow_package_id=package_id,
            workflow_package_key="schedule_materializer_overlap_queue_package",
            workflow_package_workflow_key="runtime_workflow",
            schedule_id=schedule_id,
            input={},
            status="running",
            started_at=now - timedelta(minutes=5),
        )
        active_run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=package_id,
            workflow_package_key="schedule_materializer_overlap_queue_package",
            workflow_package_name="schedule_materializer_overlap_queue_package",
            workflow_package_description="",
            workflow_package_status="active",
            workflow_key="runtime_workflow",
            workflow_name="Runtime Workflow",
            workflow_description="",
            manifest_hash="a" * 64,
            compiled_hash="b" * 64,
            manifest_source=(
                "apiVersion: signaldeck.workflowPackage/v1\n"
                "key: schedule_materializer_overlap_queue_package\n"
            ),
            package_definition={"metadata": {"key": "schedule_materializer_overlap_queue_package"}},
            compiled_plan={"workflows": [{"key": "runtime_workflow"}]},
            extension_dependencies=[],
            local_resource_refs={"workflows": ["runtime_workflow"]},
            input_schema={},
            launch_parameters={},
            resolved_model_connections=[],
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(active_run)
        session.commit()

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert result.queued_count == 1
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        scheduled_runs = [run for run in runs if run.schedule_fire_id is not None]
        assert len(fires) == 1
        assert fires[0].status == FireStatus.QUEUED
        assert len(runs) == 2
        assert len(scheduled_runs) == 1
        assert scheduled_runs[0].status == "queued"
        assert scheduled_runs[0].schedule_fire_id == fires[0].id


def test_schedule_materializer_concurrent_materialization_idempotency(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    _, schedule_id = _create_schedule_materializer_schedule(
        client,
        session_factory,
        package_key="schedule_materializer_idempotency_package",
        next_fire_at=now,
    )

    first = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)
    second = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=now)

    assert first.queued_count == 1
    assert second.changed_count == 0
    with session_factory() as session:
        fires = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items
        runs = session.query(Run).filter(Run.schedule_id == schedule_id).all()
        assert len(fires) == 1
        assert len(runs) == 1
        assert runs[0].schedule_fire_id == fires[0].id
