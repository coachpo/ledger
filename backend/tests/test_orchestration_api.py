from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import init_db
from app.models.persona_profile import PersonaProfile


def create_role(
    client: TestClient,
    *,
    key: str = "macro_researcher",
    name: str = "Macro Researcher",
    description: str = "Research macro signals",
    system_prompt: str = "You analyze macro conditions.",
    capability_bundle_keys: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "name": name,
        "description": description,
        "systemPrompt": system_prompt,
        "enabled": enabled,
    }
    if capability_bundle_keys is not None:
        payload["capabilityBundleKeys"] = capability_bundle_keys
    response = client.post(
        "/api/v1/orchestration/roles",
        json=payload,
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_character(
    client: TestClient,
    *,
    handle: str = "macro_researcher",
    display_name: str = "Macro Researcher",
    description: str = "Research macro signals",
    role_id: int,
    prompt_append: str = "Focus on catalysts.",
    capability_bundle_keys: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "handle": handle,
        "displayName": display_name,
        "description": description,
        "roleId": role_id,
        "promptAppend": prompt_append,
        "enabled": enabled,
    }
    if capability_bundle_keys is not None:
        payload["capabilityBundleKeys"] = capability_bundle_keys
    response = client.post(
        "/api/v1/orchestration/characters",
        json=payload,
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_role_crud_roundtrip(client: TestClient) -> None:
    created = create_role(client, capability_bundle_keys=["builtin.librarian_context"])

    assert created["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert created["version"] == 1

    list_response = client.get("/api/v1/orchestration/roles")
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()[0]["key"] == created["key"]
    assert list_response.json()[0]["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert list_response.json()[0]["version"] == 1

    get_response = client.get(f"/api/v1/orchestration/roles/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["systemPrompt"] == created["systemPrompt"]
    assert get_response.json()["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert get_response.json()["version"] == 1

    update_response = client.patch(
        f"/api/v1/orchestration/roles/{created['id']}",
        json={
            "name": "Macro Strategist",
            "enabled": False,
            "capabilityBundleKeys": ["builtin.explore_context"],
        },
    )
    assert update_response.status_code == 200, update_response.json()
    assert update_response.json()["name"] == "Macro Strategist"
    assert update_response.json()["capabilityBundleKeys"] == ["builtin.explore_context"]
    assert update_response.json()["enabled"] is False
    assert update_response.json()["version"] == 2

    delete_response = client.delete(f"/api/v1/orchestration/roles/{created['id']}")
    assert delete_response.status_code == 204, delete_response.text

    missing_response = client.get(f"/api/v1/orchestration/roles/{created['id']}")
    assert missing_response.status_code == 404, missing_response.json()


def test_role_delete_rejects_role_in_use(client: TestClient) -> None:
    role = create_role(client)
    character = create_character(client, role_id=int(role["id"]))

    delete_response = client.delete(f"/api/v1/orchestration/roles/{role['id']}")
    assert delete_response.status_code == 409, delete_response.json()
    assert delete_response.json()["code"] == "role_in_use"

    get_response = client.get(f"/api/v1/orchestration/characters/{character['id']}")
    assert get_response.status_code == 200, get_response.json()


def test_character_crud_roundtrip(client: TestClient) -> None:
    role = create_role(client, key="market_scanner", name="Market Scanner")
    created = create_character(
        client,
        handle="market_scanner",
        role_id=int(role["id"]),
        capability_bundle_keys=["builtin.librarian_context"],
    )

    assert created["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert created["roleKey"] == role["key"]
    assert created["version"] == 1

    list_response = client.get("/api/v1/orchestration/characters")
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()[0]["handle"] == created["handle"]
    assert list_response.json()[0]["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert list_response.json()[0]["roleKey"] == role["key"]
    assert list_response.json()[0]["version"] == 1

    get_response = client.get(f"/api/v1/orchestration/characters/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["displayName"] == created["displayName"]
    assert get_response.json()["capabilityBundleKeys"] == ["builtin.librarian_context"]
    assert get_response.json()["roleKey"] == role["key"]
    assert get_response.json()["version"] == 1

    update_response = client.patch(
        f"/api/v1/orchestration/characters/{created['id']}",
        json={
            "displayName": "Market Scout",
            "promptAppend": "Watch momentum.",
            "capabilityBundleKeys": ["builtin.explore_context"],
        },
    )
    assert update_response.status_code == 200, update_response.json()
    assert update_response.json()["displayName"] == "Market Scout"
    assert update_response.json()["promptAppend"] == "Watch momentum."
    assert update_response.json()["capabilityBundleKeys"] == ["builtin.explore_context"]
    assert update_response.json()["roleKey"] == role["key"]
    assert update_response.json()["version"] == 2

    delete_response = client.delete(f"/api/v1/orchestration/characters/{created['id']}")
    assert delete_response.status_code == 204, delete_response.text

    missing_response = client.get(f"/api/v1/orchestration/characters/{created['id']}")
    assert missing_response.status_code == 404, missing_response.json()


def test_character_handle_is_immutable_after_create(client: TestClient) -> None:
    role = create_role(client, key="journalist", name="Journalist")
    character = create_character(client, handle="researcher", role_id=int(role["id"]))

    response = client.patch(
        f"/api/v1/orchestration/characters/{character['id']}",
        json={"handle": "renamed_researcher"},
    )
    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "handle"


def test_role_key_is_trimmed_and_lowercased_on_create(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "  Macro_Research_Role  ",
            "name": "  Macro Research Role  ",
            "description": "   ",
            "systemPrompt": "  You analyze macro conditions.  ",
            "enabled": True,
        },
    )

    assert response.status_code == 201, response.json()
    payload = response.json()
    assert payload["key"] == "macro_research_role"
    assert payload["name"] == "Macro Research Role"
    assert payload["description"] is None
    assert payload["systemPrompt"] == "You analyze macro conditions."
    assert payload["capabilityBundleKeys"] == []


def test_role_create_rejects_invalid_key(client: TestClient) -> None:
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
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "key"


def test_role_create_rejects_invalid_capability_bundle_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "bundle_role",
            "name": "Bundle Role",
            "description": "Invalid bundle key",
            "systemPrompt": "You analyze macro conditions.",
            "capabilityBundleKeys": ["bad-key"],
            "enabled": True,
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "capabilityBundleKeys"


def test_role_create_rejects_unknown_capability_bundle_key(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "bundle_role",
            "name": "Bundle Role",
            "description": "Unknown bundle key",
            "systemPrompt": "You analyze macro conditions.",
            "capabilityBundleKeys": ["builtin.unknown_context"],
            "enabled": True,
        },
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "unknown_capability_bundle_key"


def test_role_create_rejects_reserved_executable_capability_reference(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "bundle_role",
            "name": "Bundle Role",
            "description": "Executable capability reference",
            "systemPrompt": "You analyze macro conditions.",
            "capabilityBundleKeys": ["ledger.report_lookup"],
            "enabled": True,
        },
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "reserved_capability_bundle_key"


def test_role_create_rejects_duplicate_normalized_key(client: TestClient) -> None:
    create_role(client, key="macro_research_role")

    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": " Macro_Research_Role ",
            "name": "Another Macro Research Role",
            "description": "Duplicate normalized key",
            "systemPrompt": "You analyze macro conditions.",
            "enabled": True,
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "duplicate_role_key"


def test_role_create_rejects_duplicate_name(client: TestClient) -> None:
    create_role(client, key="macro_research_role", name="Macro Research Role")

    response = client.post(
        "/api/v1/orchestration/roles",
        json={
            "key": "another_role",
            "name": "Macro Research Role",
            "description": "Duplicate role name",
            "systemPrompt": "You analyze macro conditions.",
            "enabled": True,
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "duplicate_role_name"


def test_role_update_rejects_duplicate_name(client: TestClient) -> None:
    first_role = create_role(client, key="macro_research_role", name="Macro Research Role")
    second_role = create_role(client, key="market_scanner", name="Market Scanner")

    response = client.patch(
        f"/api/v1/orchestration/roles/{second_role['id']}",
        json={"name": first_role["name"]},
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "duplicate_role_name"


def test_character_handle_is_trimmed_lowercased_and_role_key_is_exposed(client: TestClient) -> None:
    role = create_role(client, key="macro_research_role", name="Macro Research Role")

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": "  Macro_Researcher  ",
            "displayName": "  Macro Researcher  ",
            "description": "   ",
            "roleId": role["id"],
            "promptAppend": "   Focus on rates.   ",
            "enabled": True,
        },
    )

    assert response.status_code == 201, response.json()
    payload = response.json()
    assert payload["handle"] == "macro_researcher"
    assert payload["displayName"] == "Macro Researcher"
    assert payload["description"] is None
    assert payload["promptAppend"] == "Focus on rates."
    assert payload["capabilityBundleKeys"] == []
    assert payload["roleKey"] == "macro_research_role"


def test_character_create_rejects_invalid_handle(client: TestClient) -> None:
    role = create_role(client, key="macro_research_role", name="Macro Research Role")

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": "bad-handle",
            "displayName": "Bad Handle",
            "description": "Invalid handle",
            "roleId": role["id"],
            "promptAppend": "",
            "enabled": True,
        },
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "handle"


def test_character_update_rejects_invalid_capability_bundle_key(client: TestClient) -> None:
    role = create_role(client, key="bundle_role", name="Bundle Role")
    character = create_character(client, handle="bundle_character", role_id=int(role["id"]))

    response = client.patch(
        f"/api/v1/orchestration/characters/{character['id']}",
        json={"capabilityBundleKeys": ["bad-key"]},
    )

    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "capabilityBundleKeys"


def test_character_update_rejects_reserved_executable_capability_reference(
    client: TestClient,
) -> None:
    role = create_role(client, key="bundle_role", name="Bundle Role")
    character = create_character(client, handle="bundle_character", role_id=int(role["id"]))

    response = client.patch(
        f"/api/v1/orchestration/characters/{character['id']}",
        json={"capabilityBundleKeys": ["ledger.mcp.market_data"]},
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "reserved_capability_bundle_key"


def test_character_create_rejects_duplicate_normalized_handle(client: TestClient) -> None:
    role = create_role(client, key="macro_research_role", name="Macro Research Role")
    create_character(client, handle="macro_researcher", role_id=int(role["id"]))

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": " Macro_Researcher ",
            "displayName": "Duplicate Handle",
            "description": "Duplicate normalized handle",
            "roleId": role["id"],
            "promptAppend": "",
            "enabled": True,
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "duplicate_character_handle"


def test_character_create_rejects_reserved_builtin_handle(client: TestClient) -> None:
    role = create_role(client, key="specialist", name="Specialist")

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": "builtin:librarian",
            "displayName": "Builtin Librarian Copy",
            "description": "Should not be creatable",
            "roleId": role["id"],
            "promptAppend": "",
            "enabled": True,
        },
    )
    assert response.status_code == 422, response.json()
    assert response.json()["code"] == "validation_error"
    assert response.json()["details"][0]["field"] == "handle"


def test_character_create_rejects_public_builtin_handle(client: TestClient) -> None:
    role = create_role(client, key="public_specialist", name="Public Specialist")

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": "librarian",
            "displayName": "Builtin Librarian Copy",
            "description": "Should not be creatable",
            "roleId": role["id"],
            "promptAppend": "",
            "enabled": True,
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "reserved_character_handle"


def test_character_create_rejects_disabled_role(client: TestClient) -> None:
    role = create_role(client, key="disabled_role", name="Disabled Role", enabled=False)

    response = client.post(
        "/api/v1/orchestration/characters",
        json={
            "handle": "disabled_researcher",
            "displayName": "Disabled Researcher",
            "description": "Should not be creatable",
            "roleId": role["id"],
            "promptAppend": "",
            "capabilityBundleKeys": ["builtin.librarian_context"],
            "enabled": True,
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "disabled_role"


def test_character_update_rejects_disabled_role(client: TestClient) -> None:
    enabled_role = create_role(client, key="enabled_role", name="Enabled Role")
    disabled_role = create_role(
        client, key="disabled_target", name="Disabled Target", enabled=False
    )
    character = create_character(client, role_id=int(enabled_role["id"]))

    response = client.patch(
        f"/api/v1/orchestration/characters/{character['id']}",
        json={
            "roleId": disabled_role["id"],
            "capabilityBundleKeys": ["builtin.explore_context"],
        },
    )
    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "disabled_role"


def test_mention_catalog_returns_builtin_and_enabled_characters_only(client: TestClient) -> None:
    enabled_role = create_role(client, key="enabled_catalog_role", name="Enabled Catalog Role")
    active_role = create_role(client, key="active_catalog_role", name="Active Catalog Role")
    enabled_character = create_character(
        client,
        handle="active_catalog_character",
        display_name="Active Catalog Character",
        role_id=int(active_role["id"]),
    )
    disabled_character = create_character(
        client,
        handle="disabled_catalog_character",
        display_name="Disabled Catalog Character",
        role_id=int(enabled_role["id"]),
    )

    disable_role_response = client.patch(
        f"/api/v1/orchestration/roles/{enabled_role['id']}",
        json={"enabled": False},
    )
    assert disable_role_response.status_code == 200, disable_role_response.json()

    response = client.get("/api/v1/orchestration/mentions/catalog")
    assert response.status_code == 200, response.json()

    catalog = response.json()
    assert set(catalog) == {"targets"}
    handles = {item["handle"] for item in catalog["targets"]}
    assert "librarian" in handles
    assert "explore" in handles
    assert enabled_character["handle"] in handles
    assert "disabled_catalog_character" not in handles
    builtin_items = [item for item in catalog["targets"] if item["kind"] == "builtin"]
    assert builtin_items
    assert all(item["canonicalTargetId"].startswith("builtin:") for item in builtin_items)
    assert all(":" not in item["handle"] for item in builtin_items)
    assert disabled_character["handle"] not in handles
    character_item = next(
        item for item in catalog["targets"] if item["handle"] == enabled_character["handle"]
    )
    assert character_item["kind"] == "character"
    assert character_item["canonicalTargetId"] == f"character:{enabled_character['handle']}"
    assert character_item["roleKey"] == active_role["key"]


def test_legacy_orchestration_tables_gain_version_columns(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE orchestration_roles (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    system_prompt TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE orchestration_characters (
                    id SERIAL PRIMARY KEY,
                    handle VARCHAR(100) NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    role_id INTEGER NOT NULL REFERENCES orchestration_roles(id) ON DELETE RESTRICT,
                    prompt_append TEXT,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO orchestration_roles (key, name, description, system_prompt, enabled)
                VALUES ('macro_research_role', 'Macro Research Role', NULL, 'Prompt', TRUE)
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO orchestration_characters (
                    handle,
                    display_name,
                    description,
                    role_id,
                    prompt_append,
                    enabled
                )
                VALUES ('macro_researcher', 'Macro Researcher', NULL, 1, NULL, TRUE)
                """
            )

        init_db(database_url)

        inspector = inspect(engine)
        role_columns = {
            column["name"]: column for column in inspector.get_columns("orchestration_roles")
        }
        character_columns = {
            column["name"]: column for column in inspector.get_columns("orchestration_characters")
        }

        assert "version" in role_columns
        assert role_columns["version"]["nullable"] is False
        assert "capability_bundle_keys" in role_columns
        assert role_columns["capability_bundle_keys"]["nullable"] is False
        assert "version" in character_columns
        assert character_columns["version"]["nullable"] is False
        assert "capability_bundle_keys" in character_columns
        assert character_columns["capability_bundle_keys"]["nullable"] is False

        with engine.connect() as connection:
            role_version = connection.exec_driver_sql(
                "SELECT version FROM orchestration_roles WHERE key = 'macro_research_role'"
            ).scalar_one()
            role_bundle_keys = connection.exec_driver_sql(
                "SELECT capability_bundle_keys FROM orchestration_roles "
                "WHERE key = 'macro_research_role'"
            ).scalar_one()
            character_version = connection.exec_driver_sql(
                "SELECT version FROM orchestration_characters WHERE handle = 'macro_researcher'"
            ).scalar_one()
            character_bundle_keys = connection.exec_driver_sql(
                "SELECT capability_bundle_keys FROM orchestration_characters "
                "WHERE handle = 'macro_researcher'"
            ).scalar_one()

        assert role_version == 1
        assert role_bundle_keys == []
        assert character_version == 1
        assert character_bundle_keys == []
    finally:
        engine.dispose()


def test_mention_catalog_ignores_runtime_persona_profiles(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        session.add(
            PersonaProfile(
                key="managed_only_profile",
                version=1,
                origin="managed",
                status="ACTIVE",
                kind="managed_persona",
                display_name="Managed Only Profile",
                enabled=True,
                handle="managed_only_profile",
                canonical_target_id="persona:managed_only_profile",
                parent_profile_key=None,
                parent_profile_version=None,
                legacy_entity_type=None,
                legacy_entity_key=None,
                legacy_source_version=None,
                system_prompt_fragment="System prompt",
                prompt_append_fragment="Prompt append",
                default_capability_bundle_keys=[],
            )
        )
        session.add(
            PersonaProfile(
                key="imported.character.imported_only_profile",
                version=1,
                origin="imported",
                status="ACTIVE",
                kind="character_profile",
                display_name="Imported Only Profile",
                enabled=True,
                handle="imported_only_profile",
                canonical_target_id="character:imported_only_profile",
                parent_profile_key=None,
                parent_profile_version=None,
                legacy_entity_type="character",
                legacy_entity_key="imported_only_profile",
                legacy_source_version=1,
                system_prompt_fragment="",
                prompt_append_fragment="Imported prompt",
                default_capability_bundle_keys=[],
            )
        )
        session.commit()

    response = client.get("/api/v1/orchestration/mentions/catalog")
    assert response.status_code == 200, response.json()

    handles = {item["handle"] for item in response.json()["targets"]}
    assert "managed_only_profile" not in handles
    assert "imported_only_profile" not in handles
