from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, extension_disabled_error
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService


class _DigitalOracleOwnershipModule(Protocol):
    DIGITAL_ORACLE_DEFAULT_ENABLED: bool
    DIGITAL_ORACLE_EXTENSION_KEY: str
    DIGITAL_ORACLE_LABEL: str


_digital_oracle_ownership = cast(
    _DigitalOracleOwnershipModule,
    cast(object, import_module("app.extensions.signaldeck_digital_oracle.ownership")),
)
DIGITAL_ORACLE_EXTENSION_KEY = _digital_oracle_ownership.DIGITAL_ORACLE_EXTENSION_KEY
DIGITAL_ORACLE_LABEL = _digital_oracle_ownership.DIGITAL_ORACLE_LABEL
DIGITAL_ORACLE_DEFAULT_ENABLED = _digital_oracle_ownership.DIGITAL_ORACLE_DEFAULT_ENABLED


def _extension_items(client: TestClient) -> list[dict[str, object]]:
    response = client.get("/api/extensions")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert len(items) == 2
    for item in items:
        assert set(item) == {"key", "label", "enabled"}
    return items


def _extension_item(client: TestClient, extension_key: str) -> dict[str, object]:
    items = _extension_items(client)
    matches = [item for item in items if item["key"] == extension_key]
    assert len(matches) == 1
    return matches[0]


def test_list_extensions_returns_exact_slim_enabled_state(client: TestClient) -> None:
    items = _extension_items(client)

    assert items == [
        {
            "key": FINANCE_WORKSPACE_EXTENSION_KEY,
            "label": "Finance Workspace",
            "enabled": True,
        },
        {
            "key": DIGITAL_ORACLE_EXTENSION_KEY,
            "label": DIGITAL_ORACLE_LABEL,
            "enabled": DIGITAL_ORACLE_DEFAULT_ENABLED,
        },
    ]


def test_list_extensions_returns_slim_state(client: TestClient) -> None:
    response = client.get("/api/extensions")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert set(body) == {"items"}
    items = cast(list[dict[str, object]], body["items"])
    assert items
    assert all(set(item) == {"key", "label", "enabled"} for item in items)
    assert {str(item["key"]) for item in items} == {
        FINANCE_WORKSPACE_EXTENSION_KEY,
        DIGITAL_ORACLE_EXTENSION_KEY,
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


def test_toggle_extension_rejects_unknown_fields(client: TestClient) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False, "unexpected": "value"},
    )

    assert response.status_code == 422, response.json()
    assert _extension_item(client, FINANCE_WORKSPACE_EXTENSION_KEY)["enabled"] is True
    assert _extension_item(client, DIGITAL_ORACLE_EXTENSION_KEY)["enabled"] is True


def test_extensions_openapi_contract_exposes_slim_state(client: TestClient) -> None:
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
                surface="service.report",
            )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.code == "extension_disabled"
    assert exc_info.value.details == [
        {
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": "service.report",
        }
    ]
