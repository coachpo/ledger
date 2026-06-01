from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.model_connection import ModelConnection
from app.models.workflow_package import WorkflowPackage
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_EXPECTED_PACKAGE_TOOL_KEYS = {
    "signaldeck.market_data.quote_lookup",
    "signaldeck.market_data.history_lookup",
    "signaldeck.market_data.ohlcv_lookup",
    "signaldeck.indicators.lookup",
    "signaldeck.fundamentals.lookup",
    "signaldeck.news.lookup",
    "signaldeck.social_sentiment.lookup",
    "signaldeck.insider_data.lookup",
    "signaldeck.positions.lookup",
    "signaldeck.reports.lookup",
    "signaldeck.memory.lookup",
    "signaldeck.memory.write",
}


def _package_source() -> str:
    return _FIXTURE.read_text()


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    last_test_ok: bool | None = None,
    last_test_message: str | None = None,
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                name="TradingAgents Primary Model",
                description="Package API test model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                reasoning_effort="medium",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={"apiKey": "sk-package-api-secret"},
                last_tested_at=(
                    utcnow() if last_test_ok is not None or last_test_message is not None else None
                ),
                last_test_ok=last_test_ok,
                last_test_message=last_test_message,
            )
        )
        session.commit()


def _delete_existing_tradingagents_package(client: TestClient) -> None:
    packages_response = client.get("/api/workflow-packages")
    assert packages_response.status_code == 200, packages_response.json()
    package_items = cast(list[dict[str, object]], packages_response.json()["items"])
    for package in package_items:
        if package["key"] != "tradingagents_advisory_research":
            continue
        deleted = client.delete(f"/api/workflow-packages/{package['id']}")
        assert deleted.status_code == 204, deleted.text
        break


def _create_package(client: TestClient) -> dict[str, object]:
    _delete_existing_tradingagents_package(client)
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _package_source()},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def _assert_manifest_payload(
    body: dict[str, object],
    *,
    package_id: int,
    package_key: str,
) -> dict[str, object]:
    assert body["packageId"] == package_id
    assert body["packageKey"] == package_key
    assert "version" not in body
    assert "compiledPlan" not in body

    source = cast(str, body["manifestSource"])
    assert source.startswith("apiVersion: signaldeck.workflowPackage/v1")
    compiled = compile_workflow_package_manifest(source)
    package_definition = cast(dict[str, object], body["packageDefinition"])
    assert compiled["packageDefinition"] == package_definition
    assert isinstance(body["manifestHash"], str)
    assert isinstance(body["compiledHash"], str)
    assert body["manifestHash"] == compiled["manifestHash"]
    assert body["compiledHash"] == compiled["compiledHash"]

    spec = cast(dict[str, object], package_definition["spec"])
    assert cast(dict[str, object], package_definition["metadata"])["key"] == package_key

    agents = cast(list[dict[str, object]], spec["agents"])
    assert agents and agents[0]["modelConnection"] == "tradingagents_primary_model"
    assert "modelConnectionId" not in json.dumps(package_definition, sort_keys=True)

    output_schemas = cast(list[dict[str, object]], spec["outputSchemas"])
    assert output_schemas and output_schemas[0]["key"] == "analyst_report"

    capability_profiles = cast(list[dict[str, object]], spec["capabilityProfiles"])
    assert capability_profiles and capability_profiles[0]["key"] == "market_research_tools"

    mcp_servers = cast(list[dict[str, object]], spec["mcpServers"])
    assert mcp_servers == []

    workflows = cast(list[dict[str, object]], spec["workflows"])
    assert workflows and workflows[0]["key"] == "advisory_research"

    forbidden_fragments = (
        "secretPayload",
        "secretRefs",
        "requiredBindings",
        "encrypted",
        "modelConnectionId",
        "outputSchemaId",
        "capabilityId",
        "mcpServerId",
        "workflowPackageVersionId",
        "packageVersionId",
        "packageId: ",
        "runHistory",
        "dbId",
        "sk-package-api-secret",
    )
    payload_text = json.dumps(body, sort_keys=True)
    for forbidden in forbidden_fragments:
        assert forbidden not in payload_text

    return compiled


def _workflow_description(package_definition: dict[str, object], workflow_key: str) -> str:
    spec = cast(dict[str, object], package_definition["spec"])
    workflows = cast(list[dict[str, object]], spec["workflows"])
    for workflow in workflows:
        if workflow.get("key") == workflow_key:
            return cast(str, workflow["description"])
    raise AssertionError(f"Workflow {workflow_key!r} not found")


def _manifest_semantics(body: dict[str, object]) -> dict[str, object]:
    return {
        "packageDefinition": body["packageDefinition"],
        "manifestHash": body["manifestHash"],
        "compiledHash": body["compiledHash"],
    }


def _profile_tool_keys(package_definition: dict[str, object]) -> set[str]:
    spec = cast(dict[str, object], package_definition["spec"])
    return {
        tool_key
        for profile in cast(list[dict[str, object]], spec["capabilityProfiles"])
        for tool_key in cast(list[str], profile["toolKeys"])
    }


def _edited_workflow_manifest_source(source: str) -> str:
    return source.replace(
        "TradingAgents Advisory Research",
        "TradingAgents Advisory Research v2",
        1,
    )


def test_workflow_package_list_rejects_removed_status_query(client: TestClient) -> None:
    ordinary = client.get("/api/workflow-packages")
    assert ordinary.status_code == 200, ordinary.json()

    response = client.get("/api/workflow-packages", params={"status": "active"})

    assert response.status_code == 422, response.json()
    assert response.json() == {
        "code": "validation_error",
        "message": "Workflow package request validation failed",
        "details": [
            {
                "field": "status",
                "issue": "Workflow package status filtering is no longer supported",
            }
        ],
    }


def test_default_enabled_finance_extension_keeps_smoke_package_tools_unchanged(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)

    extensions_response = client.get("/api/extensions")
    assert extensions_response.status_code == 200, extensions_response.json()
    extension_items = cast(list[dict[str, object]], extensions_response.json()["items"])
    finance_extension = next(
        item for item in extension_items if item["key"] == FINANCE_WORKSPACE_EXTENSION_KEY
    )
    assert finance_extension == {
        "key": FINANCE_WORKSPACE_EXTENSION_KEY,
        "label": "Finance Workspace",
        "enabled": True,
    }

    created = _create_package(client)
    manifest_response = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert manifest_response.status_code == 200, manifest_response.json()
    manifest_body = cast(dict[str, object], manifest_response.json())
    package_definition = cast(dict[str, object], manifest_body["packageDefinition"])
    assert _profile_tool_keys(package_definition) == _EXPECTED_PACKAGE_TOOL_KEYS


def test_manifest_reads_return_hydrated_safe_package_resources(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    assert created["id"]
    assert created["key"] == "tradingagents_advisory_research"
    assert isinstance(created["manifestHash"], str)

    manifest = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert manifest.status_code == 200, manifest.json()
    manifest_body = cast(dict[str, object], manifest.json())
    _ = _assert_manifest_payload(
        manifest_body,
        package_id=cast(int, created["id"]),
        package_key="tradingagents_advisory_research",
    )

    detail = client.get(f"/api/workflow-packages/{created['id']}")
    assert detail.status_code == 200, detail.json()

    export = client.get(f"/api/workflow-packages/{created['id']}/export")
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("application/yaml")
    expected_content_disposition = (
        'attachment; filename="tradingagents_advisory_research.yaml"; '
        + "filename*=UTF-8''tradingagents_advisory_research.yaml"
    )
    assert export.headers["content-disposition"] == expected_content_disposition
    assert "apiVersion: signaldeck.workflowPackage/v1" in export.text
    assert "modelConnection: tradingagents_primary_model" in export.text
    assert "headers:" not in export.text
    assert "query:" not in export.text
    assert "Authorization: Bearer exa-inline-token" not in export.text
    assert "exaApiKey: exa-inline-key" not in export.text
    for forbidden in (
        "modelConnectionId",
        "outputSchemaId",
        "capabilityId",
        "mcpServerId",
        "secretPayload",
        "secretRefs",
        "requiredBindings",
        "encrypted",
        "sk-package-api-secret",
    ):
        assert forbidden not in export.text

    conflict = client.post(
        "/api/workflow-packages/import",
        json={"manifestSource": export.text},
    )
    assert conflict.status_code == 409, conflict.json()
    assert conflict.json()["code"] == "workflow_package_import_conflict"


def test_manifest_round_trip_save_updates_current_package_in_place(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    package_id = cast(int, created["id"])

    current = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert current.status_code == 200, current.json()
    current_body = cast(dict[str, object], current.json())
    _ = _assert_manifest_payload(
        current_body,
        package_id=package_id,
        package_key="tradingagents_advisory_research",
    )
    current_definition = cast(dict[str, object], current_body["packageDefinition"])
    assert _workflow_description(current_definition, "advisory_research") == (
        "Canonical TradingAgents advisory research topology using SignalDeck sequence and "
        "bounded loop semantics only."
    )

    edited_source = _edited_workflow_manifest_source(cast(str, current_body["manifestSource"]))
    saved = client.patch(
        f"/api/workflow-packages/{package_id}",
        json={"manifestSource": edited_source},
    )
    assert saved.status_code == 200, saved.json()
    saved_body = cast(dict[str, object], saved.json())
    assert saved_body["id"] == package_id

    updated = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert updated.status_code == 200, updated.json()
    updated_body = cast(dict[str, object], updated.json())
    _ = _assert_manifest_payload(
        updated_body,
        package_id=package_id,
        package_key="tradingagents_advisory_research",
    )
    assert saved_body["manifestHash"] == updated_body["manifestHash"]
    assert saved_body["compiledHash"] == updated_body["compiledHash"]
    assert updated_body["manifestHash"] != current_body["manifestHash"]
    updated_definition = cast(dict[str, object], updated_body["packageDefinition"])
    updated_metadata = cast(dict[str, object], updated_definition["metadata"])
    assert updated_metadata["name"] == "TradingAgents Advisory Research v2"
    assert _workflow_description(updated_definition, "advisory_research") == (
        "Canonical TradingAgents advisory research topology using SignalDeck sequence and "
        "bounded loop semantics only."
    )


def test_manifest_reads_recursively_sanitize_polluted_stored_jsonb(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    with session_factory() as session:
        package = session.get(WorkflowPackage, cast(int, created["id"]))
        assert package is not None
        polluted_definition = deepcopy(cast(dict[str, Any], package.package_definition))
        spec = cast(dict[str, Any], polluted_definition["spec"])
        agent = cast(list[dict[str, Any]], spec["agents"])[0]
        agent.update(
            {
                "id": 101,
                "agentId": 202,
                "modelConnectionId": 303,
                "secretPayload": {"apiKey": "sk-polluted-agent-secret"},
                "password": "agent-password",
            }
        )
        package.package_definition = polluted_definition
        session.add(package)
        session.commit()

    latest_manifest = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert latest_manifest.status_code == 200, latest_manifest.json()
    latest_manifest_body = cast(dict[str, object], latest_manifest.json())
    _ = _assert_manifest_payload(
        latest_manifest_body,
        package_id=cast(int, created["id"]),
        package_key="tradingagents_advisory_research",
    )
    latest_spec = cast(
        dict[str, Any],
        cast(dict[str, Any], latest_manifest_body["packageDefinition"])["spec"],
    )
    assert cast(list[dict[str, Any]], latest_spec["mcpServers"]) == []


def test_validate_manifest_reports_diagnostics_without_persisting(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    bad_source = _package_source().replace(
        "signaldeck.market_data.quote_lookup",
        "signaldeck.unknown.tool",
        1,
    )

    with session_factory() as session:
        package_count_before = session.query(WorkflowPackage).count()

    response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": bad_source},
    )

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["metadata"] is None
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert diagnostics[0]["path"] == "spec.capabilityProfiles.market_research_tools.toolKeys[3]"
    with session_factory() as session:
        assert session.query(WorkflowPackage).count() == package_count_before


def test_launch_metadata_and_create_contract_reject_removed_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    launch = client.get(f"/api/workflow-packages/{created['id']}/launch")
    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert launch_body["packageId"] == created["id"]
    assert "packageVersion" not in launch_body
    assert launch_body["workflowKey"] == "advisory_research"
    assert launch_body["ready"] is True
    assert launch_body["blockingErrors"] == []

    versioned_launch = client.get(
        f"/api/workflow-packages/{created['id']}/launch",
        params={"version": 1},
    )
    assert versioned_launch.status_code == 422, versioned_launch.json()

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")
    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert "packageVersion" not in preflight_body
    assert preflight_body["workflowKey"] == "advisory_research"
    assert preflight_body["ready"] is True

    versioned_preflight = client.post(
        f"/api/workflow-packages/{created['id']}/preflight",
        params={"version": 1},
    )
    assert versioned_preflight.status_code == 422, versioned_preflight.json()

    created_launch = client.post(
        f"/api/workflow-packages/{created['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "advisory_research",
            "parameters": {
                "ticker": "AAPL",
                "asOfDate": "2026-05-08",
                "portfolioId": "tradingagents_demo",
                "horizonDays": 30,
                "benchmarkSymbol": "SPY",
            },
        },
    )
    assert created_launch.status_code == 422, created_launch.json()

    deleted = client.delete(f"/api/workflow-packages/{created['id']}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    missing_package = client.get(f"/api/workflow-packages/{created['id']}")
    assert missing_package.status_code == 404, missing_package.json()


def test_launch_blocks_failed_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        last_test_ok=False,
        last_test_message="Connection test failed.",
    )
    created = _create_package(client)

    launch = client.get(f"/api/workflow-packages/{created['id']}/launch")
    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert launch_body["ready"] is False
    launch_errors = cast(list[dict[str, object]], launch_body["blockingErrors"])
    assert len(launch_errors) == 12
    assert launch_errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Connection test failed.",
    }
    assert {error["issue"] for error in launch_errors} == {"Connection test failed."}

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")
    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    assert preflight_body["ready"] is False
    preflight_errors = cast(list[dict[str, object]], preflight_body["blockingErrors"])
    assert len(preflight_errors) == 12
    assert preflight_errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Connection test failed.",
    }
    assert {detail["issue"] for detail in preflight_errors} == {"Connection test failed."}


def test_delete_hard_deletes_never_launched_package(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    deleted = client.delete(f"/api/workflow-packages/{created['id']}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    missing = client.get(f"/api/workflow-packages/{created['id']}")
    assert missing.status_code == 404, missing.json()
