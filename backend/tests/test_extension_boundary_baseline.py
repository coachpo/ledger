from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient

from tests.test_extension_boundary_allowlist import collect_shared_finance_imports


def test_shared_finance_import_boundary_is_clean() -> None:
    assert collect_shared_finance_imports() == {}


def test_api_tools_module_path_leakage_is_retired(
    client: TestClient,
) -> None:
    response = client.get("/api/tools")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    actual_leaks = {str(item["key"]): str(item["module"]) for item in items if "module" in item}

    assert actual_leaks == {}
