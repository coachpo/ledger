from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools import get_default_runtime_tool_registry
from app.core.errors import ApiError
from app.extensions.signaldeck_digital_oracle.ownership import DIGITAL_ORACLE_EXTENSION_KEY
from app.extensions.signaldeck_digital_oracle.runtime_types import (
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    OPTIONS_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.model_connection import ModelConnection
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_operation_invocation import RunOperationInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.models.workflow_package_schedule import (
    WorkflowPackageSchedule,
    WorkflowPackageScheduleFire,
)
from app.schemas.model_connection import (
    ModelConnectionProtocolProfile,
    default_model_connection_capabilities,
)
from app.schemas.run import RunOperationInvocationRead, RunPackageResolvedModelConnectionRead
from app.schemas.schedule import (
    DailyRecurrence,
    FireReason,
    FireStatus,
    IntervalRecurrence,
    IntervalUnit,
    ScheduleCreate,
    ScheduleStatus,
)
from app.services.agent_execution_service import AgentExecutionService
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.run_queue_service import RunQueueService
from app.services.run_service import RunService
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_schedule_materializer import WorkflowPackageScheduleMaterializer
from app.services.workflow_package_schedule_service import (
    ScheduleFireMetadata,
    WorkflowPackageScheduleService,
)
from tests.fake_openai_provider import run_fake_openai_provider
from tests.fixtures.workflow_manifests import base_manifest, base_manifest_data, dump_manifest
from tests.test_workflow_package_manifest_http_node import http_node_package_source

_EXPECTED_STRUCTURED_OUTPUT_WARNING = {
    "field": "spec.outputSchemas.summary_output.jsonSchema",
    "code": "model_capability_probe_inconclusive",
    "agentKey": "package_analyst",
    "modelConnectionKey": "package_runtime_model",
    "requirement": "structuredOutput",
    "issue": (
        "This workflow requires structured JSON output, but strict JSON-schema output has "
        "not been proven yet."
    ),
    "severity": "warning",
}
_EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING = {
    "ready": True,
    "blockingErrors": [],
    "warnings": [_EXPECTED_STRUCTURED_OUTPUT_WARNING],
}
_CURRENT_PACKAGE_AUDIT_KEYS = {
    "available",
    "manifestHash",
    "compiledHash",
    "manifestHashMatchesSnapshot",
    "compiledHashMatchesSnapshot",
    "unavailableReason",
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
    total_tokens = 23

    def __init__(self, **kwargs: Any) -> None:
        type(self).init_calls.append(kwargs)
        self.responses = self

    def __enter__(self) -> _RuntimeRecordingOpenAIClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False

    def create(self, **kwargs: Any) -> _RuntimeOpenAIResponse:
        type(self).create_calls.append(kwargs)
        return _RuntimeOpenAIResponse(
            output_text=type(self).output_text,
            total_tokens=type(self).total_tokens,
        )

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []
        cls.create_calls = []
        cls.output_text = '{"summary": "package runtime output"}'
        cls.total_tokens = 23


_TRADINGAGENTS_PRESET_KEY = "tradingagents_advisory_research"
_TRADINGAGENTS_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_TRADINGAGENTS_CANONICAL_SCHEDULES = (
    ("TradingAgents Advisory Research · 1h", "advisory_research"),
    ("TradingAgents Market Research · 1h", "market_research"),
    ("TradingAgents News Research · 1h", "news_research"),
    ("TradingAgents Fundamentals Research · 1h", "fundamentals_research"),
)
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
_DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE = (
    Path(__file__).resolve().parents[2] / "demo" / "digital_oracle_researcher.yaml"
)


def _digital_oracle_researcher_demo_source() -> str:
    return _DIGITAL_ORACLE_RESEARCHER_DEMO_FIXTURE.read_text()


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


def _seeded_tradingagents_package(client: TestClient) -> dict[str, Any]:
    _delete_existing_package(client, _TRADINGAGENTS_PRESET_KEY)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _TRADINGAGENTS_FIXTURE.read_text()},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


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


def _seed_tradingagents_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "test-api-key",
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                name="TradingAgents Primary Model",
                description="Preflight model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=None,
                last_test_ok=None,
                last_test_message=None,
            )
        )
        session.commit()


def _package_source(*, package_key: str = "runtime_package") -> str:
    return base_manifest(package_key=package_key)


_DIGITAL_ORACLE_PHASE1_TOOL_KEYS = (
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    OPTIONS_LOOKUP_TOOL_KEY,
)


class _DigitalOracleGuidanceOutput(BaseModel):
    summary: str
    signals: list[str]
    contradictions: list[str]
    limitations: list[str]
    next_questions: list[str] = Field(alias="nextQuestions")


def _digital_oracle_guidance_package_source(
    *,
    tool_keys: tuple[str, ...] = _DIGITAL_ORACLE_PHASE1_TOOL_KEYS,
) -> str:
    input_schema = {
        "type": "object",
        "properties": {
            "researchQuestion": {"type": "string"},
            "outputLanguage": {"type": "string"},
        },
        "required": ["researchQuestion", "outputLanguage"],
    }
    return base_manifest(
        package_key="digital_oracle_guidance_package",
        package_name="Digital Oracle Guidance Package",
        package_description=None,
        input_schema=input_schema,
        tool_keys=tool_keys,
        tool_profile_key="digital_oracle_phase1_tools",
        tool_profile_name="Digital Oracle Phase 1 Tools",
        output_schema_key="digital_oracle_report",
        output_schemas=[
            {
                "key": "digital_oracle_report",
                "name": "Digital Oracle Report",
                "jsonSchema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "signals": {"type": "array", "items": {"type": "string"}},
                        "contradictions": {"type": "array", "items": {"type": "string"}},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                        "nextQuestions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "summary",
                        "signals",
                        "contradictions",
                        "limitations",
                        "nextQuestions",
                    ],
                },
            }
        ],
        agent_key="digital_oracle_researcher",
        agent_name="Digital Oracle Researcher",
        system_prompt=(
            "Digital Oracle methodology is package-local for this agent.\n"
            "Decompose the research question before calling tools.\n"
            "Call the minimum relevant tools from granted package capability profiles.\n"
            "Compare contradictory signals and disclose warnings or coverage gaps.\n"
            "Synthesize a research-only report; never invent prices, filing facts,\n"
            "event probabilities, or sentiment readings.\n"
        ),
        workflow_key="research",
        workflow_name="Research",
        flow={
            "kind": "step",
            "id": "digital_oracle_research",
            "slot": "report",
            "uses": "digital_oracle_researcher",
            "with": {
                "researchQuestion": "${{ inputs.researchQuestion }}",
                "outputLanguage": "${{ inputs.outputLanguage }}",
            },
        },
        workflow_output={"from": "${{ nodes.digital_oracle_research.outputs.report }}"},
    )


def _package_source_with_optional_contract_inputs(
    *,
    package_key: str,
    workflow_sector_nullable: bool = False,
    agent_sector_nullable: bool = False,
) -> str:
    workflow_schema = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "sector": {"type": ["string", "null"] if workflow_sector_nullable else "string"},
            "horizonDays": {"type": "integer"},
        },
        "required": ["ticker"],
    }
    data = base_manifest_data(
        package_key=package_key,
        package_name="Optional Contract Runtime Package",
        package_description="Runtime package fixture for descendant input contracts.",
        input_schema=workflow_schema,
    )
    data["spec"]["agents"][0]["inputSchema"] = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "sector": {"type": ["string", "null"] if agent_sector_nullable else "string"},
            "horizonDays": {"type": "integer"},
        },
        "required": ["ticker"],
    }
    return dump_manifest(data)


def _create_package(
    client: TestClient,
    *,
    package_key: str = "runtime_package",
) -> dict[str, object]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source(package_key=package_key)},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "test-api-key",
    base_url: str = "https://provider-runtime.example.test/v1",
    model_id: str = "gpt-package-v1",
    api_style: str = "responses",
) -> None:
    with session_factory() as session:
        payload = {} if api_key is None else {"apiKey": api_key}
        session.add(
            ModelConnection(
                key="package_runtime_model",
                name="Package Runtime Model",
                description="Package runtime model binding.",
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="high",
                api_style=api_style,
                timeout_seconds=31,
                secret_payload=payload,
            )
        )
        session.commit()


def test_schedule_delete_service_detaches_direct_run_and_removes_schedule_reads(
    session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime.fromisoformat("2026-06-01T13:00:00+00:00")
    materialized_at = datetime.fromisoformat("2026-06-01T13:00:04+00:00")
    with session_factory() as session:
        package = WorkflowPackage(
            key="schedule_contract_package",
            name="Schedule Contract Package",
            description="Package used by schedule service contracts.",
            manifest_source=_package_source(package_key="schedule_contract_package"),
            manifest_hash="a" * 64,
            package_definition={
                "metadata": {"key": "schedule_contract_package", "name": "Schedule Contract"}
            },
            compiled_plan={"workflows": [{"key": "daily_research"}]},
            compiled_hash="b" * 64,
            extension_dependencies=[],
        )
        session.add(package)
        session.commit()

        service = WorkflowPackageScheduleService(session)
        schedule = service.create_schedule(
            ScheduleCreate(
                package_id=package.id,
                workflow_key="daily_research",
                name="Daily research",
                timezone="UTC",
                recurrence=DailyRecurrence(at_local_time="09:00"),
                input_template={"ticker": "{{vars.ticker}}"},
                template_vars={"ticker": "NVDA"},
            ),
            next_fire_at=scheduled_for,
        )
        fire = service.create_or_get_fire(
            ScheduleFireMetadata(
                schedule_id=schedule.id,
                fire_key="daily-research-2026-06-01T13:00:00Z",
                reason=FireReason.SCHEDULED,
                scheduled_for=scheduled_for,
                scheduled_local_date="2026-06-01",
                scheduled_local_time="09:00",
                scheduled_local_datetime="2026-06-01T09:00:00",
            ),
            status=FireStatus.QUEUED,
            materialized_at=materialized_at,
            rendered_parameters={"ticker": "NVDA"},
        )
        run = Run(
            target_kind="workflowPackage",
            target_id=package.id,
            target_key=package.key,
            target_version=1,
            workflow_package_id=package.id,
            workflow_package_key=package.key,
            workflow_package_workflow_key="daily_research",
            schedule_id=schedule.id,
            schedule_fire_id=fire.id,
            scheduled_for=scheduled_for,
            schedule_reason=FireReason.SCHEDULED.value,
            input={"ticker": "NVDA"},
            status="queued",
            queued_at=materialized_at,
        )
        run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=package.id,
            workflow_package_key=package.key,
            workflow_package_name=package.name,
            workflow_package_description=package.description,
            workflow_package_status=None,
            workflow_key="daily_research",
            workflow_name="Daily Research",
            workflow_description="",
            manifest_hash=package.manifest_hash,
            compiled_hash=package.compiled_hash,
            manifest_source=package.manifest_source,
            package_definition=package.package_definition,
            compiled_plan=package.compiled_plan,
            extension_dependencies=package.extension_dependencies,
            local_resource_refs={"workflows": ["daily_research"]},
            input_schema={},
            launch_parameters={"ticker": "NVDA"},
            resolved_model_connections=[],
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(run)
        session.commit()
        run_id = run.id

        detail = service.get_schedule(schedule.id)
        history = service.list_fire_history(schedule.id)
        service.delete_schedule(schedule.id)
        session.expunge_all()
        detached_run = session.get(Run, run_id)
        remaining_fire_count = (
            session.query(WorkflowPackageScheduleFire)
            .filter(WorkflowPackageScheduleFire.schedule_id == schedule.id)
            .count()
        )

        with pytest.raises(ApiError, match="Schedule not found"):
            service.get_schedule(schedule.id)

        with pytest.raises(ApiError, match="Schedule not found"):
            service.list_fire_history(schedule.id)

    assert schedule.package_key == "schedule_contract_package"
    assert schedule.status == ScheduleStatus.ENABLED
    assert schedule.next_fire_at == scheduled_for
    assert fire.run_id is None
    assert detail.latest_fire_id == fire.id
    assert detail.latest_run_id == run_id
    assert detail.latest_status == "queued"
    assert history.items[0].id == fire.id
    assert history.items[0].run_id == run_id
    assert detached_run is not None
    assert detached_run.schedule_id is None
    assert detached_run.schedule_fire_id is None
    assert detached_run.scheduled_for == scheduled_for
    assert detached_run.schedule_reason == FireReason.SCHEDULED.value
    assert detached_run.schedule_provenance is not None
    assert detached_run.schedule_provenance["scheduleId"] == schedule.id
    assert detached_run.schedule_provenance["scheduleFireId"] == fire.id
    assert detached_run.schedule_provenance["scheduleDeletedAt"] is not None
    assert remaining_fire_count == 0


def test_schedule_delete_preserves_direct_runs_descendants_and_run_linked_artifacts(
    session_factory: sessionmaker[Session],
) -> None:
    scheduled_for = datetime.fromisoformat("2026-06-01T13:00:00+00:00")
    materialized_at = datetime.fromisoformat("2026-06-01T13:00:04+00:00")
    preserved_deleted_at = "2026-05-31T12:00:00Z"
    with session_factory() as session:
        package = WorkflowPackage(
            key="schedule_cleanup_package",
            name="Schedule Cleanup Package",
            description="Package used by schedule cleanup tests.",
            manifest_source=_package_source(package_key="schedule_cleanup_package"),
            manifest_hash="c" * 64,
            package_definition={
                "metadata": {"key": "schedule_cleanup_package", "name": "Schedule Cleanup"}
            },
            compiled_plan={"workflows": [{"key": "runtime_workflow"}]},
            compiled_hash="d" * 64,
            extension_dependencies=[],
        )
        session.add(package)
        session.commit()

        schedule_service = WorkflowPackageScheduleService(session)
        schedule = schedule_service.create_schedule(
            ScheduleCreate(
                package_id=package.id,
                workflow_key="runtime_workflow",
                name="Daily cleanup",
                timezone="UTC",
                recurrence=DailyRecurrence(at_local_time="09:00"),
                input_template={"ticker": "{{vars.ticker}}"},
                template_vars={"ticker": "NVDA"},
            ),
            next_fire_at=scheduled_for,
        )
        fire = schedule_service.create_or_get_fire(
            ScheduleFireMetadata(
                schedule_id=schedule.id,
                fire_key="daily-cleanup-2026-06-01T13:00:00Z",
                reason=FireReason.SCHEDULED,
                scheduled_for=scheduled_for,
                scheduled_local_date="2026-06-01",
                scheduled_local_time="09:00",
                scheduled_local_datetime="2026-06-01T09:00:00",
            ),
            status=FireStatus.QUEUED,
            materialized_at=materialized_at,
            rendered_parameters={"ticker": "NVDA"},
        )

        def _attach_snapshot(run: Run, *, launch_parameters: dict[str, str]) -> None:
            run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
                workflow_package_id=package.id,
                workflow_package_key=package.key,
                workflow_package_name=package.name,
                workflow_package_description=package.description,
                workflow_package_status=None,
                workflow_key="runtime_workflow",
                workflow_name="Runtime Workflow",
                workflow_description="",
                manifest_hash=package.manifest_hash,
                compiled_hash=package.compiled_hash,
                manifest_source=package.manifest_source,
                package_definition=package.package_definition,
                compiled_plan=package.compiled_plan,
                extension_dependencies=package.extension_dependencies,
                local_resource_refs={"workflows": ["runtime_workflow"]},
                input_schema={},
                launch_parameters=launch_parameters,
                resolved_model_connections=[],
                preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
            )

        direct_queued = Run(
            target_kind="workflowPackage",
            target_id=package.id,
            target_key=package.key,
            target_version=1,
            workflow_package_id=package.id,
            workflow_package_key=package.key,
            workflow_package_workflow_key="runtime_workflow",
            schedule_id=schedule.id,
            scheduled_for=scheduled_for,
            schedule_reason=FireReason.SCHEDULED.value,
            input={"ticker": "NVDA"},
            status="queued",
            queued_at=materialized_at,
        )
        direct_running = Run(
            target_kind="workflowPackage",
            target_id=package.id,
            target_key=package.key,
            target_version=1,
            workflow_package_id=package.id,
            workflow_package_key=package.key,
            workflow_package_workflow_key="runtime_workflow",
            schedule_fire_id=fire.id,
            scheduled_for=scheduled_for,
            schedule_reason=FireReason.MANUAL.value,
            schedule_provenance={
                "scheduleId": schedule.id,
                "scheduleFireId": fire.id,
                "scheduleName": schedule.name,
                "packageId": package.id,
                "packageKey": package.key,
                "workflowKey": schedule.workflow_key,
                "timezone": schedule.timezone,
                "recurrence": {"type": "daily", "atLocalTime": "09:00"},
                "fireKey": fire.fire_key,
                "reason": FireReason.MANUAL.value,
                "scheduledFor": scheduled_for.isoformat().replace("+00:00", "Z"),
                "scheduledLocalDate": fire.scheduled_local_date,
                "scheduledLocalTime": fire.scheduled_local_time,
                "scheduledLocalDateTime": fire.scheduled_local_datetime,
                "materializedAt": materialized_at.isoformat().replace("+00:00", "Z"),
                "scheduleDeletedAt": preserved_deleted_at,
            },
            input={"ticker": "MSFT"},
            status="running",
            queued_at=materialized_at,
            started_at=materialized_at,
        )
        _attach_snapshot(direct_queued, launch_parameters={"ticker": "NVDA"})
        _attach_snapshot(direct_running, launch_parameters={"ticker": "MSFT"})
        session.add_all([direct_queued, direct_running])
        session.flush()

        rerun_descendant = Run(
            target_kind="workflowPackage",
            target_id=package.id,
            target_key=package.key,
            target_version=1,
            workflow_package_id=package.id,
            workflow_package_key=package.key,
            workflow_package_workflow_key="runtime_workflow",
            input={"ticker": "AMZN"},
            status="queued",
            queued_at=materialized_at,
            source_run_id=direct_queued.id,
        )
        _attach_snapshot(rerun_descendant, launch_parameters={"ticker": "AMZN"})
        session.add(rerun_descendant)
        session.flush()

        session.commit()
        direct_queued_id = direct_queued.id
        direct_running_id = direct_running.id
        rerun_descendant_id = rerun_descendant.id

        schedule_service.delete_schedule(schedule.id)
        session.expunge_all()

        detached_direct_queued = session.get(Run, direct_queued_id)
        detached_direct_running = session.get(Run, direct_running_id)
        detached_rerun_descendant = session.get(Run, rerun_descendant_id)
        remaining_fire_count = (
            session.query(WorkflowPackageScheduleFire)
            .filter(WorkflowPackageScheduleFire.schedule_id == schedule.id)
            .count()
        )

        assert detached_direct_queued is not None
        assert detached_direct_running is not None
        assert detached_rerun_descendant is not None
        assert detached_direct_queued.schedule_id is None
        assert detached_direct_queued.schedule_fire_id is None
        assert detached_direct_running.schedule_id is None
        assert detached_direct_running.schedule_fire_id is None
        assert detached_direct_queued.schedule_provenance is not None
        assert detached_direct_queued.schedule_provenance["scheduleId"] == schedule.id
        assert detached_direct_queued.schedule_provenance["scheduleDeletedAt"] is not None
        assert detached_direct_running.schedule_provenance is not None
        assert detached_direct_running.schedule_provenance["scheduleId"] == schedule.id
        assert detached_direct_running.schedule_provenance["scheduleFireId"] == fire.id
        direct_running_deleted_at = detached_direct_running.schedule_provenance["scheduleDeletedAt"]
        assert direct_running_deleted_at == preserved_deleted_at
        assert detached_rerun_descendant.schedule_provenance is None
        assert remaining_fire_count == 0


def test_digital_oracle_package_local_system_prompt_receives_runtime_tool_guidance(
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _digital_oracle_guidance_package_source()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    assert runtime_agent.key == "digital_oracle_researcher"
    assert runtime_agent.system_prompt.startswith(
        "Digital Oracle methodology is package-local for this agent."
    )
    assert [profile.key for profile in runtime_agent.capability_profiles] == [
        "digital_oracle_phase1_tools"
    ]
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }
    assert granted_tool_keys == set(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)

    registry = get_default_runtime_tool_registry()
    guidance = registry.get_guidance(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )

    assert "Digital Oracle methodology" not in guidance
    assert "Digital Oracle methodology is package-local for this agent." in instructions
    assert "Decompose the research question before calling tools." in instructions
    assert "Call the minimum relevant tools" in instructions
    assert "call signaldeck_digital_oracle_prediction_markets_lookup" in instructions
    assert "call signaldeck_digital_oracle_sec_filings_lookup" in instructions
    assert "call signaldeck_digital_oracle_market_sentiment_lookup" in instructions
    assert "call signaldeck_digital_oracle_macro_rates_lookup" in instructions
    assert instructions.index("Digital Oracle methodology") < instructions.index(
        "When you need prediction-market signals"
    )


def test_digital_oracle_researcher_demo_builds_execution_plan_with_package_local_methodology(
    session_factory: sessionmaker[Session],
) -> None:
    manifest_source = _digital_oracle_researcher_demo_source()
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }

    registry = get_default_runtime_tool_registry()
    guidance = registry.get_guidance(granted_tool_keys)
    declarations = registry.get_tool_declarations(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )

    expected_tool_keys = set(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS)

    assert len(plan.steps) == 7
    assert [step.agents[0].agent_key for step in plan.steps if step.agents] == [
        "digital_oracle_signal_researcher",
        "digital_oracle_signal_researcher",
        "digital_oracle_signal_researcher",
        "macro_evidence_collector",
        "web_evidence_collector",
        "sec_metadata_collector",
        "digital_oracle_synthesizer",
    ]
    assert runtime_agent.output_schema.key == "digital_oracle_report"
    assert granted_tool_keys == expected_tool_keys
    assert {declaration.tool_key for declaration in declarations} == granted_tool_keys
    assert "Digital Oracle methodology is package-local for this agent." in instructions
    assert "Decompose each research question" in instructions
    assert "granted evidence sources" in instructions
    assert "Disclose warnings" in instructions
    assert "Never invent filing facts" in instructions
    assert "call signaldeck_digital_oracle_prediction_markets_lookup" in instructions
    assert "call signaldeck_digital_oracle_sec_filings_lookup" in instructions
    assert "call signaldeck_digital_oracle_market_sentiment_lookup" in instructions
    assert "call signaldeck_digital_oracle_macro_rates_lookup" in instructions


def test_digital_oracle_guidance_respects_capability_profile_tool_grants(
    session_factory: sessionmaker[Session],
) -> None:
    granted_profile_tool_keys = (
        PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
        SEC_FILINGS_LOOKUP_TOOL_KEY,
    )
    manifest_source = _digital_oracle_guidance_package_source(
        tool_keys=granted_profile_tool_keys,
    )
    compiled = compile_workflow_package_manifest(manifest_source)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(compiled_plan, "research")
    runtime_agent = plan.steps[0].agents[0].package_runtime_agent
    assert runtime_agent is not None
    granted_tool_keys = {
        tool_key for profile in runtime_agent.capability_profiles for tool_key in profile.tool_keys
    }
    assert granted_tool_keys == set(granted_profile_tool_keys)

    registry = get_default_runtime_tool_registry()
    guidance = registry.get_guidance(granted_tool_keys)
    declarations = registry.get_tool_declarations(granted_tool_keys)

    instructions = AgentExecutionService._build_model_instructions(
        runtime_agent,
        _DigitalOracleGuidanceOutput,
        runtime_tool_guidance=guidance,
    )
    declared_tool_keys = {declaration.tool_key for declaration in declarations}

    assert declared_tool_keys == set(granted_profile_tool_keys)
    assert "signaldeck_digital_oracle_prediction_markets_lookup" in instructions
    assert "signaldeck_digital_oracle_sec_filings_lookup" in instructions
    assert "signaldeck_digital_oracle_market_sentiment_lookup" not in instructions
    assert "When you need broad market sentiment" not in guidance


def test_runtime_profile_normalizes_api_style_and_rejects_mismatch() -> None:
    chat_profile_payload: dict[str, Any] = {
        "key": "chat_model",
        "name": "Chat Model",
        "apiStyle": "chat_completions",
        "baseUrl": "https://chat.example.test/v1",
        "modelId": "gpt-chat",
        "reasoningEffort": None,
        "timeoutSeconds": 45,
        "hasApiKey": True,
    }

    normalized_profile = RunPackageResolvedModelConnectionRead.model_validate(
        chat_profile_payload,
    ).model_dump(mode="json", by_alias=True)

    assert normalized_profile["protocolProfile"] == (
        ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS.value
    )
    assert normalized_profile["apiStyle"] == "chat_completions"
    assert normalized_profile["capabilities"] == default_model_connection_capabilities(
        ModelConnectionProtocolProfile.OPENAI_CHAT_COMPLETIONS,
    ).model_dump(mode="json", by_alias=True)
    assert normalized_profile["outputStrategyPolicy"] == "prefer_strict_schema"
    assert normalized_profile["parallelToolCallsPolicy"] == "serialize"
    assert normalized_profile["reasoningPolicy"] == "allow"
    assert normalized_profile["streamingPolicy"] == "allow"
    assert normalized_profile["probeCacheTtlSeconds"] == 900

    with pytest.raises(ValidationError, match="apiStyle does not match protocolProfile"):
        RunPackageResolvedModelConnectionRead.model_validate(
            {
                **chat_profile_payload,
                "protocolProfile": ModelConnectionProtocolProfile.OPENAI_RESPONSES.value,
            },
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


def _launch_package_run(
    client: TestClient,
    package: dict[str, object],
    *,
    ticker: str = "MSFT",
) -> dict[str, Any]:
    response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "runtime_workflow",
            "parameters": {"ticker": ticker},
        },
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def test_progress_for_queued_run_uses_planned_invocation_counts_in_list_and_detail(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="queued_progress_package")
    launched = _launch_package_run(client, package, ticker="MSFT")
    run_id = int(launched["id"])
    expected_progress = {
        "unit": "invocation",
        "terminalCount": 0,
        "totalCount": 1,
        "percent": 0,
    }

    detail_response = client.get(f"/api/runs/{run_id}")
    list_response = client.get(
        "/api/runs",
        params={"workflowPackageKey": "queued_progress_package"},
    )

    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    assert detail["status"] == "queued"
    assert detail["progress"] == expected_progress
    assert detail["steps"][0]["invocations"][0]["status"] == "pending"
    assert list_response.status_code == 200, list_response.json()
    items = cast(list[dict[str, Any]], list_response.json()["items"])
    assert [item["id"] for item in items] == [run_id]
    assert items[0]["progress"] == expected_progress


def test_queue_read_models_expose_capacity_and_serial_policy_reasons_in_list_and_detail(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="queue_reason_package")
    first_run = _launch_package_run(client, package, ticker="MSFT")
    second_run = _launch_package_run(client, package, ticker="AAPL")
    first_run_id = int(first_run["id"])
    second_run_id = int(second_run["id"])

    first_detail_response = client.get(f"/api/runs/{first_run_id}")
    second_detail_response = client.get(f"/api/runs/{second_run_id}")
    list_response = client.get(
        "/api/runs",
        params={"workflowPackageKey": "queue_reason_package"},
    )

    assert first_detail_response.status_code == 200, first_detail_response.json()
    assert second_detail_response.status_code == 200, second_detail_response.json()
    assert list_response.status_code == 200, list_response.json()
    first_detail = cast(dict[str, Any], first_detail_response.json())
    second_detail = cast(dict[str, Any], second_detail_response.json())
    items = cast(list[dict[str, Any]], list_response.json()["items"])

    assert first_detail["status"] == "queued"
    assert first_detail["queue"] == {
        "state": "waiting",
        "reason": "awaiting-worker-capacity",
        "message": "Eligible to run and waiting for an available scheduler worker.",
        "blockingRunId": None,
    }
    assert second_detail["status"] == "queued"
    assert second_detail["queue"] == {
        "state": "blocked",
        "reason": "blocked-by-package-serial-policy",
        "message": (
            f"Queued behind run #{first_run_id} from the same Workflow Package "
            "because package runs execute one at a time."
        ),
        "blockingRunId": first_run_id,
    }
    assert [item["id"] for item in items] == [second_run_id, first_run_id]
    assert items[0]["status"] == "queued"
    assert items[0]["queue"] == second_detail["queue"]
    assert items[1]["status"] == "queued"
    assert items[1]["queue"] == first_detail["queue"]


def _assert_current_readiness_create_rejected(
    client: TestClient,
    *,
    run_id: int,
    expected_detail_field: str,
) -> None:
    response = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    body = response.json()
    assert response.status_code == 422, body
    assert body["code"] == "validation_error"
    assert body["message"] == "Run descendant validation failed"
    assert any(
        detail.get("field") == expected_detail_field
        for detail in cast(list[dict[str, Any]], body["details"])
    )


def test_rerun_records_canonical_required_workflow_inputs(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_contract_inputs(
                package_key="rerun_optional_payload_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package = cast(dict[str, object], created.json())
    source = _launch_package_run(client, package, ticker="MSFT")
    source_run_id = int(source["id"])

    rerun = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )

    assert rerun.status_code == 201, rerun.json()
    rerun_id = int(rerun.json()["id"])
    with session_factory() as session:
        source_run = session.get(Run, source_run_id)
        rerun_run = session.get(Run, rerun_id)
        rerun_snapshot = session.get(RunWorkflowPackageSnapshot, rerun_id)
        assert source_run is not None
        assert rerun_run is not None
        assert rerun_snapshot is not None
        assert source_run.input == {"ticker": "MSFT"}
        assert rerun_run.input == {"ticker": "AAPL"}
        assert rerun_snapshot.launch_parameters == {"ticker": "AAPL"}


def test_rerun_rejects_non_nullable_null(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = client.post(
        "/api/workflow-packages",
        json={
            "manifestSource": _package_source_with_optional_contract_inputs(
                package_key="rerun_non_nullable_null_package"
            )
        },
    )
    assert created.status_code == 201, created.json()
    package = cast(dict[str, object], created.json())
    source = _launch_package_run(client, package, ticker="MSFT")
    source_run_id = int(source["id"])
    with session_factory() as session:
        runs_before = session.query(Run).count()

    rerun = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL", "sector": None}},
    )

    assert rerun.status_code == 400, rerun.json()
    body = cast(dict[str, Any], rerun.json())
    assert body["code"] == "run_invalid_input"
    assert any(detail["field"] == "sector" for detail in body["details"])
    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def test_operation_invocation_read_shape_for_http_package_run_is_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    for key, value in {
        "slack_webhook_token": "slack-secret-value",
        "body_token": "body-secret-value",
    }.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package['id']}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    step = cast(dict[str, Any], detail["steps"][0])
    operation_invocations = cast(list[dict[str, Any]], step["operationInvocations"])
    request_metadata = cast(dict[str, Any], operation_invocations[0]["requestMetadata"])
    serialized = json.dumps(detail, sort_keys=True)

    assert step["invocations"] == []
    assert len(operation_invocations) == 1
    assert operation_invocations[0]["operationKey"] == "notify_slack"
    assert operation_invocations[0]["operationKind"] == "http"
    assert operation_invocations[0]["outputSchemaRef"] == {
        "scope": "packageLocal",
        "localId": 1,
        "key": "webhook_response",
        "version": 1,
    }
    assert set(operation_invocations[0]) == {
        field.alias or name for name, field in RunOperationInvocationRead.model_fields.items()
    }
    assert operation_invocations[0]["status"] == "pending"
    assert request_metadata["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
        "redacted": True,
    }
    assert request_metadata["body"]["token"] == {
        "from": "secret",
        "key": "body_token",
        "redacted": True,
    }
    assert "slack-secret-value" not in serialized
    assert "body-secret-value" not in serialized
    assert "secretPayload" not in serialized
    with session_factory() as session:
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() == 0
        operation = session.query(RunOperationInvocation).filter_by(run_id=run_id).one()
        assert operation.request_metadata == request_metadata


def test_secret_binding_delete_preserves_historical_detail_and_blocks_future_readiness(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())
    package_id = int(package["id"])
    secret_values = {
        "slack_webhook_token": "slack-delete-secret-value",
        "body_token": "body-delete-secret-value",
    }
    for key, value in secret_values.items():
        secret_response = client.put(
            f"/api/workflow-packages/{package_id}/secret-bindings/{key}",
            json={"value": value},
        )
        assert secret_response.status_code == 200, secret_response.json()

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "MSFT"},
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    with session_factory() as session:
        runs_before_delete = session.query(Run).count()

    delete_response = client.delete(
        f"/api/workflow-packages/{package_id}/secret-bindings/slack_webhook_token"
    )
    assert delete_response.status_code == 204, delete_response.text
    assert delete_response.content == b""

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    serialized_detail = json.dumps(detail, sort_keys=True)
    operation = cast(dict[str, Any], detail["steps"][0]["operationInvocations"][0])
    assert operation["requestMetadata"]["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
        "redacted": True,
    }
    assert operation["requestMetadata"]["body"]["token"] == {
        "from": "secret",
        "key": "body_token",
        "redacted": True,
    }
    assert all(value not in serialized_detail for value in secret_values.values())
    assert "secretPayload" not in serialized_detail

    preflight_response = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )
    assert preflight_response.status_code == 200, preflight_response.json()
    preflight = cast(dict[str, Any], preflight_response.json())
    assert preflight["ready"] is False
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], preflight["blockingErrors"])

    blocked_launch = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={
            "workflowKey": "notify",
            "parameters": {"webhookUrl": "https://example.test/hook", "ticker": "AAPL"},
        },
    )
    assert blocked_launch.status_code == 422, blocked_launch.json()
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], blocked_launch.json()["details"])

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    assert rerun_draft.json()["ready"] is False
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], rerun_draft.json()["blockingErrors"])

    rerun_create = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"webhookUrl": "https://example.test/hook", "ticker": "AAPL"}},
    )
    assert rerun_create.status_code == 422, rerun_create.json()
    assert rerun_create.json()["message"] == "Run descendant validation failed"
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in cast(list[dict[str, Any]], rerun_create.json()["details"])

    with session_factory() as session:
        assert session.query(Run).count() == runs_before_delete
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None


def test_package_run_list_filters_and_detail_provenance_are_secret_safe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key="sk-package-provenance-secret")
    first_package = _create_package(client, package_key="provenance_filter_package")
    second_package = _create_package(client, package_key="other_filter_package")
    first_package_id = cast(int, first_package["id"])

    first_run = _launch_package_run(client, first_package, ticker="MSFT")
    second_run = _launch_package_run(client, second_package, ticker="AAPL")

    by_package_key = client.get(
        "/api/runs",
        params={"workflowPackageKey": "provenance_filter_package"},
    )
    assert by_package_key.status_code == 200, by_package_key.json()
    assert [item["id"] for item in by_package_key.json()["items"]] == [first_run["id"]]

    by_package_id = client.get(
        "/api/runs",
        params={"workflowPackageId": first_package_id},
    )
    assert by_package_id.status_code == 200, by_package_id.json()
    assert [item["id"] for item in by_package_id.json()["items"]] == [first_run["id"]]

    by_workflow_key = client.get("/api/runs", params={"workflowKey": "runtime_workflow"})
    assert by_workflow_key.status_code == 200, by_workflow_key.json()
    assert [item["id"] for item in by_workflow_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    by_model_key = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_model_key.status_code == 200, by_model_key.json()
    assert [item["id"] for item in by_model_key.json()["items"]] == [
        second_run["id"],
        first_run["id"],
    ]

    detail_response = client.get(f"/api/runs/{first_run['id']}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    assert detail["targetKind"] == "workflowPackage"
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert provenance["workflowPackageId"] == first_package["id"]
    assert provenance["workflowPackageKey"] == "provenance_filter_package"
    assert provenance["workflowPackageStatus"] is None
    assert provenance["workflowPackageManifestHash"]
    assert provenance["workflowPackageCompiledHash"]
    assert provenance["workflowPackageManifestHash"] != provenance["workflowPackageCompiledHash"]
    assert provenance["workflowKey"] == "runtime_workflow"
    assert provenance["launchSnapshot"] == {
        "workflowKey": "runtime_workflow",
        "workflowName": "Runtime Workflow",
        "workflowDescription": "",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
        "parameters": {"ticker": "MSFT"},
    }
    assert provenance["localResourceRefs"] == {
        "agents": ["package_analyst"],
        "outputSchemas": ["summary_output"],
        "capabilityProfiles": [],
        "mcpServers": [],
        "workflows": ["runtime_workflow"],
    }
    assert provenance["resolvedModelConnections"] == [
        {
            "key": "package_runtime_model",
            "name": "Package Runtime Model",
            "protocolProfile": "openai_responses",
            "baseUrl": "https://provider-runtime.example.test/v1",
            "modelId": "gpt-package-v1",
            "reasoningEffort": "high",
            "capabilities": default_model_connection_capabilities("openai_responses").model_dump(
                mode="json", by_alias=True
            ),
            "outputStrategyPolicy": "prefer_strict_schema",
            "parallelToolCallsPolicy": "serialize",
            "reasoningPolicy": "allow",
            "streamingPolicy": "allow",
            "probeCacheTtlSeconds": 900,
            "apiStyle": "responses",
            "timeoutSeconds": 31,
            "hasApiKey": True,
        }
    ]
    assert provenance["preflightSummary"] == _EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING
    assert set(provenance["preflightSummary"]) == {"ready", "blockingErrors", "warnings"}
    assert set(provenance["currentPackage"]) == _CURRENT_PACKAGE_AUDIT_KEYS
    assert provenance["currentPackage"]["available"] is True
    assert provenance["currentPackage"]["manifestHashMatchesSnapshot"] is True
    assert provenance["currentPackage"]["compiledHashMatchesSnapshot"] is True
    serialized = json.dumps(detail, sort_keys=True)
    assert "sk-package-provenance-secret" not in serialized
    assert "secretPayload" not in serialized

    rerun_draft = client.get(f"/api/runs/{first_run['id']}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    rerun_provenance = cast(dict[str, Any], rerun_draft.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageKey"] == "provenance_filter_package"
    first_connection = cast(dict[str, Any], rerun_provenance["resolvedModelConnections"][0])
    assert first_connection["protocolProfile"] == "openai_responses"
    assert first_connection["outputStrategyPolicy"] == "prefer_strict_schema"
    assert first_connection["parallelToolCallsPolicy"] == "serialize"
    assert first_connection["reasoningPolicy"] == "allow"
    assert first_connection["streamingPolicy"] == "allow"
    assert first_connection["probeCacheTtlSeconds"] == 900
    assert first_connection["capabilities"] == default_model_connection_capabilities(
        "openai_responses"
    ).model_dump(mode="json", by_alias=True)


def test_new_workflow_package_runs_store_null_snapshot_status_for_fresh_and_rerun(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="null_status_snapshot_package")
    fresh_run = _launch_package_run(client, package, ticker="MSFT")
    fresh_run_id = int(fresh_run["id"])

    fresh_detail_response = client.get(f"/api/runs/{fresh_run_id}")
    assert fresh_detail_response.status_code == 200, fresh_detail_response.json()
    fresh_provenance = cast(dict[str, Any], fresh_detail_response.json()["packageProvenance"])
    assert fresh_provenance["workflowPackageStatus"] is None
    assert set(fresh_provenance["currentPackage"]) == _CURRENT_PACKAGE_AUDIT_KEYS

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        assert source_run is not None
        source_snapshot = source_run.workflow_package_snapshot
        assert source_snapshot is not None
        assert source_snapshot.workflow_package_status is None
        source_snapshot.workflow_package_status = "active"
        session.commit()

    historical_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert historical_source_response.status_code == 200, historical_source_response.json()
    historical_source_provenance = cast(
        dict[str, Any],
        historical_source_response.json()["packageProvenance"],
    )
    assert historical_source_provenance["workflowPackageStatus"] == "active"

    rerun_response = client.post(
        f"/api/runs/{fresh_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])
    assert rerun_provenance["workflowPackageStatus"] is None
    assert set(rerun_provenance["currentPackage"]) == _CURRENT_PACKAGE_AUDIT_KEYS

    stable_source_response = client.get(f"/api/runs/{fresh_run_id}")
    assert stable_source_response.status_code == 200, stable_source_response.json()
    stable_source_provenance = cast(
        dict[str, Any],
        stable_source_response.json()["packageProvenance"],
    )
    assert stable_source_provenance["workflowPackageStatus"] == "active"

    with session_factory() as session:
        source_run = session.get(Run, fresh_run_id)
        rerun = session.get(Run, rerun_id)
        assert source_run is not None
        assert rerun is not None
        assert source_run.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot is not None
        assert source_run.workflow_package_snapshot.workflow_package_status == "active"
        assert rerun.workflow_package_snapshot.workflow_package_status is None


def test_rerun_uses_run_snapshot_after_current_package_mutation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="mutated_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="MSFT")
    source_run_id = int(launched["id"])
    source_detail_response = client.get(f"/api/runs/{source_run_id}")
    assert source_detail_response.status_code == 200, source_detail_response.json()
    source_provenance = cast(dict[str, Any], source_detail_response.json()["packageProvenance"])
    snapshot_compiled_plan = deepcopy(source_provenance["compiledPlan"])
    snapshot_compiled_hash = str(source_provenance["workflowPackageCompiledHash"])

    with session_factory() as session:
        package_row = session.get(WorkflowPackage, package_id)
        assert package_row is not None
        package_row.manifest_hash = "c" * 64
        package_row.compiled_hash = "d" * 64
        package_row.compiled_plan = {"packageKey": "mutated_snapshot_package", "workflows": []}
        session.commit()

    rerun_response = client.post(
        f"/api/runs/{source_run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])
    rerun_detail_response = client.get(f"/api/runs/{rerun_id}")
    assert rerun_detail_response.status_code == 200, rerun_detail_response.json()
    rerun_provenance = cast(dict[str, Any], rerun_detail_response.json()["packageProvenance"])

    by_snapshot_model = client.get(
        "/api/runs",
        params={"modelConnectionKey": "package_runtime_model"},
    )
    assert by_snapshot_model.status_code == 200, by_snapshot_model.json()
    assert [item["id"] for item in by_snapshot_model.json()["items"]] == [
        rerun_id,
        source_run_id,
    ]

    assert rerun_provenance["compiledPlan"] == snapshot_compiled_plan
    assert rerun_provenance["workflowPackageCompiledHash"] == snapshot_compiled_hash
    assert rerun_provenance["launchSnapshot"]["parameters"] == {"ticker": "AAPL"}
    assert set(rerun_provenance["currentPackage"]) == _CURRENT_PACKAGE_AUDIT_KEYS
    assert rerun_provenance["currentPackage"]["available"] is True
    assert rerun_provenance["currentPackage"]["manifestHashMatchesSnapshot"] is False
    assert rerun_provenance["currentPackage"]["compiledHashMatchesSnapshot"] is False

    with session_factory() as session:
        rerun = session.get(Run, rerun_id)
        assert rerun is not None
        assert rerun.workflow_package_snapshot is not None
        assert rerun.workflow_package_snapshot.compiled_plan == snapshot_compiled_plan
        assert rerun.workflow_package_snapshot.launch_parameters == {"ticker": "AAPL"}


def test_package_deletion_deletes_owned_runs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "package deletion output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_owned_runs_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"
    source_invocation = cast(dict[str, Any], succeeded_detail["steps"][0]["invocations"][0])
    assert source_invocation["resolvedInput"] == {"ticker": "NVDA"}

    with session_factory() as session:
        source_run = session.get(Run, run_id)
        assert source_run is not None
        assert source_run.workflow_package_id == package_id
        assert session.query(RunStep).filter_by(run_id=run_id).count() > 0
        assert session.query(RunAgentInvocation).filter_by(run_id=run_id).count() > 0
        session.commit()

    deleted = client.delete(f"/api/workflow-packages/{package_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert client.get(f"/api/runs/{run_id}").status_code == 404

    with session_factory() as session:
        assert session.get(WorkflowPackage, package_id) is None
        assert session.get(Run, run_id) is None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is None
        assert session.query(RunStep).filter(RunStep.run_id == run_id).count() == 0
        assert (
            session.query(RunAgentInvocation).filter(RunAgentInvocation.run_id == run_id).count()
            == 0
        )


def test_deleted_model_connection_preserves_historical_detail_and_blocks_future_readiness(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "deleted connection source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="deleted_connection_snapshot_package")
    package_id = cast(int, package["id"])
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"

    with session_factory() as session:
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection_id = connection.id
        runs_before = session.query(Run).count()

    deleted_connection = client.delete(f"/api/model-connections/{connection_id}")
    assert deleted_connection.status_code == 204, deleted_connection.text
    assert deleted_connection.content == b""

    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    assert provenance["resolvedModelConnections"][0]["key"] == "package_runtime_model"
    assert provenance["currentPackage"]["available"] is True

    preflight_response = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": None, "parameters": {}},
    )
    assert preflight_response.status_code == 200, preflight_response.json()
    preflight = cast(dict[str, Any], preflight_response.json())
    assert preflight["ready"] is False
    assert any(
        detail.get("field") == "spec.agents[0].modelConnection"
        for detail in cast(list[dict[str, Any]], preflight["blockingErrors"])
    )

    launch_response = client.post(
        f"/api/workflow-packages/{package_id}/launches",
        json={"workflowKey": "runtime_workflow", "parameters": {"ticker": "AAPL"}},
    )
    assert launch_response.status_code == 422, launch_response.json()
    assert launch_response.json()["message"] == "Workflow package launch validation failed"
    assert any(
        detail.get("field") == "spec.agents[0].modelConnection"
        for detail in cast(list[dict[str, Any]], launch_response.json()["details"])
    )

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    draft = cast(dict[str, Any], rerun_draft.json())
    assert draft["ready"] is False
    assert any(
        detail.get("field") == "spec.agents[0].modelConnection"
        for detail in cast(list[dict[str, Any]], draft["blockingErrors"])
    )
    draft_provenance = cast(dict[str, Any], draft["packageProvenance"])
    assert draft_provenance["resolvedModelConnections"][0]["key"] == "package_runtime_model"

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None
        assert session.get(WorkflowPackage, package_id) is not None
        assert session.get(Run, run_id) is not None
        assert session.get(RunWorkflowPackageSnapshot, run_id) is not None

    _assert_current_readiness_create_rejected(
        client,
        run_id=run_id,
        expected_detail_field="spec.agents[0].modelConnection",
    )

    with session_factory() as session:
        assert session.query(Run).count() == runs_before


def test_rerun_executes_frozen_runtime_profile_after_live_model_connection_drift(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    _seed_model_connection(session_factory)
    package = _create_package(client, package_key="drifted_connection_snapshot_package")
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"

    with session_factory() as session:
        source_snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert source_snapshot is not None
        source_profile = cast(dict[str, Any], source_snapshot.resolved_model_connections[0])
        assert source_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
        assert source_profile["modelId"] == "gpt-package-v1"
        assert source_profile["reasoningEffort"] == "high"
        assert source_profile["timeoutSeconds"] == 31
        source_snapshot.preflight_summary = {
            "ready": False,
            "blockingErrors": [{"field": "historical", "issue": "stale source readiness"}],
            "warnings": [],
        }
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-live-drift.example.com/v1"
        connection.model_id = "gpt-package-live-drift"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "sk-package-runtime-live"}
        session.commit()
        runs_before = session.query(Run).count()

    drifted_detail_response = client.get(f"/api/runs/{run_id}")
    assert drifted_detail_response.status_code == 200, drifted_detail_response.json()
    drifted_detail = cast(dict[str, Any], drifted_detail_response.json())
    drifted_provenance = cast(dict[str, Any], drifted_detail["packageProvenance"])
    drifted_profile = cast(dict[str, Any], drifted_provenance["resolvedModelConnections"][0])
    assert drifted_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
    assert drifted_profile["modelId"] == "gpt-package-v1"
    assert drifted_profile["reasoningEffort"] == "high"
    assert drifted_profile["timeoutSeconds"] == 31
    assert "runtime-live-drift" not in json.dumps(drifted_detail, sort_keys=True)
    assert "gpt-package-live-drift" not in json.dumps(drifted_detail, sort_keys=True)

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    draft = cast(dict[str, Any], rerun_draft.json())
    assert draft["ready"] is True
    assert draft["blockingErrors"] == []
    draft_provenance = cast(dict[str, Any], draft["packageProvenance"])
    assert draft_provenance["preflightSummary"]["ready"] is False
    draft_profile = cast(dict[str, Any], draft_provenance["resolvedModelConnections"][0])
    assert draft_profile["baseUrl"] == "https://provider-runtime.example.test/v1"
    assert draft_profile["modelId"] == "gpt-package-v1"
    assert draft_profile["reasoningEffort"] == "high"
    assert draft_profile["timeoutSeconds"] == 31

    rerun_response = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])

    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift rerun output"}'
    with session_factory() as session:
        RunService(session, session_factory).execute_run(rerun_id)
    rerun_detail = _wait_for_run(client, rerun_id)
    assert rerun_detail["status"] == "succeeded"
    rerun_init_call = _RuntimeRecordingOpenAIClient.init_calls[-1]
    assert rerun_init_call["api_key"] == "sk-package-runtime-live"
    assert rerun_init_call["base_url"] == "https://provider-runtime.example.test/v1"
    assert rerun_init_call["timeout"] == 31.0
    rerun_create_call = _RuntimeRecordingOpenAIClient.create_calls[-1]
    assert rerun_create_call["model"] == "gpt-package-v1"
    assert rerun_create_call["reasoning"]["effort"] == "high"

    with session_factory() as session:
        rerun_snapshot = session.get(RunWorkflowPackageSnapshot, rerun_id)
        assert rerun_snapshot is not None
        assert (
            rerun_snapshot.resolved_model_connections == source_snapshot.resolved_model_connections
        )
        assert (
            rerun_snapshot.preflight_summary == _EXPECTED_CURRENT_READINESS_WITH_STRUCTURED_WARNING
        )
        assert session.query(Run).count() == runs_before + 1


def test_rerun_drift_keeps_literal_custom_root_request_paths(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    request_log: list[dict[str, Any]] = []
    with run_fake_openai_provider(base_path="/codex/v1", request_log=request_log) as base_url:
        _seed_model_connection(session_factory, base_url=base_url)
        package = _create_package(client, package_key="drifted_connection_path_package")
        launched = _launch_package_run(client, package, ticker="NVDA")
        run_id = int(launched["id"])

        _drain_run_queue(session_factory)
        source_detail = _wait_for_run(client, run_id)
        assert source_detail["status"] == "succeeded"

        with session_factory() as session:
            source_snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
            assert source_snapshot is not None
            source_profile = cast(dict[str, Any], source_snapshot.resolved_model_connections[0])
            assert source_profile["baseUrl"] == base_url
            connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
            connection.base_url = "https://runtime-live-drift.example.com/v1"
            connection.model_id = "gpt-package-live-drift"
            connection.reasoning_effort = "low"
            connection.timeout_seconds = 91
            session.commit()

        rerun_response = client.post(
            f"/api/runs/{run_id}/reruns",
            json={"parameters": {"ticker": "AAPL"}},
        )
        assert rerun_response.status_code == 201, rerun_response.json()
        rerun_id = int(rerun_response.json()["id"])

        with session_factory() as session:
            RunService(session, session_factory).execute_run(rerun_id)
        rerun_detail = _wait_for_run(client, rerun_id)
        assert rerun_detail["status"] == "succeeded"

        with session_factory() as session:
            rerun_snapshot = session.get(RunWorkflowPackageSnapshot, rerun_id)
            assert rerun_snapshot is not None
            rerun_profile = cast(dict[str, Any], rerun_snapshot.resolved_model_connections[0])
            assert rerun_profile["baseUrl"] == base_url

    request_paths = [cast(str, entry["path"]) for entry in request_log]
    assert request_paths == [
        "/codex/v1/responses",
        "/codex/v1/responses",
    ]
    assert "/codex/v1/v1/responses" not in request_paths
    assert "/v1/responses" not in request_paths
    assert not any(path.endswith("/chat/completions") for path in request_paths)


def test_rerun_preserves_literal_trailing_slash_base_url_after_live_model_connection_drift(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "drift source output"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    literal_base_url = "https://new.sharedchat.cc/codex/v1/"

    _seed_model_connection(session_factory, base_url=literal_base_url)
    package = _create_package(client, package_key="drifted_connection_trailing_slash_package")
    launched = _launch_package_run(client, package, ticker="NVDA")
    run_id = int(launched["id"])

    _drain_run_queue(session_factory)
    succeeded_detail = _wait_for_run(client, run_id)
    assert succeeded_detail["status"] == "succeeded"

    with session_factory() as session:
        source_snapshot = session.get(RunWorkflowPackageSnapshot, run_id)
        assert source_snapshot is not None
        source_profile = cast(dict[str, Any], source_snapshot.resolved_model_connections[0])
        assert source_profile["baseUrl"] == literal_base_url
        connection = session.query(ModelConnection).filter_by(key="package_runtime_model").one()
        connection.base_url = "https://runtime-live-drift.example.com/v1"
        connection.model_id = "gpt-package-live-drift"
        connection.reasoning_effort = "low"
        connection.timeout_seconds = 91
        connection.secret_payload = {"apiKey": "sk-package-runtime-live"}
        session.commit()

    rerun_response = client.post(
        f"/api/runs/{run_id}/reruns",
        json={"parameters": {"ticker": "AAPL"}},
    )
    assert rerun_response.status_code == 201, rerun_response.json()
    rerun_id = int(rerun_response.json()["id"])

    rerun_draft = client.get(f"/api/runs/{run_id}/rerun-draft")
    assert rerun_draft.status_code == 200, rerun_draft.json()
    assert rerun_draft.json()["packageProvenance"]["resolvedModelConnections"][0]["baseUrl"] == (
        literal_base_url
    )

    _RuntimeRecordingOpenAIClient.reset()
    with session_factory() as session:
        RunService(session, session_factory).execute_run(rerun_id)
    rerun_detail = _wait_for_run(client, rerun_id)
    assert rerun_detail["status"] == "succeeded"
    rerun_init_call = _RuntimeRecordingOpenAIClient.init_calls[-1]
    assert rerun_init_call["base_url"] == literal_base_url


def test_runtime_profile_run_fixture_9201_exposes_secret_safe_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    fixture_run_id = 9201
    fixture_package_id = 9101
    fixture_target_key = "runtime-profile-run"
    manifest_source = _package_source(package_key="runtime_profile_package")
    compiled = compile_workflow_package_manifest(manifest_source)
    package_definition = cast(dict[str, Any], deepcopy(compiled["packageDefinition"]))
    compiled_plan = cast(dict[str, Any], deepcopy(compiled["compiledPlan"]))
    package_definition["metadata"]["key"] = fixture_target_key
    compiled_plan["packageKey"] = fixture_target_key
    workflow = cast(dict[str, Any], compiled_plan["workflows"][0])
    capabilities = default_model_connection_capabilities("openai_chat_completions").model_dump(
        mode="json", by_alias=True
    )
    capabilities["strictJsonSchemaOutput"]["status"] = "unsupported"
    resolved_model_connections = [
        {
            "key": "package_runtime_model",
            "name": "Runtime Profile Model",
            "protocolProfile": "openai_chat_completions",
            "baseUrl": "https://runtime-profile.example.test/v1",
            "modelId": "fake-runtime-profile",
            "reasoningEffort": None,
            "capabilities": capabilities,
            "outputStrategyPolicy": "allow_json_object_validation",
            "parallelToolCallsPolicy": "serialize",
            "reasoningPolicy": "forbid",
            "streamingPolicy": "forbid",
            "probeCacheTtlSeconds": 120,
            "apiStyle": "chat_completions",
            "timeoutSeconds": 45,
            "hasApiKey": True,
        }
    ]

    with session_factory() as session:
        package = WorkflowPackage(
            id=fixture_package_id,
            key=fixture_target_key,
            name="Runtime Profile Package",
            description="Deterministic run-detail fixture for runtime profile provenance.",
            manifest_source=manifest_source,
            manifest_hash=str(compiled["manifestHash"]),
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=str(compiled["compiledHash"]),
            extension_dependencies=[],
        )
        session.add(package)
        session.flush()
        run = Run(
            id=fixture_run_id,
            target_kind="workflowPackage",
            target_id=fixture_package_id,
            target_key=fixture_target_key,
            target_version=1,
            workflow_package_id=fixture_package_id,
            workflow_package_key=fixture_target_key,
            workflow_package_workflow_key="runtime_workflow",
            extension_dependencies=[],
            input={"ticker": "MSFT"},
            status="succeeded",
            source_run_id=None,
            final_output={"summary": "runtime profile fixture output"},
            total_tokens=17,
            inherited_tokens=0,
            executed_tokens=17,
            trace_id="trace-runtime-profile",
            error=None,
        )
        run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
            workflow_package_id=fixture_package_id,
            workflow_package_key=fixture_target_key,
            workflow_package_name="Runtime Profile Package",
            workflow_package_description=package.description,
            workflow_package_status=None,
            workflow_key="runtime_workflow",
            workflow_name=str(workflow["name"]),
            workflow_description=str(workflow.get("description") or ""),
            manifest_hash=str(compiled["manifestHash"]),
            compiled_hash=str(compiled["compiledHash"]),
            manifest_source=manifest_source,
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            extension_dependencies=[],
            local_resource_refs={
                "agents": ["package_analyst"],
                "outputSchemas": ["summary_output"],
                "capabilityProfiles": [],
                "mcpServers": [],
                "workflows": ["runtime_workflow"],
            },
            input_schema=deepcopy(workflow["inputSchema"]),
            launch_parameters={"ticker": "MSFT"},
            resolved_model_connections=resolved_model_connections,
            preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
        )
        session.add(run)
        session.commit()

    detail_response = client.get(f"/api/runs/{fixture_run_id}")

    assert detail_response.status_code == 200, detail_response.json()
    detail = cast(dict[str, Any], detail_response.json())
    provenance = cast(dict[str, Any], detail["packageProvenance"])
    profile = cast(dict[str, Any], provenance["resolvedModelConnections"][0])
    serialized = json.dumps(detail, sort_keys=True)
    assert detail["id"] == fixture_run_id
    assert detail["targetKey"] == fixture_target_key
    assert provenance["workflowPackageKey"] == fixture_target_key
    assert provenance["launchSnapshot"]["parameters"] == {"ticker": "MSFT"}
    assert provenance["preflightSummary"] == {"ready": True, "blockingErrors": [], "warnings": []}
    assert provenance["currentPackage"]["available"] is True
    assert provenance["currentPackage"]["manifestHashMatchesSnapshot"] is True
    assert provenance["currentPackage"]["compiledHashMatchesSnapshot"] is True
    assert profile == resolved_model_connections[0]
    assert "secretPayload" not in serialized
    assert "sk-" not in serialized
    assert "providerPayload" not in serialized


def _create_tradingagents_package(client: TestClient) -> dict[str, Any]:
    return _seeded_tradingagents_package(client)


def _tradingagents_parameters() -> dict[str, object]:
    return {
        "ticker": "MSFT",
        "asOfDate": "2026-05-15",
        "horizonDays": 30,
        "benchmarkSymbol": "SPY",
    }


def test_seeded_tradingagents_advisory_manifest_exports_after_startup(
    client: TestClient,
) -> None:
    package = _seeded_tradingagents_package(client)

    response = client.get(f"/api/workflow-packages/{package['id']}/manifest")

    assert response.status_code == 200, response.json()
    manifest = cast(dict[str, Any], response.json())
    assert manifest["packageId"] == package["id"]
    assert manifest["packageKey"] == _TRADINGAGENTS_PRESET_KEY
    assert _TRADINGAGENTS_PRESET_KEY in manifest["manifestSource"]
    assert manifest["packageDefinition"]["metadata"]["key"] == _TRADINGAGENTS_PRESET_KEY

    exported = client.get(f"/api/workflow-packages/{package['id']}/export")
    assert exported.status_code == 200, exported.text


def _mcp_only_package_source(package_key: str) -> str:
    input_schema = {"type": "object"}
    return base_manifest(
        package_key=package_key,
        package_name="MCP Dependency Snapshot Fixture",
        package_description=None,
        input_schema=input_schema,
        output_schema_key="mcp_output",
        output_schemas=[
            {
                "key": "mcp_output",
                "name": "MCP Output",
                "jsonSchema": {"type": "object"},
            }
        ],
        mcp_servers=[
            {
                "key": "exa",
                "name": "Exa Web Search",
                "transport": "http-sse",
                "url": "https://mcp.exa.ai/mcp?tools=web_search_exa",
                "toolKeys": ["web_search_exa"],
            }
        ],
        agent_key="mcp_agent",
        agent_name="MCP Agent",
        model_connection="tradingagents_primary_model",
        system_prompt="Use package-private MCP search and return JSON.",
        workflow_key="mcp_flow",
        workflow_name="MCP Flow",
        flow={
            "kind": "step",
            "id": "mcp_step",
            "slot": "result",
            "uses": "mcp_agent",
            "with": {},
        },
        workflow_output={"from": "${{ nodes.mcp_step.outputs.result }}"},
    )


def test_digital_oracle_guidance_launch_persists_digital_oracle_extension_dependencies(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    create_response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _digital_oracle_guidance_package_source()},
    )
    assert create_response.status_code == 201, create_response.json()
    package = cast(dict[str, Any], create_response.json())

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "research",
            "parameters": {
                "researchQuestion": "Will rates fall this quarter?",
                "outputLanguage": "English",
            },
        },
    )

    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    dependencies = cast(list[dict[str, object]], detail_response.json()["extensionDependencies"])
    assert FINANCE_WORKSPACE_EXTENSION_KEY not in json.dumps(dependencies, sort_keys=True)
    assert dependencies == [
        {
            "extensionKey": DIGITAL_ORACLE_EXTENSION_KEY,
            "surfaces": sorted(
                [
                    *[f"runtime.tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                    *[f"tool.{tool_key}" for tool_key in _DIGITAL_ORACLE_PHASE1_TOOL_KEYS],
                ]
            ),
            "fields": [
                f"spec.capabilityProfiles.digital_oracle_phase1_tools.toolKeys[{index}]"
                for index in range(len(_DIGITAL_ORACLE_PHASE1_TOOL_KEYS))
            ],
        }
    ]
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        assert package_row.extension_dependencies == dependencies


def test_tradingagents_advisory_research_launch_persists_extension_dependencies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )

    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    detail = detail_response.json()
    dependencies = cast(list[dict[str, object]], detail["extensionDependencies"])
    assert dependencies
    assert set(dependencies[0]) == {"extensionKey", "surfaces", "fields"}
    assert dependencies[0]["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    surfaces = set(cast(list[str], dependencies[0]["surfaces"]))
    assert {
        "provider.quote",
        "provider.socialSentiment",
        "runtime.tool.signaldeck.finance.market_data.quote_lookup",
        "tool.signaldeck.finance.market_data.quote_lookup",
    } <= surfaces
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        assert package_row.extension_dependencies == dependencies


def test_run_dependency_snapshot_is_copied_from_current_package(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        frozen_dependencies = deepcopy(package_row.extension_dependencies)
        compiled_plan = deepcopy(package_row.compiled_plan)
        for profile in cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"]):
            profile["toolKeys"] = []
        package_row.compiled_plan = compiled_plan
        session.commit()

    launch_response = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "workflowKey": "advisory_research",
            "parameters": _tradingagents_parameters(),
        },
    )
    assert launch_response.status_code == 201, launch_response.json()
    run_id = int(launch_response.json()["id"])
    detail_response = client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json()["extensionDependencies"] == frozen_dependencies

    with session_factory() as session:
        package_row = session.query(WorkflowPackage).filter_by(id=int(package["id"])).one()
        package_row.extension_dependencies = []
        session.commit()

    stable_detail_response = client.get(f"/api/runs/{run_id}")
    assert stable_detail_response.status_code == 200, stable_detail_response.json()
    assert stable_detail_response.json()["extensionDependencies"] == frozen_dependencies


def test_tradingagents_materializer_persists_workflow_key_snapshots_for_canonical_schedules(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_tradingagents_model_connection(session_factory)
    package = _create_tradingagents_package(client)
    package_id = cast(int, package["id"])
    materialized_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
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
        snapshots = (
            session.query(RunWorkflowPackageSnapshot)
            .filter(RunWorkflowPackageSnapshot.run_id.in_([run.id for run in runs]))
            .order_by(RunWorkflowPackageSnapshot.run_id)
            .all()
        )
        snapshots_by_run_id = {snapshot.run_id: snapshot for snapshot in snapshots}
        runs_by_schedule_id = {cast(int, run.schedule_id): run for run in runs}

        assert len(runs) == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)
        assert len(snapshots) == len(_TRADINGAGENTS_CANONICAL_SCHEDULES)
        for schedule in schedules:
            run = runs_by_schedule_id[schedule.id]
            snapshot = snapshots_by_run_id[run.id]
            fire = WorkflowPackageScheduleService(session).list_fire_history(schedule.id).items[0]

            assert fire.status == FireStatus.QUEUED
            assert run.status == "queued"
            assert run.schedule_id == schedule.id
            assert run.schedule_fire_id == fire.id
            assert run.scheduled_for == materialized_at
            assert run.workflow_package_workflow_key == schedule.workflow_key
            assert snapshot.workflow_package_id == package_id
            assert snapshot.workflow_key == schedule.workflow_key
            assert snapshot.launch_parameters == run.input
            assert schedule.next_fire_at == materialized_at + timedelta(hours=1)


def test_scheduled_run_snapshot_materializer_persists_schedule_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    scheduled_for = datetime.fromisoformat("2026-06-01T13:00:00+00:00")
    created = _create_package(client, package_key="scheduled_run_snapshot_package")
    package_id = cast(int, created["id"])
    with session_factory() as session:
        schedule = WorkflowPackageScheduleService(session).create_schedule(
            ScheduleCreate(
                package_id=package_id,
                workflow_key="runtime_workflow",
                name="Scheduled snapshot run",
                timezone="UTC",
                recurrence=IntervalRecurrence(every=1, unit=IntervalUnit.HOURS),
                input_template={"ticker": "{{vars.ticker}}"},
                template_vars={"ticker": "MSFT"},
            ),
            next_fire_at=scheduled_for,
        )
        schedule_id = schedule.id

    result = WorkflowPackageScheduleMaterializer(session_factory).materialize_due(now=scheduled_for)

    assert result.queued_count == 1
    with session_factory() as session:
        run = session.query(Run).filter(Run.schedule_id == schedule_id).one()
        snapshot = (
            session.query(RunWorkflowPackageSnapshot)
            .filter(RunWorkflowPackageSnapshot.run_id == run.id)
            .one()
        )
        schedule_row = session.get(WorkflowPackageSchedule, schedule_id)
        fire = WorkflowPackageScheduleService(session).list_fire_history(schedule_id).items[0]
        detail = RunService(session, session_factory).get_run(run.id)
        run_id = run.id
        fire_id = fire.id

        assert schedule_row is not None
        assert run.target_kind == "workflowPackage"
        assert run.status == "queued"
        assert run.schedule_fire_id == fire.id
        assert run.scheduled_for == scheduled_for
        assert run.schedule_reason == FireReason.SCHEDULED.value
        assert run.input == {"ticker": "MSFT"}
        assert fire.status == FireStatus.QUEUED
        assert snapshot.workflow_package_id == package_id
        assert snapshot.workflow_package_key == "scheduled_run_snapshot_package"
        assert snapshot.workflow_key == "runtime_workflow"
        assert snapshot.launch_parameters == {"ticker": "MSFT"}
        assert run.schedule_provenance == {
            "scheduleId": schedule_id,
            "scheduleFireId": fire.id,
            "scheduleName": schedule_row.name,
            "packageId": package_id,
            "packageKey": "scheduled_run_snapshot_package",
            "workflowKey": schedule_row.workflow_key,
            "timezone": schedule_row.timezone,
            "recurrence": deepcopy(schedule_row.recurrence),
            "fireKey": fire.fire_key,
            "reason": FireReason.SCHEDULED.value,
            "scheduledFor": "2026-06-01T13:00:00Z",
            "scheduledLocalDate": fire.scheduled_local_date,
            "scheduledLocalTime": fire.scheduled_local_time,
            "scheduledLocalDateTime": fire.scheduled_local_datetime,
            "materializedAt": "2026-06-01T13:00:00Z",
            "scheduleDeletedAt": None,
        }
        assert detail.schedule_id == schedule_id
        assert detail.schedule_fire_id == fire.id
        assert detail.scheduled_for == scheduled_for
        assert detail.schedule_reason == FireReason.SCHEDULED.value
        assert detail.package_provenance is not None
        assert detail.package_provenance.launch_snapshot is not None
        assert detail.package_provenance.launch_snapshot.parameters == {"ticker": "MSFT"}

    api_detail_response = client.get(f"/api/runs/{run_id}")
    assert api_detail_response.status_code == 200, api_detail_response.json()
    api_detail = cast(dict[str, Any], api_detail_response.json())
    assert api_detail["scheduleId"] == schedule_id
    assert api_detail["scheduleFireId"] == fire_id
    assert api_detail["scheduledFor"] == "2026-06-01T13:00:00Z"
    assert api_detail["scheduleReason"] == "scheduled"

    api_list_response = client.get("/api/runs", params={"workflowPackageId": package_id})
    assert api_list_response.status_code == 200, api_list_response.json()
    api_items = cast(list[dict[str, Any]], api_list_response.json()["items"])
    api_item = next(item for item in api_items if item["id"] == run_id)
    assert api_item["scheduleId"] == schedule_id
    assert api_item["scheduleFireId"] == fire_id
    assert api_item["scheduledFor"] == "2026-06-01T13:00:00Z"
    assert api_item["scheduleReason"] == "scheduled"
    assert api_item["workflowKey"] == "runtime_workflow"
