# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.schemas.agent import AGENT_MANIFEST_SOURCE_MAX_LENGTH
from tests.test_agent_manifest_compiler import _expected_payload, _seed_manifest_refs
from tests.test_agent_manifest_parser import _valid_manifest_source


def _manifest_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _create_manifest_agent(client: TestClient, source: str) -> dict[str, object]:
    response = client.post("/api/agents", json={"manifestSource": source})
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def test_agent_manifest_source_rejects_oversized_payloads(client: TestClient) -> None:
    oversized_source = "a" * (AGENT_MANIFEST_SOURCE_MAX_LENGTH + 1)

    response = client.post(
        "/api/agents/validate-manifest",
        json={"manifestSource": oversized_source},
    )

    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    assert body["code"] == "validation_error"
    assert details[0]["field"] == "manifestSource"
    assert "at most" in str(details[0]["issue"])


def test_validate_manifest_returns_compiled_preview_for_valid_yaml(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source()
    with session_factory() as session:
        refs = _seed_manifest_refs(session)

    response = client.post("/api/agents/validate-manifest", json={"manifestSource": source})

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["diagnostics"] == []
    assert body["metadata"] == {
        "apiVersion": "ledger.agent/v1",
        "key": "research_agent",
        "name": "Research Agent",
        "description": "Produces a structured research summary.",
    }
    compiled_payload = cast(dict[str, object], body["compiledPayload"])
    assert compiled_payload == _expected_payload(cast(ModelConnection, refs["connection"]).id)
    assert body["runInputSchema"] == compiled_payload["inputSchema"]


def test_validate_manifest_returns_location_aware_diagnostics_for_unresolved_refs(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source().replace("research_summary@3", "missing_schema@9", 1)
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)

    response = client.post("/api/agents/validate-manifest", json={"manifestSource": source})

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["metadata"] is None
    assert body["compiledPayload"] is None
    assert body["runInputSchema"] is None
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert len(diagnostics) == 1
    assert diagnostics[0]["severity"] == "error"
    assert diagnostics[0]["path"] == "spec.outputSchema"
    assert diagnostics[0]["line"] is not None
    assert diagnostics[0]["column"] is not None
    assert "Output schema 'missing_schema' version 9 was not found" in str(
        diagnostics[0]["message"]
    )


def test_create_and_update_manifest_persist_source_and_compiled_projection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    original_source = _valid_manifest_source()
    updated_source = (
        original_source.replace("name: Research Agent", "name: Research Agent v2", 1)
        .replace("Return concise output.", "Return concise updated output.", 1)
        .replace('budgetUsd: "1.25"', 'budgetUsd: "2.50"', 1)
    )
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)

    created = _create_manifest_agent(client, original_source)
    assert created["manifestApiVersion"] == "ledger.agent/v1"
    assert created["manifestSource"] == original_source
    assert created["manifestHash"] == _manifest_hash(original_source)
    assert created["name"] == "Research Agent"
    assert created["systemPrompt"] == "You are a research analyst.\nReturn concise output."
    assert created["budgetUsd"] == "1.25000000"
    assert cast(dict[str, object], created["inputSchema"])["additionalProperties"] is False
    assert cast(dict[str, object], created["outputSchema"])["version"] == 3

    update_response = client.post(
        f"/api/agents/{created['id']}",
        json={"manifestSource": updated_source},
    )

    assert update_response.status_code == 200, update_response.json()
    updated = cast(dict[str, object], update_response.json())
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["status"] == "published"
    assert updated["name"] == "Research Agent v2"
    assert updated["manifestSource"] == updated_source
    assert updated["manifestHash"] == _manifest_hash(updated_source)
    assert updated["systemPrompt"] == "You are a research analyst.\nReturn concise updated output."
    assert updated["budgetUsd"] == "2.50000000"

    previous_response = client.get(f"/api/agents/{updated['id']}", params={"version": 1})
    assert previous_response.status_code == 200, previous_response.json()
    previous = cast(dict[str, object], previous_response.json())
    assert previous["id"] == created["id"]
    assert previous["status"] == "deprecated"
    assert previous["manifestSource"] == original_source


def test_agent_detail_reads_persisted_manifest_fields(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source()
    with session_factory() as session:
        _refs = _seed_manifest_refs(session)
    created = _create_manifest_agent(client, source)

    response = client.get(f"/api/agents/{created['id']}")

    assert response.status_code == 200, response.json()
    detail = cast(dict[str, object], response.json())
    assert detail["manifestApiVersion"] == "ledger.agent/v1"
    assert detail["manifestSource"] == source
    assert detail["manifestHash"] == _manifest_hash(source)
    assert detail["compilerVersion"]


def test_legacy_structured_create_payload_is_rejected_without_creating_agent(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        legacy_payload = _expected_payload(cast(ModelConnection, refs["connection"]).id)

    response = client.post("/api/agents", json=legacy_payload)

    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    detail_fields = {str(detail["field"]) for detail in details}
    assert body["code"] == "validation_error"
    assert "manifestSource" in detail_fields
    assert {"key", "name", "modelConnectionId", "systemPrompt"} <= detail_fields
    with session_factory() as session:
        assert session.query(Agent).filter(Agent.key == "research_agent").count() == 0


def test_legacy_structured_update_payload_is_rejected_without_creating_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    source = _valid_manifest_source()
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        legacy_payload = _expected_payload(cast(ModelConnection, refs["connection"]).id)
        _ = legacy_payload.pop("key")
    created = _create_manifest_agent(client, source)

    response = client.post(f"/api/agents/{created['id']}", json=legacy_payload)

    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    detail_fields = {str(detail["field"]) for detail in details}
    assert "manifestSource" in detail_fields
    assert {"name", "modelConnectionId", "systemPrompt"} <= detail_fields
    with session_factory() as session:
        rows = session.query(Agent).filter(Agent.key == "research_agent").all()
        assert len(rows) == 1
        assert rows[0].version == 1
        assert rows[0].status == "published"
