from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp import DefaultMcpConnectionTester
from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.platform_reference import AgentCapabilityRef, AgentMcpServerRef, WorkflowAgentRef
from app.models.report import Report
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.repositories.agent import AgentRepository
from app.repositories.capability import CapabilityRepository
from app.repositories.mcp_server import McpServerRepository
from app.repositories.model_connection import ModelConnectionRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.run import RunRepository
from app.repositories.workflow import WorkflowRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.capability import CapabilityDraftCreate, CapabilityDraftUpdate
from app.schemas.mcp_server import McpServerCreate, McpServerTransport, McpServerUpdate
from app.schemas.output_schema import OutputSchemaDraftCreate, OutputSchemaDraftUpdate
from app.schemas.run import (
    RunAgentInvocationRead,
    RunRead,
    RunRerunCreateRequest,
    RunStatus,
    RunStepReplayCreateRequest,
)
from app.services.agent_service import AgentService
from app.services.capability_service import REPORT_MEMORY_WRITE_TOOL_KEY, CapabilityService
from app.services.mcp_server_service import McpServerService
from app.services.model_connection_service import ModelConnectionService
from app.services.output_schema_service import OutputSchemaService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService

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


def _seed_run_target_fk_targets(
    session: Session,
    *,
    key_prefix: str,
) -> tuple[Agent, Workflow]:
    model_connection = _build_model_connection(
        name=f"{key_prefix} model",
        key=f"{key_prefix}_model",
        status="active",
        api_key="sk-target-fk",
    )
    output_schema = _build_output_schema(
        key=f"{key_prefix}_schema",
        version=1,
        status="published",
    )
    capability = _build_skill(key=f"{key_prefix}_capability", version=1, status="published")
    session.add_all([model_connection, output_schema, capability])
    session.flush()
    run_input_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    }
    agent = _build_agent(
        key=f"{key_prefix}_agent",
        version=1,
        status="published",
        output_schema=output_schema,
        capabilities=[capability],
        mcp_servers=[],
        budget_usd=Decimal("1.00000000"),
        model_connection_id=model_connection.id,
    )
    agent.input_schema = run_input_schema
    session.add(agent)
    session.flush()
    workflow = _build_workflow(
        key=f"{key_prefix}_workflow",
        version=1,
        status="published",
        agent=agent,
        aggregate_budget_usd=Decimal("1.00000000"),
    )
    workflow.input_schema = run_input_schema
    session.add(workflow)
    session.flush()
    return agent, workflow


def _seed_workflow_package_target(
    session: Session,
    *,
    key_prefix: str,
) -> tuple[WorkflowPackage, WorkflowPackageVersion]:
    package_key = f"{key_prefix}_package"
    package = WorkflowPackage(
        key=package_key,
        name=f"{key_prefix} package",
        description="Package target fixture",
        status="active",
        draft_source="apiVersion: signaldeck.workflowPackage/v1\n",
    )
    session.add(package)
    session.flush()
    package_version = WorkflowPackageVersion(
        package_id=package.id,
        version=1,
        manifest_source=package.draft_source,
        manifest_hash="a" * 64,
        package_definition={"metadata": {"key": package_key, "name": package.name}},
        compiled_plan={"workflows": []},
        compiled_hash="b" * 64,
    )
    session.add(package_version)
    session.flush()
    package.latest_version_id = package_version.id
    session.flush()
    return package, package_version


def _assert_executable_target_fk_identity(
    run: Run,
    *,
    agent_id: int | None = None,
    workflow_id: int | None = None,
    workflow_package_id: int | None = None,
    workflow_package_version_id: int | None = None,
) -> None:
    assert run.agent_id == agent_id
    assert run.target_workflow_id == workflow_id
    assert run.workflow_package_id == workflow_package_id
    assert run.workflow_package_version_id == workflow_package_version_id


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


def test_agent_platform_model_connection_repository_lists_rows_without_status_filters(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        alpha = _build_model_connection(
            name="Alpha Model",
            key="alpha_openai",
            status="active",
            api_key="sk-alpha-1111",
        )
        beta = _build_model_connection(
            name="Beta Model",
            key="beta_openai",
            status="active",
            api_key="sk-beta-2222",
        )
        session.add_all([beta, alpha])
        session.commit()

        repo = ModelConnectionRepository(session)
        all_connections = repo.list_connections()

        assert [item.id for item in all_connections] == [alpha.id, beta.id]
        assert all(connection.status == "active" for connection in all_connections)


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
        session.add(active)
        session.commit()

        repo = ModelConnectionRepository(session)
        service = ModelConnectionService(session)

        resolved = repo.get_by_key("primary_openai")

        assert resolved is not None and resolved.id == active.id
        assert service.resolve_connection_by_key("PRIMARY_OPENAI").id == active.id

        with pytest.raises(ApiError) as missing_error:
            _ = service.resolve_connection_by_key("missing_openai")
        assert missing_error.value.code == "validation_error"
        assert missing_error.value.details == [
            {
                "field": "modelConnection",
                "issue": "Model connection 'missing_openai' was not found",
            }
        ]


def test_model_connection_delete_unused_hard_deletes_row(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        connection = _build_model_connection(
            name="Delete Unused Model",
            key="delete_unused_model",
            status="active",
            api_key="sk-unused-delete-1111",
        )
        session.add(connection)
        session.commit()
        connection_id = connection.id

    first = client.delete(f"/api/model-connections/{connection_id}")
    assert first.status_code == 204, first.text
    assert first.content == b""

    get_after_delete = client.get(f"/api/model-connections/{connection_id}")
    assert get_after_delete.status_code == 404, get_after_delete.json()

    second = client.delete(f"/api/model-connections/{connection_id}")
    assert second.status_code == 404, second.json()

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is None


def test_model_connection_delete_blocked_by_package_version_ref(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-package-blocker-2222"
    with session_factory() as session:
        connection = _build_model_connection(
            name="Package Referenced Model",
            key="package_referenced_model",
            status="active",
            api_key=secret_value,
        )
        session.add(connection)
        session.flush()
        package = WorkflowPackageRepository(session).create_package(
            key="package_delete_blocker",
            name="Package Delete Blocker",
        )
        version = WorkflowPackageRepository(session).create_version(
            package,
            manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
            manifest_hash="package-delete-manifest-hash",
            package_definition={"metadata": {"key": package.key}},
            compiled_plan={"agents": []},
            compiled_hash="package-delete-compiled-hash",
            model_connection_refs=[(connection.id, connection.key)],
        )
        session.commit()
        connection_id = connection.id
        version_id = version.id

    response = client.delete(f"/api/model-connections/{connection_id}")
    body = cast(dict[str, object], response.json())

    assert response.status_code == 409, body
    assert body["code"] == "model_connection_in_use"
    assert body["message"] == "Model connection is in use"
    assert body["details"] == [
        {
            "field": "modelConnection",
            "issue": "Model connection is referenced",
            "refType": "workflowPackageVersion",
            "refId": version_id,
            "refKey": "package_delete_blocker@1",
        }
    ]
    assert secret_value not in str(body)
    assert "secretPayload" not in str(body)

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is not None


def test_model_connection_delete_blocked_by_agent_ref(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-agent-blocker-3333"
    with session_factory() as session:
        connection = _build_model_connection(
            name="Agent Referenced Model",
            key="agent_referenced_model",
            status="active",
            api_key=secret_value,
        )
        output_schema = _build_output_schema(
            key="agent_delete_blocker_schema",
            version=1,
            status="published",
        )
        session.add_all([connection, output_schema])
        session.flush()
        agent = _build_agent(
            key="agent_delete_blocker",
            version=1,
            status="published",
            output_schema=output_schema,
            capabilities=[],
            mcp_servers=[],
            budget_usd=Decimal("1.00000000"),
            model_connection_id=connection.id,
        )
        session.add(agent)
        session.commit()
        connection_id = connection.id
        agent_id = agent.id

    response = client.delete(f"/api/model-connections/{connection_id}")
    body = cast(dict[str, object], response.json())

    assert response.status_code == 409, body
    assert body["code"] == "model_connection_in_use"
    assert body["details"] == [
        {
            "field": "modelConnection",
            "issue": "Model connection is referenced",
            "refType": "agent",
            "refId": agent_id,
            "refKey": "agent_delete_blocker@1",
        }
    ]
    assert secret_value not in str(body)
    assert "secretPayload" not in str(body)

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is not None


def test_model_connection_delete_blocked_by_transitional_compiled_plan_ref(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-transitional-blocker-4444"
    with session_factory() as session:
        connection = _build_model_connection(
            name="Transitional Referenced Model",
            key="transitional_referenced_model",
            status="active",
            api_key=secret_value,
        )
        session.add(connection)
        session.flush()
        package = WorkflowPackageRepository(session).create_package(
            key="transitional_delete_blocker",
            name="Transitional Delete Blocker",
        )
        version = WorkflowPackageRepository(session).create_version(
            package,
            manifest_source="apiVersion: signaldeck.workflowPackage/v1\n",
            manifest_hash="transitional-delete-manifest-hash",
            package_definition={"metadata": {"key": package.key}},
            compiled_plan={
                "agents": [
                    {
                        "key": "local_agent",
                        "modelConnection": connection.key,
                    }
                ]
            },
            compiled_hash="transitional-delete-compiled-hash",
        )
        session.commit()
        connection_id = connection.id
        version_id = version.id

    response = client.delete(f"/api/model-connections/{connection_id}")
    body = cast(dict[str, object], response.json())

    assert response.status_code == 409, body
    assert body["code"] == "model_connection_in_use"
    assert body["details"] == [
        {
            "field": "modelConnection",
            "issue": "Model connection is referenced",
            "refType": "workflowPackageVersion",
            "refId": version_id,
            "refKey": "transitional_delete_blocker@1",
        }
    ]
    assert secret_value not in str(body)
    assert "secretPayload" not in str(body)

    with session_factory() as session:
        assert session.get(ModelConnection, connection_id) is not None


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
        model_connection = _build_model_connection(
            name="Version Pinning Model",
            key="version_pinning_model",
            status="active",
            api_key="sk-version-pinning",
        )
        session.add_all([published_skill, published_schema, published_server, model_connection])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_skill],
            mcp_servers=[published_server],
            budget_usd=Decimal("1.50000000"),
            model_connection_id=model_connection.id,
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
            model_connection_id=model_connection.id,
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
        model_connection = _build_model_connection(
            name="Model Filter Model",
            key="model_filter_model",
            status="active",
            api_key="sk-model-filter",
        )
        session.add_all([published_skill, published_schema, published_server, model_connection])
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
                    model_connection_id=model_connection.id,
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
                    model_connection_id=model_connection.id,
                    model="gpt-live-v2",
                ),
            ]
        )
        session.commit()

        agent_repo = AgentRepository(session)

        assert [item.key for item in agent_repo.list_latest_versions(model="gpt-snapshot-v1")] == [
            "snapshot_agent"
        ]


def test_target_fk_population_for_agent_workflow_rerun_and_replay(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    with session_factory() as session:
        agent, workflow = _seed_run_target_fk_targets(session, key_prefix="target_fk")
        agent_id = agent.id
        workflow_id = workflow.id
        service = RunService(session, session_factory)

        agent_created = service.create_target_run("agent", agent_id, {"ticker": "NVDA"})
        workflow_created = service.create_target_run("workflow", workflow_id, {"ticker": "MSFT"})

        agent_run = session.get(Run, agent_created.id)
        workflow_run = session.get(Run, workflow_created.id)
        assert agent_run is not None
        assert workflow_run is not None
        _assert_executable_target_fk_identity(agent_run, agent_id=agent_id)
        _assert_executable_target_fk_identity(workflow_run, workflow_id=workflow_id)

        agent_rerun = service.create_rerun(
            agent_run.id,
            RunRerunCreateRequest(parameters={"ticker": "AAPL"}),
        )
        agent_rerun_run = session.get(Run, agent_rerun.id)
        assert agent_rerun_run is not None
        _assert_executable_target_fk_identity(agent_rerun_run, agent_id=agent_id)

        persisted_at = datetime(2026, 5, 9, 12, 0, tzinfo=UTC_TZ)
        workflow_run.status = "succeeded"
        workflow_run.started_at = persisted_at
        workflow_run.finished_at = persisted_at
        for step in cast(list[RunStep], workflow_run.steps):
            step.status = "succeeded"
            step.started_at = persisted_at
            step.finished_at = persisted_at
            step.persisted_at = persisted_at
        session.commit()

        workflow_rerun = service.create_rerun(
            workflow_run.id,
            RunRerunCreateRequest(parameters={"ticker": "IBM"}),
        )
        workflow_replay = service.create_step_replay(
            workflow_run.id,
            RunStepReplayCreateRequest(
                replay_step_index=1,
                parameters={"ticker": "AMD"},
            ),
        )
        workflow_rerun_run = session.get(Run, workflow_rerun.id)
        workflow_replay_run = session.get(Run, workflow_replay.id)
        assert workflow_rerun_run is not None
        assert workflow_replay_run is not None
        _assert_executable_target_fk_identity(workflow_rerun_run, workflow_id=workflow_id)
        _assert_executable_target_fk_identity(workflow_replay_run, workflow_id=workflow_id)


def test_delete_target_with_queued_running_runs_cascades_target_fk_runs(
    session_factory: sessionmaker[Session],
) -> None:
    statuses = ("queued", "running", "succeeded", "failed")
    with session_factory() as session:
        agent, workflow = _seed_run_target_fk_targets(session, key_prefix="cascade_fk")
        package, package_version = _seed_workflow_package_target(
            session,
            key_prefix="cascade_fk",
        )
        target_runs: list[Run] = []
        for status_value in statuses:
            agent_run = _build_deletable_run(
                target_kind="agent",
                target_id=agent.id,
                target_key=agent.key,
            )
            agent_run.status = status_value
            agent_run.agent_id = agent.id
            workflow_run = _build_deletable_run(
                target_kind="workflow",
                target_id=workflow.id,
                target_key=workflow.key,
            )
            workflow_run.status = status_value
            workflow_run.target_workflow_id = workflow.id
            package_run = _build_deletable_run(
                target_kind="workflowPackage",
                target_id=package.id,
                target_key=package.key,
            )
            package_run.status = status_value
            package_run.workflow_package_id = package.id
            package_run.workflow_package_key = package.key
            package_run.workflow_package_version_id = package_version.id
            package_run.workflow_package_version = package_version.version
            package_run.workflow_package_hash = package_version.manifest_hash
            package_run.workflow_package_workflow_key = "runtime_workflow"
            target_runs.extend([agent_run, workflow_run, package_run])
        session.add_all(target_runs)
        session.commit()
        run_ids = [run.id for run in target_runs]
        agent_id = agent.id
        workflow_id = workflow.id
        package_id = package.id

        session.expunge_all()
        for target_model, target_id in (
            (Agent, agent_id),
            (Workflow, workflow_id),
            (WorkflowPackage, package_id),
        ):
            target = session.get(target_model, target_id)
            assert target is not None
            session.delete(target)
        session.commit()
        session.expunge_all()

        assert all(session.get(Run, run_id) is None for run_id in run_ids)


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
        model_connection = _build_model_connection(
            name="Run Detail Model",
            key="run_detail_model",
            status="active",
            api_key="sk-run-detail",
        )
        session.add_all([published_skill, published_schema, published_server, model_connection])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_skill],
            mcp_servers=[published_server],
            budget_usd=Decimal("1.25000000"),
            model_connection_id=model_connection.id,
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
                    "extensionDependencies": [],
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
            "extensionDependencies",
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
        model_connection = _build_model_connection(
            name="Post Run Memory Model",
            key="post_run_memory_model",
            status="active",
            api_key="sk-post-run-memory",
        )
        session.add_all([capability, output_schema, model_connection])
        session.flush()

        agent = _build_agent(
            key="portfolio_manager",
            version=1,
            status="published",
            output_schema=output_schema,
            capabilities=[capability],
            mcp_servers=[],
            budget_usd=Decimal("1.25000000"),
            model_connection_id=model_connection.id,
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


def _build_deletable_run(
    *,
    target_kind: str = "workflow",
    target_id: int = 9001,
    target_key: str = "delete_target",
) -> Run:
    return Run(
        target_kind=target_kind,
        target_id=target_id,
        target_key=target_key,
        target_version=1,
        input={"ticker": "NVDA"},
        status="succeeded",
        final_output={"summary": "done"},
        total_tokens=11,
        inherited_tokens=0,
        executed_tokens=11,
    )


def _build_run_memory_report(run_id: int, *, slug: str, source: str = "agent") -> Report:
    return Report(
        name=slug,
        slug=slug,
        source=source,
        content="memory",
        metadata_={
            "analysis": {
                "reviewType": "agent_memory",
                "versionGroup": "agent_memory/v1",
                "runId": run_id,
            }
        },
    )


def test_run_delete_cascades_steps_invocations_and_agent_memory_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_deletable_run()
        session.add(run)
        session.flush()
        step = RunStep(run_id=run.id, step_index=1, status="succeeded", origin="planned")
        session.add(step)
        session.flush()
        invocation = RunAgentInvocation(
            run_step_id=step.id,
            run_id=run.id,
            step_index=1,
            slot="decision",
            position=0,
            agent_id=1,
            agent_key="delete_agent",
            agent_version=1,
            output_schema_id=1,
            output_schema_version=1,
            input_mode="passthrough",
            wiring={},
            optional=False,
            status="succeeded",
            resolved_input={"ticker": "NVDA"},
            resolved_input_origin="passthrough",
            output={"decision": "buy"},
            output_origin="executed",
            tokens=11,
        )
        retained = _build_run_memory_report(run.id + 100, slug="retained_memory")
        external = _build_run_memory_report(run.id, slug="external_memory", source="external")
        non_memory = Report(
            name="agent_non_memory",
            slug="agent_non_memory",
            source="agent",
            content="not memory",
            metadata_={"analysis": {"reviewType": "other", "runId": run.id}},
        )
        owned = _build_run_memory_report(run.id, slug="owned_memory")
        session.add_all([invocation, owned, retained, external, non_memory])
        session.commit()
        run_id = run.id
        step_id = step.id
        invocation_id = invocation.id

        RunService(session).delete_run(run_id)
        session.expunge_all()

        assert session.get(Run, run_id) is None
        assert session.get(RunStep, step_id) is None
        assert session.get(RunAgentInvocation, invocation_id) is None
        remaining_slugs = {report.slug for report in session.query(Report).all()}
        assert remaining_slugs == {"retained_memory", "external_memory", "agent_non_memory"}


def test_lineage_set_null_on_run_delete(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        source = _build_deletable_run(target_id=9101, target_key="source_run")
        session.add(source)
        session.flush()
        descendant = _build_deletable_run(target_id=9102, target_key="descendant_run")
        descendant.source_run_id = source.id
        descendant.lineage_root_run_id = source.id
        session.add(descendant)
        session.commit()
        source_id = source.id
        descendant_id = descendant.id

        RunService(session).delete_run(source_id)
        session.expire_all()

        persisted = session.get(Run, descendant_id)
        assert persisted is not None
        assert persisted.source_run_id is None
        assert persisted.lineage_root_run_id is None


def test_delete_run_route_returns_204_then_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _build_deletable_run(target_id=9201, target_key="route_delete")
        session.add(run)
        session.flush()
        session.add(_build_run_memory_report(run.id, slug="route_owned_memory"))
        session.commit()
        run_id = run.id

    first = client.delete(f"/api/runs/{run_id}")
    assert first.status_code == 204, first.text
    assert first.content == b""

    second = client.delete(f"/api/runs/{run_id}")
    assert second.status_code == 404, second.json()

    with session_factory() as session:
        assert session.query(Report).filter_by(slug="route_owned_memory").one_or_none() is None


def _seed_delete_graph(session: Session) -> dict[str, int]:
    connection = _build_model_connection(
        name="Delete Graph OpenAI",
        key="delete_graph_openai",
        status="active",
        api_key="sk-delete-graph",
    )
    output_schema = _build_output_schema(
        key="delete_graph_schema",
        version=1,
        status="published",
    )
    capability = _build_skill(key="delete_graph_capability", version=1, status="published")
    mcp_server = _build_mcp_server(
        key="delete_graph_mcp",
        version=1,
        status="published",
        transport="stdio",
    )
    session.add_all([connection, output_schema, capability, mcp_server])
    session.flush()
    agent = _build_agent(
        key="delete_graph_agent",
        version=1,
        status="published",
        output_schema=output_schema,
        capabilities=[capability],
        mcp_servers=[mcp_server],
        budget_usd=Decimal("1.00"),
        model_connection_id=connection.id,
    )
    session.add(agent)
    session.flush()
    workflow = _build_workflow(
        key="delete_graph_workflow",
        version=1,
        status="published",
        agent=agent,
        aggregate_budget_usd=Decimal("1.00"),
    )
    session.add(workflow)
    session.flush()
    session.add_all(
        [
            WorkflowAgentRef(workflow_id=workflow.id, agent_id=agent.id),
            AgentCapabilityRef(
                agent_id=agent.id,
                capability_id=capability.id,
                capability_key=capability.key,
            ),
            AgentMcpServerRef(
                agent_id=agent.id,
                mcp_server_id=mcp_server.id,
                mcp_server_key=mcp_server.key,
            ),
        ]
    )
    session.commit()
    return {
        "connection_id": connection.id,
        "schema_id": output_schema.id,
        "capability_id": capability.id,
        "mcp_server_id": mcp_server.id,
        "agent_id": agent.id,
        "workflow_id": workflow.id,
    }


def test_workflow_delete_cascades_owned_runs_but_not_referenced_agent(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_delete_graph(session)
        run = _build_deletable_run(
            target_kind="workflow",
            target_id=ids["workflow_id"],
            target_key="delete_graph_workflow",
        )
        run.target_workflow_id = ids["workflow_id"]
        session.add(run)
        session.flush()
        session.add(_build_run_memory_report(run.id, slug="workflow_delete_memory"))
        session.commit()
        run_id = run.id

        WorkflowService(session).delete_workflow(ids["workflow_id"])
        session.expunge_all()

        assert session.get(Workflow, ids["workflow_id"]) is None
        assert session.get(Run, run_id) is None
        assert session.get(Agent, ids["agent_id"]) is not None
        assert session.query(WorkflowAgentRef).count() == 0
        assert session.query(Report).filter_by(slug="workflow_delete_memory").one_or_none() is None


def test_agent_delete_blocked_by_workflow_refs_then_deletes_when_allowed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_delete_graph(session)
        run = _build_deletable_run(
            target_kind="agent",
            target_id=ids["agent_id"],
            target_key="delete_graph_agent",
        )
        run.agent_id = ids["agent_id"]
        session.add(run)
        session.flush()
        session.add(_build_run_memory_report(run.id, slug="agent_delete_memory"))
        session.commit()
        run_id = run.id

        repository = AgentRepository(session)
        service = AgentService(session, get_default_tool_catalog(), DefaultMcpConnectionTester())
        assert repository.get(ids["agent_id"]) is not None
        with pytest.raises(ApiError) as exc_info:
            service.delete_agent(ids["agent_id"])  # pyright: ignore[reportAttributeAccessIssue]
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "agent_delete_blocked"

        _ = session.query(WorkflowAgentRef).delete()
        session.commit()
        service.delete_agent(ids["agent_id"])  # pyright: ignore[reportAttributeAccessIssue]
        session.expunge_all()

        assert session.get(Agent, ids["agent_id"]) is None
        assert session.get(Run, run_id) is None
        assert session.query(AgentCapabilityRef).count() == 0
        assert session.query(AgentMcpServerRef).count() == 0
        assert session.query(Report).filter_by(slug="agent_delete_memory").one_or_none() is None


def test_shared_dependency_delete_blocked_by_agent_refs(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        ids = _seed_delete_graph(session)
        with pytest.raises(ApiError) as schema_error:
            OutputSchemaService(session).delete_schema(ids["schema_id"])
        with pytest.raises(ApiError) as capability_error:
            CapabilityService(session, get_default_tool_catalog()).delete_capability(
                ids["capability_id"]
            )
        with pytest.raises(ApiError) as mcp_error:
            McpServerService(session, DefaultMcpConnectionTester()).delete_server(
                ids["mcp_server_id"]
            )

        assert schema_error.value.status_code == 409
        assert schema_error.value.details[0]["agentId"] == ids["agent_id"]
        assert capability_error.value.status_code == 409
        assert capability_error.value.details[0]["agentId"] == ids["agent_id"]
        assert mcp_error.value.status_code == 409
        assert mcp_error.value.details[0]["agentId"] == ids["agent_id"]


def test_draft_replacement_physically_deletes_superseded_global_drafts(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        output_schema = OutputSchemaService(session).create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "draft_replace_schema",
                    "kind": "standalone",
                    "name": "Draft Replace Schema",
                    "description": "Before",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {"before": {"type": "string"}},
                    },
                }
            )
        )
        capability = CapabilityService(session, get_default_tool_catalog()).create_draft(
            CapabilityDraftCreate.model_validate(
                {
                    "key": "draft_replace_capability",
                    "name": "Draft Replace Capability",
                    "toolKeys": [REPORT_MEMORY_WRITE_TOOL_KEY],
                }
            )
        )
        mcp_server = McpServerService(session, DefaultMcpConnectionTester()).create_draft(
            McpServerCreate.model_validate(
                {
                    "key": "draft-replace-mcp",
                    "name": "Draft Replace MCP",
                    "transport": "stdio",
                    "command": "python3",
                    "args": ["-V"],
                }
            )
        )
        original_ids = {output_schema.id, capability.id, mcp_server.id}

        updated_schema = OutputSchemaService(session).update_draft(
            output_schema.id,
            OutputSchemaDraftUpdate.model_validate(
                {
                    "name": "Updated Draft Replace Schema",
                    "jsonSchema": {"type": "object", "properties": {"after": {"type": "string"}}},
                }
            ),
        )
        updated_capability = CapabilityService(session, get_default_tool_catalog()).update_draft(
            capability.id,
            CapabilityDraftUpdate.model_validate(
                {
                    "name": "Updated Draft Replace Capability",
                    "toolKeys": [REPORT_MEMORY_WRITE_TOOL_KEY],
                }
            ),
        )
        updated_mcp_server = McpServerService(session, DefaultMcpConnectionTester()).update_draft(
            mcp_server.id,
            McpServerUpdate.model_validate(
                {
                    "name": "Updated Draft Replace MCP",
                    "transport": McpServerTransport.STDIO.value,
                    "command": "python3",
                    "args": ["-V"],
                }
            ),
        )
        session.expunge_all()

        assert {updated_schema.id, updated_capability.id, updated_mcp_server.id}.isdisjoint(
            original_ids
        )
        assert all(session.get(OutputSchema, row_id) is None for row_id in [output_schema.id])
        assert all(session.get(Capability, row_id) is None for row_id in [capability.id])
        assert all(session.get(McpServer, row_id) is None for row_id in [mcp_server.id])
        assert session.get(OutputSchema, updated_schema.id) is not None
        assert session.get(Capability, updated_capability.id) is not None
        assert session.get(McpServer, updated_mcp_server.id) is not None
