# pyright: reportMissingImports=false, reportPrivateUsage=false

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import (
    AGENT_MANIFEST_API_VERSION,
    AGENT_MANIFEST_COMPILER_VERSION,
    TEMPORARY_AGENT_MANIFEST_HASH,
    TEMPORARY_AGENT_MANIFEST_SOURCE,
    Agent,
)
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.services.agent_manifest_backfill import (
    AgentManifestBackfillError,
    AgentManifestBackfillService,
)
from app.services.agent_manifest_compiler import compile_agent_manifest
from app.services.agent_manifest_decompiler import decompile_agent_model
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
from tests.test_agent_manifest_compiler import _seed_manifest_refs


def _manifest_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _create_legacy_agent(session: Session, refs: dict[str, object], key: str) -> Agent:
    connection = cast(ModelConnection, refs["connection"])
    output_schema = cast(OutputSchema, refs["output_schema"])
    agent = Agent(
        key=key,
        version=1,
        status="published",
        name=key.replace("_", " ").title(),
        description="Backfill converts this legacy compiled payload to YAML.",
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
        capabilities=[
            {
                "capabilityId": 999,
                "capabilityKey": "sec_filing_lookup",
                "capabilityVersion": 2,
            },
        ],
        mcp_servers=[
            {"mcpServerId": 888, "mcpServerKey": "market_data", "mcpServerVersion": 1},
        ],
        budget_usd=Decimal("1.25"),
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


def test_agent_manifest_backfill_dry_run_reports_counts_without_writes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        agent = _create_legacy_agent(session, refs, "dry_run_agent")

        report = AgentManifestBackfillService(session).audit()
        session.refresh(agent)

        assert report.total == 1
        assert report.converted == 1
        assert report.skipped_already_current == 0
        assert report.failed == 0
        assert report.persisted == 0
        assert agent.manifest_source == TEMPORARY_AGENT_MANIFEST_SOURCE
        assert agent.manifest_hash == TEMPORARY_AGENT_MANIFEST_HASH


def test_agent_manifest_backfill_persists_lossless_manifest_source_and_hash(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        agent = _create_legacy_agent(session, refs, "persist_agent")

        report = AgentManifestBackfillService(session).audit(persist=True)
        session.refresh(agent)
        decompiled = decompile_agent_model(agent, session)
        compiled = compile_agent_manifest(agent.manifest_source, session)

        assert report.total == 1
        assert report.converted == 1
        assert report.skipped_already_current == 0
        assert report.failed == 0
        assert report.persisted == 1
        assert agent.manifest_api_version == AGENT_MANIFEST_API_VERSION
        assert agent.manifest_source.startswith("apiVersion: ledger.agent/v1\nkind: Agent\n")
        assert agent.manifest_hash == _manifest_hash(agent.manifest_source)
        assert agent.compiler_version == AGENT_MANIFEST_COMPILER_VERSION
        assert agent.model_connection_snapshot == build_model_connection_runtime_snapshot(
            cast(ModelConnection, refs["connection"])
        )
        assert compiled == decompiled.payload
        assert compiled["key"] == "persist_agent"


def test_agent_manifest_backfill_skips_verified_current_manifest_versions(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        agent = _create_legacy_agent(session, refs, "idempotent_agent")
        first_report = AgentManifestBackfillService(session).audit(persist=True)
        session.refresh(agent)
        first_source = agent.manifest_source

        second_report = AgentManifestBackfillService(session).audit(persist=True)
        session.refresh(agent)

        assert first_report.persisted == 1
        assert second_report.total == 1
        assert second_report.converted == 0
        assert second_report.skipped_already_current == 1
        assert second_report.failed == 0
        assert second_report.persisted == 0
        assert agent.manifest_source == first_source


def test_agent_manifest_backfill_rewrites_lossless_noncanonical_manifest_source(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        agent = _create_legacy_agent(session, refs, "noncanonical_agent")
        noncanonical_source = (
            "kind: Agent\n"
            "apiVersion: ledger.agent/v1\n"
            "metadata: {name: Noncanonical Agent, key: noncanonical_agent, "
            "description: Backfill converts this legacy compiled payload to YAML.}\n"
            "spec:\n"
            "  modelConnection: primary_openai\n"
            '  systemPrompt: "You are a research analyst.\\nReturn concise output."\n'
            "  outputSchema: research_summary@3\n"
            "  mcpServers: [market_data@1]\n"
            "  capabilities: [sec_filing_lookup@2]\n"
            '  budgetUsd: "1.25000000"\n'
            "  inputSchema: {required: [ticker], properties: {ticker: {type: string}}, "
            "additionalProperties: false, type: object}\n"
        )
        canonical_source = decompile_agent_model(agent, session).source
        agent.manifest_api_version = AGENT_MANIFEST_API_VERSION
        agent.manifest_source = noncanonical_source
        agent.manifest_hash = _manifest_hash(noncanonical_source)
        agent.compiler_version = AGENT_MANIFEST_COMPILER_VERSION
        session.commit()

        assert noncanonical_source != canonical_source
        assert (
            compile_agent_manifest(noncanonical_source, session)
            == decompile_agent_model(
                agent,
                session,
            ).payload
        )

        report = AgentManifestBackfillService(session).audit(persist=True)
        session.refresh(agent)

        assert report.total == 1
        assert report.converted == 1
        assert report.skipped_already_current == 0
        assert report.failed == 0
        assert report.persisted == 1
        assert agent.manifest_source == canonical_source
        assert agent.manifest_hash == _manifest_hash(canonical_source)


def test_agent_manifest_backfill_write_mode_rolls_back_when_any_agent_version_fails(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        good_agent = _create_legacy_agent(session, refs, "good_agent")
        bad_agent = _create_legacy_agent(session, refs, "bad_agent")
        bad_agent.output_schema_version = 999_999
        session.commit()

        with pytest.raises(AgentManifestBackfillError) as excinfo:
            _ = AgentManifestBackfillService(session).audit(persist=True)
        report = excinfo.value.report
        session.refresh(good_agent)
        session.refresh(bad_agent)

        assert report.total == 2
        assert report.converted == 1
        assert report.skipped_already_current == 0
        assert report.failed == 1
        assert report.persisted == 0
        assert [(failure.key, failure.version) for failure in report.failures] == [("bad_agent", 1)]
        assert "missing output schema" in report.failures[0].message
        assert good_agent.manifest_source == TEMPORARY_AGENT_MANIFEST_SOURCE
        assert good_agent.manifest_hash == TEMPORARY_AGENT_MANIFEST_HASH
        assert bad_agent.manifest_source == TEMPORARY_AGENT_MANIFEST_SOURCE
        assert bad_agent.manifest_hash == TEMPORARY_AGENT_MANIFEST_HASH
