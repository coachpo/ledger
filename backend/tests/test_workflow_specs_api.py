from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.workflow_spec import WorkflowSpec


def _build_workflow_spec(
    *,
    key: str,
    version: int,
    origin: str = "managed",
    status: str,
) -> WorkflowSpec:
    return WorkflowSpec(
        key=key,
        version=version,
        origin=origin,
        status=status,
        name=f"{key}-{version}",
        graph_definition={
            "entryStepKey": "analysis",
            "steps": [{"stepKey": "analysis", "agentSpecKey": "position_analyst"}],
        },
        final_output_contract={
            "kind": "json",
            "schema": {"type": "object"},
            "description": "Structured output",
        },
        mention_policy={
            "version": 1,
            "allowCharacterPersonas": True,
            "allowedBuiltinHandles": ["librarian"],
        },
        execution_mode="structured_output",
        default_tool_ids=["ledger.report_lookup"],
        allowed_capability_bundle_keys=["builtin.librarian_context"],
        connector_ids=["ledger.mcp.market_data"],
        review_mode="conservative",
        approval_policy_overrides=[
            {
                "stepKey": "analysis",
                "capabilityKey": "ledger.mcp.market_data",
                "approvalMode": "required",
            }
        ],
    )


def create_workflow_spec_draft(
    client: TestClient,
    *,
    key: str = "managed_workflow_spec",
    name: str = "Managed Workflow Spec",
    graph_definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v2/workflow-specs",
        json={
            "key": key,
            "name": name,
            "graphDefinition": graph_definition
            or {
                "entryStepKey": "analysis",
                "steps": [{"stepKey": "analysis", "agentSpecKey": "position_analyst"}],
            },
            "finalOutputContract": {
                "kind": "json",
                "schema": {"type": "object"},
                "description": "Structured output",
            },
            "mentionPolicy": {
                "version": 1,
                "allowCharacterPersonas": True,
                "allowedBuiltinHandles": ["librarian"],
            },
            "executionMode": "structured_output",
            "defaultToolIds": ["ledger.report_lookup"],
            "allowedCapabilityBundleKeys": ["builtin.librarian_context"],
            "connectorIds": ["ledger.mcp.market_data"],
            "reviewMode": "conservative",
            "approvalPolicyOverrides": [
                {
                    "stepKey": "analysis",
                    "capabilityKey": "ledger.mcp.market_data",
                    "approvalMode": "required",
                }
            ],
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def test_workflow_spec_create_patch_activate_and_list_read_behavior(client: TestClient) -> None:
    created = create_workflow_spec_draft(client, key="  managed_workflow_spec  ")

    assert created["key"] == "managed_workflow_spec"
    assert created["version"] == 1
    assert created["origin"] == "managed"
    assert created["status"] == "DRAFT"
    assert created["entryAgentKey"] == "position_analyst"

    update_response = client.patch(
        f"/api/v2/workflow-specs/{created['id']}",
        json={
            "name": "Managed Workflow Spec v2",
            "graphDefinition": {
                "entryStepKey": "review",
                "steps": [{"stepKey": "review", "agentSpecKey": "risk_reviewer"}],
            },
            "reviewMode": "none",
            "defaultToolIds": ["ledger.orchestration_catalog_lookup"],
            "allowedCapabilityBundleKeys": ["builtin.explore_context"],
            "connectorIds": ["ledger.mcp.company_filings"],
        },
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()
    assert updated["name"] == "Managed Workflow Spec v2"
    assert updated["entryAgentKey"] == "risk_reviewer"
    assert updated["reviewMode"] == "none"
    assert updated["defaultToolIds"] == ["ledger.orchestration_catalog_lookup"]
    assert updated["allowedCapabilityBundleKeys"] == ["builtin.explore_context"]
    assert updated["connectorIds"] == ["ledger.mcp.company_filings"]

    get_response = client.get(f"/api/v2/workflow-specs/{created['id']}")
    assert get_response.status_code == 200, get_response.json()
    assert get_response.json()["entryAgentKey"] == "risk_reviewer"

    list_response = client.get("/api/v2/workflow-specs", params={"origin": "managed"})
    assert list_response.status_code == 200, list_response.json()
    assert list_response.json()["items"] == [get_response.json()]

    activate_response = client.post(f"/api/v2/workflow-specs/{created['id']}/activate")
    assert activate_response.status_code == 200, activate_response.json()
    assert activate_response.json()["status"] == "ACTIVE"

    active_list_response = client.get(
        "/api/v2/workflow-specs",
        params={"origin": "managed", "status": "ACTIVE"},
    )
    assert active_list_response.status_code == 200, active_list_response.json()
    assert active_list_response.json()["items"] == [activate_response.json()]


def test_workflow_spec_duplicate_draft_is_rejected(client: TestClient) -> None:
    create_workflow_spec_draft(client, key="duplicate_workflow_spec")

    response = client.post(
        "/api/v2/workflow-specs",
        json={
            "key": "duplicate_workflow_spec",
            "name": "Duplicate Workflow Spec",
            "graphDefinition": {
                "entryStepKey": "analysis",
                "steps": [{"stepKey": "analysis", "agentSpecKey": "position_analyst"}],
            },
            "finalOutputContract": {
                "kind": "json",
                "schema": {"type": "object"},
                "description": "Structured output",
            },
            "mentionPolicy": {
                "version": 1,
                "allowCharacterPersonas": True,
                "allowedBuiltinHandles": ["librarian"],
            },
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["code"] == "workflow_spec_duplicate_draft"


def test_workflow_spec_activate_demotes_existing_active_without_duplicate_active_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created = create_workflow_spec_draft(client, key="seeded_internal_backtest_v1")

    response = client.post(f"/api/v2/workflow-specs/{created['id']}/activate")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["version"] == 2

    with session_factory() as session:
        rows = session.scalars(
            select(WorkflowSpec)
            .where(WorkflowSpec.key == "seeded_internal_backtest_v1")
            .order_by(WorkflowSpec.version.asc())
        ).all()

    assert [(row.origin, row.version, row.status) for row in rows] == [
        ("seeded", 1, "DEPRECATED"),
        ("managed", 2, "ACTIVE"),
    ]


def test_workflow_spec_patch_rejects_non_draft_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        spec = _build_workflow_spec(key="immutable_workflow_spec", version=1, status="ACTIVE")
        session.add(spec)
        session.commit()
        spec_id = spec.id

    response = client.patch(
        f"/api/v2/workflow-specs/{spec_id}",
        json={"name": "Should Not Patch"},
    )

    assert response.status_code == 400, response.json()
    assert response.json()["code"] == "workflow_spec_invalid_patch_transition"


def test_workflow_spec_invalid_lifecycle_transitions_are_rejected(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        draft = _build_workflow_spec(key="invalid_workflow_draft", version=1, status="DRAFT")
        active = _build_workflow_spec(key="invalid_workflow_active", version=1, status="ACTIVE")
        session.add_all([draft, active])
        session.commit()
        draft_id = draft.id
        active_id = active.id

    deprecate_response = client.post(f"/api/v2/workflow-specs/{draft_id}/deprecate")
    assert deprecate_response.status_code == 400, deprecate_response.json()
    assert deprecate_response.json()["code"] == "workflow_spec_invalid_deprecate_transition"

    archive_response = client.post(f"/api/v2/workflow-specs/{active_id}/archive")
    assert archive_response.status_code == 400, archive_response.json()
    assert archive_response.json()["code"] == "workflow_spec_invalid_archive_transition"


def test_workflow_spec_deprecate_and_archive_transitions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        spec = _build_workflow_spec(key="retired_workflow_spec", version=1, status="ACTIVE")
        session.add(spec)
        session.commit()
        spec_id = spec.id

    deprecate_response = client.post(f"/api/v2/workflow-specs/{spec_id}/deprecate")
    assert deprecate_response.status_code == 200, deprecate_response.json()
    assert deprecate_response.json()["status"] == "DEPRECATED"

    archive_response = client.post(f"/api/v2/workflow-specs/{spec_id}/archive")
    assert archive_response.status_code == 200, archive_response.json()
    assert archive_response.json()["status"] == "ARCHIVED"
