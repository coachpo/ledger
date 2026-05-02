from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError
from app.models.agent import Agent
from app.models.base import Base
from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.run import Run
from app.models.workflow import Workflow
from app.schemas.output_schema import OutputSchemaDraftCreate
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
        tool_grants=[{"tool": f"{key}.lookup"}],
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
    per_step_outputs: dict[str, list[dict[str, object]]],
    final_output: object | None,
    total_tokens: int,
    total_cost_usd: Decimal,
    trace_id: str | None,
    started_at: datetime,
    finished_at: datetime | None,
    error: str | None = None,
) -> Run:
    return Run(
        target_kind=target_kind,
        target_id=target_id,
        target_key=target_key,
        target_version=target_version,
        input={"ticker": "NVDA", "horizonDays": 30},
        per_step_outputs=per_step_outputs,
        final_output=final_output,
        status=status,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
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
        "has_api_key",
        "api_key_last4",
        "last_tested_at",
        "last_test_ok",
        "last_test_message",
        "api_style",
    } <= set(model_connection_table.c.keys())
    assert model_connection_table.c.api_style.nullable is False
    assert model_connection_table.c.api_style.default is not None
    assert model_connection_table.c.api_style.server_default is not None
    assert {
        "ck_model_connections_status",
        "ck_model_connections_reasoning_effort",
        "ck_model_connections_api_style",
        "ck_model_connections_timeout_seconds_positive",
        "uq_model_connections_key",
    } <= {constraint.name for constraint in model_connection_table.constraints if constraint.name}
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
                organization=None,
                project=None,
                model_id="gpt-5.4-mini",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
                has_api_key=False,
                api_key_last4=None,
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
                organization=None,
                project=None,
                model_id="gpt-5.4",
                reasoning_effort="medium",
                timeout_seconds=60,
                secret_payload={},
                has_api_key=False,
                api_key_last4=None,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_agent_platform_agent_models_pin_versioned_dependencies_and_enforce_status_indexes(
    session_factory,
) -> None:
    assert AGENT_PLATFORM_EXECUTION_TABLE_NAMES <= set(Base.metadata.tables)
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


def test_agent_platform_run_models_persist_per_step_outputs_totals_timestamps_and_trace_ids(
    session_factory,
) -> None:
    run_table = Base.metadata.tables["runs"]
    assert {"ix_runs_status", "ix_runs_target", "ix_runs_target_key"} <= {
        index.name for index in run_table.indexes
    }
    assert {"target_kind", "target_id", "target_key", "target_version"} <= set(run_table.c.keys())
    assert {"workflow_id", "workflow_key", "workflow_version"}.isdisjoint(run_table.c.keys())

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

        started_at = datetime(2026, 4, 19, 10, 0, tzinfo=UTC_TZ)
        finished_at = datetime(2026, 4, 19, 10, 2, tzinfo=UTC_TZ)
        run = _build_run(
            target_kind="workflow",
            target_id=workflow.id,
            target_key=workflow.key,
            target_version=workflow.version,
            status="succeeded",
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
                        "traceSpanId": "span-analysis",
                    }
                ]
            },
            final_output={"headline": "Buy"},
            total_tokens=321,
            total_cost_usd=Decimal("0.15000000"),
            trace_id="trace-market-review",
            started_at=started_at,
            finished_at=finished_at,
        )
        session.add(run)
        session.add(
            _build_run(
                target_kind="agent",
                target_id=published_agent.id,
                target_key=published_agent.key,
                target_version=published_agent.version,
                status="failed",
                per_step_outputs={"1": []},
                final_output=None,
                total_tokens=0,
                total_cost_usd=Decimal("0"),
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
        assert stored_run.per_step_outputs["1"][0]["traceSpanId"] == "span-analysis"
        assert stored_run.per_step_outputs["1"][0]["resolvedInput"] == {"ticker": "NVDA"}
        assert stored_run.total_tokens == 321
        assert stored_run.total_cost_usd == Decimal("0.15000000")
        assert stored_run.trace_id == "trace-market-review"
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
