from __future__ import annotations

from typing import cast

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, extension_disabled_error
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService


def _extension_item(client: TestClient) -> dict[str, object]:
    response = client.get("/api/extensions")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert len(items) == 1
    return items[0]


def test_list_extensions_returns_exact_slim_enabled_state(client: TestClient) -> None:
    item = _extension_item(client)

    assert item == {
        "key": FINANCE_WORKSPACE_EXTENSION_KEY,
        "label": "Finance Workspace",
        "enabled": True,
    }


def test_toggle_extension_state_persistence_and_enabled_views(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert response.status_code == 200, response.json()
    disabled_body = cast(dict[str, object], response.json())
    assert disabled_body == {
        "key": FINANCE_WORKSPACE_EXTENSION_KEY,
        "label": "Finance Workspace",
        "enabled": False,
    }

    with session_factory() as session:
        snapshot = ExtensionService(session).resolve_state(FINANCE_WORKSPACE_EXTENSION_KEY)
        assert snapshot.extension_key == FINANCE_WORKSPACE_EXTENSION_KEY
        assert snapshot.enabled is False

    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": True},
    )
    assert response.status_code == 200, response.json()
    enabled_body = cast(dict[str, object], response.json())
    assert enabled_body == {
        "key": FINANCE_WORKSPACE_EXTENSION_KEY,
        "label": "Finance Workspace",
        "enabled": True,
    }

    with session_factory() as session:
        snapshot = ExtensionService(session).resolve_state(FINANCE_WORKSPACE_EXTENSION_KEY)
    assert snapshot.enabled is True


@pytest.mark.parametrize(
    ("removed_field", "value"),
    [
        ("disabledReason", "maintenance"),
        ("defaultEnabled", False),
        ("stateVersion", 2),
    ],
)
def test_toggle_extension_rejects_removed_metadata_fields(
    client: TestClient,
    removed_field: str,
    value: object,
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False, removed_field: value},
    )

    assert response.status_code == 422, response.json()
    assert _extension_item(client)["enabled"] is True


def test_extensions_openapi_contract_omits_removed_public_fields(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.json()
    openapi = cast(dict[str, object], response.json())
    components = cast(dict[str, object], openapi["components"])
    schemas = cast(dict[str, dict[str, object]], components["schemas"])

    extension_read = schemas["ExtensionRead"]
    read_properties = cast(dict[str, object], extension_read["properties"])
    assert set(read_properties) == {"key", "label", "enabled"}

    toggle_request = schemas["ExtensionToggleRequest"]
    toggle_properties = cast(dict[str, object], toggle_request["properties"])
    assert set(toggle_properties) == {"enabled"}

    removed_fields = {
        "defaultEnabled",
        "phase",
        "versioningRule",
        "contributionCategories",
        "dependencies",
        "contributions",
        "stateVersion",
        "enabledAt",
        "disabledAt",
        "disabledReason",
        "createdAt",
        "updatedAt",
    }
    assert removed_fields.isdisjoint(read_properties)
    assert removed_fields.isdisjoint(toggle_properties)
    assert "ExtensionContributionRead" not in schemas


def test_extension_disabled_error_contract_helper() -> None:
    error = extension_disabled_error(
        extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
        surface="/api/v1/portfolios",
    )

    assert error.status_code == status.HTTP_403_FORBIDDEN
    assert error.code == "extension_disabled"
    assert error.message == "Extension is disabled"
    assert error.details == [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": "/api/v1/portfolios",
        }
    ]


def test_extension_state_helper_raises_extension_disabled_error(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = ExtensionService(session)
        _ = service.set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )
        with pytest.raises(ApiError) as exc_info:
            _ = service.require_enabled(
                FINANCE_WORKSPACE_EXTENSION_KEY,
                surface="runtime.tool.signaldeck.reports.write",
            )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "extension_disabled"
    assert exc_info.value.details == [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": "runtime.tool.signaldeck.reports.write",
        }
    ]
