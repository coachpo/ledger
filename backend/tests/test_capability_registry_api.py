from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability_registry_entry import CapabilityRegistryEntry


def _tool_payload(
    *, key: str, approval_mode: str | None = None, **overrides: Any
) -> dict[str, Any]:
    normalized_key = key.strip().lower()
    payload: dict[str, Any] = {
        "key": key,
        "type": "tool",
        "displayName": "Managed Tool Capability",
        "description": "Managed tool capability description.",
        "adapterKey": f"{normalized_key}.adapter",
        "configSchema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "additionalProperties": False,
        },
    }
    if approval_mode is not None:
        payload["approvalMode"] = approval_mode
    payload.update(overrides)
    return payload


def _connector_payload(
    *, key: str, approval_mode: str | None = None, **overrides: Any
) -> dict[str, Any]:
    payload = _tool_payload(
        key=key,
        approval_mode=approval_mode,
        type="connector",
        displayName="Managed Connector Capability",
        description="Managed connector capability description.",
        transport="mcp",
        lifecycle="placeholder",
    )
    payload.update(overrides)
    return payload


def _bundle_payload(
    *, key: str, approval_mode: str | None = None, **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "type": "bundle",
        "displayName": "Managed Bundle Capability",
        "description": "Managed bundle capability description.",
        "bundleMembers": [
            {
                "memberType": "tool",
                "capabilityKey": "ledger.report_lookup",
                "capabilityVersion": 1,
            }
        ],
    }
    if approval_mode is not None:
        payload["approvalMode"] = approval_mode
    payload.update(overrides)
    return payload


def _build_capability_entry(
    *,
    key: str,
    version: int,
    status: str,
    origin: str = "managed",
    capability_type: str = "tool",
    approval_mode: str = "not_required",
    adapter_key: str | None = None,
    config_schema: dict[str, Any] | None = None,
    bundle_members: list[dict[str, Any]] | None = None,
    transport: str | None = None,
    lifecycle: str | None = None,
) -> CapabilityRegistryEntry:
    if adapter_key is None and capability_type != "bundle":
        adapter_key = f"{key}.adapter"
    if config_schema is None and capability_type != "bundle":
        config_schema = {"type": "object"}
    return CapabilityRegistryEntry(
        key=key,
        version=version,
        origin=origin,
        status=status,
        type=capability_type,
        display_name=f"{key}-{version}",
        description=f"Capability description for {key}",
        approval_mode=approval_mode,
        adapter_key=adapter_key,
        config_schema=config_schema,
        bundle_members=bundle_members,
        transport=transport,
        lifecycle=lifecycle,
    )


def create_capability_draft(
    client: TestClient,
    *,
    key: str = "managed.tool_alpha",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v2/capabilities",
        json=payload or _tool_payload(key=key),
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_capability_create_patch_activate_and_list_read_behavior(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = create_capability_draft(client, key="  managed.tool_alpha  ")

    assert created["key"] == "managed.tool_alpha"
    assert created["version"] == 1
    assert created["origin"] == "managed"
    assert created["status"] == "DRAFT"
    assert created["type"] == "tool"
    assert created["approvalMode"] == "not_required"
    assert created["bundleMembers"] is None
    assert created["transport"] is None
    assert created["lifecycle"] is None

    with session_factory() as session:
        bundle_members_is_null = session.execute(
            text(
                "SELECT bundle_members IS NULL "
                "FROM capability_registry_entries WHERE id = :capability_id"
            ),
            {"capability_id": created["id"]},
        ).scalar_one()
    assert bundle_members_is_null is True

    update_response = client.patch(
        f"/api/v2/capabilities/{created['id']}",
        json={
            "displayName": "Managed Tool Capability v2",
            "description": "Updated tool capability description.",
            "approvalMode": "required",
            "adapterKey": "managed.tool_alpha.adapter.v2",
            "configSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
                "additionalProperties": False,
            },
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["displayName"] == "Managed Tool Capability v2"
    assert updated["description"] == "Updated tool capability description."
    assert updated["approvalMode"] == "required"
    assert updated["adapterKey"] == "managed.tool_alpha.adapter.v2"
    assert updated["configSchema"] == {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
        "additionalProperties": False,
    }

    get_response = client.get(f"/api/v2/capabilities/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json() == updated

    list_response = client.get(
        "/api/v2/capabilities",
        params={"origin": "managed", "type": "tool"},
    )
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [updated]

    activate_response = client.post(f"/api/v2/capabilities/{created['id']}/activate")
    assert activate_response.status_code == 200, activate_response.json()
    activated = activate_response.json()
    assert activated["status"] == "ACTIVE"

    active_list_response = client.get(
        "/api/v2/capabilities",
        params={"origin": "managed", "status": "ACTIVE"},
    )
    assert active_list_response.status_code == 200, active_list_response.json()
    assert active_list_response.json()["items"] == [activated]


def test_capability_seeded_rows_are_read_only_and_seeded_keys_are_reserved(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    seeded_list_response = client.get(
        "/api/v2/capabilities",
        params={"origin": "seeded", "type": "bundle"},
    )
    assert seeded_list_response.status_code == 200, seeded_list_response.json()
    seeded_bundle = next(
        item
        for item in seeded_list_response.json()["items"]
        if item["key"] == "builtin.librarian_context"
    )
    assert seeded_bundle["origin"] == "seeded"
    assert seeded_bundle["status"] == "ACTIVE"
    assert seeded_bundle["bundleMembers"] == [
        {
            "memberType": "tool",
            "capabilityKey": "ledger.report_lookup",
            "capabilityVersion": 1,
        },
        {
            "memberType": "tool",
            "capabilityKey": "ledger.orchestration_catalog_lookup",
            "capabilityVersion": 1,
        },
    ]

    get_seeded_response = client.get(f"/api/v2/capabilities/{seeded_bundle['id']}")
    assert get_seeded_response.status_code == 200, get_seeded_response.json()
    assert get_seeded_response.json() == seeded_bundle

    patch_response = client.patch(
        f"/api/v2/capabilities/{seeded_bundle['id']}",
        json={"displayName": "Should Fail"},
    )
    assert patch_response.status_code == 400, patch_response.json()
    assert patch_response.json()["code"] == "capability_origin_immutable"

    activate_response = client.post(f"/api/v2/capabilities/{seeded_bundle['id']}/activate")
    assert activate_response.status_code == 400, activate_response.json()
    assert activate_response.json()["code"] == "capability_origin_immutable"

    create_reserved_response = client.post(
        "/api/v2/capabilities",
        json=_tool_payload(key="ledger.report_lookup"),
    )
    assert create_reserved_response.status_code == 400, create_reserved_response.json()
    assert create_reserved_response.json()["code"] == "capability_seeded_key_reserved"

    with session_factory() as session:
        managed_shadow = _build_capability_entry(
            key="ledger.report_lookup",
            version=2,
            origin="managed",
            status="DRAFT",
        )
        session.add(managed_shadow)
        session.commit()
        shadow_id = managed_shadow.id

    activate_shadow_response = client.post(f"/api/v2/capabilities/{shadow_id}/activate")
    assert activate_shadow_response.status_code == 400, activate_shadow_response.json()
    assert activate_shadow_response.json()["code"] == "capability_seeded_key_reserved"


def test_capability_duplicate_draft_is_rejected(client: TestClient) -> None:
    create_capability_draft(client, key="managed.duplicate_tool")

    response = client.post(
        "/api/v2/capabilities",
        json=_tool_payload(key="managed.duplicate_tool"),
    )
    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "capability_duplicate_draft"


@pytest.mark.parametrize(
    ("key", "bundle_members", "error_code"),
    [
        (
            "managed.bundle_missing_member",
            [
                {
                    "memberType": "tool",
                    "capabilityKey": "ledger.report_lookup",
                    "capabilityVersion": 99,
                }
            ],
            "capability_bundle_member_not_found",
        ),
        (
            "managed.bundle_type_mismatch",
            [
                {
                    "memberType": "connector",
                    "capabilityKey": "ledger.report_lookup",
                    "capabilityVersion": 1,
                }
            ],
            "capability_bundle_member_type_mismatch",
        ),
        (
            "managed.bundle_nested_member",
            [
                {
                    "memberType": "bundle",
                    "capabilityKey": "builtin.librarian_context",
                    "capabilityVersion": 1,
                }
            ],
            "capability_nested_bundle_member",
        ),
    ],
)
def test_capability_bundle_validation_rejects_invalid_members(
    client: TestClient,
    key: str,
    bundle_members: list[dict[str, Any]],
    error_code: str,
) -> None:
    response = client.post(
        "/api/v2/capabilities",
        json=_bundle_payload(key=key, bundleMembers=bundle_members),
    )
    assert response.status_code == 400, response.json()
    assert response.json()["code"] == error_code


def test_capability_connector_fields_and_approval_rules_are_enforced(client: TestClient) -> None:
    created = client.post(
        "/api/v2/capabilities",
        json=_connector_payload(key="managed.connector_alpha"),
    )
    assert created.status_code == 201, created.json()
    assert created.json()["approvalMode"] == "required"
    assert created.json()["transport"] == "mcp"
    assert created.json()["lifecycle"] == "placeholder"

    non_connector_transport_response = client.post(
        "/api/v2/capabilities",
        json=_tool_payload(key="managed.tool_with_transport", transport="mcp"),
    )
    assert (
        non_connector_transport_response.status_code == 400
    ), non_connector_transport_response.json()
    assert non_connector_transport_response.json()["code"] == "capability_connector_fields_invalid"

    missing_connector_fields_response = client.post(
        "/api/v2/capabilities",
        json=_connector_payload(
            key="managed.connector_missing_fields",
            transport=None,
        ),
    )
    assert (
        missing_connector_fields_response.status_code == 400
    ), missing_connector_fields_response.json()
    assert (
        missing_connector_fields_response.json()["code"] == "capability_connector_fields_required"
    )

    invalid_connector_lifecycle_response = client.post(
        "/api/v2/capabilities",
        json=_connector_payload(
            key="managed.connector_invalid_lifecycle",
            lifecycle="pending",
        ),
    )
    assert (
        invalid_connector_lifecycle_response.status_code == 400
    ), invalid_connector_lifecycle_response.json()
    assert (
        invalid_connector_lifecycle_response.json()["code"]
        == "capability_connector_lifecycle_invalid"
    )

    invalid_connector_approval_response = client.post(
        "/api/v2/capabilities",
        json=_connector_payload(
            key="managed.connector_relaxed_approval",
            approval_mode="not_required",
        ),
    )
    assert (
        invalid_connector_approval_response.status_code == 400
    ), invalid_connector_approval_response.json()
    assert (
        invalid_connector_approval_response.json()["code"] == "capability_invalid_approval_override"
    )

    invalid_bundle_approval_response = client.post(
        "/api/v2/capabilities",
        json=_bundle_payload(
            key="managed.bundle_requires_approval",
            approval_mode="required",
        ),
    )
    assert (
        invalid_bundle_approval_response.status_code == 400
    ), invalid_bundle_approval_response.json()
    assert (
        invalid_bundle_approval_response.json()["code"] == "capability_bundle_approval_mode_invalid"
    )
