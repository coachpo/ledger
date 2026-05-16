from __future__ import annotations

from typing import cast

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError, extension_disabled_error
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService


def _extension_item(client: TestClient) -> dict[str, object]:
    response = client.get("/api/extensions")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    assert len(items) == 1
    return items[0]


def test_list_extensions_default_enabled_state_and_contributions(client: TestClient) -> None:
    item = _extension_item(client)

    assert item["key"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert item["label"] == "Finance Workspace"
    assert item["enabled"] is True
    assert item["defaultEnabled"] is True
    assert item["phase"] == "phase_1_bundled_first_party"
    assert item["stateVersion"] == 1
    assert item["enabledAt"] is not None
    assert item["disabledAt"] is None
    assert item["disabledReason"] is None
    assert "backend_api_routes" in cast(list[str], item["contributionCategories"])

    contributions = cast(list[dict[str, object]], item["contributions"])
    surfaces_by_category = {
        str(contribution["surface"]): contribution for contribution in contributions
    }
    quote_tool = surfaces_by_category[FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS[0]]
    assert quote_tool["category"] == "native_runtime_tools"
    assert quote_tool["ownerExtensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert quote_tool["dependencies"] == []
    assert quote_tool["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY


def test_toggle_extension_state_persistence_and_enabled_views(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False, "disabledReason": "maintenance window"},
    )
    assert response.status_code == 200, response.json()
    disabled_body = cast(dict[str, object], response.json())
    assert disabled_body["enabled"] is False
    assert disabled_body["stateVersion"] == 2
    assert disabled_body["disabledReason"] == "maintenance window"
    assert disabled_body["disabledAt"] is not None

    with session_factory() as session:
        service = ExtensionService(session)
        snapshot = service.resolve_state(FINANCE_WORKSPACE_EXTENSION_KEY)
        assert snapshot.enabled is False
        assert snapshot.disabled_reason == "maintenance window"
        assert service.list_enabled_discovery_contributions() == []
        assert service.list_enabled_execution_contributions() == []
        assert service.list_all_contributions()

    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": True},
    )
    assert response.status_code == 200, response.json()
    enabled_body = cast(dict[str, object], response.json())
    assert enabled_body["enabled"] is True
    assert enabled_body["stateVersion"] == 3
    assert enabled_body["disabledReason"] is None
    assert enabled_body["disabledAt"] is None

    with session_factory() as session:
        snapshot = ExtensionService(session).resolve_state(FINANCE_WORKSPACE_EXTENSION_KEY)
    assert snapshot.enabled is True


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
