from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.persona_profile import PersonaProfile


def _build_persona(
    *,
    key: str,
    version: int,
    origin: str,
    status: str,
    kind: str,
    display_name: str,
    enabled: bool,
    canonical_target_id: str,
    handle: str | None = None,
) -> PersonaProfile:
    return PersonaProfile(
        key=key,
        version=version,
        origin=origin,
        status=status,
        kind=kind,
        display_name=display_name,
        enabled=enabled,
        handle=handle,
        canonical_target_id=canonical_target_id,
        parent_profile_key=None,
        parent_profile_version=None,
        legacy_entity_type=None,
        legacy_entity_key=None,
        legacy_source_version=None,
        system_prompt_fragment="System instructions.",
        prompt_append_fragment="Append instructions.",
        default_capability_bundle_keys=["builtin.librarian_context"],
    )


def test_persona_profiles_api_lists_latest_versions_and_supports_key_reads(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add_all(
            [
                _build_persona(
                    key="managed.persona.alpha",
                    version=1,
                    origin="managed",
                    status="DEPRECATED",
                    kind="managed_persona",
                    display_name="Managed Persona Alpha v1",
                    enabled=True,
                    canonical_target_id="persona:managed.persona.alpha",
                ),
                _build_persona(
                    key="managed.persona.alpha",
                    version=2,
                    origin="managed",
                    status="DRAFT",
                    kind="managed_persona",
                    display_name="Managed Persona Alpha v2",
                    enabled=True,
                    canonical_target_id="persona:managed.persona.alpha",
                ),
                _build_persona(
                    key="imported.character.analyst",
                    version=4,
                    origin="imported",
                    status="ACTIVE",
                    kind="character_profile",
                    display_name="Analyst",
                    enabled=True,
                    canonical_target_id="character:analyst",
                    handle="analyst",
                ),
                _build_persona(
                    key="builtin.librarian",
                    version=1,
                    origin="seeded",
                    status="ACTIVE",
                    kind="builtin_profile",
                    display_name="Librarian",
                    enabled=True,
                    canonical_target_id="builtin:librarian",
                    handle="librarian",
                ),
            ]
        )
        session.commit()

    list_response = client.get("/api/v2/personas")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    listed_keys = [item["key"] for item in list_payload["items"]]
    assert "builtin.librarian" in listed_keys
    assert "imported.character.analyst" in listed_keys
    assert "managed.persona.alpha" in listed_keys
    managed_entry = next(
        item for item in list_payload["items"] if item["key"] == "managed.persona.alpha"
    )
    assert managed_entry["version"] == 2
    assert managed_entry["status"] == "DRAFT"

    filtered_response = client.get("/api/v2/personas", params={"origin": "imported"})
    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert [item["key"] for item in filtered_payload["items"]] == ["imported.character.analyst"]

    detail_response = client.get("/api/v2/personas/managed.persona.alpha")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["key"] == "managed.persona.alpha"
    assert detail_payload["version"] == 2
    assert detail_payload["displayName"] == "Managed Persona Alpha v2"
    assert detail_payload["defaultCapabilityBundleKeys"] == ["builtin.librarian_context"]


def test_persona_profiles_api_returns_404_for_unknown_key(client: TestClient) -> None:
    response = client.get("/api/v2/personas/does.not.exist")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_studio_persona_profiles_support_managed_drafts_versions_and_lifecycle(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            _build_persona(
                key="imported.character.analyst",
                version=1,
                origin="imported",
                status="ACTIVE",
                kind="character_profile",
                display_name="Analyst",
                enabled=True,
                canonical_target_id="character:analyst",
                handle="analyst",
            )
        )
        session.commit()

    create_response = client.post(
        "/api/v2/studio/persona-profiles",
        json={
            "key": "managed.persona.alpha",
            "displayName": "Managed Persona Alpha",
            "enabled": True,
            "handle": "alpha_guide",
            "systemPromptFragment": "System draft instructions.",
            "promptAppendFragment": "Append draft instructions.",
            "defaultCapabilityBundleKeys": ["builtin.librarian_context"],
        },
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()
    assert created["origin"] == "managed"
    assert created["status"] == "DRAFT"
    assert created["kind"] == "managed_persona"
    assert created["version"] == 1
    assert created["canonicalTargetId"] == "persona:managed.persona.alpha"

    latest_response = client.get("/api/v2/studio/persona-profiles/managed.persona.alpha")
    assert latest_response.status_code == 200, latest_response.json()
    assert latest_response.json()["version"] == 1

    versions_response = client.get("/api/v2/studio/persona-profiles/managed.persona.alpha/versions")
    assert versions_response.status_code == 200, versions_response.json()
    assert versions_response.json() == {
        "items": [
            {
                "version": 1,
                "status": "DRAFT",
                "origin": "managed",
                "createdAt": created["createdAt"],
            }
        ]
    }

    patch_response = client.patch(
        "/api/v2/studio/persona-profiles/managed.persona.alpha/versions/1",
        json={
            "displayName": "Managed Persona Alpha Draft",
            "promptAppendFragment": "Updated append instructions.",
            "systemPromptFragment": "Updated system instructions.",
        },
    )
    assert patch_response.status_code == 200, patch_response.json()
    assert patch_response.json()["displayName"] == "Managed Persona Alpha Draft"
    assert patch_response.json()["promptAppendFragment"] == "Updated append instructions."

    activate_response = client.post(
        "/api/v2/studio/persona-profiles/managed.persona.alpha/versions/1/activate"
    )
    assert activate_response.status_code == 200, activate_response.json()
    assert activate_response.json()["status"] == "ACTIVE"

    second_draft_response = client.post(
        "/api/v2/studio/persona-profiles",
        json={
            "key": "managed.persona.alpha",
            "displayName": "Managed Persona Alpha Draft v2",
            "enabled": True,
            "handle": "alpha_guide",
            "systemPromptFragment": "Second draft system instructions.",
            "promptAppendFragment": "Second draft append instructions.",
            "defaultCapabilityBundleKeys": ["builtin.librarian_context"],
        },
    )
    assert second_draft_response.status_code == 201, second_draft_response.json()
    assert second_draft_response.json()["version"] == 2
    assert second_draft_response.json()["status"] == "DRAFT"

    deprecate_response = client.post(
        "/api/v2/studio/persona-profiles/managed.persona.alpha/versions/1/deprecate"
    )
    assert deprecate_response.status_code == 200, deprecate_response.json()
    assert deprecate_response.json()["status"] == "DEPRECATED"

    archive_response = client.post(
        "/api/v2/studio/persona-profiles/managed.persona.alpha/versions/2/archive"
    )
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "ARCHIVED"

    version_detail_response = client.get(
        "/api/v2/studio/persona-profiles/managed.persona.alpha/versions/2"
    )
    assert version_detail_response.status_code == 200, version_detail_response.json()
    assert version_detail_response.json()["status"] == "ARCHIVED"

    studio_list_response = client.get("/api/v2/studio/persona-profiles")
    assert studio_list_response.status_code == 200, studio_list_response.json()
    listed = next(
        item
        for item in studio_list_response.json()["items"]
        if item["key"] == "managed.persona.alpha"
    )
    assert listed["version"] == 2
    assert listed["status"] == "ARCHIVED"


def test_studio_persona_profiles_keep_imported_personas_read_only(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            _build_persona(
                key="imported.character.analyst",
                version=1,
                origin="imported",
                status="ACTIVE",
                kind="character_profile",
                display_name="Analyst",
                enabled=True,
                canonical_target_id="character:analyst",
                handle="analyst",
            )
        )
        session.commit()

    create_response = client.post(
        "/api/v2/studio/persona-profiles",
        json={
            "key": "imported.character.analyst",
            "displayName": "Should not work",
            "enabled": True,
        },
    )
    assert create_response.status_code == 400, create_response.json()
    assert create_response.json()["code"] == "persona_profile_origin_immutable"

    patch_response = client.patch(
        "/api/v2/studio/persona-profiles/imported.character.analyst/versions/1",
        json={"displayName": "Still should not work"},
    )
    assert patch_response.status_code == 400, patch_response.json()
    assert patch_response.json()["code"] == "persona_profile_origin_immutable"
