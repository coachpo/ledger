from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent_spec import AgentSpec


def _build_agent_spec(
    *,
    key: str,
    version: int,
    origin: str = "managed",
    status: str,
) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin=origin,
        status=status,
        name=f"{key}-{version}",
        instructions=f"Instructions for {key} v{version}",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={
            "kind": "json",
            "schema": {"type": "object"},
            "description": "Structured output",
        },
        default_capability_bundle_keys=["builtin.librarian_context"],
        default_persona_profile_keys=["builtin:librarian"],
    )


def create_agent_spec_draft(
    client: TestClient,
    *,
    key: str = "managed_agent_spec",
    name: str = "Managed Agent Spec",
    instructions: str = "Follow the managed runtime instructions.",
) -> dict[str, Any]:
    response = client.post(
        "/api/v2/agent-specs",
        json={
            "key": key,
            "name": name,
            "instructions": instructions,
            "modelPolicy": {"model": "gpt-5.4-mini"},
            "finalOutputContract": {
                "kind": "json",
                "schema": {"type": "object"},
                "description": "Structured output",
            },
            "defaultCapabilityBundleKeys": ["builtin.librarian_context"],
            "defaultPersonaProfileKeys": ["builtin:librarian"],
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_agent_spec_create_patch_activate_and_list_read_behavior(client: TestClient) -> None:
    created = create_agent_spec_draft(client, key="  managed_agent_spec  ")

    assert created["key"] == "managed_agent_spec"
    assert created["version"] == 1
    assert created["origin"] == "managed"
    assert created["status"] == "DRAFT"
    assert created["finalOutputContract"]["schema"] == {"type": "object"}

    update_response = client.patch(
        f"/api/v2/agent-specs/{created['id']}",
        json={
            "name": "Managed Agent Spec v2",
            "instructions": "Use the revised runtime instructions.",
            "modelPolicy": {"model": "gpt-5.4"},
            "defaultCapabilityBundleKeys": ["builtin.explore_context"],
            "defaultPersonaProfileKeys": ["builtin:explore"],
            "finalOutputContract": {
                "kind": "markdown",
                "schema": {"type": "string"},
                "description": "Markdown output",
            },
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["name"] == "Managed Agent Spec v2"
    assert updated["instructions"] == "Use the revised runtime instructions."
    assert updated["modelPolicy"] == {"model": "gpt-5.4"}
    assert updated["defaultCapabilityBundleKeys"] == ["builtin.explore_context"]
    assert updated["defaultPersonaProfileKeys"] == ["builtin:explore"]
    assert updated["finalOutputContract"] == {
        "kind": "markdown",
        "schema": {"type": "string"},
        "description": "Markdown output",
    }

    get_response = client.get(f"/api/v2/agent-specs/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["name"] == "Managed Agent Spec v2"

    list_response = client.get("/api/v2/agent-specs", params={"origin": "managed"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [get_response.json()]

    activate_response = client.post(f"/api/v2/agent-specs/{created['id']}/activate")
    assert activate_response.status_code == 200, activate_response.json()
    assert activate_response.json()["status"] == "ACTIVE"

    active_list_response = client.get(
        "/api/v2/agent-specs",
        params={"origin": "managed", "status": "ACTIVE"},
    )
    assert active_list_response.status_code == 200, active_list_response.json()
    assert active_list_response.json()["items"] == [activate_response.json()]


def test_agent_spec_create_draft_rejects_duplicate_draft(client: TestClient) -> None:
    create_agent_spec_draft(client, key="duplicate_agent_spec")

    response = client.post(
        "/api/v2/agent-specs",
        json={
            "key": "duplicate_agent_spec",
            "name": "Duplicate Agent Spec",
            "instructions": "This should fail.",
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "agent_spec_duplicate_draft"


def test_agent_spec_activate_demotes_existing_active_without_duplicate_active_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = create_agent_spec_draft(client, key="position_analyst")

    response = client.post(f"/api/v2/agent-specs/{created['id']}/activate")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["version"] == 2

    with session_factory() as session:
        rows = session.scalars(
            select(AgentSpec)
            .where(AgentSpec.key == "position_analyst")
            .order_by(AgentSpec.version.asc())
        ).all()

    assert [(row.origin, row.version, row.status) for row in rows] == [
        ("seeded", 1, "DEPRECATED"),
        ("managed", 2, "ACTIVE"),
    ]


def test_agent_spec_patch_rejects_non_draft_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        spec = _build_agent_spec(key="immutable_agent_spec", version=1, status="ACTIVE")
        session.add(spec)
        session.commit()
        spec_id = spec.id

    response = client.patch(
        f"/api/v2/agent-specs/{spec_id}",
        json={"name": "Should Not Patch"},
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "agent_spec_invalid_patch_transition"


def test_agent_spec_deprecate_and_archive_transitions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        spec = _build_agent_spec(key="retired_agent_spec", version=1, status="ACTIVE")
        session.add(spec)
        session.commit()
        spec_id = spec.id

    deprecate_response = client.post(f"/api/v2/agent-specs/{spec_id}/deprecate")
    assert deprecate_response.status_code == 200, deprecate_response.json()
    assert deprecate_response.json()["status"] == "DEPRECATED"

    archive_response = client.post(f"/api/v2/agent-specs/{spec_id}/archive")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "ARCHIVED"
