from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.model_connection import ModelConnection
from app.models.platform_reference import WorkflowPackageVersionModelConnection
from app.models.workflow_package import WorkflowPackageVersion

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _package_source() -> str:
    return _FIXTURE.read_text()


def _seed_model_connection(session_factory: sessionmaker[Session]) -> None:
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


def test_create_export_import_package_without_secrets(
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
    assert "apiVersion: ledger.workflowPackage/v1" in export.text
    assert "modelConnection: tradingagents_primary_model" in export.text
    for forbidden in (
        "modelConnectionId",
        "outputSchemaId",
        "capabilityId",
        "mcpServerId",
        "secretPayload",
        "apiKey",
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


def test_validate_manifest_reports_diagnostics_without_persisting(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    bad_source = _package_source().replace(
        "ledger.market_data.quote_lookup",
        "ledger.unknown.tool",
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
