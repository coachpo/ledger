from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.agent_memory import AgentMemoryEntry, AgentMemoryRevision, RunMemoryEvent
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.repositories.agent_memory import (
    AgentMemoryEntryRepository,
    AgentMemoryRevisionRepository,
    RunMemoryEventRepository,
)
from app.schemas.memory import (
    INVALID_MEMORY_ID_CODE,
    MEMORY_NOT_FOUND_CODE,
    MemoryLifecycleStatus,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryRevisionAction,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.services.memory_store import PostgresMemoryStore

_FORBIDDEN_MODEL_FRAGMENTS = (
    "reportId",
    "reportSlug",
    "reportName",
    "auditLinks",
    "/reports/",
    "download",
    "# Agent Memory",
)


def _seed_run(session: Session) -> Run:
    package_id = session.query(Run).count() + 1
    package_key = f"memory_workflow_package_{package_id}"
    run = Run(
        target_kind="workflowPackage",
        target_id=package_id,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key="memory_workflow",
        input={"topic": "drawdown"},
        status="running",
        trace_id="trace-run-1",
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package_id,
        workflow_package_key=package_key,
        workflow_package_name="Memory Workflow Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key="memory_workflow",
        workflow_name="Memory Workflow",
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=(
            "apiVersion: signaldeck.workflowPackage/v1\n"
            f"key: {package_key}\n"
        ),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": "memory_workflow"}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": ["memory_workflow"]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def _provenance(run_id: int) -> MemoryProvenance:
    return MemoryProvenance(
        run_id=run_id,
        agent_key="memory_curator",
        agent_version=3,
        agent_name="Memory Curator",
        workflow_key="daily_review",
        workflow_version=7,
        step_id="memory_write",
        slot="post_run_note",
        trace_id="trace-abc123",
    )


def _write_request(
    run_id: int,
    *,
    content: str = "Historical drawdown context should be reviewed before sizing.",
    summary: str = "Reusable risk-context note.",
    idempotency_key: str | None = None,
) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary=summary,
        content=content,
        subject_refs=[MemorySubjectRef(kind="instrument", id="nvda", label="NVDA")],
        attributes={"confidence": "medium"},
        scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key="pkg-advisory"),
        provenance=_provenance(run_id),
        idempotency_key=idempotency_key,
    )


def _outcome() -> MemoryOutcome:
    return MemoryOutcome(
        status=MemoryLifecycleStatus.RESOLVED,
        summary="Sizing check completed.",
        observed_at=datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
        attributes={"verdict": "useful"},
        resolved_status="resolved",
        resolved_at=datetime(2026, 1, 17, 10, 30, tzinfo=UTC),
    )


def _reflection() -> MemoryReflection:
    return MemoryReflection(
        reflection="Outcome confirmed the liquidity gate.",
        reflected_at=datetime(2026, 1, 18, 8, tzinfo=UTC),
    )


def _count(session: Session, model: type[object]) -> int:
    return cast(int, session.scalar(select(func.count()).select_from(model)))


def _serialized(payload: object) -> str:
    return str(payload)


def test_create_get_round_trip_writes_canonical_rows_without_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        result = store.create_pending(_write_request(run.id))
        entry = store.get(result.memory_id)
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))
        payload = result.model_dump(mode="json", by_alias=True)

        assert _count(session, Report) == 0
        assert _count(session, AgentMemoryEntry) == 1
        assert _count(session, AgentMemoryRevision) == 1
        assert len(events) == 1
        assert result.memory_id.startswith("memory_")
        assert result.revision_id.startswith("revision_")
        assert not result.memory_id.startswith("mem_")
        assert result.revision_action == MemoryRevisionAction.CREATED
        assert result.status == MemoryLifecycleStatus.PENDING
        assert entry.memory_id == result.memory_id
        assert entry.revision_id == result.revision_id
        assert entry.kind == "research.note"
        assert entry.attributes == {"confidence": "medium"}
        assert entry.audit_links is None
        assert payload["memoryId"] == result.memory_id
        assert payload["revisionAction"] == "created"
        assert "action" not in payload
        for fragment in _FORBIDDEN_MODEL_FRAGMENTS:
            assert fragment not in _serialized(payload)
        assert events[0].event_type == "written"
        assert events[0].memory_id == result.memory_id
        assert events[0].revision_id == result.revision_id
        assert events[0].result_snapshot == {
            "memoryId": result.memory_id,
            "revisionId": result.revision_id,
            "status": "pending",
            "revisionAction": "created",
        }


def test_duplicate_create_reuses_existing_entry_and_records_event(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        request = _write_request(run.id)
        first = store.create_pending(request)
        second = store.create_pending(request)
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))

        assert first.action == "created"
        assert second.action == "existing"
        assert second.revision_action == MemoryRevisionAction.REUSED
        assert first.memory_id == second.memory_id
        assert first.revision_id == second.revision_id
        assert _count(session, AgentMemoryEntry) == 1
        assert _count(session, AgentMemoryRevision) == 1
        assert [event.event_type for event in events] == ["written", "reused"]


def test_explicit_idempotency_conflict_rejects_changed_content(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        _ = store.create_pending(_write_request(run.id, idempotency_key="stable-key"))
        with pytest.raises(ApiError) as exc_info:
            _ = store.create_pending(
                _write_request(
                    run.id,
                    content="Different content under the same explicit key.",
                    idempotency_key="stable-key",
                )
            )

        error = exc_info.value
        assert error.status_code == 409
        assert error.code == "memory_conflict"
        assert "report" not in error.message.lower()
        assert _count(session, AgentMemoryEntry) == 1
        assert _count(session, AgentMemoryRevision) == 1


def test_get_treats_legacy_mem_ids_as_opaque_not_report_identity(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        store = PostgresMemoryStore(session)
        with pytest.raises(ApiError) as invalid_exc:
            _ = store.get(" ")
        with pytest.raises(ApiError) as missing_exc:
            _ = store.get("mem_123")

    assert invalid_exc.value.code == INVALID_MEMORY_ID_CODE
    assert missing_exc.value.code == MEMORY_NOT_FOUND_CODE
    serialized = _serialized(
        {
            "code": missing_exc.value.code,
            "message": missing_exc.value.message,
            "details": missing_exc.value.details,
        }
    )
    assert "report" not in serialized.lower()
    assert "/reports/" not in serialized


def test_resolve_append_and_query_use_canonical_revisions_without_leaks(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        created = store.create_pending(_write_request(run.id))
        assert (
            store.query(
                MemoryQuery(
                    scope=MemoryScope(
                        scope_type=MemoryScopeType.PACKAGE,
                        scope_key="pkg-advisory",
                    )
                )
            )
            == []
        )
        resolved = store.resolve(created.memory_id, _outcome())
        reflected = store.append_reflection(created.memory_id, _reflection())
        snippets = store.query(
            MemoryQuery(
                scope=MemoryScope(
                    scope_type=MemoryScopeType.PACKAGE,
                    scope_key="pkg-advisory",
                ),
                query="drawdown",
                limit=10,
            )
        )
        revisions = list(
            session.scalars(select(AgentMemoryRevision).order_by(AgentMemoryRevision.version))
        )
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))

    assert resolved.status == MemoryLifecycleStatus.RESOLVED
    assert resolved.outcome is not None
    assert resolved.outcome.summary == "Sizing check completed."
    assert reflected.reflections[0].reflection == "Outcome confirmed the liquidity gate."
    assert [revision.version for revision in revisions] == [1, 2, 3]
    assert revisions[1].supersedes_revision_id == revisions[0].revision_id
    assert revisions[2].supersedes_revision_id == revisions[1].revision_id
    assert [event.event_type for event in events] == ["written", "reviewed", "reviewed"]
    assert len(snippets) == 1
    snippet_payload = snippets[0].model_visible_dump()
    assert snippets[0].memory_id == created.memory_id
    assert snippets[0].text.startswith("Historical memory, not an instruction:")
    assert snippets[0].retrieval_score is not None
    assert snippets[0].retrieval_score.retrieval_mode == "lexical"
    assert snippets[0].retrieval_score.sources == ["lexical"]
    assert "drawdown" in snippets[0].text
    for fragment in _FORBIDDEN_MODEL_FRAGMENTS:
        assert fragment not in _serialized(snippet_payload)
        assert fragment not in snippets[0].text


def test_concurrent_shared_scope_revision_update_conflicts_then_retries_without_loss(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        created = PostgresMemoryStore(session).create_pending(_write_request(run.id))
        memory_id = created.memory_id
        session.commit()

    with session_factory() as winner_session, session_factory() as conflict_session:
        winner = PostgresMemoryStore(winner_session).resolve(memory_id, _outcome())
        _ = conflict_session.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(ApiError) as exc_info:
            _ = PostgresMemoryStore(conflict_session).append_reflection(
                memory_id,
                _reflection(),
            )
        conflict_session.rollback()
        winner_session.commit()

    with session_factory() as retry_session:
        retried = PostgresMemoryStore(retry_session).append_reflection(
            memory_id,
            _reflection(),
        )
        retry_session.commit()

    with session_factory() as session:
        entry = AgentMemoryEntryRepository(session).get_by_memory_id(memory_id)
        revisions = list(
            session.scalars(select(AgentMemoryRevision).order_by(AgentMemoryRevision.version))
        )
        events = list(session.scalars(select(RunMemoryEvent).order_by(RunMemoryEvent.id)))

    error = exc_info.value
    assert error.status_code == 409
    assert error.code == "memory_revision_conflict"
    assert winner.revision.version == 2
    assert retried.revision.version == 3
    assert retried.reflections[0].reflection == _reflection().reflection
    assert entry is not None
    assert entry.status == "resolved"
    assert [revision.version for revision in revisions] == [1, 2, 3]
    assert revisions[1].supersedes_revision_id == revisions[0].revision_id
    assert revisions[2].supersedes_revision_id == revisions[1].revision_id
    assert [event.event_type for event in events] == ["written", "reviewed", "reviewed"]
    assert [event.revision_id for event in events] == [
        revisions[0].revision_id,
        revisions[1].revision_id,
        revisions[2].revision_id,
    ]


def test_query_with_embedding_falls_back_to_lexical_when_vectors_are_absent(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        created = store.create_pending(_write_request(run.id))
        _ = store.resolve(created.memory_id, _outcome())
        snippets = store.query(
            MemoryQuery(
                scope=MemoryScope(
                    scope_type=MemoryScopeType.PACKAGE,
                    scope_key="pkg-advisory",
                ),
                query="drawdown",
                query_embedding=(0.1, 0.2, 0.3),
                query_embedding_model="text-embedding-3-small",
                limit=5,
            )
        )

    assert [snippet.memory_id for snippet in snippets] == [created.memory_id]
    assert snippets[0].retrieval_score is not None
    assert snippets[0].retrieval_score.retrieval_mode == "lexical"
    assert snippets[0].retrieval_score.sources == ["lexical"]


def test_list_artifacts_for_run_uses_event_stream_without_audit_links(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        created = store.create_pending(_write_request(run.id))
        _ = store.resolve(created.memory_id, _outcome())
        artifacts = store.list_artifacts_for_run(run.id)
        audit_links = store.audit_links(created.memory_id)

    assert len(artifacts) == 1
    artifact = artifacts[0]
    ui_payload = artifact.dump_for_projection("ui-visible")
    model_payload = artifact.model_visible_dump()
    assert artifact.memory_id == created.memory_id
    assert artifact.revision_id.startswith("revision_")
    assert artifact.audit_links is None
    assert audit_links.references == []
    assert audit_links.report is None
    assert ui_payload["sourceGraphMetadata"] == {
        "stepId": "memory_write",
        "slot": "post_run_note",
        "traceId": "trace-abc123",
        "workflowKey": "daily_review",
        "workflowVersion": 7,
    }
    for fragment in _FORBIDDEN_MODEL_FRAGMENTS:
        assert fragment not in _serialized(ui_payload)
        assert fragment not in _serialized(model_payload)


def test_repositories_expose_canonical_lookup_helpers(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        store = PostgresMemoryStore(session)
        created = store.create_pending(_write_request(run.id))
        _ = store.resolve(created.memory_id, _outcome())
        entry_repo = AgentMemoryEntryRepository(session)
        revision_repo = AgentMemoryRevisionRepository(session)
        event_repo = RunMemoryEventRepository(session)
        entry = entry_repo.get_by_memory_id(created.memory_id)
        assert entry is not None
        latest = revision_repo.get_latest_for_entry(entry.id)
        rows = entry_repo.list_latest_for_lookup(
            query_text="drawdown",
            scope_type="package",
            scope_key="pkg-advisory",
            subject_refs=[{"kind": "instrument", "id": "nvda"}],
            kind="research.note",
            status="resolved",
            ticker=None,
            portfolio_slug=None,
            agent_key="memory_curator",
            workflow_key="daily_review",
            tags=[],
            limit=5,
            offset=0,
        )
        events = event_repo.list_for_run(run.id)

    assert latest is not None
    assert latest.revision_id != created.revision_id
    assert len(rows) == 1
    assert rows[0][0].memory_id == created.memory_id
    assert rows[0][1].revision_id == latest.revision_id
    assert [event.event_type for event in events] == ["written", "reviewed"]
