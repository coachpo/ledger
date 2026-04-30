from __future__ import annotations

from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.models.skill import Skill
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
from tests.test_agent_manifest_compiler import _seed_manifest_refs


def _create_capability(client: TestClient, payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/capabilities", json=payload)
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def test_capability_crud_uses_tool_grants_while_skills_stay_legacy(
    client: TestClient,
) -> None:
    created = _create_capability(
        client,
        {
            "key": "market_research",
            "name": "Market Research",
            "description": "Server-owned research tools.",
            "toolGrants": [
                {"tool": "ledger.positions.lookup"},
                {"tool": "ledger.reports.lookup"},
            ],
        },
    )

    assert created["status"] == "draft"
    assert "toolGrants" in created
    assert "toolDefinitions" not in created
    created_grants = cast(list[dict[str, object]], created["toolGrants"])
    assert [item["tool"] for item in created_grants] == [
        "ledger.positions.lookup",
        "ledger.reports.lookup",
    ]

    legacy_detail = client.get(f"/api/skills/{created['id']}")
    assert legacy_detail.status_code == 200, legacy_detail.json()
    legacy_payload = legacy_detail.json()
    assert "toolDefinitions" in legacy_payload
    assert "toolGrants" not in legacy_payload
    assert [item["tool"] for item in legacy_payload["toolDefinitions"]] == [
        "ledger.positions.lookup",
        "ledger.reports.lookup",
    ]

    update_response = client.patch(
        f"/api/capabilities/{created['id']}",
        json={"name": "Market Research v2", "toolGrants": [{"tool": "ledger.reports.lookup"}]},
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated["toolGrants"][0]["tool"] == "ledger.reports.lookup"
    assert "toolDefinitions" not in updated

    archived_original = client.get(f"/api/capabilities/{created['id']}")
    assert archived_original.status_code == 200, archived_original.json()
    assert archived_original.json()["status"] == "archived"

    activated = client.post(f"/api/capabilities/{updated['id']}/activate")
    assert activated.status_code == 200, activated.json()
    assert activated.json()["status"] == "published"

    list_response = client.get("/api/capabilities", params={"status": "published"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [activated.json()]

    archive_response = client.delete(f"/api/capabilities/{updated['id']}")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "archived"


def test_capability_create_accepts_legacy_tool_definitions_as_import_alias(
    client: TestClient,
) -> None:
    created = _create_capability(
        client,
        {
            "key": "legacy_import_tools",
            "name": "Legacy Import Tools",
            "toolDefinitions": [{"tool": "ledger.reports.lookup"}],
        },
    )

    assert "toolGrants" in created
    assert "toolDefinitions" not in created
    tool_grants = cast(list[dict[str, object]], created["toolGrants"])
    assert tool_grants[0]["tool"] == "ledger.reports.lookup"


def test_capability_request_rejects_tool_grants_and_tool_definitions_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/capabilities",
        json={
            "key": "conflicting_tools",
            "name": "Conflicting Tools",
            "toolGrants": [{"tool": "ledger.reports.lookup"}],
            "toolDefinitions": [{"tool": "ledger.positions.lookup"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    with session_factory() as session:
        assert session.query(Skill).filter(Skill.key == "conflicting_tools").count() == 0


def test_legacy_skill_request_rejects_tool_grants_and_tool_definitions_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/skills",
        json={
            "key": "legacy_conflicting_tools",
            "name": "Legacy Conflicting Tools",
            "toolGrants": [{"tool": "ledger.reports.lookup"}],
            "toolDefinitions": [{"tool": "ledger.positions.lookup"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    with session_factory() as session:
        assert session.query(Skill).filter(Skill.key == "legacy_conflicting_tools").count() == 0


def test_capability_patch_conflict_does_not_archive_existing_draft(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = _create_capability(
        client,
        {
            "key": "patch_conflict_tools",
            "name": "Patch Conflict Tools",
            "toolGrants": [{"tool": "ledger.reports.lookup"}],
        },
    )

    response = client.patch(
        f"/api/capabilities/{created['id']}",
        json={
            "toolGrants": [{"tool": "ledger.reports.lookup"}],
            "toolDefinitions": [{"tool": "ledger.positions.lookup"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    with session_factory() as session:
        rows = session.query(Skill).filter(Skill.key == "patch_conflict_tools").all()
        assert len(rows) == 1
        assert rows[0].status == "draft"


def test_persisted_legacy_skill_refs_resolve_as_agent_capabilities(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        connection = cast(ModelConnection, refs["connection"])
        output_schema = cast(OutputSchema, refs["output_schema"])
        skill = cast(Skill, refs["skill"])
        agent = Agent(
            key="legacy_skill_ref_agent",
            version=1,
            status="published",
            name="Legacy Skill Ref Agent",
            description="Reads persisted skill refs through capability API aliases.",
            model_connection_id=connection.id,
            model_connection_snapshot=build_model_connection_runtime_snapshot(connection),
            model=connection.model_id,
            system_prompt="Summarize the request.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema_id=output_schema.id,
            output_schema_version=output_schema.version,
            skills=[{"skillId": skill.id, "skillKey": skill.key, "skillVersion": skill.version}],
            mcp_servers=[],
            budget_usd=Decimal("0"),
        )
        session.add(agent)
        session.commit()
        agent_id = agent.id

    response = client.get(f"/api/agents/{agent_id}")

    assert response.status_code == 200, response.json()
    body = response.json()
    capabilities = cast(list[dict[str, object]], body["capabilities"])
    skills = cast(list[dict[str, object]], body["skills"])
    assert capabilities[0]["key"] == "sec_filing_lookup"
    assert capabilities[0]["toolGrants"] == [
        {
            "tool": "ledger.reports.lookup",
            "displayName": "Report Lookup",
            "description": "Read persisted Ledger reports through server-owned report lookups.",
        }
    ]
    assert "toolDefinitions" not in capabilities[0]
    assert skills[0]["toolDefinitions"] == capabilities[0]["toolGrants"]
    assert "toolGrants" not in skills[0]
