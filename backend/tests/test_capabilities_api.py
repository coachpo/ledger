from __future__ import annotations

from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.agent import Agent
from app.models.capability import Capability
from app.models.model_connection import ModelConnection
from app.models.output_schema import OutputSchema
from app.services.model_connection_snapshot import build_model_connection_runtime_snapshot
from tests.test_agent_manifest_compiler import (
    _seed_manifest_refs,  # pyright: ignore[reportPrivateUsage]
)

TRADINGAGENTS_TOOL_KEYS = (
    "ledger.market_data.ohlcv_lookup",
    "ledger.indicators.lookup",
    "ledger.fundamentals.lookup",
    "ledger.news.lookup",
    "ledger.insider_data.lookup",
)


def _create_capability(client: TestClient, payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/capabilities", json=payload)
    assert response.status_code == 201, response.json()
    return cast(dict[str, object], response.json())


def test_capability_create_and_read_accepts_tradingagents_tool_grants(
    client: TestClient,
) -> None:
    created = _create_capability(
        client,
        {
            "key": "tradingagents_market_data",
            "name": "TradingAgents Market Data",
            "description": "TradingAgents native market-data tools.",
            "toolGrants": [{"tool": tool_key} for tool_key in TRADINGAGENTS_TOOL_KEYS],
        },
    )

    assert "toolGrants" in created
    assert "toolDefinitions" not in created
    created_grants = cast(list[dict[str, object]], created["toolGrants"])
    assert [item["tool"] for item in created_grants] == list(TRADINGAGENTS_TOOL_KEYS)

    read_response = client.get(f"/api/capabilities/{created['id']}")
    assert read_response.status_code == 200, read_response.json()
    read_body = cast(dict[str, object], read_response.json())
    assert "toolGrants" in read_body
    assert "toolDefinitions" not in read_body
    read_grants = cast(list[dict[str, object]], read_body["toolGrants"])
    assert [item["tool"] for item in read_grants] == list(TRADINGAGENTS_TOOL_KEYS)


def test_capability_create_rejects_unknown_tool_grant_without_persisting_draft(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/capabilities",
        json={
            "key": "unknown_trading_tool",
            "name": "Unknown Trading Tool",
            "description": "Unknown tools must still fail catalog validation.",
            "toolGrants": [{"tool": "ledger.stock_analysis.report_lookup"}],
        },
    )

    assert response.status_code == 422
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    assert body["code"] == "validation_error"
    assert any(
        detail["field"] == "toolGrants.0.tool"
        and "Unknown server-declared tool 'ledger.stock_analysis.report_lookup'"
        in str(detail["issue"])
        for detail in details
    )
    with session_factory() as session:
        persisted_count = (
            session.query(Capability).filter(Capability.key == "unknown_trading_tool").count()
        )
        assert persisted_count == 0


def test_capability_crud_uses_tool_grants(
    client: TestClient,
) -> None:
    created = _create_capability(
        client,
        {
            "key": "market_research",
            "name": "Market Research",
            "description": "Server-owned research tools.",
            "toolGrants": [
                {"tool": "ledger.positions.lookup"},
                {"tool": "ledger.reports.lookup"},
            ],
        },
    )

    assert created["status"] == "draft"
    assert "toolGrants" in created
    assert "toolDefinitions" not in created
    created_grants = cast(list[dict[str, object]], created["toolGrants"])
    assert [item["tool"] for item in created_grants] == [
        "ledger.positions.lookup",
        "ledger.reports.lookup",
    ]

    update_response = client.patch(
        f"/api/capabilities/{created['id']}",
        json={"name": "Market Research v2", "toolGrants": [{"tool": "ledger.reports.lookup"}]},
    )
    assert update_response.status_code == 200, update_response.json()
    updated = cast(dict[str, object], update_response.json())
    updated_grants = cast(list[dict[str, object]], updated["toolGrants"])
    assert updated["id"] != created["id"]
    assert updated["version"] == 2
    assert updated_grants[0]["tool"] == "ledger.reports.lookup"
    assert "toolDefinitions" not in updated

    archived_original = client.get(f"/api/capabilities/{created['id']}")
    assert archived_original.status_code == 200, archived_original.json()
    assert archived_original.json()["status"] == "archived"

    activated = client.post(f"/api/capabilities/{updated['id']}/activate")
    assert activated.status_code == 200, activated.json()
    assert activated.json()["status"] == "published"

    list_response = client.get("/api/capabilities", params={"status": "published"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [activated.json()]

    archive_response = client.delete(f"/api/capabilities/{updated['id']}")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "archived"


def test_legacy_skill_routes_return_404_and_openapi_omits_them(
    client: TestClient,
) -> None:
    assert client.get("/api/skills").status_code == 404
    assert client.post("/api/skills", json={}).status_code == 404
    assert client.get("/api/skills/1").status_code == 404
    assert client.post("/api/skills/1/activate").status_code == 404

    paths = cast(dict[str, object], client.get("/openapi.json").json()["paths"])
    assert "/api/capabilities" in paths
    assert all(not path.startswith("/api/skills") for path in paths)


def test_capability_request_rejects_tool_definitions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/capabilities",
        json={
            "key": "conflicting_tools",
            "name": "Conflicting Tools",
            "toolDefinitions": [{"tool": "ledger.positions.lookup"}],
        },
    )

    assert response.status_code == 422
    body = cast(dict[str, object], response.json())
    details = cast(list[dict[str, object]], body["details"])
    assert body["code"] == "validation_error"
    assert any(str(detail["field"]).endswith("toolDefinitions") for detail in details)
    with session_factory() as session:
        assert session.query(Capability).filter(Capability.key == "conflicting_tools").count() == 0


def test_capability_patch_rejects_tool_definitions_without_archiving_existing_draft(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = _create_capability(
        client,
        {
            "key": "patch_conflict_tools",
            "name": "Patch Conflict Tools",
            "toolGrants": [{"tool": "ledger.reports.lookup"}],
        },
    )

    response = client.patch(
        f"/api/capabilities/{created['id']}",
        json={
            "toolDefinitions": [{"tool": "ledger.positions.lookup"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    with session_factory() as session:
        rows = session.query(Capability).filter(Capability.key == "patch_conflict_tools").all()
        assert len(rows) == 1
        assert rows[0].status == "draft"


def test_persisted_capability_refs_resolve_as_agent_capabilities(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        refs = _seed_manifest_refs(session)
        connection = cast(ModelConnection, refs["connection"])
        output_schema = cast(OutputSchema, refs["output_schema"])
        capability = cast(Capability, refs["capability"])
        agent = Agent(
            key="capability_ref_agent",
            version=1,
            status="published",
            name="Capability Ref Agent",
            description="Reads persisted capability refs.",
            model_connection_id=connection.id,
            model_connection_snapshot=build_model_connection_runtime_snapshot(connection),
            model=connection.model_id,
            system_prompt="Summarize the request.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema_id=output_schema.id,
            output_schema_version=output_schema.version,
            capabilities=[
                {
                    "capabilityId": capability.id,
                    "capabilityKey": capability.key,
                    "capabilityVersion": capability.version,
                }
            ],
            mcp_servers=[],
            budget_usd=Decimal("0"),
        )
        session.add(agent)
        session.commit()
        agent_id = agent.id

    response = client.get(f"/api/agents/{agent_id}")

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    capabilities = cast(list[dict[str, object]], body["capabilities"])
    assert capabilities[0]["key"] == "sec_filing_lookup"
    assert capabilities[0]["toolGrants"] == [
        {
            "tool": "ledger.reports.lookup",
            "displayName": "Report Lookup",
            "description": "Read persisted Ledger reports through server-owned report lookups.",
        }
    ]
    assert "toolDefinitions" not in capabilities[0]
    assert "skills" not in body
