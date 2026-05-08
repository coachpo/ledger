from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.report import Report
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.capability import CapabilityRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.run import RunAgentInvocationRead, RunRead, RunStatus
from app.services.capability_service import REPORT_MEMORY_WRITE_TOOL_KEY
from app.services.model_connection_service import ModelConnectionService
from app.services.run_service import RunService

UTC_TZ = timezone.utc  # noqa: UP017


def _build_skill(*, key: str, version: int, status: str) -> Capability:
    return Capability(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Capability description",
        tool_keys=[f"{key}.lookup"],
    )


def _build_output_schema(
    *,
    key: str,
    version: int,
    status: str,
    kind: str = "standalone",
    registry_refs: list[str] | None = None,
) -> OutputSchema:
    return OutputSchema(
        key=key,
        version=version,
        status=status,
        kind=kind,
        name=f"{key}-{version}",
        description="Output schema description",
        json_schema={"type": "object", "properties": {"headline": {"type": "string"}}},
        registry_refs=list(registry_refs or []),
    )


def _build_mcp_server(
    *,
    key: str,
    version: int,
    status: str,
    transport: str,
    enabled: bool = True,
) -> McpServer:
    return McpServer(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="MCP server description",
        transport=transport,
        command="python -m market_data" if transport == "stdio" else None,
        url="https://example.com/mcp" if transport == "http-sse" else None,
        auth={"apiKey": f"token-{version}"},
        enabled=enabled,
    )


def _build_model_connection(
    *,
    name: str,
    key: str | None = None,
    status: str,
    api_key: str,
    model_id: str = "gpt-5.4-mini",
    api_style: str = "responses",
) -> ModelConnection:
    return ModelConnection(
        key=key or name.strip().lower().replace(" ", "_"),
        status=status,
        name=name,
        description=f"{name} description",
        base_url="https://api.openai.com/v1",
        organization=None,
        project=None,
        model_id=model_id,
        reasoning_effort="medium",
        api_style=api_style,
        timeout_seconds=60,
        secret_payload={"apiKey": api_key},
    )


def _build_agent(
    *,
    key: str,
    version: int,
    status: str,
    output_schema: OutputSchema,
    capabilities: list[Capability],
    mcp_servers: list[McpServer],
    budget_usd: Decimal,
    model_connection_id: int = 1,
    model: str = "openai:gpt-5.4-mini",
) -> Agent:
    return Agent(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Agent description",
        model_connection_id=model_connection_id,
        model=model,
        system_prompt="Assess the input and return a typed result.",
        input_schema={"type": "object", "required": ["ticker"]},
        output_schema_id=output_schema.id,
        output_schema_version=output_schema.version,
        capabilities=[
            {
                "capabilityId": capability.id,
                "capabilityKey": capability.key,
                "capabilityVersion": capability.version,
            }
            for capability in capabilities
        ],
        mcp_servers=[
            {
                "mcpServerId": server.id,
                "mcpServerKey": server.key,
                "mcpServerVersion": server.version,
            }
            for server in mcp_servers
        ],
        budget_usd=budget_usd,
    )


def _build_workflow(
    *,
    key: str,
    version: int,
    status: str,
    agent: Agent,
    aggregate_budget_usd: Decimal,
) -> Workflow:
    return Workflow(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Workflow description",
        input_schema={"type": "object", "required": ["ticker"]},
        steps=[
            {
                "index": 1,
                "agents": [
                    {
                        "slot": "analysis",
                        "agentId": agent.id,
                        "agentKey": agent.key,
                        "agentVersion": agent.version,
                        "outputSchemaId": agent.output_schema_id,
                        "outputSchemaVersion": agent.output_schema_version,
                        "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        "optional": False,
                        "budgetUsd": str(agent.budget_usd),
                    }
                ],
            }
        ],
        output_spec={
            "kind": "slot",
            "stepIndex": 1,
            "slot": "analysis",
            "agentId": agent.id,
            "agentKey": agent.key,
            "agentVersion": agent.version,
            "outputSchemaId": agent.output_schema_id,
            "outputSchemaVersion": agent.output_schema_version,
        },
        aggregate_budget_usd=aggregate_budget_usd,
    )


def _build_agent_platform_run(
    *,
    workflow: Workflow,
    status: str,
    total_tokens: int,
    started_at: datetime | None,
    finished_at: datetime | None,
    trace_id: str | None,
    final_output: object | None,
) -> Run:
    return Run(
        target_kind="workflow",
        target_id=workflow.id,
        target_key=workflow.key,
        target_version=workflow.version,
        input={"ticker": "NVDA", "horizonDays": 30},
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        trace_id=trace_id,
        started_at=started_at,
        finished_at=finished_at,
    )


def _seed_agent_platform_versioned_rows(session: Session) -> None:
    session.add_all(
        [
            _build_skill(key="research_skill", version=1, status="published"),
            _build_skill(key="research_skill", version=2, status="draft"),
            _build_skill(key="summarize_skill", version=1, status="published"),
            _build_output_schema(
                key="decision_schema",
                version=1,
                status="published",
                registry_refs=["Action"],
            ),
            _build_output_schema(
                key="decision_schema",
                version=2,
                status="draft",
                registry_refs=["Action", "PriceTarget"],
            ),
            _build_output_schema(
                key="action_type",
                version=1,
                status="published",
                kind="shared",
            ),
            _build_output_schema(
                key="action_type",
                version=2,
                status="draft",
                kind="shared",
                registry_refs=["PriceTarget"],
            ),
            _build_mcp_server(
                key="market_data",
                version=1,
                status="published",
                transport="http-sse",
                enabled=True,
            ),
            _build_mcp_server(
                key="market_data",
                version=2,
                status="draft",
                transport="stdio",
                enabled=False,
            ),
            _build_mcp_server(
                key="filings",
                version=1,
                status="published",
                transport="http-sse",
                enabled=False,
            ),
        ]
    )
    session.commit()


def test_agent_platform_capability_repository_resolves_published_versions_and_latest_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent_platform_versioned_rows(session)

        capability_repo = CapabilityRepository(session)

        published_capability = capability_repo.resolve_version("research_skill", None)
        draft_capability = capability_repo.resolve_version("research_skill", 2)
        assert published_capability is not None
        assert published_capability.version == 1
        assert draft_capability is not None
        assert draft_capability.status == "draft"
        assert [item.version for item in capability_repo.list_versions("research_skill")] == [2, 1]
        assert [(item.key, item.version) for item in capability_repo.list_latest_versions()] == [
            ("research_skill", 2),
            ("summarize_skill", 1),
        ]
        assert [
            (item.key, item.version)
            for item in capability_repo.list_latest_versions(status="published")
        ] == [
            ("research_skill", 1),
            ("summarize_skill", 1),
        ]


def test_agent_platform_output_schema_repository_resolves_registry_refs_and_versions(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent_platform_versioned_rows(session)

        output_schema_repo = OutputSchemaRepository(session)

        published_schema = output_schema_repo.resolve_version("decision_schema", None)
        draft_schema = output_schema_repo.get_draft_by_key("decision_schema")
        published_registry_entry = output_schema_repo.resolve_registry_ref("action_type")
        draft_registry_entry = output_schema_repo.resolve_registry_ref("action_type", 2)

        assert published_schema is not None
        assert published_schema.version == 1
        assert draft_schema is not None
        assert draft_schema.registry_refs == ["Action", "PriceTarget"]
        assert published_registry_entry is not None
        assert published_registry_entry.kind == "shared"
        assert published_registry_entry.version == 1
        assert draft_registry_entry is not None
        assert draft_registry_entry.registry_refs == ["PriceTarget"]
        assert [item.key for item in output_schema_repo.list_registry_entries()] == ["action_type"]


def test_agent_platform_mcp_repository_filters_enabled_servers_and_versions(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent_platform_versioned_rows(session)

        mcp_repo = McpServerRepository(session)

        published_server = mcp_repo.resolve_version("market_data", None, enabled=True)
        draft_server = mcp_repo.get_draft_by_key("market_data")
        enabled_latest = mcp_repo.list_latest_versions(enabled=True)
        published_enabled = mcp_repo.list_latest_versions(status="published", enabled=True)
        http_sse_servers = mcp_repo.list_latest_versions(transport="http-sse")

        assert published_server is not None
        assert published_server.version == 1
        assert draft_server is not None
        assert draft_server.transport == "stdio"
        assert draft_server.enabled is False
        assert [(item.key, item.version) for item in enabled_latest] == [("market_data", 1)]
        assert [(item.key, item.version) for item in published_enabled] == [("market_data", 1)]
        assert [(item.key, item.version) for item in http_sse_servers] == [
            ("filings", 1),
            ("market_data", 1),
        ]


def test_agent_platform_model_connection_repository_filters_active_and_archived_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        archived = _build_model_connection(
            name="Archived Connection",
            key="archived_openai",
            status="archived",
            api_key="sk-archived-4444",
        )
        alpha_active = _build_model_connection(
            name="Alpha Active",
            key="alpha_openai",
            status="active",
            api_key="sk-active-1111",
        )
        beta_active = _build_model_connection(
            name="Beta Active",
            key="beta_openai",
            status="active",
            api_key="sk-active-2222",
        )
        session.add_all([archived, beta_active, alpha_active])
        session.commit()

        repo = ModelConnectionRepository(session)
        all_connections = repo.list_connections()
        active_connections = repo.list_active()
        archived_connections = repo.list_connections(status="archived")
        archived_row = repo.get(archived.id)

        assert [(item.name, item.status) for item in all_connections] == [
            ("Alpha Active", "active"),
            ("Beta Active", "active"),
            ("Archived Connection", "archived"),
        ]
        assert [item.id for item in active_connections] == [alpha_active.id, beta_active.id]
        assert [item.id for item in archived_connections] == [archived.id]
        assert archived_row is not None
        assert archived_row.status == "archived"
        assert archived_row.secret_payload == {"apiKey": "sk-archived-4444"}


def test_agent_platform_model_connection_repository_and_service_resolve_by_key(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        active = _build_model_connection(
            name="Primary OpenAI",
            key="primary_openai",
            status="active",
            api_key="sk-active-1111",
        )
        archived = _build_model_connection(
            name="Archived OpenAI",
            key="archived_openai",
            status="archived",
            api_key="sk-archived-2222",
        )
        session.add_all([active, archived])
        session.commit()

        repo = ModelConnectionRepository(session)
        service = ModelConnectionService(session)

        resolved = repo.get_by_key("primary_openai")
        active_only = repo.resolve_active_by_key("primary_openai")
        archived_active_only = repo.resolve_active_by_key("archived_openai")

        assert resolved is not None and resolved.id == active.id
        assert active_only is not None and active_only.id == active.id
        assert archived_active_only is None
        assert service.resolve_connection_by_key("PRIMARY_OPENAI").id == active.id

        with pytest.raises(ApiError) as missing_error:
            service.resolve_connection_by_key("missing_openai")
        assert missing_error.value.code == "validation_error"
        assert missing_error.value.details == [
            {
                "field": "modelConnection",
                "issue": "Model connection 'missing_openai' was not found",
            }
        ]

        with pytest.raises(ApiError) as archived_error:
            service.resolve_connection_by_key("archived_openai")
        assert archived_error.value.code == "validation_error"
        assert archived_error.value.details == [
            {"field": "modelConnection", "issue": "Archived model connections cannot be selected"}
        ]


def test_agent_platform_workflow_version_pinning_repositories_preserve_saved_versions(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        published_skill = _build_skill(key="research_skill", version=1, status="published")
        published_schema = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        published_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        session.add_all([published_skill, published_schema, published_server])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_skill],
            mcp_servers=[published_server],
            budget_usd=Decimal("1.50000000"),
        )
        session.add(published_agent)
        session.flush()
        published_workflow = _build_workflow(
            key="market_review",
            version=1,
            status="published",
            agent=published_agent,
            aggregate_budget_usd=Decimal("1.50000000"),
        )
        session.add(published_workflow)
        session.flush()

        draft_schema = _build_output_schema(
            key="decision_schema",
            version=2,
            status="draft",
        )
        session.add(draft_schema)
        session.flush()
        draft_agent = _build_agent(
            key="research_agent",
            version=2,
            status="draft",
            output_schema=draft_schema,
            capabilities=[published_skill],
            mcp_servers=[published_server],
            budget_usd=Decimal("2.75000000"),
        )
        session.add(draft_agent)
        session.flush()
        draft_workflow = _build_workflow(
            key="market_review",
            version=2,
            status="draft",
            agent=draft_agent,
            aggregate_budget_usd=Decimal("2.75000000"),
        )
        session.add(draft_workflow)
        session.commit()

        agent_repo = AgentRepository(session)
        workflow_repo = WorkflowRepository(session)

        published_agent_row = agent_repo.resolve_version("research_agent", None)
        draft_agent_row = agent_repo.resolve_version("research_agent", 2)
        published_workflow_row = workflow_repo.resolve_version("market_review", 1)
        draft_workflow_row = workflow_repo.resolve_version("market_review", 2)

        assert published_agent_row is not None
        assert published_agent_row.output_schema_version == 1
        assert draft_agent_row is not None
        assert draft_agent_row.output_schema_version == 2
        assert published_workflow_row is not None
        assert published_workflow_row.steps[0]["agents"][0]["agentVersion"] == 1
        assert published_workflow_row.steps[0]["agents"][0]["outputSchemaVersion"] == 1
        assert published_workflow_row.output_spec["agentVersion"] == 1
        assert published_workflow_row.aggregate_budget_usd == Decimal("1.50000000")
        assert draft_workflow_row is not None
        assert draft_workflow_row.steps[0]["agents"][0]["agentVersion"] == 2
        assert draft_workflow_row.steps[0]["agents"][0]["outputSchemaVersion"] == 2
        assert [(item.key, item.version) for item in workflow_repo.list_latest_versions()] == [
            ("market_review", 2)
        ]


def test_agent_repository_model_filter_uses_saved_agent_model_value(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        published_skill = _build_skill(key="research_skill", version=1, status="published")
        published_schema = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        published_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        session.add_all([published_skill, published_schema, published_server])
        session.flush()
        session.add_all(
            [
                _build_agent(
                    key="snapshot_agent",
                    version=1,
                    status="published",
                    output_schema=published_schema,
                    capabilities=[published_skill],
                    mcp_servers=[published_server],
                    budget_usd=Decimal("1.00000000"),
                    model="gpt-snapshot-v1",
                ),
                _build_agent(
                    key="live_connection_agent",
                    version=1,
                    status="published",
                    output_schema=published_schema,
                    capabilities=[published_skill],
                    mcp_servers=[published_server],
                    budget_usd=Decimal("1.00000000"),
                    model="gpt-live-v2",
                ),
            ]
        )
        session.commit()

        agent_repo = AgentRepository(session)

        assert [item.key for item in agent_repo.list_latest_versions(model="gpt-snapshot-v1")] == [
            "snapshot_agent"
        ]


def test_agent_platform_run_detail_repository_returns_persisted_monitor_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        published_skill = _build_skill(key="research_skill", version=1, status="published")
        published_schema = _build_output_schema(
            key="decision_schema",
            version=1,
            status="published",
        )
        published_server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        session.add_all([published_skill, published_schema, published_server])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_skill],
            mcp_servers=[published_server],
            budget_usd=Decimal("1.25000000"),
        )
        session.add(published_agent)
        session.flush()
        workflow = _build_workflow(
            key="market_review",
            version=1,
            status="published",
            agent=published_agent,
            aggregate_budget_usd=Decimal("1.25000000"),
        )
        session.add(workflow)
        session.flush()

        earlier_run = _build_agent_platform_run(
            workflow=workflow,
            status="failed",
            total_tokens=120,
            started_at=datetime(2026, 4, 19, 9, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 9, 1, tzinfo=UTC_TZ),
            trace_id="trace-older",
            final_output=None,
        )
        earlier_run.queued_at = datetime(2026, 4, 19, 8, 59, tzinfo=UTC_TZ)
        queued_run = _build_agent_platform_run(
            workflow=workflow,
            status=RunStatus.QUEUED.value,
            total_tokens=0,
            started_at=None,
            finished_at=None,
            trace_id=None,
            final_output=None,
        )
        queued_run.queued_at = datetime(2026, 4, 19, 11, 0, tzinfo=UTC_TZ)
        latest_run = _build_agent_platform_run(
            workflow=workflow,
            status="succeeded",
            total_tokens=321,
            started_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ),
            trace_id="trace-latest",
            final_output={"headline": "Buy"},
        )
        latest_run.queued_at = datetime(2026, 4, 19, 9, 59, tzinfo=UTC_TZ)
        session.add_all([earlier_run, latest_run, queued_run])
        session.flush()
        latest_step = RunStep(
            run_id=latest_run.id,
            step_index=1,
            status="succeeded",
            origin="planned",
            started_at=latest_run.started_at,
            finished_at=latest_run.finished_at,
            persisted_at=latest_run.finished_at,
        )
        session.add(latest_step)
        session.flush()
        session.add(
            RunAgentInvocation(
                run_step_id=latest_step.id,
                run_id=latest_run.id,
                step_index=1,
                slot="analysis",
                position=0,
                agent_id=published_agent.id,
                agent_key=published_agent.key,
                agent_version=published_agent.version,
                output_schema_id=published_agent.output_schema_id,
                output_schema_version=published_agent.output_schema_version,
                input_mode="passthrough",
                wiring={},
                optional=False,
                status="succeeded",
                resolved_input={"ticker": "NVDA"},
                resolved_input_origin="passthrough",
                output={"headline": "Buy"},
                output_origin="executed",
                tokens=321,
                duration_ms=1450,
                trace_span_id="span-latest",
                started_at=latest_run.started_at,
                finished_at=latest_run.finished_at,
                persisted_at=latest_run.finished_at,
            )
        )
        session.commit()

        run_repo = RunRepository(session)

        run_detail = run_repo.get_detail(latest_run.id)
        listed_runs = run_repo.list_for_target(target_kind="workflow", target_key="market_review")
        filtered_runs = run_repo.list_all(
            target_kind="workflow",
            target_key="market_review",
            status="succeeded",
        )
        queued_runs = run_repo.list_all(
            target_kind="workflow",
            target_key="market_review",
            status="queued",
        )
        latest_for_workflow = run_repo.get_latest_for_target(
            target_kind="workflow",
            target_key="market_review",
        )

        assert run_detail is not None
        detail_steps = cast(list[RunStep], run_detail.steps)
        assert len(detail_steps) == 1
        assert detail_steps[0].step_index == 1
        detail_invocations = cast(list[RunAgentInvocation], detail_steps[0].invocations)
        assert len(detail_invocations) == 1
        assert detail_invocations[0].trace_span_id == "span-latest"
        assert detail_invocations[0].resolved_input == {"ticker": "NVDA"}
        serialized_detail = cast(
            dict[str, object],
            RunRead.model_validate(
                {
                    "id": run_detail.id,
                    "targetKind": run_detail.target_kind,
                    "targetId": run_detail.target_id,
                    "targetKey": run_detail.target_key,
                    "targetVersion": run_detail.target_version,
                    "input": run_detail.input,
                    "sourceRunId": run_detail.source_run_id,
                    "lineageRootRunId": run_detail.lineage_root_run_id,
                    "replayStepIndex": run_detail.forked_from_step_index,
                    "resumeStepIndex": run_detail.resume_step_index,
                    "finalOutput": run_detail.final_output,
                    "status": run_detail.status,
                    "totalTokens": run_detail.total_tokens,
                    "inheritedTokens": run_detail.inherited_tokens,
                    "executedTokens": run_detail.executed_tokens,
                    "traceId": run_detail.trace_id,
                    "error": run_detail.error,
                    "queuedAt": run_detail.queued_at,
                    "startedAt": run_detail.started_at,
                    "finishedAt": run_detail.finished_at,
                    "createdAt": run_detail.created_at,
                    "updatedAt": run_detail.updated_at,
                    "steps": [],
                    "memoryArtifacts": [],
                    "packageProvenance": None,
                }
            ).model_dump(mode="json", by_alias=True),
        )
        serialized_invocation = cast(
            dict[str, object],
            RunAgentInvocationRead.model_validate(detail_invocations[0]).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        assert "perStepOutputs" not in serialized_detail
        assert set(serialized_detail) == {
            "id",
            "targetKind",
            "targetId",
            "targetKey",
            "targetVersion",
            "input",
            "sourceRunId",
            "lineageRootRunId",
            "replayStepIndex",
            "resumeStepIndex",
            "finalOutput",
            "status",
            "totalTokens",
            "inheritedTokens",
            "executedTokens",
            "traceId",
            "error",
            "queuedAt",
            "startedAt",
            "finishedAt",
            "createdAt",
            "updatedAt",
            "steps",
            "memoryArtifacts",
            "packageProvenance",
        }
        assert serialized_detail["queuedAt"] == "2026-04-19T09:59:00Z"
        assert detail_steps[0].step_index == 1
        assert set(serialized_invocation) == {
            "id",
            "runStepId",
            "runId",
            "stepIndex",
            "slot",
            "position",
            "agentId",
            "agentKey",
            "agentVersion",
            "outputSchemaId",
            "outputSchemaVersion",
            "inputMode",
            "wiring",
            "graphMetadata",
            "optional",
            "status",
            "resolvedInput",
            "resolvedInputOrigin",
            "output",
            "outputOrigin",
            "errorCode",
            "errorMessage",
            "errorDetails",
            "tokens",
            "durationMs",
            "traceSpanId",
            "sourceInvocationId",
            "startedAt",
            "finishedAt",
            "persistedAt",
            "createdAt",
            "updatedAt",
        }
        assert serialized_invocation["traceSpanId"] == "span-latest"
        assert run_detail.total_tokens == 321
        assert run_detail.trace_id == "trace-latest"
        assert run_detail.final_output == {"headline": "Buy"}
        assert [run.id for run in listed_runs] == [queued_run.id, latest_run.id, earlier_run.id]
        assert [run.id for run in filtered_runs] == [latest_run.id]
        assert [run.id for run in queued_runs] == [queued_run.id]
        assert latest_for_workflow is not None
        assert latest_for_workflow.id == queued_run.id


def test_run_service_post_run_memory_artifact_writes_memory_native_detail(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        capability = Capability(
            key="post_run_memory_writer",
            version=1,
            status="published",
            name="Post Run Memory Writer",
            description="Grants post-run memory writes.",
            tool_keys=[REPORT_MEMORY_WRITE_TOOL_KEY],
        )
        output_schema = _build_output_schema(
            key="post_run_memory_schema",
            version=1,
            status="published",
        )
        session.add_all([capability, output_schema])
        session.flush()

        agent = _build_agent(
            key="portfolio_manager",
            version=1,
            status="published",
            output_schema=output_schema,
            capabilities=[capability],
            mcp_servers=[],
            budget_usd=Decimal("1.25000000"),
        )
        session.add(agent)
        session.flush()
        workflow = _build_workflow(
            key="post_run_memory_workflow",
            version=1,
            status="published",
            agent=agent,
            aggregate_budget_usd=Decimal("1.25000000"),
        )
        source_refs = {
            "ticker": {"source": "inputs", "path": "ticker"},
            "portfolioSlug": {"source": "inputs", "path": "portfolioSlug"},
            "horizonDays": {"source": "inputs", "path": "horizonDays"},
            "action": _post_run_memory_node_ref("action"),
            "rationale": _post_run_memory_node_ref("rationale"),
            "riskSummary": _post_run_memory_node_ref("riskSummary"),
            "executionPlan": _post_run_memory_node_ref("executionPlan"),
            "confidence": _post_run_memory_node_ref("confidence"),
            "decisionSummary": _post_run_memory_node_ref("decisionSummary"),
        }
        workflow.output_spec = {
            **workflow.output_spec,
            "compiledGraph": {
                "postRunMemory": {
                    "enabled": True,
                    "sourceRefs": source_refs,
                    "benchmarkSymbol": {"source": "inputs", "path": "benchmarkSymbol"},
                }
            },
        }
        session.add(workflow)
        session.flush()
        started_at = datetime(2026, 4, 20, 12, 0, tzinfo=UTC_TZ)
        finished_at = datetime(2026, 4, 20, 12, 2, tzinfo=UTC_TZ)
        run = _build_agent_platform_run(
            workflow=workflow,
            status="succeeded",
            total_tokens=321,
            started_at=started_at,
            finished_at=finished_at,
            trace_id="trace-post-run-memory",
            final_output={"decision": "buy"},
        )
        run.input = {
            "ticker": "NVDA",
            "portfolioSlug": "core_us",
            "horizonDays": 30,
            "benchmarkSymbol": "SPY",
        }
        run.queued_at = datetime(2026, 4, 20, 11, 59, tzinfo=UTC_TZ)
        session.add(run)
        session.flush()
        step = RunStep(
            run_id=run.id,
            step_index=1,
            status="succeeded",
            origin="planned",
            started_at=started_at,
            finished_at=finished_at,
            persisted_at=finished_at,
            graph_metadata={"nodeId": "portfolio_decision", "nodeKind": "step"},
        )
        session.add(step)
        session.flush()
        session.add(
            RunAgentInvocation(
                run_step_id=step.id,
                run_id=run.id,
                step_index=1,
                slot="decision",
                position=0,
                agent_id=agent.id,
                agent_key=agent.key,
                agent_version=agent.version,
                output_schema_id=output_schema.id,
                output_schema_version=output_schema.version,
                input_mode="passthrough",
                wiring={},
                graph_metadata={"nodeId": "portfolio_decision", "nodeKind": "step"},
                optional=False,
                status="succeeded",
                resolved_input={"ticker": "NVDA"},
                resolved_input_origin="passthrough",
                output={
                    "action": "buy",
                    "rationale": "Durable demand supports ownership.",
                    "riskSummary": "Volatility remains elevated.",
                    "executionPlan": "Scale in after market confirmation.",
                    "confidence": "high",
                    "decisionSummary": "Post-run memory summary.",
                },
                output_origin="executed",
                tokens=321,
                duration_ms=1400,
                trace_span_id="span-post-run-memory",
                started_at=started_at,
                finished_at=finished_at,
                persisted_at=finished_at,
            )
        )
        session.commit()

        service = RunService(session)
        run_id = run.id
        service._create_post_run_memory_artifact(run_id)
        service._create_post_run_memory_artifact(run_id)
        session.commit()
        reports = session.query(Report).order_by(Report.id).all()
        detail = cast(
            dict[str, object],
            service.get_run(run_id).model_dump(mode="json", by_alias=True),
        )

    assert len(reports) == 1
    report = reports[0]
    assert report.source == "agent"
    analysis = cast(dict[str, object], report.metadata_["analysis"])
    created_by = cast(dict[str, object], report.metadata_["createdBy"])
    assert analysis["reviewType"] == "agent_memory"
    assert analysis["versionGroup"] == "agent_memory/v1"
    assert analysis["runId"] == run_id
    assert analysis["decisionSummary"] == "Post-run memory summary."
    assert created_by["type"] == "agent"

    artifacts = cast(list[dict[str, object]], detail["memoryArtifacts"])
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert {"reportId", "slug", "name"}.isdisjoint(artifact)
    assert artifact["memoryId"] == f"mem_{report.id}"
    assert artifact["summary"] == "Post-run memory summary."
    assert artifact["status"] == "pending"
    assert artifact["sourceGraphMetadata"] == {
        "nodeId": "portfolio_decision",
        "slot": "decision",
        "traceId": "trace-post-run-memory",
        "workflowKey": "post_run_memory_workflow",
        "workflowVersion": 1,
    }
    audit_links = cast(dict[str, object], artifact["auditLinks"])
    report_link = cast(dict[str, object], audit_links["report"])
    assert report_link["slug"] == report.slug
    assert report_link["name"] == report.name
    assert report_link["url"] == f"/reports/{report.slug}"
    assert report_link["downloadUrl"] == f"/api/v1/reports/{report.slug}/download"
    assert "reportId" not in report_link


def _post_run_memory_node_ref(path: str) -> dict[str, object]:
    return {
        "source": "nodes",
        "stepIndex": 1,
        "compiledSlot": "decision",
        "sourceNodeId": "portfolio_decision",
        "sourceSlot": "decision",
        "path": path,
    }
