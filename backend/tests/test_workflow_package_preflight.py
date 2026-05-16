# pyright: reportExplicitAny=false, reportAny=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnnecessaryCast=false
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.formatting import utcnow
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.model_connection import ModelConnection
from app.models.workflow_package import WorkflowPackageVersion
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.extension import ExtensionToggleRequest
from app.services.extension_service import ExtensionService
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_preflight import WorkflowPackagePreflightService
from tests.test_workflow_package_manifest_http_node import http_node_package_source

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _package_source() -> str:
    return _FIXTURE.read_text()


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


def _create_package(client: TestClient) -> dict[str, Any]:
    _delete_existing_tradingagents_package(client)
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session],
    *,
    api_key: str | None = "sk-preflight",
    connection_kind: str = "provider",
    last_test_ok: bool | None = None,
    last_test_message: str | None = None,
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                connection_kind=connection_kind,
                name="TradingAgents Primary Model",
                description="Preflight model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_tested_at=(
                    utcnow() if last_test_ok is not None or last_test_message is not None else None
                ),
                last_test_ok=last_test_ok,
                last_test_message=last_test_message,
            )
        )
        session.commit()


def test_preflight_accepts_fixture_report_lookup_and_write_tool_keys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_package_source())
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    profiles_by_key = {str(profile["key"]): profile for profile in profiles}

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

    assert errors == []
    assert cast(list[str], profiles_by_key["memory_write_tools"]["toolKeys"]) == [
        "signaldeck.reports.lookup",
        "signaldeck.reports.write",
    ]
    assert cast(list[dict[str, Any]], compiled_plan["mcpServers"]) == []
    assert "fanout" not in _package_source()
    assert "kind: sequence" in _package_source()


def test_preflight_rejects_duplicate_and_phase_one_memory_tool_keys(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
    for profile in profiles:
        if profile["key"] == "memory_write_tools":
            profile["toolKeys"] = [
                "signaldeck.reports.write",
                "signaldeck.reports.write",
                "signaldeck.memory.write",
            ]

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._tool_errors(compiled_plan)

    assert {
        "field": "spec.capabilityProfiles.memory_write_tools.toolKeys[1]",
        "issue": "Duplicate tool key 'signaldeck.reports.write' is not allowed",
    } in errors
    assert {
        "field": "spec.capabilityProfiles.memory_write_tools.toolKeys[2]",
        "issue": "Unknown server-declared tool 'signaldeck.memory.write'",
    } in errors


def test_create_blocks_missing_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _delete_existing_tradingagents_package(client)
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 422, response.json()
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Workflow package manifest validation failed"
    details = cast(list[dict[str, object]], body["details"])
    expected_count = _package_source().count("modelConnection: tradingagents_primary_model")
    assert len(details) == expected_count
    assert [detail["field"] for detail in details] == [
        f"spec.agents[{index}].modelConnection" for index in range(expected_count)
    ]
    assert {detail["issue"] for detail in details} == {
        "Model connection 'tradingagents_primary_model' was not found"
    }
    with session_factory() as session:
        assert session.query(WorkflowPackageVersion).count() == 0


def test_preflight_reports_binding_schema_tool_and_graph_failures(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)

    with session_factory() as session:
        repository = WorkflowPackageRepository(session)
        version = repository.get_latest_version(int(created["id"]))
        assert version is not None
        compiled_plan = deepcopy(cast(dict[str, Any], version.compiled_plan))
        package_definition = deepcopy(cast(dict[str, Any], version.package_definition))
        profiles = cast(list[dict[str, Any]], compiled_plan["capabilityProfiles"])
        for profile in profiles:
            if profile["key"] == "market_research_tools":
                profile["toolKeys"] = ["signaldeck.unknown.tool"]
        cast(list[dict[str, Any]], compiled_plan["outputSchemas"])[0]["jsonSchema"] = {
            "type": "object",
            "properties": {
                "broken": {"type": "object", "patternProperties": {".*": {"type": "string"}}}
            },
        }
        cast(list[dict[str, Any]], compiled_plan["mcpServers"]).append(
            {
                "key": "research_context",
                "name": "Research Context",
                "transport": "http-sse",
                "url": "https://mcp.example.test/sse?tools=web_search_exa",
                "headers": {"Authorization": "Bearer inline-token"},
                "query": {"exaApiKey": "inline-key"},
                "toolKeys": ["web_search_exa"],
            }
        )
        workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
        cast(list[dict[str, Any]], workflow["steps"])[0]["agents"][0]["wiring"] = {
            "ticker": {"from": "step", "stepIndex": 1, "slot": "market_report"}
        }
        version.compiled_plan = compiled_plan
        version.package_definition = package_definition
        session.commit()

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.capabilityProfiles.market_research_tools.toolKeys[0]",
        "issue": "Unknown server-declared tool 'signaldeck.unknown.tool'",
    } in errors
    assert any(
        error["field"] == "spec.outputSchemas[0].jsonSchema.properties.broken.patternProperties"
        and error["issue"] == "patternProperties is not supported"
        for error in errors
    )
    assert not any(
        str(error["field"]).startswith("spec.mcpServers.research_context") for error in errors
    )
    assert {
        "field": "spec.workflows.advisory_research.graph.steps[0].agents[0].with.ticker",
        "issue": "cycle",
    } in errors


def test_preflight_blocks_secretless_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory, api_key=None)
    created = _create_package(client)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    assert preflight.json()["ready"] is False
    errors = preflight.json()["blockingErrors"]
    assert errors
    assert errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "API key is not configured",
    }


def test_preflight_blocks_failed_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        last_test_ok=False,
        last_test_message="Connection test failed.",
    )
    created = _create_package(client)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    assert preflight.json()["ready"] is False
    errors = preflight.json()["blockingErrors"]
    assert errors
    assert errors[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Connection test failed.",
    }


def test_preflight_warns_on_deterministic_smoke_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(
        session_factory,
        api_key=None,
        connection_kind="deterministic_smoke",
        last_test_ok=False,
        last_test_message="Connection test failed.",
    )
    created = _create_package(client)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []
    warnings = cast(list[dict[str, object]], body["warnings"])
    assert len(warnings) == 12
    assert warnings[0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Deterministic smoke connection will run offline",
        "severity": "warning",
        "connectionKind": "deterministic_smoke",
    }


def _create_http_package(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": http_node_package_source()},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def test_preflight_blocks_missing_secret_binding_for_http_node(
    client: TestClient,
) -> None:
    created = _create_http_package(client)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'body_token' is not configured",
    } in errors
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request",
        "issue": "HTTP secret binding 'slack_webhook_token' is not configured",
    } in errors


def test_preflight_accepts_configured_secret_bindings_for_http_node(
    client: TestClient,
) -> None:
    created = _create_http_package(client)
    for key in ("body_token", "slack_webhook_token"):
        response = client.put(
            f"/api/workflow-packages/{created['id']}/secret-bindings/{key}",
            json={"value": f"{key}-secret"},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "packageId": created["id"],
            "key": key,
            "hasValue": True,
            "createdAt": response.json()["createdAt"],
            "updatedAt": response.json()["updatedAt"],
        }

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is True
    assert body["blockingErrors"] == []


def test_preflight_reports_unsupported_http_method_and_malformed_step_ref(
    session_factory: sessionmaker[Session],
) -> None:
    compiled = compile_workflow_package_manifest(http_node_package_source())
    compiled_plan = deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))
    workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
    operation = cast(list[dict[str, Any]], workflow["steps"])[0]["operations"][0]
    operation["method"] = "PATCH"
    cast(dict[str, Any], operation["request"])["body"] = {"from": "step", "stepIndex": 1}
    package_version = WorkflowPackageVersion(
        package_id=987,
        version=1,
        manifest_source=http_node_package_source(),
        manifest_hash="a" * 64,
        package_definition=cast(dict[str, Any], compiled["packageDefinition"]),
        compiled_plan=compiled_plan,
        compiled_hash="b" * 64,
        validation_summary={"diagnostics": []},
    )

    with session_factory() as session:
        errors = WorkflowPackagePreflightService(session)._http_errors(
            package_version,
            compiled_plan,
        )

    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].method",
        "issue": "Unsupported HTTP method 'PATCH'; allowed methods: GET, POST",
    } in errors
    assert {
        "field": "spec.workflows.notify.graph.steps[0].operations[0].request.body",
        "issue": "HTTP node step reference is malformed",
    } in errors


def _disable_finance_extension(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _ = ExtensionService(session).set_extension_enabled(
            FINANCE_WORKSPACE_EXTENSION_KEY,
            ExtensionToggleRequest(enabled=False),
        )


def test_create_blocks_tradingagents_advisory_research_when_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    _disable_finance_extension(session_factory)
    _delete_existing_tradingagents_package(client)

    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})

    assert response.status_code == 422, response.json()
    body = response.json()
    assert body["code"] == "validation_error"
    details = cast(list[dict[str, object]], body["details"])
    assert any(
        "extension 'signaldeck.finance' is disabled" in str(detail.get("issue"))
        and str(detail.get("path", "")).startswith("spec.capabilityProfiles.")
        for detail in details
    )


def test_preflight_blocks_tradingagents_advisory_research_when_extension_disabled(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed_model_connection(session_factory)
    created = _create_package(client)
    _disable_finance_extension(session_factory)

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    errors = cast(list[dict[str, object]], body["blockingErrors"])
    assert any(
        error.get("code") == "extension_disabled"
        and error.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and error.get("surface") == "tool.signaldeck.market_data.quote_lookup"
        for error in errors
    )
