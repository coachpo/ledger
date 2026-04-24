from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.skill import Skill
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.repositories.skill import SkillRepository
from app.repositories.workflow import WorkflowRepository

UTC_TZ = timezone.utc  # noqa: UP017


def _build_skill(*, key: str, version: int, status: str) -> Skill:
    return Skill(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Skill description",
        tool_definitions=[{"tool": f"{key}.lookup"}],
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
    status: str,
    api_key: str,
    model_id: str = "gpt-5.4-mini",
) -> ModelConnection:
    return ModelConnection(
        status=status,
        name=name,
        description=f"{name} description",
        base_url="https://api.openai.com/v1",
        organization=None,
        project=None,
        model_id=model_id,
        reasoning_effort="medium",
        timeout_seconds=60,
        secret_payload={"apiKey": api_key},
        has_api_key=True,
        api_key_last4=api_key[-4:],
    )


def _build_agent(
    *,
    key: str,
    version: int,
    status: str,
    output_schema: OutputSchema,
    skills: list[Skill],
    mcp_servers: list[McpServer],
    budget_usd: Decimal,
    model_connection_id: int = 1,
) -> Agent:
    return Agent(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Agent description",
        model_connection_id=model_connection_id,
        model="openai:gpt-5.4-mini",
        system_prompt="Assess the input and return a typed result.",
        input_schema={"type": "object", "required": ["ticker"]},
        output_schema_id=output_schema.id,
        output_schema_version=output_schema.version,
        skills=[
            {"skillId": skill.id, "skillKey": skill.key, "skillVersion": skill.version}
            for skill in skills
        ],
        mcp_servers=[
            {
                "mcpServerId": server.id,
                "mcpServerKey": server.key,
                "mcpServerVersion": server.version,
            }
            for server in mcp_servers
        ],
        temperature=0.2,
        max_tool_rounds=2,
        budget_usd=budget_usd,
        streaming=True,
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
            "kind": "agent",
            "slot": "analysis",
            "agentId": agent.id,
            "agentKey": agent.key,
            "agentVersion": agent.version,
            "outputSchemaId": agent.output_schema_id,
            "outputSchemaVersion": agent.output_schema_version,
            "wiring": {"ticker": {"from": "input", "path": "ticker"}},
        },
        aggregate_budget_usd=aggregate_budget_usd,
    )


def _build_agent_platform_run(
    *,
    workflow: Workflow,
    status: str,
    total_tokens: int,
    total_cost_usd: Decimal,
    started_at: datetime,
    finished_at: datetime | None,
    trace_id: str | None,
    per_step_outputs: dict[str, list[dict[str, object]]],
    final_output: object | None,
) -> Run:
    return Run(
        workflow_id=workflow.id,
        workflow_key=workflow.key,
        workflow_version=workflow.version,
        input={"ticker": "NVDA", "horizonDays": 30},
        per_step_outputs=per_step_outputs,
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
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


def test_agent_platform_skill_repository_resolves_published_versions_and_latest_rows(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_agent_platform_versioned_rows(session)

        skill_repo = SkillRepository(session)

        published_skill = skill_repo.resolve_version("research_skill", None)
        draft_skill = skill_repo.resolve_version("research_skill", 2)
        assert published_skill is not None
        assert published_skill.version == 1
        assert draft_skill is not None
        assert draft_skill.status == "draft"
        assert [item.version for item in skill_repo.list_versions("research_skill")] == [2, 1]
        assert [(item.key, item.version) for item in skill_repo.list_latest_versions()] == [
            ("research_skill", 2),
            ("summarize_skill", 1),
        ]
        assert [
            (item.key, item.version) for item in skill_repo.list_latest_versions(status="published")
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
            status="archived",
            api_key="sk-archived-4444",
        )
        alpha_active = _build_model_connection(
            name="Alpha Active",
            status="active",
            api_key="sk-active-1111",
        )
        beta_active = _build_model_connection(
            name="Beta Active",
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
            skills=[published_skill],
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
            skills=[published_skill],
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
            skills=[published_skill],
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
            total_cost_usd=Decimal("0.05000000"),
            started_at=datetime(2026, 4, 19, 9, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 9, 1, tzinfo=UTC_TZ),
            trace_id="trace-older",
            per_step_outputs={
                "1": [
                    {
                        "slot": "analysis",
                        "agentVersion": 1,
                        "resolvedInput": {"ticker": "NVDA"},
                        "output": None,
                        "error": {"message": "timeout"},
                        "status": "failed",
                        "tokens": 120,
                        "costUsd": "0.05000000",
                        "durationMs": 61000,
                        "traceSpanId": "span-older",
                    }
                ]
            },
            final_output=None,
        )
        latest_run = _build_agent_platform_run(
            workflow=workflow,
            status="succeeded",
            total_tokens=321,
            total_cost_usd=Decimal("0.15000000"),
            started_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ),
            finished_at=datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ),
            trace_id="trace-latest",
            per_step_outputs={
                "1": [
                    {
                        "slot": "analysis",
                        "agentId": published_agent.id,
                        "agentKey": published_agent.key,
                        "agentVersion": published_agent.version,
                        "outputSchemaId": published_agent.output_schema_id,
                        "outputSchemaVersion": published_agent.output_schema_version,
                        "resolvedInput": {"ticker": "NVDA"},
                        "output": {"headline": "Buy"},
                        "error": None,
                        "status": "succeeded",
                        "tokens": 321,
                        "costUsd": "0.15000000",
                        "durationMs": 1450,
                        "traceSpanId": "span-latest",
                    }
                ]
            },
            final_output={"headline": "Buy"},
        )
        session.add_all([earlier_run, latest_run])
        session.commit()

        run_repo = RunRepository(session)

        run_detail = run_repo.get_detail(latest_run.id)
        listed_runs = run_repo.list_for_workflow(workflow_key="market_review")
        filtered_runs = run_repo.list_all(workflow_key="market_review", status="succeeded")
        latest_for_workflow = run_repo.get_latest_for_workflow(workflow_key="market_review")

        assert run_detail is not None
        assert run_detail.per_step_outputs["1"][0]["traceSpanId"] == "span-latest"
        assert run_detail.per_step_outputs["1"][0]["resolvedInput"] == {"ticker": "NVDA"}
        assert run_detail.total_tokens == 321
        assert run_detail.total_cost_usd == Decimal("0.15000000")
        assert run_detail.trace_id == "trace-latest"
        assert run_detail.final_output == {"headline": "Buy"}
        assert [run.id for run in listed_runs] == [latest_run.id, earlier_run.id]
        assert [run.id for run in filtered_runs] == [latest_run.id]
        assert latest_for_workflow is not None
        assert latest_for_workflow.id == latest_run.id
