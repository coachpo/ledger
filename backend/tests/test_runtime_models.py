from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.base import Base
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow import Workflow
from app.schemas.output_schema import OutputSchemaDraftCreate
from app.schemas.run import RunListItemRead, RunMemoryArtifactRead, RunRead, RunStatus
from app.services.output_schema_service import OutputSchemaService

UTC_TZ = timezone.utc  # noqa: UP017

LEGACY_BACKEND_TABLE_NAMES = {
    "agent_specs",
    "workflow_specs",
    "persona_profiles",
    "capability_registry_entries",
    "runtime_runs",
    "runtime_trace_events",
    "runtime_approvals",
    "runtime_checkpoints",
    "runtime_run_artifacts",
    "persona_projection_events",
    "orchestration_roles",
    "orchestration_characters",
}
AGENT_PLATFORM_CONFIG_TABLE_NAMES = {
    "capabilities",
    "mcp_servers",
    "model_connections",
    "output_schemas",
}
AGENT_PLATFORM_EXECUTION_TABLE_NAMES = {
    "agents",
    "workflows",
    "runs",
}


def _build_capability(*, key: str, version: int, status: str) -> Capability:
    return Capability(
        key=key,
        version=version,
        status=status,
        name=f"{key}-{version}",
        description="Toolset description",
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
        description="Schema description",
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
        auth={"apiKey": "secret-token", "header": "Authorization"},
        enabled=enabled,
    )


def _build_agent(
    *,
    key: str,
    version: int,
    status: str,
    output_schema: OutputSchema,
    capabilities: list[Capability],
    mcp_servers: list[McpServer],
    budget_usd: Decimal = Decimal("1.25000000"),
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


def _build_run(
    *,
    target_kind: str,
    target_id: int,
    target_key: str,
    target_version: int,
    status: str,
    final_output: object | None,
    total_tokens: int,
    trace_id: str | None,
    started_at: datetime | None,
    finished_at: datetime | None,
    error: str | None = None,
) -> Run:
    return Run(
        target_kind=target_kind,
        target_id=target_id,
        target_key=target_key,
        target_version=target_version,
        input={"ticker": "NVDA", "horizonDays": 30},
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        trace_id=trace_id,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )


def test_legacy_backend_tables_are_not_registered_on_metadata() -> None:
    assert LEGACY_BACKEND_TABLE_NAMES.isdisjoint(Base.metadata.tables)


def test_agent_platform_config_tables_are_registered_on_metadata() -> None:
    assert AGENT_PLATFORM_CONFIG_TABLE_NAMES <= set(Base.metadata.tables)

    capability_table = Base.metadata.tables["capabilities"]
    mcp_server_table = Base.metadata.tables["mcp_servers"]
    model_connection_table = Base.metadata.tables["model_connections"]
    output_schema_table = Base.metadata.tables["output_schemas"]

    assert {"uq_capabilities_published_key", "uq_capabilities_draft_key"} <= {
        index.name for index in capability_table.indexes
    }
    assert {"uq_mcp_servers_published_key", "uq_mcp_servers_draft_key"} <= {
        index.name for index in mcp_server_table.indexes
    }
    assert {
        "ix_model_connections_key",
        "ix_model_connections_status",
        "ix_model_connections_model_id",
    } <= {index.name for index in model_connection_table.indexes}
    assert {"uq_output_schemas_published_key", "uq_output_schemas_draft_key"} <= {
        index.name for index in output_schema_table.indexes
    }
    assert "config" in mcp_server_table.c
    assert {
        "secret_payload",
        "key",
        "last_tested_at",
        "last_test_ok",
        "last_test_message",
        "reasoning_effort",
        "api_style",
    } <= set(model_connection_table.c.keys())
    reasoning_effort_column = model_connection_table.c.reasoning_effort
    assert reasoning_effort_column.nullable is True
    assert getattr(reasoning_effort_column.type, "length", None) == 128
    assert str(reasoning_effort_column.default) == "ScalarElementColumnDefault('medium')"
    assert str(reasoning_effort_column.server_default) == (
        "DefaultClause('medium', for_update=False)"
    )
    assert model_connection_table.c.api_style.nullable is False
    assert model_connection_table.c.api_style.default is not None
    assert model_connection_table.c.api_style.server_default is not None
    constraints = {
        constraint.name: constraint
        for constraint in model_connection_table.constraints
        if constraint.name
    }
    assert {
        "ck_model_connections_status",
        "ck_model_connections_reasoning_effort",
        "ck_model_connections_api_style",
        "ck_model_connections_timeout_seconds_positive",
        "uq_model_connections_key",
    } <= constraints.keys()
    reasoning_effort_constraint = cast(
        CheckConstraint,
        constraints["ck_model_connections_reasoning_effort"],
    )
    assert str(reasoning_effort_constraint.sqltext) == (
        "reasoning_effort IS NULL OR (length(btrim(reasoning_effort)) BETWEEN 1 AND 128)"
    )
    assert "ck_mcp_servers_target" not in {
        constraint.name for constraint in mcp_server_table.constraints if constraint.name
    }


def test_agent_platform_model_connections_enforce_unique_keys(session_factory) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="primary_openai",
                status="active",
                name="Primary OpenAI",
                description="Primary model connection",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.4-mini",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
            )
        )
        session.commit()

        session.add(
            ModelConnection(
                key="primary_openai",
                status="active",
                name="Duplicate OpenAI",
                description="Duplicate model connection",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.4",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_agent_platform_agent_models_pin_versioned_dependencies_and_enforce_status_indexes(
    session_factory,
) -> None:
    assert AGENT_PLATFORM_EXECUTION_TABLE_NAMES <= set(Base.metadata.tables)
    run_step_table = Base.metadata.tables["run_steps"]
    invocation_table = Base.metadata.tables["run_agent_invocations"]
    assert "graph_metadata" in run_step_table.c
    assert "graph_metadata" in invocation_table.c
    agent_table = Base.metadata.tables["agents"]
    assert {
        "uq_agents_published_key",
        "uq_agents_draft_key",
        "ix_agents_model_connection",
        "ix_agents_output_schema",
    } <= {index.name for index in agent_table.indexes}
    assert agent_table.c.model_connection_id.nullable is False
    assert agent_table.c.model_connection_snapshot.nullable is False
    assert {"temperature", "max_tool_rounds", "streaming"}.isdisjoint(agent_table.c.keys())

    with session_factory() as session:
        published_capability = _build_capability(
            key="research_capability",
            version=1,
            status="published",
        )
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
        session.add_all([published_capability, published_schema, published_server])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_capability],
            mcp_servers=[published_server],
        )
        session.add(published_agent)
        session.commit()
        session.refresh(published_agent)

        stored_agent = session.get(Agent, published_agent.id)
        assert stored_agent is not None
        assert stored_agent.output_schema_version == 1
        assert stored_agent.capabilities == [
            {
                "capabilityId": published_capability.id,
                "capabilityKey": "research_capability",
                "capabilityVersion": 1,
            }
        ]
        assert stored_agent.mcp_servers == [
            {
                "mcpServerId": published_server.id,
                "mcpServerKey": "market_data",
                "mcpServerVersion": 1,
            }
        ]
        assert stored_agent.budget_usd == Decimal("1.25000000")

        draft_schema = _build_output_schema(
            key="decision_schema",
            version=2,
            status="draft",
        )
        session.add(draft_schema)
        session.flush()
        session.add(
            _build_agent(
                key="research_agent",
                version=2,
                status="published",
                output_schema=draft_schema,
                capabilities=[published_capability],
                mcp_servers=[published_server],
                budget_usd=Decimal("2.50000000"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        draft_schema = _build_output_schema(
            key="decision_schema",
            version=2,
            status="draft",
        )
        session.add(draft_schema)
        session.flush()

        session.add(
            _build_agent(
                key="research_agent",
                version=2,
                status="draft",
                output_schema=draft_schema,
                capabilities=[published_capability],
                mcp_servers=[published_server],
                budget_usd=Decimal("2.50000000"),
            )
        )
        session.commit()

        session.add(
            _build_agent(
                key="research_agent",
                version=3,
                status="draft",
                output_schema=draft_schema,
                capabilities=[published_capability],
                mcp_servers=[published_server],
                budget_usd=Decimal("3.00000000"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_agent_platform_skill_models_enforce_single_published_and_single_draft_versions(
    session_factory,
) -> None:
    with session_factory() as session:
        session.add(_build_capability(key="market_lookup", version=1, status="published"))
        session.commit()

        session.add(_build_capability(key="market_lookup", version=2, status="published"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_build_capability(key="market_lookup", version=2, status="draft"))
        session.commit()

        session.add(_build_capability(key="market_lookup", version=3, status="draft"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_agent_platform_output_schema_models_preserve_registry_refs_and_active_versions(
    session_factory,
) -> None:
    with session_factory() as session:
        session.add(
            _build_output_schema(
                key="decision_schema",
                version=1,
                status="published",
                kind="shared",
                registry_refs=["Action"],
            )
        )
        session.commit()

        session.add(
            _build_output_schema(
                key="decision_schema",
                version=2,
                status="published",
                kind="shared",
                registry_refs=["Action", "PriceTarget"],
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        draft_schema = _build_output_schema(
            key="decision_schema",
            version=2,
            status="draft",
            kind="shared",
            registry_refs=["Action", "PriceTarget"],
        )
        session.add(draft_schema)
        session.commit()
        session.refresh(draft_schema)

        stored_schema = session.get(OutputSchema, draft_schema.id)
        assert stored_schema is not None
        assert stored_schema.kind == "shared"
        assert stored_schema.registry_refs == ["Action", "PriceTarget"]
        assert stored_schema.json_schema["type"] == "object"


def test_agent_platform_schema_registry_resolves_transitive_refs_for_runtime_compilation(
    session_factory,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        action_schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "action_type",
                    "kind": "shared",
                    "name": "Action Type",
                    "jsonSchema": {"type": "string", "enum": ["buy", "hold", "sell"]},
                }
            )
        )
        service.activate(action_schema.id)

        price_target = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "price_target",
                    "kind": "shared",
                    "name": "Price Target",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "action": {"$ref": "registry://action_type"},
                            "horizonDays": {"type": "integer"},
                        },
                        "required": ["ticker", "action", "horizonDays"],
                    },
                }
            )
        )
        service.activate(price_target.id)

        decision = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "trading_decision",
                    "name": "Trading Decision",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "targets": {
                                "type": "array",
                                "items": {"$ref": "registry://price_target"},
                            },
                        },
                        "required": ["summary", "targets"],
                    },
                }
            )
        )

        stored_decision = session.get(OutputSchema, decision.id)
        assert stored_decision is not None
        assert (
            stored_decision.json_schema["properties"]["targets"]["items"]["$ref"]
            == "registry://price_target@1"
        )

        model_type = service.compile_schema_model(decision.id)
        validated = model_type.model_validate(
            {
                "summary": "Watch the setup",
                "targets": [
                    {"ticker": "NVDA", "action": "buy", "horizonDays": 30},
                    {"ticker": "MSFT", "action": "hold", "horizonDays": 60},
                ],
            }
        )
        assert validated.model_dump() == {
            "summary": "Watch the setup",
            "targets": [
                {"ticker": "NVDA", "action": "buy", "horizonDays": 30},
                {"ticker": "MSFT", "action": "hold", "horizonDays": 60},
            ],
        }

        with pytest.raises(ValidationError):
            model_type.model_validate(
                {
                    "summary": "Bad action",
                    "targets": [{"ticker": "NVDA", "action": "wait", "horizonDays": 30}],
                }
            )


def test_agent_platform_schema_compiler_preserves_metadata_without_changing_validation(
    session_factory,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "metadata_runtime_input",
                    "name": "Metadata Runtime Input",
                    "jsonSchema": {
                        "type": "object",
                        "title": "Run input",
                        "description": "Values supplied when starting a run.",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "title": "Ticker symbol",
                                "description": "Public market ticker to research.",
                            },
                            "horizonDays": {
                                "type": "integer",
                                "title": "Horizon days",
                                "description": "Optional number of days to assess.",
                            },
                            "priceTargets": {
                                "type": "array",
                                "title": "Price targets",
                                "description": "Optional candidate price targets.",
                                "items": {
                                    "type": "number",
                                    "title": "Price target",
                                    "description": "Candidate target price.",
                                },
                            },
                        },
                        "required": ["ticker"],
                        "additionalProperties": False,
                    },
                }
            )
        )

        json_schema = schema.json_schema
        properties = json_schema["properties"]
        assert json_schema["title"] == "Run input"
        assert json_schema["description"] == "Values supplied when starting a run."
        assert properties["ticker"]["title"] == "Ticker symbol"
        assert properties["horizonDays"]["description"] == "Optional number of days to assess."
        assert "horizonDays" not in json_schema["required"]
        assert properties["priceTargets"]["description"] == "Optional candidate price targets."
        assert properties["priceTargets"]["items"]["title"] == "Price target"

        model_type = service.compile_schema_model(schema.id)
        validated = model_type.model_validate({"ticker": "NVDA", "priceTargets": [125.5]})
        assert validated.model_dump(exclude_none=True) == {
            "ticker": "NVDA",
            "priceTargets": [125.5],
        }

        with pytest.raises(ValidationError):
            model_type.model_validate({"horizonDays": 30})


def test_agent_platform_schema_compiler_imports_and_renders_json_schema_defaults(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "defaulted_runtime_input",
                    "name": "Defaulted Runtime Input",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "default": "NVDA"},
                            "request": {
                                "type": "object",
                                "properties": {
                                    "horizonDays": {"type": "integer", "default": 30},
                                },
                                "default": {"horizonDays": 30},
                            },
                        },
                        "required": ["ticker"],
                        "additionalProperties": False,
                    },
                }
            )
        )
        stored_schema = session.get(OutputSchema, schema.id)
        assert stored_schema is not None
        rendered = service.get_schema(schema.id)

    properties = cast(dict[str, object], schema.json_schema["properties"])
    ticker = cast(dict[str, object], properties["ticker"])
    request = cast(dict[str, object], properties["request"])
    request_properties = cast(dict[str, object], request["properties"])
    horizon_days = cast(dict[str, object], request_properties["horizonDays"])
    assert ticker["default"] == "NVDA"
    assert request["default"] == {"horizonDays": 30}
    assert horizon_days["default"] == 30
    assert stored_schema.json_schema == schema.json_schema
    assert rendered.json_schema == schema.json_schema

    builder_payload = cast(
        dict[str, object],
        schema.builder.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    builder_field_payloads = cast(list[dict[str, object]], builder_payload["fields"])
    builder_fields = {
        str(field["name"]): cast(dict[str, object], field["schema"])
        for field in builder_field_payloads
    }
    assert builder_fields["ticker"]["defaultValue"] == "NVDA"
    assert builder_fields["request"]["defaultValue"] == {"horizonDays": 30}


def test_agent_platform_schema_compiler_exports_builder_default_value_as_json_schema_default(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "builder_defaulted_runtime_input",
                    "name": "Builder Defaulted Runtime Input",
                    "builder": {
                        "kind": "object",
                        "allowAdditionalProperties": False,
                        "fields": [
                            {
                                "name": "ticker",
                                "required": False,
                                "schema": {"kind": "string", "defaultValue": "NVDA"},
                            },
                            {
                                "name": "horizonDays",
                                "required": False,
                                "schema": {"kind": "integer", "defaultValue": 30},
                            },
                        ],
                    },
                }
            )
        )

    properties = cast(dict[str, object], schema.json_schema["properties"])
    ticker = cast(dict[str, object], properties["ticker"])
    horizon_days = cast(dict[str, object], properties["horizonDays"])
    required = cast(list[str], schema.json_schema["required"])
    assert ticker["default"] == "NVDA"
    assert horizon_days["default"] == 30
    assert required == []


@pytest.mark.parametrize(
    ("schema_key", "property_schema", "expected_field", "expected_issue"),
    [
        (
            "string_default_number",
            {"ticker": {"type": "string", "default": 123}},
            "jsonSchema.properties.ticker.default",
            "Default value must match schema type 'string'",
        ),
        (
            "integer_default_bool",
            {"horizonDays": {"type": "integer", "default": True}},
            "jsonSchema.properties.horizonDays.default",
            "Default value must match schema type 'integer'",
        ),
        (
            "object_default_missing_required",
            {
                "request": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "horizonDays": {"type": "integer"},
                    },
                    "required": ["ticker", "horizonDays"],
                    "default": {"ticker": "NVDA"},
                }
            },
            "jsonSchema.properties.request.default.horizonDays",
            "Default object is missing required field 'horizonDays'",
        ),
        (
            "null_default",
            {"ticker": {"type": "string", "default": None}},
            "jsonSchema.properties.ticker.default",
            "Null defaults are not supported",
        ),
        (
            "enum_default_wrong_value",
            {"action": {"type": "string", "enum": ["buy", "sell"], "default": "hold"}},
            "jsonSchema.properties.action.default",
            "Default value must equal one enum value",
        ),
        (
            "enum_default_null",
            {"action": {"type": "string", "enum": ["buy", "sell"], "default": None}},
            "jsonSchema.properties.action.default",
            "Null defaults are not supported",
        ),
        (
            "literal_default_wrong_value",
            {"action": {"type": "string", "const": "buy", "default": "sell"}},
            "jsonSchema.properties.action.default",
            "Default value must equal the literal value",
        ),
        (
            "literal_default_null",
            {"action": {"type": "string", "const": "buy", "default": None}},
            "jsonSchema.properties.action.default",
            "Null defaults are not supported",
        ),
    ],
)
def test_agent_platform_schema_compiler_rejects_invalid_json_schema_defaults(
    session_factory: sessionmaker[Session],
    schema_key: str,
    property_schema: dict[str, object],
    expected_field: str,
    expected_issue: str,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_draft(
                OutputSchemaDraftCreate.model_validate(
                    {
                        "key": schema_key,
                        "name": schema_key.replace("_", " ").title(),
                        "jsonSchema": {
                            "type": "object",
                            "properties": property_schema,
                            "additionalProperties": False,
                        },
                    }
                )
            )

    assert excinfo.value.code == "validation_error"
    assert any(
        detail["field"] == expected_field and expected_issue in detail["issue"]
        for detail in excinfo.value.details
    )


@pytest.mark.parametrize(
    ("default_value", "expected_issue"),
    [
        (None, "Null defaults are not supported"),
        ("hold", "Default value must equal one enum value"),
    ],
)
def test_agent_platform_schema_compiler_validates_ref_defaults_against_resolved_schema(
    session_factory: sessionmaker[Session],
    default_value: object,
    expected_issue: str,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)
        shared_action = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "default_ref_action_type",
                    "kind": "shared",
                    "name": "Default Ref Action Type",
                    "jsonSchema": {"type": "string", "enum": ["buy", "sell"]},
                }
            )
        )
        service.activate(shared_action.id)

        accepted_schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "default_ref_valid",
                    "name": "Default Ref Valid",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "$ref": "registry://default_ref_action_type",
                                "default": "buy",
                            }
                        },
                        "additionalProperties": False,
                    },
                }
            )
        )
        accepted_action = cast(
            dict[str, object],
            cast(dict[str, object], accepted_schema.json_schema["properties"])["action"],
        )
        assert accepted_action["$ref"] == "registry://default_ref_action_type@1"
        assert accepted_action["default"] == "buy"

        with pytest.raises(ApiError) as excinfo:
            service.create_draft(
                OutputSchemaDraftCreate.model_validate(
                    {
                        "key": "default_ref_invalid",
                        "name": "Default Ref Invalid",
                        "jsonSchema": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "$ref": "registry://default_ref_action_type",
                                    "default": default_value,
                                }
                            },
                            "additionalProperties": False,
                        },
                    }
                )
            )

    assert excinfo.value.code == "validation_error"
    assert any(
        detail["field"] == "jsonSchema.properties.action.default"
        and expected_issue in detail["issue"]
        for detail in excinfo.value.details
    )


def test_agent_platform_runtime_model_keeps_defaulted_required_fields_required(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)
        schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "runtime_default_strictness",
                    "name": "Runtime Default Strictness",
                    "jsonSchema": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "default": "NVDA"},
                            "horizonDays": {"type": "integer", "default": 30},
                        },
                        "required": ["ticker"],
                        "additionalProperties": False,
                    },
                }
            )
        )
        model_type = service.compile_schema_model(schema.id)

    with pytest.raises(ValidationError) as excinfo:
        _ = model_type.model_validate({"horizonDays": 45})
    assert any(
        error["loc"] == ("ticker",) and error["type"] == "missing"
        for error in excinfo.value.errors()
    )

    validated = model_type.model_validate({"ticker": "MSFT"})
    assert validated.model_dump() == {"ticker": "MSFT", "horizonDays": 30}

    explicit_value = model_type.model_validate({"ticker": "AAPL", "horizonDays": 60})
    assert explicit_value.model_dump() == {"ticker": "AAPL", "horizonDays": 60}


def test_agent_platform_schema_compiler_supports_discriminated_union_models(
    session_factory,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)

        bullish_signal = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "bullish_signal",
                    "kind": "shared",
                    "name": "Bullish Signal",
                    "jsonSchema": {
                        "type": "object",
                        "title": "Bullish signal",
                        "description": "Bullish branch payload.",
                        "properties": {
                            "kind": {"const": "bullish"},
                            "score": {"type": "integer"},
                        },
                        "required": ["kind", "score"],
                    },
                }
            )
        )
        service.activate(bullish_signal.id)

        bearish_signal = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "bearish_signal",
                    "kind": "shared",
                    "name": "Bearish Signal",
                    "jsonSchema": {
                        "type": "object",
                        "title": "Bearish signal",
                        "description": "Bearish branch payload.",
                        "properties": {
                            "kind": {"const": "bearish"},
                            "reason": {"type": "string"},
                        },
                        "required": ["kind", "reason"],
                    },
                }
            )
        )
        service.activate(bearish_signal.id)

        union_schema = service.create_draft(
            OutputSchemaDraftCreate.model_validate(
                {
                    "key": "signal_union",
                    "name": "Signal Union",
                    "jsonSchema": {
                        "title": "Signal union",
                        "description": "Discriminated signal branch.",
                        "anyOf": [
                            {"$ref": "registry://bullish_signal"},
                            {"$ref": "registry://bearish_signal"},
                        ],
                        "discriminator": {"propertyName": "kind"},
                    },
                }
            )
        )

        union_json_schema = union_schema.json_schema
        assert union_json_schema["title"] == "Signal union"
        assert union_json_schema["description"] == "Discriminated signal branch."
        assert union_json_schema["anyOf"] == [
            {"$ref": "registry://bullish_signal@1"},
            {"$ref": "registry://bearish_signal@1"},
        ]
        assert bullish_signal.json_schema["title"] == "Bullish signal"
        assert bullish_signal.json_schema["description"] == "Bullish branch payload."
        assert bearish_signal.json_schema["title"] == "Bearish signal"
        assert bearish_signal.json_schema["description"] == "Bearish branch payload."

        model_type = service.compile_schema_model(union_schema.id)
        validated = model_type.model_validate({"kind": "bullish", "score": 9})
        assert validated.model_dump() == {"kind": "bullish", "score": 9}

        with pytest.raises(ValidationError):
            model_type.model_validate({"kind": "bearish", "score": 5})


@pytest.mark.parametrize(
    ("schema_key", "schema_fragment", "expected_field", "expected_issue"),
    [
        (
            "pattern_properties",
            {"patternProperties": {"^x": {"type": "string"}}},
            "jsonSchema.patternProperties",
            "patternProperties is not supported",
        ),
        (
            "one_of",
            {"oneOf": []},
            "jsonSchema.oneOf",
            "Only discriminated anyOf unions are supported",
        ),
        ("all_of", {"allOf": []}, "jsonSchema.allOf", "allOf is not supported"),
        (
            "if_keyword",
            {"if": {"type": "object"}},
            "jsonSchema.if",
            "if/then/else is not supported",
        ),
        (
            "then_keyword",
            {"then": {"type": "object"}},
            "jsonSchema.then",
            "if/then/else is not supported",
        ),
        (
            "else_keyword",
            {"else": {"type": "object"}},
            "jsonSchema.else",
            "if/then/else is not supported",
        ),
        ("not_keyword", {"not": {"type": "object"}}, "jsonSchema.not", "not is not supported"),
        (
            "schema_additional_properties",
            {"additionalProperties": {"type": "string"}},
            "jsonSchema.additionalProperties",
            "Schema-valued additionalProperties is not supported",
        ),
    ],
)
def test_agent_platform_schema_compiler_keeps_unsupported_keywords_rejected(
    session_factory,
    schema_key: str,
    schema_fragment: dict[str, object],
    expected_field: str,
    expected_issue: str,
) -> None:
    with session_factory() as session:
        service = OutputSchemaService(session)
        json_schema = {
            "type": "object",
            "title": "Unsupported keyword guard",
            "description": "Metadata must not loosen schema keyword rules.",
            "properties": {"ticker": {"type": "string", "title": "Ticker"}},
            "required": ["ticker"],
            **schema_fragment,
        }

        with pytest.raises(ApiError) as excinfo:
            service.create_draft(
                OutputSchemaDraftCreate.model_validate(
                    {
                        "key": f"unsupported_{schema_key}",
                        "name": "Unsupported Keyword Guard",
                        "jsonSchema": json_schema,
                    }
                )
            )

    assert excinfo.value.code == "validation_error"
    assert any(
        detail["field"] == expected_field and expected_issue in detail["issue"]
        for detail in excinfo.value.details
    )


def test_agent_platform_mcp_models_encrypt_auth_and_enforce_constraints(session_factory) -> None:
    with session_factory() as session:
        server = _build_mcp_server(
            key="market_data",
            version=1,
            status="published",
            transport="http-sse",
        )
        session.add(server)
        session.commit()
        session.refresh(server)

        raw_config_payload = session.execute(
            text("SELECT config::text FROM mcp_servers WHERE id = :id"),
            {"id": server.id},
        ).scalar_one()
        assert "secret-token" not in raw_config_payload
        assert "Authorization" not in raw_config_payload

        stored_server = session.get(McpServer, server.id)
        assert stored_server is not None
        assert stored_server.headers == {"Authorization": "secret-token"}
        assert stored_server.auth == {"apiKey": "secret-token", "header": "Authorization"}

        session.add(
            _build_mcp_server(
                key="market_data",
                version=2,
                status="published",
                transport="stdio",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        compatibility_server = McpServer(
            key="stdio_market_data",
            version=1,
            status="draft",
            name="stdio-market-data",
            description="Direct constructor compatibility",
            transport="stdio",
            command="python",
            args=["-m", "market_data"],
            env={"LEDGER_MODE": "test"},
            enabled=False,
        )
        session.add(compatibility_server)
        session.commit()
        session.refresh(compatibility_server)

        assert compatibility_server.config == {
            "name": "stdio-market-data",
            "description": "Direct constructor compatibility",
            "enabled": False,
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "market_data"],
            "env": {"LEDGER_MODE": "test"},
        }


def test_agent_platform_workflow_models_pin_agent_schema_versions_and_aggregate_budget(
    session_factory,
) -> None:
    workflow_table = Base.metadata.tables["workflows"]
    assert {"uq_workflows_published_key", "uq_workflows_draft_key"} <= {
        index.name for index in workflow_table.indexes
    }

    with session_factory() as session:
        published_capability = _build_capability(
            key="research_capability",
            version=1,
            status="published",
        )
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
        session.add_all([published_capability, published_schema, published_server])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_capability],
            mcp_servers=[published_server],
            budget_usd=Decimal("1.50000000"),
        )
        session.add(published_agent)
        session.flush()

        workflow = _build_workflow(
            key="market_review",
            version=1,
            status="published",
            agent=published_agent,
            aggregate_budget_usd=Decimal("1.50000000"),
        )
        session.add(workflow)
        session.commit()
        session.refresh(workflow)

        stored_workflow = session.get(Workflow, workflow.id)
        assert stored_workflow is not None
        assert stored_workflow.steps[0]["agents"][0]["agentVersion"] == 1
        assert stored_workflow.steps[0]["agents"][0]["outputSchemaVersion"] == 1
        assert stored_workflow.output_spec["agentVersion"] == 1
        assert stored_workflow.aggregate_budget_usd == Decimal("1.50000000")

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
            capabilities=[published_capability],
            mcp_servers=[published_server],
            budget_usd=Decimal("2.75000000"),
        )
        session.add(draft_agent)
        session.flush()
        session.add(
            _build_workflow(
                key="market_review",
                version=2,
                status="draft",
                agent=draft_agent,
                aggregate_budget_usd=Decimal("2.75000000"),
            )
        )
        session.commit()


def test_agent_platform_run_models_persist_steps_invocations_totals_timestamps_and_trace_ids(
    session_factory,
) -> None:
    run_table = Base.metadata.tables["runs"]
    assert {"ix_runs_status", "ix_runs_target", "ix_runs_target_key"} <= {
        index.name for index in run_table.indexes
    }
    assert {"target_kind", "target_id", "target_key", "target_version", "queued_at"} <= set(
        run_table.c.keys()
    )
    assert run_table.c.status.default is not None
    assert run_table.c.status.server_default is not None
    assert str(run_table.c.status.default) == "ScalarElementColumnDefault('queued')"
    assert run_table.c.started_at.nullable is True
    assert run_table.c.queued_at.nullable is False
    assert {"workflow_id", "workflow_key", "workflow_version", "per_step_outputs"}.isdisjoint(
        run_table.c.keys()
    )

    with session_factory() as session:
        published_capability = _build_capability(
            key="research_capability",
            version=1,
            status="published",
        )
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
        session.add_all([published_capability, published_schema, published_server])
        session.flush()

        published_agent = _build_agent(
            key="research_agent",
            version=1,
            status="published",
            output_schema=published_schema,
            capabilities=[published_capability],
            mcp_servers=[published_server],
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

        queued_at = datetime(2026, 4, 19, 9, 59, tzinfo=UTC_TZ)
        started_at = datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ)
        finished_at = datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ)
        run = _build_run(
            target_kind="workflow",
            target_id=workflow.id,
            target_key=workflow.key,
            target_version=workflow.version,
            status="succeeded",
            final_output={"headline": "Buy"},
            total_tokens=321,
            trace_id="trace-market-review",
            started_at=started_at,
            finished_at=finished_at,
        )
        run.queued_at = queued_at
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
            graph_metadata={"nodeId": "analysis", "nodeKind": "step"},
        )
        session.add(step)
        session.flush()
        session.add(
            RunAgentInvocation(
                run_step_id=step.id,
                run_id=run.id,
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
                graph_metadata={"nodeId": "analysis", "nodeKind": "step"},
                optional=False,
                status="succeeded",
                resolved_input={"ticker": "NVDA"},
                resolved_input_origin="passthrough",
                output={"headline": "Buy"},
                output_origin="executed",
                tokens=321,
                duration_ms=1450,
                trace_span_id="span-analysis",
                started_at=started_at,
                finished_at=finished_at,
                persisted_at=finished_at,
            )
        )
        session.add(
            _build_run(
                target_kind="agent",
                target_id=published_agent.id,
                target_key=published_agent.key,
                target_version=published_agent.version,
                status="failed",
                final_output=None,
                total_tokens=0,
                trace_id="trace-agent-run",
                started_at=started_at,
                finished_at=finished_at,
                error="Missing API key",
            )
        )
        session.commit()
        session.refresh(run)

        stored_run = session.get(Run, run.id)
        assert stored_run is not None
        assert stored_run.target_kind == "workflow"
        assert stored_run.target_id == workflow.id
        assert stored_run.target_key == workflow.key
        assert stored_run.target_version == 1
        assert len(stored_run.steps) == 1
        assert stored_run.steps[0].step_index == 1
        assert stored_run.steps[0].status == "succeeded"
        assert stored_run.steps[0].graph_metadata == {"nodeId": "analysis", "nodeKind": "step"}
        assert len(stored_run.steps[0].invocations) == 1
        assert stored_run.steps[0].invocations[0].graph_metadata == {
            "nodeId": "analysis",
            "nodeKind": "step",
        }
        assert stored_run.steps[0].invocations[0].trace_span_id == "span-analysis"
        assert stored_run.steps[0].invocations[0].resolved_input == {"ticker": "NVDA"}
        assert stored_run.total_tokens == 321
        assert stored_run.trace_id == "trace-market-review"
        assert stored_run.queued_at == queued_at
        assert stored_run.started_at == started_at
        assert stored_run.finished_at == finished_at
        assert stored_run.created_at is not None
        assert stored_run.updated_at is not None

        stored_agent_run = session.query(Run).filter_by(trace_id="trace-agent-run").one()
        assert stored_agent_run.target_kind == "agent"
        assert stored_agent_run.target_id == published_agent.id
        assert stored_agent_run.target_key == published_agent.key
        assert stored_agent_run.target_version == published_agent.version
        assert stored_agent_run.error == "Missing API key"


def test_agent_platform_run_model_allows_queued_status_and_rejects_unknown_status(
    session_factory,
) -> None:
    queued_at = datetime(2026, 4, 20, 11, 0, tzinfo=UTC_TZ)

    with session_factory() as session:
        queued_run = _build_run(
            target_kind="workflow",
            target_id=1,
            target_key="queued_workflow",
            target_version=1,
            status=RunStatus.QUEUED.value,
            final_output=None,
            total_tokens=0,
            trace_id=None,
            started_at=None,
            finished_at=None,
        )
        queued_run.queued_at = queued_at
        session.add(queued_run)
        session.commit()
        session.refresh(queued_run)

        assert queued_run.status == "queued"
        assert queued_run.queued_at == queued_at
        assert queued_run.started_at is None
        assert queued_run.finished_at is None

        session.add(
            _build_run(
                target_kind="workflow",
                target_id=1,
                target_key="queued_workflow",
                target_version=1,
                status="cancelled",
                final_output=None,
                total_tokens=0,
                trace_id=None,
                started_at=None,
                finished_at=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_run_memory_artifact_schema_serializes_memory_native_contract() -> None:
    created_at = datetime(2026, 4, 20, 12, 30, tzinfo=UTC_TZ)
    artifact = RunMemoryArtifactRead.model_validate(
        {
            "memoryId": "mem_1001",
            "summary": "NVDA buy memory",
            "status": "pending",
            "createdAt": created_at,
            "provenance": {
                "runId": 42,
                "agentKey": "portfolio_manager",
                "agentVersion": 3,
                "workflowKey": "market_review",
                "workflowVersion": 1,
            },
            "sourceGraphMetadata": {"nodeId": "portfolio_decision", "slot": "decision"},
            "auditLinks": {
                "report": {
                    "slug": "agent_memory_nvda",
                    "name": "agent_memory_nvda",
                    "url": "/reports/agent_memory_nvda",
                    "downloadUrl": "/api/v1/reports/agent_memory_nvda/download",
                }
            },
        }
    )

    payload = cast(dict[str, object], artifact.model_dump(mode="json", by_alias=True))

    assert set(payload) == {
        "memoryId",
        "summary",
        "status",
        "createdAt",
        "provenance",
        "sourceGraphMetadata",
        "auditLinks",
    }
    assert {"reportId", "slug", "name"}.isdisjoint(payload)
    assert payload["memoryId"] == "mem_1001"
    report = cast(dict[str, object], cast(dict[str, object], payload["auditLinks"])["report"])
    assert report["downloadUrl"] == "/api/v1/reports/agent_memory_nvda/download"
    assert "reportId" not in report


def test_agent_platform_run_schemas_serialize_queued_without_started_at() -> None:
    queued_at = datetime(2026, 4, 20, 11, 0, tzinfo=UTC_TZ)
    common_payload = {
        "id": 42,
        "targetKind": "workflow",
        "targetId": 7,
        "targetKey": "queued_workflow",
        "targetVersion": 1,
        "status": "queued",
        "totalTokens": 0,
        "traceId": None,
        "queuedAt": queued_at,
        "startedAt": None,
        "finishedAt": None,
    }

    list_item = RunListItemRead.model_validate(common_payload)
    detail = RunRead.model_validate(
        {
            **common_payload,
            "input": {"ticker": "NVDA"},
            "resumeStepIndex": 1,
            "finalOutput": None,
            "inheritedTokens": 0,
            "executedTokens": 0,
            "error": None,
            "createdAt": queued_at,
            "updatedAt": queued_at,
            "steps": [],
            "memoryArtifacts": [],
        }
    )

    list_payload = cast(
        dict[str, object],
        list_item.model_dump(mode="json", by_alias=True),
    )
    detail_payload = cast(
        dict[str, object],
        detail.model_dump(mode="json", by_alias=True),
    )

    assert list_payload == {
        **common_payload,
        "queuedAt": "2026-04-20T11:00:00Z",
    }
    assert detail_payload["startedAt"] is None
    assert set(detail_payload) == {
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
