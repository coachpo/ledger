# pyright: reportMissingImports=false, reportPrivateUsage=false

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.services.agent_manifest_compiler import compile_agent_manifest
from app.services.agent_manifest_decompiler import decompile_agent_model
from app.services.agent_manifest_parser import parse_agent_manifest
from tests.test_agent_manifest_compiler import _expected_payload, _seed_manifest_refs


def _agent_row(refs: dict[str, object]) -> Agent:
    connection = refs["connection"]
    output_schema = refs["output_schema"]
    assert isinstance(connection, ModelConnection)
    assert isinstance(output_schema, OutputSchema)
    return Agent(
        key="research_agent",
        version=1,
        status="published",
        name="Research Agent",
        description="Produces a structured research summary.",
        model_connection_id=connection.id,
        model=connection.model_id,
        system_prompt="You are a research analyst.\nReturn concise output.",
        input_schema={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
        output_schema_id=output_schema.id,
        output_schema_version=output_schema.version,
        skills=[
            {"skillId": 999, "skillKey": "sec_filing_lookup", "skillVersion": 2},
        ],
        mcp_servers=[
            {"mcpServerId": 888, "mcpServerKey": "market_data", "mcpServerVersion": 1},
        ],
        budget_usd=Decimal("1.25"),
    )


def test_decompile_agent_manifest_round_trips_stored_payload_to_canonical_yaml(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        agent = _agent_row(refs)
        result = decompile_agent_model(agent, session)
        parsed = parse_agent_manifest(result.source)

        assert result.source.startswith("apiVersion: ledger.agent/v1\nkind: Agent\n")
        assert "systemPrompt: |" in result.source
        assert "capabilities:" in result.source
        assert "skills:" not in result.source
        assert 'budgetUsd: "1.25"' in result.source
        assert parsed.diagnostics == []
        assert parsed.manifest is not None
        assert parsed.manifest.spec.model_connection == "primary_openai"
        connection = refs["connection"]
        assert isinstance(connection, ModelConnection)
        expected_payload = _expected_payload(connection.id)
        assert compile_agent_manifest(result.source, session) == expected_payload
        assert result.payload == expected_payload


def test_decompile_agent_manifest_omits_runtime_only_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        result = decompile_agent_model(_agent_row(refs), session)

    assert "modelConnectionId" not in result.source
    assert "skillId" not in result.source
    assert "skillKey" not in result.source
    assert "mcpServerId" not in result.source
    assert "outputSchemaId" not in result.source
