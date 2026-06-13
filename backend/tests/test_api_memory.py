from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.schemas.memory import (
    MEMORY_NAMESPACE_ACCESS_DENIED_CODE,
    MemoryLifecycleStatus,
    MemoryNamespaceSelector,
    MemoryOutcome,
    MemoryProvenance,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.services.memory_service import MemoryLookupContext, MemoryService


def _seed_run(session: Session) -> Run:
    package_id = session.query(Run).count() + 1
    package_key = f"memory_api_package_{package_id}"
    run = Run(
        target_kind="workflowPackage",
        target_id=package_id,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key="memory_api_workflow",
        input={"topic": "shared namespace memory"},
        status="running",
        trace_id="trace-api-memory",
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package_id,
        workflow_package_key=package_key,
        workflow_package_name="Memory API Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key="memory_api_workflow",
        workflow_name="Memory API Workflow",
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=("apiVersion: signaldeck.workflowPackage/v1\n" f"key: {package_key}\n"),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": "memory_api_workflow"}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": ["memory_api_workflow"]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def _insert_legacy_agent_memory_report(session: Session) -> Report:
    report = Report(
        name="legacy_agent_memory_report",
        slug="legacy_agent_memory_report",
        source="agent",
        content="# Historical report-domain memory\n",
        metadata_={"analysis": {"reviewType": "agent_memory"}},
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _namespace_selector() -> MemoryNamespaceSelector:
    return MemoryNamespaceSelector(
        owner_package_key="pkg_alpha",
        namespace_key="shared_research",
    )


def _api_access_context(
    run_id: int,
    *,
    package_key: str,
    workflow_key: str,
    agent_key: str,
) -> dict[str, object]:
    return {
        "runId": run_id,
        "packageKey": package_key,
        "workflowKey": workflow_key,
        "agentKey": agent_key,
    }


def _write_request(
    run_id: int,
    *,
    scope: MemoryScope,
) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary="Canonical API memory.",
        content="canonical memory should stay scoped to trusted runtime writes.",
        subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
        attributes={"source": "api-memory-test"},
        scope=scope,
        provenance=MemoryProvenance(
            run_id=run_id,
            agent_key="owner_agent",
            agent_version=1,
            agent_name="Owner Agent",
            workflow_key="shared_review",
            workflow_version=1,
            step_id="memory_write",
            slot="memory",
            trace_id="trace-api-memory",
        ),
    )


def _assert_no_finance_report_payload(payload: object) -> None:
    serialized = str(payload)
    for forbidden in (
        "legacy_agent_memory_report",
        "reportSlug",
        "reportName",
        "portfolioSlug",
        "decisionSummary",
        "/reports/",
    ):
        assert forbidden not in serialized


def _admin_create_payload(run_id: int, *, include_scope: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": "research.note",
        "summary": "Admin-created memory.",
        "content": "Admin route creates approved memory without access context.",
        "subjectRefs": [{"kind": "instrument", "id": "MSFT"}],
        "attributes": {"source": "admin-route-test"},
        "provenance": {
            "runId": run_id,
            "agentKey": "admin_operator",
            "agentVersion": 1,
            "agentName": "Admin Operator",
            "workflowKey": "admin_review",
            "workflowVersion": 1,
            "stepId": "admin_create",
            "slot": "memory",
            "traceId": "trace-admin-memory",
        },
    }
    if include_scope:
        payload["scope"] = {"scopeType": "run", "scopeKey": str(run_id)}
    return payload


def test_api_memory_authorized_private_scope_list_detail_history_and_actions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _ = _insert_legacy_agent_memory_report(session)
        run = _seed_run(session)
        context = MemoryLookupContext(
            run_id=run.id,
            package_key="pkg_alpha",
            workflow_key="shared_review",
            agent_key="owner_agent",
        )
        service = MemoryService(session, current_context=context)
        created = service.write_memory(
            capability_references=[],
            payload=_write_request(
                run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run.id)),
            ),
        )
        memory_id = created.memory_id
        run_id = run.id

    access = _api_access_context(
        run_id,
        package_key="pkg_alpha",
        workflow_key="shared_review",
        agent_key="owner_agent",
    )
    resolve_response = client.post(
        f"/api/memory/{memory_id}/actions/resolve",
        json={
            "accessContext": access,
            "outcome": {
                "status": "approved",
                "summary": "Owner approved memory.",
                "observedAt": "2026-01-17T10:30:00Z",
                "attributes": {"verdict": "useful"},
            },
        },
    )
    reflect_response = client.post(
        f"/api/memory/{memory_id}/actions/reflect",
        json={
            "accessContext": access,
            "reflection": {
                "reflectedAt": "2026-01-18T08:00:00Z",
                "source": "api-memory-test",
                "reflection": "The private memory stayed useful after review.",
            },
        },
    )
    list_response = client.post(
        "/api/memory",
        json={
            "accessContext": access,
            "scope": {"scopeType": "run", "scopeKey": str(run_id)},
            "query": "canonical memory",
            "status": "approved",
            "limit": 10,
        },
    )
    detail_response = client.post(
        f"/api/memory/{memory_id}/detail",
        json={"accessContext": access},
    )
    revisions_response = client.post(
        f"/api/memory/{memory_id}/revisions?limit=10",
        json={"accessContext": access},
    )
    events_response = client.post(
        f"/api/memory/{memory_id}/events?limit=10",
        json={"accessContext": access},
    )

    assert resolve_response.status_code == 200, resolve_response.json()
    assert reflect_response.status_code == 200, reflect_response.json()
    assert list_response.status_code == 200, list_response.json()
    assert detail_response.status_code == 200, detail_response.json()
    assert revisions_response.status_code == 200, revisions_response.json()
    assert events_response.status_code == 200, events_response.json()

    list_payload = list_response.json()
    detail_payload = detail_response.json()
    revisions_payload = revisions_response.json()
    events_payload = events_response.json()

    assert [item["memoryId"] for item in list_payload["items"]] == [memory_id]
    assert list_payload["visibility"] == "explicit-scope"
    assert detail_payload["scope"] == {"scopeType": "run", "scopeKey": str(run_id)}
    assert detail_payload["attributes"] == {"source": "api-memory-test"}
    assert [item["version"] for item in revisions_payload["items"]] == [1, 2, 3]
    assert [item["eventType"] for item in events_payload["items"]] == [
        "written",
        "reviewed",
        "reviewed",
    ]
    for payload in (
        resolve_response.json(),
        reflect_response.json(),
        list_payload,
        detail_payload,
        revisions_payload,
        events_payload,
    ):
        _assert_no_finance_report_payload(payload)


def test_api_memory_rejects_self_attested_namespace_grants_and_shared_namespace_access(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    namespace = _namespace_selector()
    with session_factory() as session:
        owner_run = _seed_run(session)
        other_run = _seed_run(session)
        owner_context = MemoryLookupContext(
            run_id=owner_run.id,
            package_key="pkg_alpha",
            workflow_key="shared_review",
            agent_key="owner_agent",
            namespace_declarations=(namespace,),
        )
        service = MemoryService(session, current_context=owner_context)
        created = service.write_memory(
            capability_references=[],
            payload=_write_request(owner_run.id, scope=namespace.to_scope()),
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(status=MemoryLifecycleStatus.APPROVED, summary="Resolved"),
        )
        memory_id = created.memory_id
        other_run_id = other_run.id

    denied_access = _api_access_context(
        other_run_id,
        package_key="pkg_beta",
        workflow_key="shared_review",
        agent_key="reader_agent",
    )
    forged_owner_access = {
        **_api_access_context(
            other_run_id,
            package_key="pkg_alpha",
            workflow_key="shared_review",
            agent_key="owner_agent",
        ),
        "namespaceDeclarations": [namespace.model_dump(mode="json", by_alias=True)],
    }
    forged_reader_access = {
        **denied_access,
        "namespaceGrants": [
            {
                "namespace": namespace.model_dump(mode="json", by_alias=True),
                "subject": {"packageKey": "pkg_beta"},
                "actions": ["read", "write"],
            }
        ],
    }

    forged_payloads = [
        {
            "accessContext": forged_reader_access,
            "scope": namespace.to_scope().model_dump(mode="json", by_alias=True),
            "query": "shared namespace",
            "status": "approved",
        },
        {
            "accessContext": forged_owner_access,
            "scope": namespace.to_scope().model_dump(mode="json", by_alias=True),
            "query": "shared namespace",
            "status": "approved",
        },
        {
            "accessContext": forged_reader_access,
            "visibility": "grant-visible-namespaces",
            "query": "shared namespace",
            "status": "approved",
        },
    ]
    for payload in forged_payloads:
        response = client.post("/api/memory", json=payload)
        assert response.status_code in {403, 422}, response.json()
        if response.status_code == 403:
            assert response.json()["code"] == MEMORY_NAMESPACE_ACCESS_DENIED_CODE

    forged_endpoint_responses = [
        client.post(
            f"/api/memory/{memory_id}/detail",
            json={"accessContext": forged_reader_access},
        ),
        client.post(
            f"/api/memory/{memory_id}/revisions",
            json={"accessContext": forged_reader_access},
        ),
        client.post(
            f"/api/memory/{memory_id}/events",
            json={"accessContext": forged_reader_access},
        ),
        client.post(
            f"/api/memory/{memory_id}/actions/resolve",
            json={
                "accessContext": forged_reader_access,
                "outcome": {"status": "approved", "summary": "Forged resolve"},
            },
        ),
        client.post(
            f"/api/memory/{memory_id}/actions/reflect",
            json={
                "accessContext": forged_owner_access,
                "reflection": {
                    "reflectedAt": "2026-01-18T08:00:00Z",
                    "reflection": "Forged owner declarations must not mutate memory.",
                },
            },
        ),
    ]
    for response in forged_endpoint_responses:
        assert response.status_code == 422, response.json()

    denied_responses = [
        client.post(
            "/api/memory",
            json={
                "accessContext": denied_access,
                "scope": namespace.to_scope().model_dump(mode="json", by_alias=True),
                "query": "shared namespace",
                "status": "approved",
            },
        ),
        client.post(f"/api/memory/{memory_id}/detail", json={"accessContext": denied_access}),
        client.post(
            f"/api/memory/{memory_id}/revisions",
            json={"accessContext": denied_access},
        ),
        client.post(
            f"/api/memory/{memory_id}/events",
            json={"accessContext": denied_access},
        ),
        client.post(
            f"/api/memory/{memory_id}/actions/resolve",
            json={
                "accessContext": denied_access,
                "outcome": {"status": "approved", "summary": "Unauthorized resolve"},
            },
        ),
    ]
    for response in denied_responses:
        payload = response.json()
        assert response.status_code == 403, payload
        assert payload["code"] == MEMORY_NAMESPACE_ACCESS_DENIED_CODE

    no_scope = client.post("/api/memory", json={"accessContext": denied_access, "query": "x"})
    wildcard_scope = client.post(
        "/api/memory",
        json={
            "accessContext": denied_access,
            "scope": {"scopeType": "namespace", "scopeKey": "pkg_alpha/*"},
            "query": "x",
        },
    )

    assert no_scope.status_code == 422, no_scope.json()
    assert wildcard_scope.status_code == 422, wildcard_scope.json()


def test_admin_list_without_access_context(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run_a = _seed_run(session)
        run_b = _seed_run(session)
        service = MemoryService(session)
        created_a = service.write_memory(
            capability_references=[],
            payload=_write_request(
                run_a.id,
                scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run_a.id)),
            ),
        )
        _ = service.resolve_memory(
            created_a.memory_id,
            MemoryOutcome(status=MemoryLifecycleStatus.APPROVED, summary="Admin-visible"),
        )
        created_b = service.write_memory(
            capability_references=[],
            payload=_write_request(
                run_b.id,
                scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run_b.id)),
            ),
        )
        memory_ids = {created_a.memory_id, created_b.memory_id}

    response = client.get("/api/memory/admin/entries")
    invalid_response = client.get("/api/memory/admin/entries", params={"limit": "201"})

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert {"items", "total", "limit", "offset", "sort"}.issubset(payload)
    assert payload["total"] == 2
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["sort"] == "updatedAtDesc"
    assert {item["memoryId"] for item in payload["items"]} == memory_ids
    for item in payload["items"]:
        assert {
            "memoryId",
            "revisionId",
            "status",
            "kind",
            "summary",
            "excerpt",
            "subjectRefs",
            "scope",
            "provenance",
            "createdAt",
            "updatedAt",
            "lastEventType",
        }.issubset(item)
    assert "accessContext" not in str(payload)
    assert "maxCharacters" not in str(payload)
    assert invalid_response.status_code == 422, invalid_response.json()
    assert invalid_response.json()["code"] == "validation_error"


def test_admin_filters_narrow_and_clearing_filters_restores_full_corpus(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        alpha_run = _seed_run(session)
        beta_run = _seed_run(session)
        gamma_run = _seed_run(session)
        alpha_run_id = alpha_run.id
        alpha_package_key = alpha_run.workflow_package_key
        beta_package_key = beta_run.workflow_package_key
        gamma_package_key = gamma_run.workflow_package_key

        alpha_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=alpha_run.id,
                package_key=alpha_package_key,
                workflow_key="alpha_workflow",
                agent_key="alpha_agent",
            ),
        )
        alpha = alpha_service.write_memory(
            capability_references=[],
            payload=_write_request(
                alpha_run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(alpha_run.id)),
            ).model_copy(
                update={
                    "kind": "research.note",
                    "summary": "Alpha admin filter memory.",
                    "content": "alpha operator package filter needle.",
                    "provenance": MemoryProvenance(
                        run_id=alpha_run.id,
                        agent_key="alpha_agent",
                        agent_version=1,
                        agent_name="Alpha Agent",
                        workflow_key="alpha_workflow",
                        workflow_version=1,
                        step_id="alpha_step",
                        slot="memory",
                        trace_id="trace-alpha-admin-filter",
                    ),
                }
            ),
        )
        _ = alpha_service.resolve_memory(
            alpha.memory_id,
            MemoryOutcome(status=MemoryLifecycleStatus.APPROVED, summary="Alpha resolved"),
        )

        beta_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=beta_run.id,
                package_key=beta_package_key,
                workflow_key="beta_workflow",
                agent_key="beta_agent",
            ),
        )
        beta = beta_service.write_memory(
            capability_references=[],
            payload=_write_request(
                beta_run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.WORKFLOW, scope_key="beta_workflow"),
            ).model_copy(
                update={
                    "kind": "decision.note",
                    "summary": "Beta admin filter memory.",
                    "content": "beta operator workflow filter needle.",
                    "provenance": MemoryProvenance(
                        run_id=beta_run.id,
                        agent_key="beta_agent",
                        agent_version=1,
                        agent_name="Beta Agent",
                        workflow_key="beta_workflow",
                        workflow_version=1,
                        step_id="beta_step",
                        slot="memory",
                        trace_id="trace-beta-admin-filter",
                    ),
                }
            ),
        )
        _ = beta_service.resolve_memory(
            beta.memory_id,
            MemoryOutcome(status=MemoryLifecycleStatus.ARCHIVED, summary="Beta expired"),
        )

        gamma_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=gamma_run.id,
                package_key=gamma_package_key,
                workflow_key="gamma_workflow",
                agent_key="gamma_agent",
            ),
        )
        gamma = gamma_service.write_memory(
            capability_references=[],
            payload=_write_request(
                gamma_run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.AGENT, scope_key="gamma_agent"),
            ).model_copy(
                update={
                    "kind": "risk.note",
                    "summary": "Gamma admin filter memory.",
                    "content": "gamma-query-needle operator agent filter memory.",
                    "provenance": MemoryProvenance(
                        run_id=gamma_run.id,
                        agent_key="gamma_agent",
                        agent_version=1,
                        agent_name="Gamma Agent",
                        workflow_key="gamma_workflow",
                        workflow_version=1,
                        step_id="gamma_step",
                        slot="memory",
                        trace_id="trace-gamma-admin-filter",
                    ),
                }
            ),
        )
        memory_ids = {alpha.memory_id, beta.memory_id, gamma.memory_id}

    filter_cases = [
        ({"packageKey": alpha_package_key}, {alpha.memory_id}),
        ({"workflowKey": "beta_workflow"}, {beta.memory_id}),
        ({"agentKey": "gamma_agent"}, {gamma.memory_id}),
        ({"runId": str(alpha_run_id)}, {alpha.memory_id}),
        ({"scopeType": "workflow"}, {beta.memory_id}),
        ({"kind": "decision.note"}, {beta.memory_id}),
        ({"status": "pending"}, {gamma.memory_id}),
        ({"query": "gamma-query-needle"}, {gamma.memory_id}),
    ]

    for params, expected_ids in filter_cases:
        response = client.get("/api/memory/admin/entries", params=params)
        assert response.status_code == 200, response.json()
        payload = response.json()
        assert payload["total"] == len(expected_ids)
        assert {item["memoryId"] for item in payload["items"]} == expected_ids
        assert "accessContext" not in str(payload)
        assert "maxCharacters" not in str(payload)

    cleared_response = client.get("/api/memory/admin/entries")
    detail_response = client.get(f"/api/memory/admin/entries/{alpha.memory_id}")
    revisions_response = client.get(f"/api/memory/admin/entries/{alpha.memory_id}/revisions")
    events_response = client.get(f"/api/memory/admin/entries/{alpha.memory_id}/events")

    assert cleared_response.status_code == 200, cleared_response.json()
    cleared_payload = cleared_response.json()
    assert cleared_payload["total"] == 3
    assert {item["memoryId"] for item in cleared_payload["items"]} == memory_ids
    assert detail_response.status_code == 200, detail_response.json()
    assert revisions_response.status_code == 200, revisions_response.json()
    assert events_response.status_code == 200, events_response.json()
    assert detail_response.json()["memoryId"] == alpha.memory_id
    assert [item["version"] for item in revisions_response.json()["items"]] == [1, 2]
    assert [item["eventType"] for item in events_response.json()["items"]] == [
        "written",
        "reviewed",
    ]


def test_admin_create_requires_scope(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        run_id = run.id
        session.commit()

    missing_scope = client.post(
        "/api/memory/admin/entries",
        json=_admin_create_payload(run_id, include_scope=False),
    )
    created = client.post("/api/memory/admin/entries", json=_admin_create_payload(run_id))

    assert missing_scope.status_code == 422, missing_scope.json()
    assert missing_scope.json()["code"] == "validation_error"
    assert created.status_code == 200, created.json()
    created_payload = created.json()
    memory_id = created_payload["memoryId"]
    detail = client.get(f"/api/memory/admin/entries/{memory_id}")
    revisions = client.get(f"/api/memory/admin/entries/{memory_id}/revisions")
    events = client.get(f"/api/memory/admin/entries/{memory_id}/events")
    status_update = client.patch(
        f"/api/memory/admin/entries/{memory_id}/status",
        json={"status": "archived", "summary": "Admin archived memory."},
    )

    assert created_payload["status"] == "approved"
    assert created_payload["scope"] == {"scopeType": "run", "scopeKey": str(run_id)}
    assert "accessContext" not in str(created_payload)
    assert detail.status_code == 200, detail.json()
    assert revisions.status_code == 200, revisions.json()
    assert events.status_code == 200, events.json()
    assert status_update.status_code == 200, status_update.json()
    assert status_update.json()["status"] == "archived"


def test_admin_write_payload_validation_and_scope_mutation_attempts(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        run_id = run.id
        session.commit()

    invalid_create = client.post(
        "/api/memory/admin/entries",
        json={**_admin_create_payload(run_id), "status": "deleted"},
    )
    blank_content = client.post(
        "/api/memory/admin/entries",
        json={**_admin_create_payload(run_id), "content": ""},
    )
    created = client.post("/api/memory/admin/entries", json=_admin_create_payload(run_id))
    assert created.status_code == 200, created.json()
    memory_id = created.json()["memoryId"]

    revision_scope_mutation = client.post(
        f"/api/memory/admin/entries/{memory_id}/revisions",
        json={
            "summary": "Mutating scope should fail.",
            "content": "Revision payload must not accept scope mutation.",
            "provenance": _admin_create_payload(run_id)["provenance"],
            "scope": {"scopeType": "package", "scopeKey": "other_package"},
        },
    )
    status_scope_mutation = client.patch(
        f"/api/memory/admin/entries/{memory_id}/status",
        json={
            "status": "approved",
            "summary": "Mutating scope should fail.",
            "scope": {"scopeType": "package", "scopeKey": "other_package"},
        },
    )

    invalid_responses = (
        invalid_create,
        blank_content,
        revision_scope_mutation,
        status_scope_mutation,
    )
    for response in invalid_responses:
        assert response.status_code == 422, response.json()
        assert response.json()["code"] == "validation_error"
