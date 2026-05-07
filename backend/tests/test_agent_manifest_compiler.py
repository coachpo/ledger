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
from tests.test_workflow_manifest_parser import (
    GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES,
    GENERIC_PLATFORM_MODEL_CONNECTION_SETUP,
)


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
        secret_payload={"apiKey": "configured-test-value"},
        has_api_key=True,
        api_key_last4="test",
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
        tool_keys=["ledger.reports.lookup"],
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


def _seed_platform_graph_manifest_refs(session: Session) -> None:
    connection = ModelConnection(
        key=GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["key"],
        status="active",
        name="Platform Graph Demo Local GPT 5.4 Mini",
        description="Platform Graph Demo local OpenAI-family model connection.",
        base_url=GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["baseUrl"],
        model_id=GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["modelId"],
        reasoning_effort=GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["reasoningEffort"],
        api_style=GENERIC_PLATFORM_MODEL_CONNECTION_SETUP["apiStyle"],
        timeout_seconds=60,
        secret_payload={"apiKey": "configured-test-value"},
        has_api_key=True,
        api_key_last4="test",
    )
    state_schema: dict[str, object] = {"type": "object", "additionalProperties": True}
    transition_schema = {
        "type": "object",
        "properties": {"nextState": state_schema},
        "required": ["nextState"],
        "additionalProperties": False,
    }
    schema_payloads = {
        "platform_graph_analyst_report": state_schema,
        "platform_graph_investment_debate_transition": transition_schema,
        "platform_graph_research_plan": state_schema,
        "platform_graph_trader_proposal": state_schema,
        "platform_graph_risk_debate_transition": transition_schema,
        "platform_graph_portfolio_decision": state_schema,
    }
    schema_names = {
        "platform_graph_analyst_report": "Platform Graph Demo Analyst Report",
        "platform_graph_investment_debate_transition": (
            "Platform Graph Demo Investment Debate Transition"
        ),
        "platform_graph_research_plan": "Platform Graph Demo Research Plan",
        "platform_graph_trader_proposal": "Platform Graph Demo Trader Proposal",
        "platform_graph_risk_debate_transition": "Platform Graph Demo Risk Debate Transition",
        "platform_graph_portfolio_decision": "Platform Graph Demo Portfolio Decision",
    }
    output_schemas = [
        OutputSchema(
            key=key,
            version=1,
            status="published",
            kind="standalone",
            name=schema_names[key],
            description=f"{schema_names[key]} schema.",
            json_schema=json_schema,
            registry_refs=[],
        )
        for key, json_schema in schema_payloads.items()
    ]
    capability_tool_keys = {
        "platform_graph_market_data": [
            "ledger.market_data.quote_lookup",
            "ledger.market_data.history_lookup",
            "ledger.market_data.ohlcv_lookup",
            "ledger.indicators.lookup",
        ],
        "platform_graph_fundamentals": ["ledger.fundamentals.lookup"],
        "platform_graph_news": [
            "ledger.news.lookup",
            "ledger.insider_data.lookup",
        ],
        "ledger_reports": ["ledger.reports.lookup"],
        "ledger_positions": ["ledger.positions.lookup"],
        "platform_graph_memory": ["ledger.reports.write"],
    }
    capabilities = [
        Capability(
            key=key,
            version=1,
            status="published",
            name=key.replace("_", " ").title(),
            description=f"{key} capability for manifest compilation.",
            tool_keys=tool_keys,
        )
        for key, tool_keys in capability_tool_keys.items()
    ]
    session.add_all([connection, *output_schemas, *capabilities])
    session.commit()


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


@pytest.mark.parametrize(
    ("role", "expected_capability_ref"),
    [
        ("market_analyst", "platform_graph_market_data@1"),
        ("social_analyst", "platform_graph_news@1"),
        ("news_analyst", "platform_graph_news@1"),
        ("fundamentals_analyst", "platform_graph_fundamentals@1"),
        ("bull_researcher", "ledger_reports@1"),
        ("bear_researcher", "ledger_reports@1"),
        ("research_manager", "ledger_reports@1"),
        ("trader", "ledger_positions@1"),
        ("aggressive_risk_analyst", "ledger_reports@1"),
        ("neutral_risk_analyst", "ledger_reports@1"),
        ("conservative_risk_analyst", "ledger_reports@1"),
        ("portfolio_manager", "ledger_reports@1,platform_graph_memory@1"),
    ],
)
def test_compile_platform_graph_example_agent_manifest_resolves_expected_capability(
    session_factory: sessionmaker[Session],
    role: str,
    expected_capability_ref: str,
) -> None:
    expected_capabilities = [
        {"capabilityKey": key, "capabilityVersion": int(raw_version)}
        for key, raw_version in (item.split("@", 1) for item in expected_capability_ref.split(","))
    ]

    with session_factory() as session:
        _seed_platform_graph_manifest_refs(session)
        payload = compile_agent_manifest(GENERIC_PLATFORM_AGENT_MANIFEST_SOURCES[role], session)

    assert payload["capabilities"] == expected_capabilities


def test_compile_agent_manifest_preserves_input_schema_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace(
        """  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
    required:
      - ticker
""",
        """  inputSchema:
    type: object
    title: Research request
    description: Inputs collected before the agent runs.
    additionalProperties: false
    properties:
      ticker:
        type: string
        title: Ticker symbol
        description: Public market ticker to research.
      horizon_days:
        type: integer
        title: Horizon days
        description: Optional number of days to assess.
      price_targets:
        type: array
        title: Price targets
        description: Optional candidate price targets.
        items:
          type: number
          title: Price target
          description: Candidate target price.
      signal:
        title: Signal
        description: Discriminated signal branch.
        anyOf:
          - type: object
            title: Bullish signal
            description: Bullish branch payload.
            properties:
              kind:
                const: bullish
              score:
                type: integer
            required:
              - kind
              - score
            additionalProperties: false
          - type: object
            title: Bearish signal
            description: Bearish branch payload.
            properties:
              kind:
                const: bearish
              reason:
                type: string
            required:
              - kind
              - reason
            additionalProperties: false
        discriminator:
          propertyName: kind
    required:
      - ticker
      - signal
""",
        1,
    )

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        payload = compile_agent_manifest(source, session)

    input_schema = cast(dict[str, object], payload["inputSchema"])
    properties = cast(dict[str, dict[str, object]], input_schema["properties"])
    price_targets = properties["price_targets"]
    price_items = cast(dict[str, object], price_targets["items"])
    signal = properties["signal"]
    signal_variants = cast(list[dict[str, object]], signal["anyOf"])

    assert input_schema["title"] == "Research request"
    assert input_schema["description"] == "Inputs collected before the agent runs."
    assert properties["ticker"]["title"] == "Ticker symbol"
    assert properties["horizon_days"]["description"] == "Optional number of days to assess."
    assert "horizon_days" not in cast(list[str], input_schema["required"])
    assert price_targets["description"] == "Optional candidate price targets."
    assert price_items["title"] == "Price target"
    assert signal["title"] == "Signal"
    assert signal_variants[0]["title"] == "Bullish signal"
    assert signal_variants[1]["description"] == "Bearish branch payload."
    assert (
        AgentCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_agent_manifest_preserves_valid_input_schema_defaults(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace(
        """      ticker:
        type: string
    required:
      - ticker
""",
        """      ticker:
        type: string
        default: NVDA
      horizon_days:
        type: integer
        default: 30
    required:
      - ticker
""",
        1,
    )

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        payload = compile_agent_manifest(source, session)

    input_schema = cast(dict[str, object], payload["inputSchema"])
    properties = cast(dict[str, dict[str, object]], input_schema["properties"])
    assert properties["ticker"]["default"] == "NVDA"
    assert properties["horizon_days"]["default"] == 30
    assert "horizon_days" not in cast(list[str], input_schema["required"])
    assert (
        AgentCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_agent_manifest_rejects_invalid_input_schema_default_with_property_path(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace(
        """      ticker:
        type: string
""",
        """      ticker:
        type: string
        default: 123
""",
        1,
    )

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert any(
        diagnostic.path == "spec.inputSchema.properties.ticker.default"
        and "Default value must match schema type 'string'" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


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


@pytest.mark.parametrize(
    ("schema_fragment", "expected_path", "expected_message"),
    [
        (
            "patternProperties:\n      ^x: {type: string}",
            "spec.inputSchema.patternProperties",
            "patternProperties is not supported",
        ),
        ("oneOf: []", "spec.inputSchema.oneOf", "Only discriminated anyOf unions are supported"),
        ("allOf: []", "spec.inputSchema.allOf", "allOf is not supported"),
        ("if: {type: object}", "spec.inputSchema.if", "if/then/else is not supported"),
        ("then: {type: object}", "spec.inputSchema.then", "if/then/else is not supported"),
        ("else: {type: object}", "spec.inputSchema.else", "if/then/else is not supported"),
        ("not: {type: object}", "spec.inputSchema.not", "not is not supported"),
        (
            "additionalProperties:\n      type: string",
            "spec.inputSchema.additionalProperties",
            "Schema-valued additionalProperties is not supported",
        ),
    ],
)
def test_compile_agent_manifest_rejects_unsupported_input_schema_constructs(
    session_factory: sessionmaker[Session],
    schema_fragment: str,
    expected_path: str,
    expected_message: str,
) -> None:
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        source = _valid_manifest_source().replace(
            "    additionalProperties: false",
            f"    {schema_fragment}",
            1,
        )

        with pytest.raises(AgentManifestCompilerError) as excinfo:
            _ = compile_agent_manifest(source, session)

    assert any(
        diagnostic.path == expected_path and expected_message in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


__all__ = ["_expected_payload", "_seed_manifest_refs"]
