# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.agents.mcp import DefaultMcpConnectionTester
from app.core.errors import ApiError
from app.db.upgrades import upgrade_legacy_schema
from app.models.agent import (
    AGENT_MANIFEST_API_VERSION,
    AGENT_MANIFEST_COMPILER_VERSION,
    TEMPORARY_AGENT_MANIFEST_HASH,
    TEMPORARY_AGENT_MANIFEST_SOURCE,
    Agent,
)
from app.models.model_connection import ModelConnection
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.agent_manifest_decompiler import decompile_agent_model
from app.services.agent_service import AgentService
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
from tests.test_agent_manifest_compiler import _expected_payload, _seed_manifest_refs
from tests.test_agent_manifest_parser import _valid_manifest_source


def _agent_service(session: Session) -> AgentService:
    return AgentService(
        session,
        get_default_tool_catalog(),
        DefaultMcpConnectionTester(),
    )


def _manifest_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def test_agent_service_persists_manifest_source_and_compiled_projection(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source()

    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        created = _agent_service(session).create_agent_from_manifest(source)
        created_payload = created.model_dump(mode="json", by_alias=True)
        created_row = session.get(Agent, created.id)

        assert created_row is not None
        assert created.manifest_api_version == AGENT_MANIFEST_API_VERSION
        assert created.manifest_source == source
        assert created.manifest_hash == _manifest_hash(source)
        assert created.compiler_version == AGENT_MANIFEST_COMPILER_VERSION
        assert created_payload["manifestApiVersion"] == AGENT_MANIFEST_API_VERSION
        assert created_payload["manifestSource"] == source
        assert created_payload["manifestHash"] == _manifest_hash(source)
        assert created_payload["compilerVersion"] == AGENT_MANIFEST_COMPILER_VERSION
        assert created.name == "Research Agent"
        assert created.system_prompt == "You are a research analyst.\nReturn concise output."
        assert created.budget_usd == Decimal("1.25")
        assert created_row.manifest_source == source
        assert created_row.manifest_hash == _manifest_hash(source)
        assert created_row.model_connection_id == cast(ModelConnection, refs["connection"]).id
        assert created_row.model_connection_snapshot == build_model_connection_runtime_snapshot(
            cast(ModelConnection, refs["connection"])
        )
        assert "apiKey" not in json.dumps(created_row.model_connection_snapshot)
        assert created_row.output_schema_version == 3


@pytest.mark.parametrize(
    ("reasoning_effort", "expected_reasoning_effort"),
    [(None, None), ("custom-exact", "custom-exact")],
)
def test_agent_manifest_save_read_decompile_preserves_reasoning_snapshot(
    session_factory: sessionmaker[Session],
    reasoning_effort: str | None,
    expected_reasoning_effort: str | None,
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        connection = cast(ModelConnection, refs["connection"])
        connection.reasoning_effort = reasoning_effort
        session.commit()

        service = _agent_service(session)
        created = service.create_agent_from_manifest(_valid_manifest_source())
        created_payload = created.model_dump(mode="json", by_alias=True)
        created_row = session.get(Agent, created.id)

        assert created_row is not None
        assert created.model_connection_snapshot.reasoning_effort == expected_reasoning_effort
        assert (
            created_payload["modelConnectionSnapshot"]["reasoningEffort"]
            == expected_reasoning_effort
        )
        assert (
            created_row.model_connection_snapshot["reasoning_effort"] == expected_reasoning_effort
        )

        decompiled = decompile_agent_model(created_row, session)
        session.refresh(created_row)
        reread = service.get_agent(created.id)

        assert decompiled.payload["modelConnectionId"] == connection.id
        assert decompiled.payload["key"] == "research_agent"
        assert "reasoningEffort" not in decompiled.source
        assert "reasoning_effort" not in decompiled.source
        assert (
            created_row.model_connection_snapshot["reasoning_effort"] == expected_reasoning_effort
        )
        assert reread.model_connection_snapshot.reasoning_effort == expected_reasoning_effort


def test_agent_service_structured_create_write_is_rejected_without_persisting_row(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        payload = AgentCreate.model_validate(
            _expected_payload(cast(ModelConnection, refs["connection"]).id)
        )

        with pytest.raises(ApiError) as excinfo:
            _agent_service(session).create_agent(payload)

        assert excinfo.value.code == "validation_error"
        assert excinfo.value.message == "Structured agent writes are not supported"
        assert session.query(Agent).filter(Agent.key == "research_agent").count() == 0


def test_agent_service_structured_update_write_is_rejected_without_persisting_version(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source()
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        service = _agent_service(session)
        created = service.create_agent_from_manifest(source)
        legacy_payload = _expected_payload(cast(ModelConnection, refs["connection"]).id)
        _ = legacy_payload.pop("key")
        update_payload = AgentUpdate.model_validate(legacy_payload)

        with pytest.raises(ApiError) as excinfo:
            service.update_agent(created.id, update_payload)

        assert excinfo.value.code == "validation_error"
        assert excinfo.value.message == "Structured agent writes are not supported"
        rows = session.query(Agent).filter(Agent.key == "research_agent").all()
        assert len(rows) == 1
        assert rows[0].version == 1
        assert rows[0].status == "published"


def test_agent_manifest_update_creates_version_and_preserves_historical_source(
    session_factory: sessionmaker[Session],
) -> None:
    original_source = _valid_manifest_source()
    updated_source = (
        original_source.replace("name: Research Agent", "name: Research Agent v2", 1)
        .replace(
            "description: Produces a structured research summary.",
            "description: Produces an updated structured research summary.",
            1,
        )
        .replace("Return concise output.", "Return concise updated output.", 1)
        .replace('budgetUsd: "1.25"', 'budgetUsd: "2.50"', 1)
    )

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
        service = _agent_service(session)
        created = service.create_agent_from_manifest(original_source)
        updated = service.update_agent_from_manifest(created.id, updated_source)
        previous = service.get_agent(updated.id, version=1)

        assert updated.id != created.id
        assert updated.version == 2
        assert updated.status == "published"
        assert updated.name == "Research Agent v2"
        assert (
            updated.system_prompt == "You are a research analyst.\nReturn concise updated output."
        )
        assert updated.budget_usd == Decimal("2.50")
        assert updated.manifest_source == updated_source
        assert updated.manifest_hash == _manifest_hash(updated_source)

        assert previous.id == created.id
        assert previous.version == 1
        assert previous.status == "deprecated"
        assert previous.name == "Research Agent"
        assert previous.manifest_source == original_source
        assert previous.manifest_hash == _manifest_hash(original_source)


def test_agent_manifest_service_validation_preserves_compiler_diagnostic_location(
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace("research_summary@3", "missing_schema@9", 1)

    with session_factory() as session:
        _refs = _seed_manifest_refs(session)

        with pytest.raises(ApiError) as excinfo:
            _agent_service(session).create_agent_from_manifest(source)

    assert excinfo.value.code == "validation_error"
    assert excinfo.value.message == "Agent manifest validation failed"
    assert len(excinfo.value.details) == 1
    detail = excinfo.value.details[0]
    assert detail["field"] == "manifestSource"
    assert detail["path"] == "spec.outputSchema"
    assert detail["line"] is not None
    assert detail["column"] is not None
    assert "Output schema 'missing_schema' version 9 was not found" in str(detail["issue"])


def test_upgrade_legacy_schema_adds_agent_manifest_columns_idempotently(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            _ = connection.exec_driver_sql(
                """
                CREATE TABLE agents (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    key VARCHAR(120) NOT NULL,
                    version INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    name VARCHAR(200) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    model VARCHAR(200) NOT NULL,
                    system_prompt TEXT NOT NULL,
                    input_schema JSONB NOT NULL,
                    output_schema_id INTEGER NOT NULL,
                    output_schema_version INTEGER NOT NULL,
                    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
                    mcp_servers JSONB NOT NULL DEFAULT '[]'::jsonb,
                    budget_usd NUMERIC(20, 8) NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_agents_key_version UNIQUE (key, version)
                )
                """
            )
            _ = connection.execute(
                text(
                    """
                    INSERT INTO agents (
                        key, version, status, name, description, model, system_prompt,
                        input_schema, output_schema_id, output_schema_version, skills,
                        mcp_servers, budget_usd
                    ) VALUES (
                        :key, 1, 'published', :name, '', :model, :system_prompt,
                        CAST(:input_schema AS jsonb), 1, 1, '[]'::jsonb, '[]'::jsonb, 0
                    )
                    """
                ),
                {
                    "key": "legacy_manifest_agent",
                    "name": "Legacy Manifest Agent",
                    "model": "gpt-5.4-mini",
                    "system_prompt": "Summarize the ticker.",
                    "input_schema": json.dumps(
                        {
                            "type": "object",
                            "properties": {"ticker": {"type": "string"}},
                            "required": ["ticker"],
                        }
                    ),
                },
            )

        upgrade_legacy_schema(engine)
        upgrade_legacy_schema(engine)

        agent_columns = {column["name"]: column for column in inspect(engine).get_columns("agents")}
        with engine.connect() as connection:
            stored_manifest = connection.execute(
                text(
                    """
                    SELECT manifest_api_version, manifest_source, manifest_hash, compiler_version
                    FROM agents
                    WHERE key = :key
                    """
                ),
                {"key": "legacy_manifest_agent"},
            ).one()

        assert agent_columns["manifest_api_version"]["nullable"] is False
        assert agent_columns["manifest_source"]["nullable"] is False
        assert agent_columns["manifest_hash"]["nullable"] is False
        assert agent_columns["compiler_version"]["nullable"] is False
        assert stored_manifest == (
            AGENT_MANIFEST_API_VERSION,
            TEMPORARY_AGENT_MANIFEST_SOURCE,
            TEMPORARY_AGENT_MANIFEST_HASH,
            AGENT_MANIFEST_COMPILER_VERSION,
        )
    finally:
        engine.dispose()
