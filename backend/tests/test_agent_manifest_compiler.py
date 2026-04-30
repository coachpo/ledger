# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability import Capability
from app.models.mcp_server import McpServer
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.schemas.agent import AgentCreate
from app.services.agent_manifest_compiler import AgentManifestCompilerError, compile_agent_manifest
from app.services.agent_manifest_parser import parse_agent_manifest
from tests.test_agent_manifest_parser import _valid_manifest_source


def _seed_manifest_refs(session: Session) -> dict[str, object]:
    connection = ModelConnection(
        key="primary_openai",
        status="active",
        name="Primary OpenAI",
        description="Primary model connection.",
        base_url="https://api.openai.com/v1",
        model_id="gpt-5.4-mini",
        reasoning_effort="medium",
        timeout_seconds=60,
        secret_payload={"apiKey": "sk-test-secret-1234"},
        has_api_key=True,
        api_key_last4="1234",
    )
    output_schema = OutputSchema(
        key="research_summary",
        version=3,
        status="published",
        kind="standalone",
        name="Research Summary",
        description="Structured research summary.",
        json_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        registry_refs=[],
    )
    capability = Capability(
        key="sec_filing_lookup",
        version=2,
        status="published",
        name="SEC Filing Lookup",
        description="Looks up filings.",
        tool_grants=[{"tool": "ledger.reports.lookup"}],
    )
    mcp_server = McpServer(
        key="market_data",
        version=1,
        status="published",
        config={
            "name": "Market Data",
            "description": "Market data MCP server.",
            "enabled": True,
            "transport": "stdio",
            "command": "python3",
            "args": ["-V"],
            "env": {},
        },
    )
    session.add_all([connection, output_schema, capability, mcp_server])
    session.commit()
    return {
        "connection": connection,
        "output_schema": output_schema,
        "capability": capability,
        "mcp_server": mcp_server,
    }


def _expected_payload(connection_id: int) -> dict[str, object]:
    return {
        "key": "research_agent",
        "name": "Research Agent",
        "description": "Produces a structured research summary.",
        "modelConnectionId": connection_id,
        "systemPrompt": "You are a research analyst.\nReturn concise output.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "outputSchemaKey": "research_summary",
        "outputSchemaVersion": 3,
        "capabilities": [{"capabilityKey": "sec_filing_lookup", "capabilityVersion": 2}],
        "mcpServers": [{"mcpServerKey": "market_data", "mcpServerVersion": 1}],
        "budgetUsd": "1.25",
    }


def test_compile_agent_manifest_source_matches_current_agent_payload(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        payload = compile_agent_manifest(_valid_manifest_source(), session)

    assert payload == _expected_payload(cast(ModelConnection, refs["connection"]).id)
    assert (
        AgentCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_agent_manifest_accepts_validated_manifest(
    session_factory: sessionmaker[Session],
) -> None:
    result = parse_agent_manifest(_valid_manifest_source())
    assert result.diagnostics == []
    assert result.manifest is not None

    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        payload = compile_agent_manifest(result.manifest, session)

    assert payload == _expected_payload(cast(ModelConnection, refs["connection"]).id)


def test_compile_agent_manifest_rejects_legacy_skills_manifest(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace("  capabilities:", "  skills:", 1)

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert len(excinfo.value.diagnostics) == 1
    assert excinfo.value.diagnostics[0].path == "spec.skills"


def test_compile_agent_manifest_rejects_capability_alias_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace(
        "  capabilities:\n    - sec_filing_lookup@2\n",
        "  capabilities:\n    - sec_filing_lookup@2\n  skills:\n    - sec_filing_lookup@2\n",
        1,
    )

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert len(excinfo.value.diagnostics) == 1
    assert excinfo.value.diagnostics[0].path == "spec.skills"


def test_compile_agent_manifest_resolves_by_model_connection_key_not_raw_id(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        payload = compile_agent_manifest(_valid_manifest_source(), session)

    assert payload["modelConnectionId"] == cast(ModelConnection, refs["connection"]).id
    assert "modelConnection" not in payload


def test_compile_agent_manifest_reports_unresolved_refs_with_paths(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        source = _valid_manifest_source().replace("research_summary@3", "missing_schema@9", 1)

        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert len(excinfo.value.diagnostics) == 1
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.path == "spec.outputSchema"
    assert diagnostic.line is not None
    assert "Output schema 'missing_schema' version 9 was not found" in diagnostic.message


def test_compile_agent_manifest_reports_unresolved_capability_refs_with_canonical_path(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        source = _valid_manifest_source().replace("sec_filing_lookup@2", "missing_capability@9")

        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert len(excinfo.value.diagnostics) == 1
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.path == "spec.capabilities[0]"
    assert diagnostic.line is not None
    assert "Capability 'missing_capability' version 9 was not found" in diagnostic.message


def test_compile_agent_manifest_rejects_unsupported_input_schema_constructs(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        source = _valid_manifest_source().replace(
            "      ticker:\n        type: string",
            "      ticker:\n        type: string\n    patternProperties:\n      ^x: {type: string}",
            1,
        )

        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert any(
        diagnostic.path == "spec.inputSchema.patternProperties"
        and "patternProperties is not supported" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


__all__ = ["_expected_payload", "_seed_manifest_refs"]
