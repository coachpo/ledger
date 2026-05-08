# pyright: reportExplicitAny=false, reportAny=false, reportPrivateUsage=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnnecessaryCast=false
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.model_connection import ModelConnection
from app.repositories.workflow_package import WorkflowPackageRepository

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _package_source() -> str:
    return _FIXTURE.read_text()


def _create_package(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/workflow-packages", json={"manifestSource": _package_source()})
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _seed_model_connection(
    session_factory: sessionmaker[Session], *, api_key: str | None = "sk-preflight"
) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                status="active",
                name="TradingAgents Primary Model",
                description="Preflight model binding.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.5-mini",
                api_style="responses",
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
            )
        )
        session.commit()


def test_save_warns_but_preflight_blocks_missing_model_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = _create_package(client)

    assert created["warnings"]
    assert created["warnings"][0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Model connection 'tradingagents_primary_model' was not found",
        "severity": "warning",
    }
    with session_factory() as session:
        version = WorkflowPackageRepository(session).get_latest_version(int(created["id"]))
        assert version is not None
        assert version.validation_summary["warnings"] == created["warnings"]

    preflight = client.post(f"/api/workflow-packages/{created['id']}/preflight")

    assert preflight.status_code == 200, preflight.json()
    body = preflight.json()
    assert body["ready"] is False
    assert body["blockingErrors"]
    assert body["blockingErrors"][0] == {
        "field": "spec.agents[0].modelConnection",
        "issue": "Model connection 'tradingagents_primary_model' was not found",
    }


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
                profile["toolKeys"] = ["ledger.unknown.tool"]
        cast(list[dict[str, Any]], compiled_plan["outputSchemas"])[0]["jsonSchema"] = {
            "type": "object",
            "properties": {
                "broken": {"type": "object", "patternProperties": {".*": {"type": "string"}}}
            },
        }
        compiled_plan["mcpServers"] = [
            {
                "key": "research_context",
                "name": "Research Context",
                "transport": "stdio",
                "command": "python",
                "args": ["server.py"],
                "requiredBindings": ["env.RESEARCH_TOKEN"],
            }
        ]
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
        "issue": "Unknown server-declared tool 'ledger.unknown.tool'",
    } in errors
    assert any(
        error["field"] == "spec.outputSchemas[0].jsonSchema.properties.broken.patternProperties"
        and error["issue"] == "patternProperties is not supported"
        for error in errors
    )
    assert {
        "field": "spec.mcpServers.research_context.requiredBindings[0]",
        "issue": "MCP secret binding 'env.RESEARCH_TOKEN' is not configured",
    } in errors
    assert {
        "field": "spec.workflows.advisory_research.graph.steps[0].agents[0].with.ticker",
        "issue": "cycle",
    } in errors


def test_preflight_blocks_archived_or_secretless_model_connection(
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
