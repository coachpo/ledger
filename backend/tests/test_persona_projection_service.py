from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.orchestration_role import OrchestrationRole
from app.models.persona_profile import PersonaProfile
from app.models.persona_projection_event import PersonaProjectionEvent
from app.schemas.orchestration import OrchestrationRoleCreate
from app.services.orchestration_service import OrchestrationService


def _create_role(
    client: TestClient,
    *,
    key: str,
    name: str,
    system_prompt: str = "You analyze macro conditions.",
    capability_bundle_keys: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "name": name,
        "description": f"{name} description",
        "systemPrompt": system_prompt,
        "enabled": enabled,
    }
    if capability_bundle_keys is not None:
        payload["capabilityBundleKeys"] = capability_bundle_keys
    response = client.post("/api/v1/orchestration/roles", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def _create_character(
    client: TestClient,
    *,
    handle: str,
    display_name: str,
    role_id: int,
    prompt_append: str = "Focus on catalysts.",
    capability_bundle_keys: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "handle": handle,
        "displayName": display_name,
        "description": f"{display_name} description",
        "roleId": role_id,
        "promptAppend": prompt_append,
        "enabled": enabled,
    }
    if capability_bundle_keys is not None:
        payload["capabilityBundleKeys"] = capability_bundle_keys
    response = client.post("/api/v1/orchestration/characters", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()


def _iter_profiles(
    session: Session,
    *,
    key: str,
) -> list[PersonaProfile]:
    return list(
        session.scalars(
            select(PersonaProfile)
            .where(PersonaProfile.key == key)
            .order_by(PersonaProfile.version.desc(), PersonaProfile.id.desc())
        )
    )


def _iter_events(
    session: Session,
    *,
    legacy_entity_type: str,
    legacy_entity_key: str,
) -> list[PersonaProjectionEvent]:
    return list(
        session.scalars(
            select(PersonaProjectionEvent)
            .where(PersonaProjectionEvent.legacy_entity_type == legacy_entity_type)
            .where(PersonaProjectionEvent.legacy_entity_key == legacy_entity_key)
            .order_by(PersonaProjectionEvent.id.asc())
        )
    )


def test_role_api_write_through_projects_imported_persona_versions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = _create_role(
        client,
        key="macro_research_role",
        name="Macro Research Role",
        capability_bundle_keys=["builtin.librarian_context"],
    )

    with session_factory() as session:
        created_profiles = _iter_profiles(session, key="imported.role.macro_research_role")
        assert len(created_profiles) == 1
        created_profile = created_profiles[0]
        assert created_profile.origin == "imported"
        assert created_profile.status == "ACTIVE"
        assert created_profile.kind == "role_template"
        assert created_profile.display_name == "Macro Research Role"
        assert created_profile.enabled is True
        assert created_profile.handle is None
        assert created_profile.canonical_target_id == "role:macro_research_role"
        assert created_profile.parent_profile_key is None
        assert created_profile.parent_profile_version is None
        assert created_profile.legacy_entity_type == "role"
        assert created_profile.legacy_entity_key == "macro_research_role"
        assert created_profile.legacy_source_version == int(created["version"])
        assert created_profile.system_prompt_fragment == str(created["systemPrompt"])
        assert created_profile.prompt_append_fragment == ""
        assert created_profile.default_capability_bundle_keys == ["builtin.librarian_context"]
        assert [
            (event.operation, event.persona_profile_version, event.legacy_source_version)
            for event in _iter_events(
                session,
                legacy_entity_type="role",
                legacy_entity_key="macro_research_role",
            )
        ] == [("create", 1, 1)]

    update_response = client.patch(
        f"/api/v1/orchestration/roles/{created['id']}",
        json={
            "name": "Macro Strategist",
            "systemPrompt": "You synthesize macro catalysts.",
            "enabled": False,
            "capabilityBundleKeys": ["builtin.explore_context"],
        },
    )
    assert update_response.status_code == 200, update_response.json()

    with session_factory() as session:
        profiles = _iter_profiles(session, key="imported.role.macro_research_role")
        assert [
            (profile.version, profile.status, profile.legacy_source_version) for profile in profiles
        ] == [
            (2, "ACTIVE", 2),
            (1, "DEPRECATED", 1),
        ]
        assert sum(profile.status == "ACTIVE" for profile in profiles) == 1

        active_profile = profiles[0]
        assert active_profile.display_name == "Macro Strategist"
        assert active_profile.enabled is False
        assert active_profile.system_prompt_fragment == "You synthesize macro catalysts."
        assert active_profile.default_capability_bundle_keys == ["builtin.explore_context"]

        assert [
            (event.operation, event.persona_profile_version, event.legacy_source_version)
            for event in _iter_events(
                session,
                legacy_entity_type="role",
                legacy_entity_key="macro_research_role",
            )
        ] == [
            ("create", 1, 1),
            ("deprecate", 1, 1),
            ("reproject", 2, 2),
        ]


def test_character_api_write_through_projects_parent_lineage_and_single_active_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    primary_role = _create_role(client, key="macro_role", name="Macro Role")
    secondary_role = _create_role(client, key="news_role", name="News Role")
    created_character = _create_character(
        client,
        handle="macro_researcher",
        display_name="Macro Researcher",
        role_id=int(primary_role["id"]),
        capability_bundle_keys=["builtin.librarian_context"],
    )

    with session_factory() as session:
        created_profiles = _iter_profiles(session, key="imported.character.macro_researcher")
        assert len(created_profiles) == 1
        created_profile = created_profiles[0]
        assert created_profile.origin == "imported"
        assert created_profile.status == "ACTIVE"
        assert created_profile.kind == "character_profile"
        assert created_profile.display_name == "Macro Researcher"
        assert created_profile.enabled is True
        assert created_profile.handle == "macro_researcher"
        assert created_profile.canonical_target_id == "character:macro_researcher"
        assert created_profile.parent_profile_key == "imported.role.macro_role"
        assert created_profile.parent_profile_version == 1
        assert created_profile.legacy_entity_type == "character"
        assert created_profile.legacy_entity_key == "macro_researcher"
        assert created_profile.legacy_source_version == int(created_character["version"])
        assert created_profile.system_prompt_fragment == ""
        assert created_profile.prompt_append_fragment == "Focus on catalysts."
        assert created_profile.default_capability_bundle_keys == ["builtin.librarian_context"]

    update_response = client.patch(
        f"/api/v1/orchestration/characters/{created_character['id']}",
        json={
            "roleId": secondary_role["id"],
            "promptAppend": "Watch revisions.",
            "enabled": False,
            "capabilityBundleKeys": ["builtin.explore_context"],
        },
    )
    assert update_response.status_code == 200, update_response.json()

    with session_factory() as session:
        role_profiles = _iter_profiles(session, key="imported.role.news_role")
        assert [(profile.version, profile.status) for profile in role_profiles] == [(1, "ACTIVE")]

        profiles = _iter_profiles(session, key="imported.character.macro_researcher")
        assert [
            (
                profile.version,
                profile.status,
                profile.legacy_source_version,
                profile.parent_profile_key,
                profile.parent_profile_version,
            )
            for profile in profiles
        ] == [
            (2, "ACTIVE", 2, "imported.role.news_role", 1),
            (1, "DEPRECATED", 1, "imported.role.macro_role", 1),
        ]
        assert sum(profile.status == "ACTIVE" for profile in profiles) == 1

        active_profile = profiles[0]
        assert active_profile.enabled is False
        assert active_profile.prompt_append_fragment == "Watch revisions."
        assert active_profile.default_capability_bundle_keys == ["builtin.explore_context"]

        assert [
            (event.operation, event.persona_profile_version, event.legacy_source_version)
            for event in _iter_events(
                session,
                legacy_entity_type="character",
                legacy_entity_key="macro_researcher",
            )
        ] == [
            ("create", 1, 1),
            ("deprecate", 1, 1),
            ("reproject", 2, 2),
        ]


def test_projection_failure_rolls_back_legacy_and_imported_writes(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = OrchestrationService(session)

        def _raise_projection_error(_: OrchestrationRole) -> None:
            raise RuntimeError("projection exploded")

        monkeypatch.setattr(
            service.persona_projection_service, "project_role", _raise_projection_error
        )

        with pytest.raises(RuntimeError, match="projection exploded"):
            service.create_role(
                OrchestrationRoleCreate(
                    key="rollback_role",
                    name="Rollback Role",
                    description="Should rollback",
                    system_prompt="You should never persist.",
                    capability_bundle_keys=[],
                    enabled=True,
                )
            )

    with session_factory() as session:
        persisted_role = session.scalar(
            select(OrchestrationRole).where(OrchestrationRole.key == "rollback_role")
        )
        assert persisted_role is None
        assert _iter_profiles(session, key="imported.role.rollback_role") == []
        assert (
            _iter_events(
                session,
                legacy_entity_type="role",
                legacy_entity_key="rollback_role",
            )
            == []
        )


def test_validation_failure_does_not_create_legacy_or_imported_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "bad-key",
            "name": "Bad Key Role",
            "description": "Invalid key",
            "systemPrompt": "You analyze macro conditions.",
            "enabled": True,
        },
    )
    assert response.status_code == 422, response.json()

    with session_factory() as session:
        assert (
            session.scalar(
                select(OrchestrationRole).where(OrchestrationRole.name == "Bad Key Role")
            )
            is None
        )
        assert _iter_profiles(session, key="imported.role.bad-key") == []
        assert _iter_events(session, legacy_entity_type="role", legacy_entity_key="bad-key") == []


def test_character_delete_archives_imported_persona_and_records_archive_event(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    role = _create_role(client, key="delete_character_role", name="Delete Character Role")
    created_character = _create_character(
        client,
        handle="delete_character_target",
        display_name="Delete Character Target",
        role_id=int(role["id"]),
    )

    delete_response = client.delete(f"/api/v1/orchestration/characters/{created_character['id']}")
    assert delete_response.status_code == 204, delete_response.text

    with session_factory() as session:
        profiles = _iter_profiles(session, key="imported.character.delete_character_target")
        assert [
            (profile.version, profile.status, profile.legacy_source_version) for profile in profiles
        ] == [(1, "ARCHIVED", 1)]
        assert sum(profile.status == "ACTIVE" for profile in profiles) == 0
        assert [
            (event.operation, event.persona_profile_version, event.legacy_source_version)
            for event in _iter_events(
                session,
                legacy_entity_type="character",
                legacy_entity_key="delete_character_target",
            )
        ] == [
            ("create", 1, 1),
            ("archive", 1, 1),
        ]


def test_role_delete_archives_imported_persona_and_records_archive_event(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_role = _create_role(client, key="delete_role_target", name="Delete Role Target")

    delete_response = client.delete(f"/api/v1/orchestration/roles/{created_role['id']}")
    assert delete_response.status_code == 204, delete_response.text

    with session_factory() as session:
        profiles = _iter_profiles(session, key="imported.role.delete_role_target")
        assert [
            (profile.version, profile.status, profile.legacy_source_version) for profile in profiles
        ] == [(1, "ARCHIVED", 1)]
        assert sum(profile.status == "ACTIVE" for profile in profiles) == 0
        assert [
            (event.operation, event.persona_profile_version, event.legacy_source_version)
            for event in _iter_events(
                session,
                legacy_entity_type="role",
                legacy_entity_key="delete_role_target",
            )
        ] == [
            ("create", 1, 1),
            ("archive", 1, 1),
        ]
