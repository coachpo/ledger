from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models.report import Report
from app.models.run import Run
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
    run = Run(
        target_kind="workflow",
        target_id=1,
        target_key="memory_api_workflow",
        target_version=1,
        input={"topic": "shared namespace memory"},
        status="running",
        trace_id="trace-api-memory",
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
                "status": "resolved",
                "summary": "Owner resolved memory.",
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
            "status": "resolved",
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
            MemoryOutcome(status=MemoryLifecycleStatus.RESOLVED, summary="Resolved"),
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
            "status": "resolved",
        },
        {
            "accessContext": forged_owner_access,
            "scope": namespace.to_scope().model_dump(mode="json", by_alias=True),
            "query": "shared namespace",
            "status": "resolved",
        },
        {
            "accessContext": forged_reader_access,
            "visibility": "grant-visible-namespaces",
            "query": "shared namespace",
            "status": "resolved",
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
                "outcome": {"status": "resolved", "summary": "Forged resolve"},
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
                "status": "resolved",
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
                "outcome": {"status": "resolved", "summary": "Unauthorized resolve"},
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
