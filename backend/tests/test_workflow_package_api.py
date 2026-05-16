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
from app.models.platform_reference import WorkflowPackageVersionModelConnection
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)
_EXPECTED_FINANCE_TOOL_KEYS = {
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
    "signaldeck.reports.write",
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


def _create_package(client: TestClient) -> dict[str, object]:
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
    version: int,
    expected_mcp_headers: dict[str, str] | None = None,
    expected_mcp_query: dict[str, str] | None = None,
) -> dict[str, object]:
    assert body["packageId"] == package_id
    assert body["packageKey"] == package_key
    assert body["version"] == version
    assert "compiledPlan" not in body

    source = cast(str, body["manifestSource"])
    assert source.startswith("apiVersion: signaldeck.workflowPackage/v1")
    if expected_mcp_headers is None:
        expected_mcp_headers = {"Authorization": "Bearer exa-inline-token"}
    if expected_mcp_query is None:
        expected_mcp_query = {"exaApiKey": "exa-inline-key"}
    for value in expected_mcp_headers.values():
        assert value in source
    for value in expected_mcp_query.values():
        assert value in source
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
    assert mcp_servers and mcp_servers[0]["key"] == "exa"
    assert mcp_servers[0]["headers"] == expected_mcp_headers
    assert mcp_servers[0]["query"] == expected_mcp_query
    assert "secretRefs" not in mcp_servers[0]
    assert "requiredBindings" not in mcp_servers[0]

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
        "runtime",
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
    old_description = "description: Neutral advisory workflow fixture for package smoke coverage."
    new_description = (
        "description: Neutral advisory workflow fixture for package smoke coverage after edit."
    )
    assert old_description in source
    return source.replace(old_description, new_description, 1)


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
    assert finance_extension["enabled"] is True
    assert finance_extension["defaultEnabled"] is True

    source = _package_source()
    assert FINANCE_WORKSPACE_EXTENSION_KEY not in source

    created = _create_package(client)
    manifest_response = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert manifest_response.status_code == 200, manifest_response.json()
    manifest_body = cast(dict[str, object], manifest_response.json())
    package_definition = cast(dict[str, object], manifest_body["packageDefinition"])
    assert _profile_tool_keys(package_definition) == _EXPECTED_FINANCE_TOOL_KEYS


def test_manifest_reads_return_hydrated_safe_package_resources(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    assert created["id"]
    assert created["key"] == "tradingagents_advisory_research"
    assert created["status"] == "active"
    assert created["latestVersion"] == 1
    assert isinstance(created["manifestHash"], str)

    latest_manifest = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert latest_manifest.status_code == 200, latest_manifest.json()
    latest_manifest_body = cast(dict[str, object], latest_manifest.json())
    _ = _assert_manifest_payload(
        latest_manifest_body,
        package_id=cast(int, created["id"]),
        package_key="tradingagents_advisory_research",
        version=1,
    )

    explicit_manifest = client.get(
        f"/api/workflow-packages/{created['id']}/manifest",
        params={"version": 1},
    )
    assert explicit_manifest.status_code == 200, explicit_manifest.json()
    explicit_manifest_body = cast(dict[str, object], explicit_manifest.json())
    assert explicit_manifest_body == latest_manifest_body

    detail = client.get(f"/api/workflow-packages/{created['id']}")
    assert detail.status_code == 200, detail.json()
    assert detail.json()["latestVersionId"] == created["latestVersionId"]

    versions = client.get(f"/api/workflow-packages/{created['id']}/versions")
    assert versions.status_code == 200, versions.json()
    version_items = cast(list[dict[str, object]], versions.json()["items"])
    assert [item["version"] for item in version_items] == [1]

    export = client.get(f"/api/workflow-packages/{created['id']}/export", params={"version": 1})
    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("application/yaml")
    assert "apiVersion: signaldeck.workflowPackage/v1" in export.text
    assert "modelConnection: tradingagents_primary_model" in export.text
    assert "headers:" in export.text
    assert "query:" in export.text
    assert "Authorization: Bearer exa-inline-token" in export.text
    assert "exaApiKey: exa-inline-key" in export.text
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

    imported_version = client.post(
        "/api/workflow-packages/import",
        json={"manifestSource": export.text, "mode": "createVersion"},
    )
    assert imported_version.status_code == 201, imported_version.json()
    imported_version_body = cast(dict[str, object], imported_version.json())
    created_latest_version_id = cast(int, created["latestVersionId"])
    imported_latest_version_id = cast(int, imported_version_body["latestVersionId"])
    assert imported_version_body["id"] == created["id"]
    assert imported_version_body["latestVersion"] == 2

    with session_factory() as session:
        refs = (
            session.query(WorkflowPackageVersionModelConnection)
            .order_by(WorkflowPackageVersionModelConnection.workflow_package_version_id.asc())
            .all()
        )
        assert [ref.workflow_package_version_id for ref in refs] == [
            created_latest_version_id,
            imported_latest_version_id,
        ]
        assert [ref.model_connection_key for ref in refs] == [
            "tradingagents_primary_model",
            "tradingagents_primary_model",
        ]

    versions = client.get(f"/api/workflow-packages/{created['id']}/versions")
    assert versions.status_code == 200, versions.json()
    version_items = cast(list[dict[str, object]], versions.json()["items"])
    assert [item["version"] for item in version_items] == [2, 1]


def test_manifest_round_trip_save_creates_immutable_next_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    package_id = cast(int, created["id"])

    version_one = client.get(
        f"/api/workflow-packages/{package_id}/manifest",
        params={"version": 1},
    )
    assert version_one.status_code == 200, version_one.json()
    version_one_body = cast(dict[str, object], version_one.json())
    _ = _assert_manifest_payload(
        version_one_body,
        package_id=package_id,
        package_key="tradingagents_advisory_research",
        version=1,
    )
    version_one_definition = cast(dict[str, object], version_one_body["packageDefinition"])
    assert _workflow_description(version_one_definition, "advisory_research") == (
        "Neutral advisory workflow fixture for package smoke coverage."
    )

    edited_source = _edited_workflow_manifest_source(cast(str, version_one_body["manifestSource"]))
    saved = client.patch(
        f"/api/workflow-packages/{package_id}",
        json={"manifestSource": edited_source},
    )
    assert saved.status_code == 200, saved.json()
    saved_body = cast(dict[str, object], saved.json())
    assert saved_body["id"] == package_id
    assert saved_body["latestVersion"] == 2
    assert saved_body["latestVersionId"] != created["latestVersionId"]

    latest = client.get(f"/api/workflow-packages/{package_id}/manifest")
    assert latest.status_code == 200, latest.json()
    version_two_body = cast(dict[str, object], latest.json())
    _ = _assert_manifest_payload(
        version_two_body,
        package_id=package_id,
        package_key="tradingagents_advisory_research",
        version=2,
    )
    assert saved_body["manifestHash"] == version_two_body["manifestHash"]
    assert saved_body["compiledHash"] == version_two_body["compiledHash"]
    assert version_two_body["manifestHash"] != version_one_body["manifestHash"]
    assert version_two_body["compiledHash"] != version_one_body["compiledHash"]
    version_two_definition = cast(dict[str, object], version_two_body["packageDefinition"])
    assert _workflow_description(version_two_definition, "advisory_research") == (
        "Neutral advisory workflow fixture for package smoke coverage after edit."
    )

    historical = client.get(
        f"/api/workflow-packages/{package_id}/manifest",
        params={"version": 1},
    )
    assert historical.status_code == 200, historical.json()
    historical_body = cast(dict[str, object], historical.json())
    _ = _assert_manifest_payload(
        historical_body,
        package_id=package_id,
        package_key="tradingagents_advisory_research",
        version=1,
    )
    assert _manifest_semantics(historical_body) == _manifest_semantics(version_one_body)
    assert _manifest_semantics(historical_body) != _manifest_semantics(version_two_body)
    historical_definition = cast(dict[str, object], historical_body["packageDefinition"])
    assert _workflow_description(historical_definition, "advisory_research") == (
        "Neutral advisory workflow fixture for package smoke coverage."
    )

    versions = client.get(f"/api/workflow-packages/{package_id}/versions")
    assert versions.status_code == 200, versions.json()
    version_items = cast(list[dict[str, object]], versions.json()["items"])
    assert [item["version"] for item in version_items] == [2, 1]


def test_manifest_reads_recursively_sanitize_polluted_stored_jsonb(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    with session_factory() as session:
        package = session.get(WorkflowPackage, cast(int, created["id"]))
        assert package is not None
        original_version = session.get(
            WorkflowPackageVersion,
            cast(int, created["latestVersionId"]),
        )
        assert original_version is not None
        polluted_definition = deepcopy(cast(dict[str, Any], original_version.package_definition))
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
        mcp_server = cast(list[dict[str, Any]], spec["mcpServers"])[0]
        mcp_server.update(
            {
                "id": 404,
                "mcpServerId": 505,
                "secretPayload": {"apiKey": "sk-polluted-mcp-secret"},
                "headers": {
                    "Authorization": "Bearer live-header",
                    "X-Api-Key": "live-api-key",
                },
                "query": {"exaApiKey": "live-query-key"},
                "encrypted": {"ciphertext": "encrypted-bytes"},
            }
        )
        polluted_version = WorkflowPackageVersion(
            package_id=package.id,
            version=2,
            manifest_source=original_version.manifest_source,
            manifest_hash=original_version.manifest_hash,
            package_definition=polluted_definition,
            compiled_plan=deepcopy(cast(dict[str, Any], original_version.compiled_plan)),
            compiled_hash=original_version.compiled_hash,
            validation_summary=deepcopy(original_version.validation_summary),
        )
        polluted_version.compiled_plan["runtime"] = {"debug": True}
        session.add(polluted_version)
        session.flush()
        package.latest_version_id = polluted_version.id
        session.commit()

    latest_manifest = client.get(f"/api/workflow-packages/{created['id']}/manifest")
    assert latest_manifest.status_code == 200, latest_manifest.json()
    latest_manifest_body = cast(dict[str, object], latest_manifest.json())
    _ = _assert_manifest_payload(
        latest_manifest_body,
        package_id=cast(int, created["id"]),
        package_key="tradingagents_advisory_research",
        version=2,
        expected_mcp_headers={
            "Authorization": "Bearer live-header",
            "X-Api-Key": "live-api-key",
        },
        expected_mcp_query={"exaApiKey": "live-query-key"},
    )
    latest_spec = cast(
        dict[str, Any],
        cast(dict[str, Any], latest_manifest_body["packageDefinition"])["spec"],
    )
    latest_mcp = cast(list[dict[str, Any]], latest_spec["mcpServers"])[0]
    assert latest_mcp["headers"] == {
        "Authorization": "Bearer live-header",
        "X-Api-Key": "live-api-key",
    }
    assert latest_mcp["query"] == {"exaApiKey": "live-query-key"}
    assert "secretRefs" not in latest_mcp
    assert "requiredBindings" not in latest_mcp

    explicit_manifest = client.get(
        f"/api/workflow-packages/{created['id']}/manifest",
        params={"version": 1},
    )
    assert explicit_manifest.status_code == 200, explicit_manifest.json()
    explicit_manifest_body = cast(dict[str, object], explicit_manifest.json())
    _ = _assert_manifest_payload(
        explicit_manifest_body,
        package_id=cast(int, created["id"]),
        package_key="tradingagents_advisory_research",
        version=1,
    )
    assert explicit_manifest_body["version"] == 1


def test_validate_manifest_reports_diagnostics_without_persisting(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    bad_source = _package_source().replace(
        "signaldeck.market_data.quote_lookup",
        "signaldeck.unknown.tool",
        1,
    )

    response = client.post(
        "/api/workflow-packages/validate-manifest",
        json={"manifestSource": bad_source},
    )

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["metadata"] is None
    diagnostics = cast(list[dict[str, object]], body["diagnostics"])
    assert diagnostics[0]["path"] == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
    with session_factory() as session:
        assert session.query(WorkflowPackageVersion).count() == 0


def test_launch_metadata_and_stub_creation(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    launch = client.get(f"/api/workflow-packages/{created['id']}/launch")
    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())
    assert launch_body["packageId"] == created["id"]
    assert launch_body["packageVersion"] == 1
    assert launch_body["workflowKey"] == "advisory_research"
    assert launch_body["ready"] is True
    assert launch_body["blockingErrors"] == []

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
                "initialInvestmentDebateState": {},
                "initialRiskDebateState": {},
            },
        },
    )
    assert created_launch.status_code == 201, created_launch.json()
    assert created_launch.json()["status"] == "queued"
    assert created_launch.json()["workflowPackageId"] == created["id"]
    assert created_launch.json()["workflowKey"] == "advisory_research"

    versions = client.get(f"/api/workflow-packages/{created['id']}/versions")
    assert versions.status_code == 200, versions.json()
    assert versions.json()["items"][0]["launchedAt"] is not None

    latest_version_id = cast(int, created["latestVersionId"])
    deleted = client.delete(f"/api/workflow-packages/{created['id']}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    missing_package = client.get(f"/api/workflow-packages/{created['id']}")
    assert missing_package.status_code == 404, missing_package.json()
    missing_run = client.get(f"/api/runs/{created_launch.json()['id']}")
    assert missing_run.status_code == 404, missing_run.json()
    with session_factory() as session:
        assert session.get(WorkflowPackageVersion, latest_version_id) is None
        assert (
            session.query(WorkflowPackageVersionModelConnection)
            .filter_by(workflow_package_version_id=latest_version_id)
            .count()
        ) == 0


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
                "initialInvestmentDebateState": {},
                "initialRiskDebateState": {},
            },
        },
    )
    assert created_launch.status_code == 422, created_launch.json()
    created_launch_body = cast(dict[str, object], created_launch.json())
    assert created_launch_body["code"] == "validation_error"
    assert created_launch_body["message"] == "Workflow package launch validation failed"
    launch_details = cast(list[dict[str, object]], created_launch_body["details"])
    assert len(launch_details) == 12
    assert launch_details[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Connection test failed.",
    }
    assert {detail["issue"] for detail in launch_details} == {"Connection test failed."}


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
