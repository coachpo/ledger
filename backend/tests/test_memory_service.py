from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agents.runtime_tools.memory import (
    MEMORY_LOOKUP_TOOL_KEY,
    MEMORY_TOOL_ACCESS_DENIED_CODE,
    MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    MEMORY_WRITE_GRANT_POLICY,
    MEMORY_WRITE_TOOL_KEY,
)
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.agent_memory import (
    AgentMemoryChunk,
    AgentMemoryEmbedding,
    AgentMemoryEntry,
    AgentMemoryRevision,
    RunMemoryEvent,
)
from app.models.report import Report
from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.repositories.agent_memory import AgentMemoryEntryRepository, RunMemoryEventRepository
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.memory import (
    MEMORY_NAMESPACE_ACCESS_DENIED_CODE,
    MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE,
    MemoryAdminCreateRequest,
    MemoryAdminListQuery,
    MemoryAdminRevisionCreateRequest,
    MemoryAdminWorkflowVisibilityUpdateRequest,
    MemoryNamespaceGrant,
    MemoryNamespaceSelector,
    MemoryOutcome,
    MemoryProvenance,
    MemoryQuery,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
)
from app.services.extension_service import ExtensionService
from app.services.memory_context_service import MemoryContextService
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.runtime_tool_grants import RuntimeToolGrantError


def _capability_references(
    tools: list[str] | None = None,
) -> list[dict[str, object]]:
    return [{"toolKeys": list(tools or [MEMORY_WRITE_TOOL_KEY])}]


def _seed_run(session: Session, *, run_id: int | None = None) -> Run:
    package_id = run_id if run_id is not None else session.query(Run).count() + 1
    package_key = f"platform_graph_daily_review_package_{package_id}"
    run = Run(
        id=run_id,
        target_kind="workflowPackage",
        target_id=package_id,
        target_key=package_key,
        target_version=1,
        workflow_package_key=package_key,
        workflow_package_workflow_key="platform_graph_daily_review",
        input={"ticker": "NVDA"},
        status="running",
        trace_id="trace-abc123",
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package_id,
        workflow_package_key=package_key,
        workflow_package_name="Platform Graph Daily Review Package",
        workflow_package_description="",
        workflow_package_status="active",
        workflow_key="platform_graph_daily_review",
        workflow_name="Platform Graph Daily Review",
        workflow_description="",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        manifest_source=(f"apiVersion: signaldeck.workflowPackage/v1\nkey: {package_key}\n"),
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"workflows": [{"key": "platform_graph_daily_review"}]},
        extension_dependencies=[],
        local_resource_refs={"workflows": ["platform_graph_daily_review"]},
        input_schema={},
        launch_parameters=run.input,
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()
    session.refresh(run)
    return run


def _seed_run_invocation(session: Session, run: Run) -> RunAgentInvocation:
    step = RunStep(
        run_id=run.id,
        step_index=1,
        status="running",
        graph_metadata={"nodeId": "portfolio_decision"},
    )
    session.add(step)
    session.flush()
    session.refresh(step)
    invocation = RunAgentInvocation(
        run_step_id=step.id,
        run_id=run.id,
        step_index=1,
        slot="decision",
        position=0,
        agent_id=1,
        agent_key="portfolio_manager",
        agent_version=3,
        output_schema_id=1,
        output_schema_version=1,
        input_mode="wired",
        graph_metadata={"nodeId": "portfolio_decision"},
        status="running",
    )
    session.add(invocation)
    session.flush()
    session.refresh(invocation)
    return invocation


def _write_request(run_id: int = 42) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        kind="research.note",
        summary="Long-term compounding memory.",
        content=(
            "Earnings durability supports a long position. "
            "Sizing should account for semiconductor cyclicality."
        ),
        subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
        attributes={"confidence": "high"},
        scope=MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(run_id)),
        provenance=MemoryProvenance(
            run_id=run_id,
            agent_key="portfolio_manager",
            agent_version=3,
            agent_name="Portfolio Manager",
            workflow_key="platform_graph_daily_review",
            workflow_version=5,
            step_id="portfolio_decision",
            slot="decision",
            trace_id="trace-abc123",
        ),
    )


def _admin_create_request(
    run_id: int,
    *,
    scope: MemoryScope,
    visible_to_workflow: bool = True,
    summary: str = "Admin package memory.",
    content: str = "admin managed package alpha lookup signal.",
) -> MemoryAdminCreateRequest:
    return MemoryAdminCreateRequest(
        kind="research.note",
        summary=summary,
        content=content,
        subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
        attributes={"adminFixture": "true"},
        scope=scope,
        provenance=MemoryProvenance(
            run_id=run_id,
            agent_key="ignored_payload_agent",
            agent_version=7,
            agent_name="Ignored Payload Agent",
            workflow_key="admin_workflow",
            workflow_version=1,
            step_id="admin_write",
            slot="memory",
            trace_id="trace-admin-write",
        ),
        visible_to_workflow=visible_to_workflow,
    )


def _reports(session: Session) -> list[Report]:
    return list(session.scalars(select(Report).order_by(Report.id)))


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _disable_finance_workspace(session: Session) -> None:
    _ = ExtensionService(session).set_extension_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        ExtensionToggleRequest.model_validate({"enabled": False}),
    )


def _write_request_for_context(
    run_id: int,
    *,
    workflow_key: str,
    agent_key: str,
    scope: MemoryScope,
    summary: str,
    content: str,
) -> MemoryWriteRequest:
    request = _write_request(run_id)
    return request.model_copy(
        update={
            "scope": scope,
            "summary": summary,
            "content": content,
            "provenance": request.provenance.model_copy(
                update={
                    "agent_key": agent_key,
                    "workflow_key": workflow_key,
                    "step_id": "memory_write",
                    "slot": "memory",
                }
            ),
        }
    )


def _namespace_selector() -> MemoryNamespaceSelector:
    return MemoryNamespaceSelector(
        owner_package_key="pkg_alpha",
        namespace_key="shared_research",
    )


def _namespace_grant(
    *,
    package_key: str,
    actions: list[str],
    workflow_key: str | None = None,
    agent_key: str | None = None,
) -> MemoryNamespaceGrant:
    return MemoryNamespaceGrant.model_validate(
        {
            "namespace": _namespace_selector().model_dump(mode="json", by_alias=True),
            "subject": {
                "packageKey": package_key,
                "workflowKey": workflow_key,
                "agentKey": agent_key,
            },
            "actions": actions,
        }
    )


def test_admin_operator_lists_all_packages(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package_a_run = _seed_run(session)
        package_b_run = _seed_run(session)
        package_a_run_id = package_a_run.id
        package_b_run_id = package_b_run.id
        package_a_key = package_a_run.workflow_package_key
        service = MemoryService(session)
        package_a = service.write_memory(
            capability_references=[],
            payload=_write_request(package_a_run.id).model_copy(
                update={
                    "summary": "Package A operator memory.",
                    "content": "trusted operator corpus includes package alpha memory.",
                }
            ),
        )
        package_b = service.write_memory(
            capability_references=[],
            payload=_write_request(package_b_run.id).model_copy(
                update={
                    "summary": "Package B operator memory.",
                    "content": "trusted operator corpus includes package beta memory.",
                }
            ),
        )
        _ = service.resolve_memory(
            package_a.memory_id,
            MemoryOutcome(summary="Package A resolved"),
        )
        _ = service.resolve_memory(
            package_b.memory_id,
            MemoryOutcome(summary="Package B resolved"),
        )

        all_memory = service.list_admin_memory(MemoryAdminListQuery())
        package_a_memory = service.list_admin_memory(
            MemoryAdminListQuery(package_key=package_a_key)
        )
        detail = service.get_admin_memory(package_b.memory_id)
        revisions = service.list_admin_memory_revisions(package_b.memory_id, limit=10, offset=0)
        events = service.list_admin_memory_events(package_b.memory_id, limit=10, offset=0)
        with pytest.raises(RuntimeToolGrantError) as runtime_global_denied:
            _ = service.query_memory(MemoryQuery(query="trusted operator corpus"))

    assert all_memory.total == 2
    assert {item.memory_id for item in all_memory.items} == {
        package_a.memory_id,
        package_b.memory_id,
    }
    assert {item.provenance.run_id for item in all_memory.items} == {
        package_a_run_id,
        package_b_run_id,
    }
    assert [item.memory_id for item in package_a_memory.items] == [package_a.memory_id]
    assert detail.memory_id == package_b.memory_id
    assert [revision.version for revision in revisions.items] == [1, 2]
    assert [event.event_type for event in events.items] == ["written", "reviewed"]
    assert runtime_global_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE


def test_admin_create_resolved_affects_matching_runtime_lookup(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run_a = _seed_run(session)
        run_b = _seed_run(session)
        package_a_key = "pkg_admin_alpha"
        package_b_key = "pkg_admin_beta"
        service = MemoryService(session)
        created = service.create_admin_memory(
            _admin_create_request(
                run_a.id,
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_a_key),
                content="admin scoped alpha workflow-visible memory should match alpha only.",
            )
        )
        alpha_snippets = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run_a.id,
                package_key=package_a_key,
                workflow_key="admin_workflow",
                agent_key="admin_agent",
            ),
        ).query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_a_key),
                query="alpha workflow-visible",
                limit=10,
            ),
            record_event=False,
        )
        beta_snippets = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run_b.id,
                package_key=package_b_key,
                workflow_key="admin_workflow",
                agent_key="admin_agent",
            ),
        ).query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_b_key),
                query="alpha workflow-visible",
                limit=10,
            ),
            record_event=False,
        )
        admin_list = service.list_admin_memory(MemoryAdminListQuery())
        events = service.list_admin_memory_events(created.memory_id, limit=10, offset=0)

    assert created.visible_to_workflow is True
    assert created.scope == MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_a_key)
    assert created.provenance.created_by_type == "operator"
    assert created.provenance.agent_key == "local-instance-operator"
    assert [snippet.memory_id for snippet in alpha_snippets] == [created.memory_id]
    assert beta_snippets == []
    assert [item.memory_id for item in admin_list.items] == [created.memory_id]
    assert [event.event_type for event in events.items] == ["operator_created"]
    assert events.items[0].filters["source"] == "operator"
    assert events.items[0].filters["actor"] == "local-instance-operator"
    assert events.items[0].filters["channel"] == "memory_admin"


def test_admin_hard_delete_cascades_dependents_and_excludes_runtime_lookup(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        package_key = "pkg_admin_delete_cascade"
        service = MemoryService(session)
        created = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                content="admin delete cascade runtime lookup marker should disappear.",
            )
        )
        entry = session.scalar(
            select(AgentMemoryEntry).where(AgentMemoryEntry.memory_id == created.memory_id)
        )
        assert entry is not None
        revision = session.scalar(
            select(AgentMemoryRevision).where(
                AgentMemoryRevision.revision_id == created.revision_id
            )
        )
        assert revision is not None
        chunk = AgentMemoryChunk(
            memory_entry_id=entry.id,
            memory_revision_id=revision.id,
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            chunk_id=f"{revision.revision_id}:chunk-0",
            chunk_index=0,
            chunking_version="memory-core-chunker/v1",
            content=revision.content,
            content_hash=revision.content_hash,
            source_content_hash=revision.content_hash,
            token_count=5,
        )
        session.add(chunk)
        session.flush()
        session.refresh(chunk)
        session.add(
            AgentMemoryEmbedding(
                memory_chunk_id=chunk.id,
                memory_entry_id=entry.id,
                memory_revision_id=revision.id,
                memory_id=entry.memory_id,
                revision_id=revision.revision_id,
                chunk_id=chunk.chunk_id,
                embedding_provider="test",
                embedding_model="text-embedding-3-small",
                embedding_dimensions=3,
                content_hash=revision.content_hash,
                chunking_version=chunk.chunking_version,
                status="pending",
                metadata_={"source": "hard-delete-test"},
            )
        )
        session.commit()

        runtime_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key=package_key,
                workflow_key="admin_workflow",
                agent_key="admin_agent",
            ),
        )
        before_delete = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="delete cascade runtime lookup marker",
                limit=10,
            ),
            record_event=False,
        )
        event_types_before_delete = list(
            session.scalars(select(RunMemoryEvent.event_type).order_by(RunMemoryEvent.id))
        )

        service.delete_admin_memory(created.memory_id)

        after_delete = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="delete cascade runtime lookup marker",
                limit=10,
            ),
            record_event=False,
        )
        event_rows_after_delete = session.execute(
            select(
                RunMemoryEvent.event_type,
                RunMemoryEvent.memory_entry_id,
                RunMemoryEvent.memory_revision_id,
                RunMemoryEvent.memory_id,
                RunMemoryEvent.revision_id,
            ).order_by(RunMemoryEvent.id)
        ).all()
        row_counts = (
            _count(session, AgentMemoryEntry),
            _count(session, AgentMemoryRevision),
            _count(session, AgentMemoryChunk),
            _count(session, AgentMemoryEmbedding),
        )

    assert [snippet.memory_id for snippet in before_delete] == [created.memory_id]
    assert after_delete == []
    assert row_counts == (0, 0, 0, 0)
    assert event_types_before_delete == ["operator_created"]
    assert event_rows_after_delete == [
        ("operator_created", None, None, created.memory_id, created.revision_id)
    ]


def test_admin_workflow_visibility_revision_lookup(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        package_key = "pkg_admin_visibility"
        service = MemoryService(session)
        created = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                visible_to_workflow=False,
                content="workflow-hidden admin memory is not in runtime lookup yet.",
            )
        )
        runtime_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key=package_key,
                workflow_key="admin_workflow",
                agent_key="admin_agent",
            ),
        )
        hidden_snippets = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="admin memory",
                limit=10,
            ),
            record_event=False,
        )
        workflow_visible = service.update_admin_memory_workflow_visibility(
            created.memory_id,
            MemoryAdminWorkflowVisibilityUpdateRequest(visible_to_workflow=True),
        )
        workflow_visible_snippets = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="admin memory",
                limit=10,
            ),
            record_event=False,
        )
        revised = service.create_admin_memory_revision(
            created.memory_id,
            MemoryAdminRevisionCreateRequest(
                summary="Revised admin memory.",
                content="latest admin revision controls future lookup content.",
                subject_refs=[MemorySubjectRef(kind="instrument", id="NVDA")],
                attributes={"revision": "latest"},
                provenance=MemoryProvenance(
                    run_id=run.id,
                    agent_key="ignored_reviser",
                    agent_version=2,
                    workflow_key="admin_workflow",
                    workflow_version=1,
                    step_id="admin_revision",
                    slot="memory",
                    trace_id="trace-admin-revision",
                ),
            ),
        )
        latest_snippets = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="latest admin revision",
                limit=10,
            ),
            record_event=False,
        )
        workflow_hidden = service.update_admin_memory_workflow_visibility(
            created.memory_id,
            MemoryAdminWorkflowVisibilityUpdateRequest(
                visible_to_workflow=False,
                summary="Admin workflow-hidden memory.",
            ),
        )
        workflow_hidden_snippets = runtime_service.query_memory(
            MemoryQuery(
                scope=MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key),
                query="latest admin revision",
                limit=10,
            ),
            record_event=False,
        )
        admin_detail = service.get_admin_memory(created.memory_id)
        events = service.list_admin_memory_events(created.memory_id, limit=10, offset=0)
        revisions = service.list_admin_memory_revisions(created.memory_id, limit=10, offset=0)

    assert hidden_snippets == []
    assert workflow_visible.visible_to_workflow is True
    assert [snippet.memory_id for snippet in workflow_visible_snippets] == [created.memory_id]
    assert revised.content == "latest admin revision controls future lookup content."
    assert [snippet.content for snippet in latest_snippets] == [revised.content]
    assert workflow_hidden.visible_to_workflow is False
    assert workflow_hidden_snippets == []
    assert admin_detail.visible_to_workflow is False
    assert admin_detail.content == revised.content
    assert [event.event_type for event in events.items] == [
        "operator_created",
        "operator_visibility_changed",
        "operator_revised",
        "operator_visibility_changed",
    ]
    assert [revision.version for revision in revisions.items] == [1, 2, 3, 4]


def test_admin_list_visibility_sort(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(session)
        package_scope = MemoryScope(
            scope_type=MemoryScopeType.PACKAGE,
            scope_key="pkg_admin_sort",
        )
        first_hidden = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                visible_to_workflow=False,
                summary="First hidden admin sort memory.",
                content="first hidden admin sort memory " + ("x" * 700),
            )
        )
        visible = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                visible_to_workflow=True,
                summary="Workflow-visible admin sort memory.",
                content="workflow-visible admin sort memory.",
            )
        )
        later_hidden = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                visible_to_workflow=False,
                summary="Later hidden admin sort memory.",
                content="later hidden admin sort memory.",
            )
        )
        base_time = datetime(2026, 6, 13, 12, tzinfo=UTC)
        entries = {
            entry.memory_id: entry
            for entry in session.scalars(
                select(AgentMemoryEntry).where(
                    AgentMemoryEntry.memory_id.in_(
                        [first_hidden.memory_id, visible.memory_id, later_hidden.memory_id]
                    )
                )
            )
        }
        entries[first_hidden.memory_id].created_at = base_time
        entries[first_hidden.memory_id].updated_at = base_time + timedelta(minutes=2)
        entries[visible.memory_id].created_at = base_time + timedelta(minutes=1)
        entries[visible.memory_id].updated_at = base_time + timedelta(minutes=2)
        entries[later_hidden.memory_id].created_at = base_time + timedelta(minutes=3)
        entries[later_hidden.memory_id].updated_at = base_time + timedelta(minutes=1)
        session.commit()

        default_list = service.list_admin_memory(MemoryAdminListQuery())
        created_sort = service.list_admin_memory(MemoryAdminListQuery(sort="createdAtDesc"))
        hidden_only = service.list_admin_memory(MemoryAdminListQuery(visible_to_workflow=False))

    assert default_list.total == 3
    assert [item.memory_id for item in default_list.items] == [
        visible.memory_id,
        first_hidden.memory_id,
        later_hidden.memory_id,
    ]
    assert {item.visible_to_workflow for item in default_list.items} == {False, True}
    assert [item.memory_id for item in created_sort.items] == [
        later_hidden.memory_id,
        visible.memory_id,
        first_hidden.memory_id,
    ]
    assert {item.memory_id for item in hidden_only.items} == {
        first_hidden.memory_id,
        later_hidden.memory_id,
    }
    assert len(default_list.items[1].excerpt) <= 500


def test_admin_lexical_search_no_vector(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_vector_path(*args: object, **kwargs: object) -> object:
        raise AssertionError("admin search must not use vector memory paths")

    monkeypatch.setattr(
        AgentMemoryEntryRepository,
        "list_vector_lookup_candidates",
        fail_vector_path,
    )
    monkeypatch.setattr(
        AgentMemoryEntryRepository,
        "_embedding_table_available",
        fail_vector_path,
    )
    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(session)
        package_scope = MemoryScope(
            scope_type=MemoryScopeType.PACKAGE,
            scope_key="pkg_admin_search",
        )
        content_match = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                summary="Content matched memory.",
                content="adminneedle appears in latest revision content.",
            )
        )
        summary_match = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                summary="adminneedle appears in latest revision summary.",
                content="summary matched memory body.",
            )
        )
        subject_match = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                summary="Subject matched memory.",
                content="subject matched memory body.",
            ).model_copy(
                update={"subject_refs": [MemorySubjectRef(kind="instrument", id="adminneedle")]}
            )
        )
        _noise = service.create_admin_memory(
            _admin_create_request(
                run.id,
                scope=package_scope,
                summary="Unrelated memory.",
                content="unrelated content stays out of lexical search.",
            )
        )

        results = service.list_admin_memory(MemoryAdminListQuery(query="adminneedle"))

    assert results.total == 3
    assert {item.memory_id for item in results.items} == {
        content_match.memory_id,
        summary_match.memory_id,
        subject_match.memory_id,
    }
    assert all(len(item.excerpt) <= 500 for item in results.items)


def test_package_runtime_broader_scopes_are_package_isolated(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        alpha_run = _seed_run(session)
        beta_run = _seed_run(session)
        shared_workflow_key = "shared_review"
        shared_agent_key = "shared_agent"
        alpha_context = MemoryLookupContext(
            run_id=alpha_run.id,
            package_key="pkg_alpha",
            workflow_key=shared_workflow_key,
            agent_key=shared_agent_key,
        )
        beta_context = MemoryLookupContext(
            run_id=beta_run.id,
            package_key="pkg_beta",
            workflow_key=shared_workflow_key,
            agent_key=shared_agent_key,
        )
        alpha_service = MemoryService(session, current_context=alpha_context)
        beta_service = MemoryService(session, current_context=beta_context)
        alpha_created = alpha_service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                alpha_run.id,
                workflow_key=shared_workflow_key,
                agent_key=shared_agent_key,
                scope=MemoryScope(
                    scope_type=MemoryScopeType.AGENT,
                    scope_key=shared_agent_key,
                ),
                summary="Alpha package isolation memory.",
                content="package isolation signal belongs only to alpha.",
            ),
        )
        beta_created = beta_service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                beta_run.id,
                workflow_key=shared_workflow_key,
                agent_key=shared_agent_key,
                scope=MemoryScope(
                    scope_type=MemoryScopeType.AGENT,
                    scope_key=shared_agent_key,
                ),
                summary="Beta package isolation memory.",
                content="package isolation signal belongs only to beta.",
            ),
        )
        _ = alpha_service.resolve_memory(
            alpha_created.memory_id,
            MemoryOutcome(summary="Alpha resolved"),
        )
        _ = beta_service.resolve_memory(
            beta_created.memory_id,
            MemoryOutcome(summary="Beta resolved"),
        )
        alpha_snippets = alpha_service.query_memory(
            MemoryQuery(query="package isolation", limit=10),
            record_event=False,
        )
        beta_snippets = beta_service.query_memory(
            MemoryQuery(query="package isolation", limit=10),
            record_event=False,
        )
        entries = {
            entry.memory_id: entry
            for entry in session.scalars(
                select(AgentMemoryEntry).where(
                    AgentMemoryEntry.memory_id.in_(
                        [alpha_created.memory_id, beta_created.memory_id]
                    )
                )
            )
        }

    assert entries[alpha_created.memory_id].scope_type == "agent"
    assert entries[alpha_created.memory_id].scope_key == "pkg_alpha:shared_agent"
    assert entries[beta_created.memory_id].scope_type == "agent"
    assert entries[beta_created.memory_id].scope_key == "pkg_beta:shared_agent"
    assert [snippet.memory_id for snippet in alpha_snippets] == [alpha_created.memory_id]
    assert [snippet.memory_id for snippet in beta_snippets] == [beta_created.memory_id]


def test_admin_created_namespace_memory_still_requires_runtime_namespace_rules(
    session_factory: sessionmaker[Session],
) -> None:
    namespace = _namespace_selector()
    with session_factory() as session:
        admin_run = _seed_run(session)
        reader_run = _seed_run(session)
        writer_run = _seed_run(session)
        service = MemoryService(session)
        created = service.create_admin_memory(
            _admin_create_request(
                admin_run.id,
                scope=namespace.to_scope(),
                summary="Admin namespace guardrail memory.",
                content="admin namespace runtime grant marker stays scoped.",
            )
        )
        owner_without_declaration = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=admin_run.id,
                package_key="pkg_alpha",
                workflow_key="shared_review",
                agent_key="owner_agent",
            ),
        )
        owner_with_declaration = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=admin_run.id,
                package_key="pkg_alpha",
                workflow_key="shared_review",
                agent_key="owner_agent",
                namespace_declarations=(namespace,),
            ),
        )
        reader_without_grant = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=reader_run.id,
                package_key="pkg_beta",
                workflow_key="shared_review",
                agent_key="reader_agent",
            ),
        )
        reader_with_grant = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=reader_run.id,
                package_key="pkg_beta",
                workflow_key="shared_review",
                agent_key="reader_agent",
                namespace_grants=(_namespace_grant(package_key="pkg_beta", actions=["read"]),),
            ),
        )
        writer_without_grant = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=writer_run.id,
                package_key="pkg_gamma",
                workflow_key="shared_review",
                agent_key="writer_agent",
            ),
        )
        writer_with_grant = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=writer_run.id,
                package_key="pkg_gamma",
                workflow_key="shared_review",
                agent_key="writer_agent",
                namespace_grants=(_namespace_grant(package_key="pkg_gamma", actions=["write"]),),
            ),
        )

        with pytest.raises(RuntimeToolGrantError) as owner_denied:
            _ = owner_without_declaration.query_memory(
                MemoryQuery(scope=namespace.to_scope(), query="runtime grant marker"),
                record_event=False,
            )
        with pytest.raises(RuntimeToolGrantError) as reader_denied:
            _ = reader_without_grant.query_memory(
                MemoryQuery(scope=namespace.to_scope(), query="runtime grant marker"),
                record_event=False,
            )
        with pytest.raises(RuntimeToolGrantError) as writer_denied:
            _ = writer_without_grant.write_memory(
                capability_references=[],
                payload=_write_request_for_context(
                    writer_run.id,
                    workflow_key="shared_review",
                    agent_key="writer_agent",
                    scope=namespace.to_scope(),
                    summary="Denied namespace writer memory.",
                    content="missing namespace write grant cannot add memory.",
                ),
            )
        owner_snippets = owner_with_declaration.query_memory(
            MemoryQuery(
                scope=namespace.to_scope(),
                query="runtime grant marker",
                limit=5,
            ),
            record_event=False,
        )
        reader_snippets = reader_with_grant.query_memory(
            MemoryQuery(
                scope=namespace.to_scope(),
                query="runtime grant marker",
                limit=5,
            ),
            record_event=False,
        )
        writer_created = writer_with_grant.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                writer_run.id,
                workflow_key="shared_review",
                agent_key="writer_agent",
                scope=namespace.to_scope(),
                summary="Granted namespace writer memory.",
                content="write grant can add admin namespace guardrail memory.",
            ),
        )
        entries = list(session.scalars(select(AgentMemoryEntry).order_by(AgentMemoryEntry.id)))

    assert created.provenance.created_by_type == "operator"
    assert owner_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert reader_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert writer_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert [snippet.memory_id for snippet in owner_snippets] == [created.memory_id]
    assert [snippet.memory_id for snippet in reader_snippets] == [created.memory_id]
    assert {entry.memory_id for entry in entries} == {created.memory_id, writer_created.memory_id}
    assert {entry.scope_type for entry in entries} == {"namespace"}
    assert {entry.scope_key for entry in entries} == {namespace.qualified_key}


def test_shared_namespace_owner_and_grant_read_write_semantics(
    session_factory: sessionmaker[Session],
) -> None:
    namespace = _namespace_selector()
    with session_factory() as session:
        owner_run = _seed_run(session)
        reader_run = _seed_run(session)
        writer_run = _seed_run(session)
        owner_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=owner_run.id,
                package_key="pkg_alpha",
                workflow_key="shared_review",
                agent_key="owner_agent",
                namespace_declarations=(namespace,),
            ),
        )
        owner_created = owner_service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                owner_run.id,
                workflow_key="shared_review",
                agent_key="owner_agent",
                scope=namespace.to_scope(),
                summary="Shared namespace owner memory.",
                content="shared namespace signal from the owner package.",
            ),
        )
        _ = owner_service.resolve_memory(
            owner_created.memory_id,
            MemoryOutcome(summary="Owner resolved"),
        )
        reader_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=reader_run.id,
                package_key="pkg_beta",
                workflow_key="shared_review",
                agent_key="reader_agent",
                namespace_grants=(_namespace_grant(package_key="pkg_beta", actions=["read"]),),
            ),
        )
        reader_snippets = reader_service.query_memory(
            MemoryQuery(
                scope=namespace.to_scope(),
                query="shared namespace",
                limit=5,
            ),
            record_event=False,
        )
        writer_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=writer_run.id,
                package_key="pkg_gamma",
                workflow_key="shared_review",
                agent_key="writer_agent",
                namespace_grants=(_namespace_grant(package_key="pkg_gamma", actions=["write"]),),
            ),
        )
        writer_created = writer_service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                writer_run.id,
                workflow_key="shared_review",
                agent_key="writer_agent",
                scope=namespace.to_scope(),
                summary="Shared namespace writer memory.",
                content="write-only grant can add but not read shared namespace memory.",
            ),
        )
        with pytest.raises(RuntimeToolGrantError) as read_denied:
            _ = writer_service.query_memory(
                MemoryQuery(scope=namespace.to_scope(), query="shared namespace"),
                record_event=False,
            )
        entries = list(session.scalars(select(AgentMemoryEntry).order_by(AgentMemoryEntry.id)))

    assert [snippet.memory_id for snippet in reader_snippets] == [owner_created.memory_id]
    assert read_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert read_denied.value.message == MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE
    assert {entry.memory_id for entry in entries} == {
        owner_created.memory_id,
        writer_created.memory_id,
    }
    assert {entry.scope_type for entry in entries} == {"namespace"}
    assert {entry.scope_key for entry in entries} == {namespace.qualified_key}


def test_shared_namespace_access_denied_without_grant_and_global_search_denied(
    session_factory: sessionmaker[Session],
) -> None:
    namespace = _namespace_selector()
    with session_factory() as session:
        owner_run = _seed_run(session)
        other_run = _seed_run(session)
        owner_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=owner_run.id,
                package_key="pkg_alpha",
                workflow_key="shared_review",
                agent_key="owner_agent",
                namespace_declarations=(namespace,),
            ),
        )
        created = owner_service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                owner_run.id,
                workflow_key="shared_review",
                agent_key="owner_agent",
                scope=namespace.to_scope(),
                summary="Shared namespace denial memory.",
                content="missing grants must not reveal this namespace memory.",
            ),
        )
        unauthorized_service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=other_run.id,
                package_key="pkg_beta",
                workflow_key="shared_review",
                agent_key="reader_agent",
            ),
        )

        with pytest.raises(RuntimeToolGrantError) as namespace_denied:
            _ = unauthorized_service.query_memory(
                MemoryQuery(scope=namespace.to_scope(), query="denial"),
                record_event=False,
            )
        with pytest.raises(RuntimeToolGrantError) as ownerless_denied:
            _ = MemoryService(
                session,
                current_context=MemoryLookupContext(
                    run_id=other_run.id,
                    package_key="pkg_alpha",
                    workflow_key="shared_review",
                    agent_key="owner_agent",
                ),
            ).write_memory(
                capability_references=[],
                payload=_write_request_for_context(
                    other_run.id,
                    workflow_key="shared_review",
                    agent_key="owner_agent",
                    scope=namespace.to_scope(),
                    summary="Undeclared namespace write.",
                    content="owner packages must declare shared namespaces before writing.",
                ),
            )
        with pytest.raises(RuntimeToolGrantError) as global_denied:
            _ = MemoryService(session).query_memory(MemoryQuery(query="denial"))

    assert created.memory_id.startswith("memory_")
    assert namespace_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert ownerless_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE
    assert global_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE


def test_namespace_validation_rejects_wildcard_grants_ownerless_and_private_cross_package_writes(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ValidationError):
        _ = MemoryNamespaceSelector(owner_package_key="*", namespace_key="shared_research")
    with pytest.raises(ValidationError):
        _ = MemoryNamespaceSelector(owner_package_key="", namespace_key="shared_research")
    with pytest.raises(ValidationError):
        _ = MemoryNamespaceGrant.model_validate(
            {
                "namespace": _namespace_selector().model_dump(mode="json", by_alias=True),
                "subject": {"packageKey": "pkg_beta"},
                "actions": ["*"],
            }
        )

    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key="pkg_alpha",
                workflow_key="private_workflow",
                agent_key="private_agent",
            ),
        )
        with pytest.raises(RuntimeToolGrantError) as private_denied:
            _ = service.write_memory(
                capability_references=[],
                payload=_write_request_for_context(
                    run.id,
                    workflow_key="private_workflow",
                    agent_key="private_agent",
                    scope=MemoryScope(
                        scope_type=MemoryScopeType.PACKAGE,
                        scope_key="pkg_beta",
                    ),
                    summary="Cross-package private memory.",
                    content="private writes must not target another package scope.",
                ),
            )

    assert private_denied.value.code == MEMORY_NAMESPACE_ACCESS_DENIED_CODE


def test_package_runtime_run_scope_default_remains_run_scoped(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                package_key="pkg_default_scope",
                workflow_key="platform_graph_daily_review",
                agent_key="portfolio_manager",
            ),
        )
        created = service.write_memory(
            capability_references=[],
            payload=_write_request(run.id),
        )
        entry = session.scalar(
            select(AgentMemoryEntry).where(AgentMemoryEntry.memory_id == created.memory_id)
        )
        written_event = session.scalar(
            select(RunMemoryEvent).where(
                RunMemoryEvent.memory_id == created.memory_id,
                RunMemoryEvent.event_type == "written",
            )
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(summary="Run resolved"),
        )
        snippets = service.query_memory(
            MemoryQuery(query="compounding", limit=5),
            record_event=False,
        )

    assert entry is not None
    assert entry.scope_type == "run"
    assert entry.scope_key == str(run.id)
    assert written_event is not None
    assert written_event.run_id == run.id
    assert written_event.filters["scope"] == {"scopeType": "run", "scopeKey": str(run.id)}
    assert created.provenance.run_id == run.id
    assert [snippet.memory_id for snippet in snippets] == [created.memory_id]


def test_package_runtime_current_context_lookup_uses_canonical_scope_keys(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        context = MemoryLookupContext(
            run_id=run.id,
            package_key="pkg_current_context",
            workflow_key="shared_workflow",
            agent_key="shared_agent",
            trace_span_id="span-current-context",
        )
        service = MemoryService(session, current_context=context)
        created = service.write_memory(
            capability_references=[],
            payload=_write_request_for_context(
                run.id,
                workflow_key="shared_workflow",
                agent_key="shared_agent",
                scope=MemoryScope(
                    scope_type=MemoryScopeType.WORKFLOW,
                    scope_key="shared_workflow",
                ),
                summary="Current context canonical lookup memory.",
                content="canonical fallback should find this workflow memory.",
            ),
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(summary="Workflow resolved"),
        )
        snippets = service.query_memory(MemoryQuery(query="canonical fallback", limit=5))
        retrieval_event = session.scalar(
            select(RunMemoryEvent)
            .where(
                RunMemoryEvent.run_id == run.id,
                RunMemoryEvent.event_type == "retrieved",
            )
            .order_by(RunMemoryEvent.id.desc())
        )

    assert [snippet.memory_id for snippet in snippets] == [created.memory_id]
    assert retrieval_event is not None
    effective_scopes = [
        (item["scope"]["scopeType"], item["scope"]["scopeKey"])
        for item in retrieval_event.filters["effective"]
    ]
    assert ("workflow", "pkg_current_context:shared_workflow") in effective_scopes
    assert ("agent", "pkg_current_context:shared_agent") in effective_scopes
    assert ("workflow", "shared_workflow") not in effective_scopes
    assert ("agent", "shared_agent") not in effective_scopes
    assert retrieval_event.filters["context"] == {
        "runId": run.id,
        "packageKey": "pkg_current_context",
        "workflowKey": "shared_workflow",
        "agentKey": "shared_agent",
        "traceSpanId": "span-current-context",
    }


def test_core_memory_service_write_requires_grant_and_creates_no_report(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        with pytest.raises(RuntimeToolGrantError) as exc_info:
            _ = MemoryService(session).write_memory(
                capability_references=_capability_references([MEMORY_LOOKUP_TOOL_KEY]),
                payload=_write_request(),
                grant_policy=MEMORY_WRITE_GRANT_POLICY,
            )
        reports = _reports(session)

    assert exc_info.value.code == MEMORY_TOOL_ACCESS_DENIED_CODE
    assert exc_info.value.message == MEMORY_WRITE_ACCESS_DENIED_MESSAGE
    assert reports == []


def test_core_memory_service_write_returns_canonical_memory_projections(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(session)
        result = service.write_memory(
            capability_references=_capability_references(),
            payload=_write_request(run.id),
            grant_policy=MEMORY_WRITE_GRANT_POLICY,
        )
        entry = service.get_memory(result.memory_id)
        artifacts = service.list_run_artifacts(run.id)
        reports = _reports(session)
        entry_count = _count(session, AgentMemoryEntry)
        revision_count = _count(session, AgentMemoryRevision)
        event_count = _count(session, RunMemoryEvent)

    assert reports == []
    assert entry_count == 1
    assert revision_count == 1
    assert event_count == 1
    assert result.memory_id.startswith("memory_")
    assert not result.memory_id.startswith("mem_")
    assert entry.memory_id == result.memory_id
    assert entry.audit_links is None
    model_payload = result.model_visible_dump()
    assert model_payload["memoryId"] == result.memory_id
    assert "auditLinks" not in model_payload
    assert "reportId" not in model_payload
    assert "reportSlug" not in model_payload
    assert "reportName" not in model_payload

    assert len(artifacts) == 1
    artifact = artifacts[0]
    ui_payload = artifact.dump_for_projection("ui-visible")
    artifact_model_payload = artifact.model_visible_dump()
    assert artifact.memory_id == result.memory_id
    assert ui_payload["sourceGraphMetadata"] == {
        "stepId": "portfolio_decision",
        "slot": "decision",
        "traceId": "trace-abc123",
        "workflowKey": "platform_graph_daily_review",
        "workflowVersion": 5,
    }
    assert "auditLinks" not in artifact_model_payload
    assert "reportSlug" not in str(artifact_model_payload)


def test_core_memory_service_query_binds_current_context_with_finance_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _disable_finance_workspace(session)
        run = _seed_run(session)
        service = MemoryService(session)
        created = service.write_memory(
            capability_references=[],
            payload=_write_request(run.id),
        )
        approved = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(summary="Memory resolved"),
        )
        snippets = service.query_memory(
            MemoryQuery(query="compounding"),
            current_context=MemoryLookupContext(
                run_id=run.id,
                agent_key="portfolio_manager",
                workflow_key="platform_graph_daily_review",
            ),
        )
        reports = _reports(session)

    assert approved.visible_to_workflow is True
    assert [snippet.memory_id for snippet in snippets] == [created.memory_id]
    assert "Long-term compounding memory" in snippets[0].text
    assert reports == []


def test_current_context_fallback_globally_reranks_before_limit(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        context = MemoryLookupContext(
            run_id=run.id,
            package_key="pkg_ranking",
            workflow_key="platform_graph_daily_review",
            agent_key="portfolio_manager",
        )
        service = MemoryService(session, current_context=context)
        run_scoped = service.write_memory(
            capability_references=[],
            payload=_write_request(run.id).model_copy(
                update={
                    "scope": MemoryScope(
                        scope_type=MemoryScopeType.RUN,
                        scope_key=str(run.id),
                    ),
                    "summary": "Run scoped shared ranking memory.",
                    "content": "shared ranking signal from the broad run scope.",
                }
            ),
        )
        agent_scoped = service.write_memory(
            capability_references=[],
            payload=_write_request(run.id).model_copy(
                update={
                    "scope": MemoryScope(
                        scope_type=MemoryScopeType.AGENT,
                        scope_key="portfolio_manager",
                    ),
                    "summary": "Agent scoped shared ranking memory.",
                    "content": "shared ranking signal from the tight agent scope.",
                }
            ),
        )
        _ = service.resolve_memory(
            run_scoped.memory_id,
            MemoryOutcome(summary="Run resolved"),
        )
        _ = service.resolve_memory(
            agent_scoped.memory_id,
            MemoryOutcome(summary="Agent resolved"),
        )

        snippets = service.query_memory(MemoryQuery(query="shared ranking", limit=1))

    assert [snippet.memory_id for snippet in snippets] == [agent_scoped.memory_id]
    assert snippets[0].retrieval_score is not None
    assert snippets[0].retrieval_score.scope_specificity == 5


def test_core_memory_query_uses_lexical_candidates_and_records_score_provenance(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source_run = _seed_run(session)
        retrieval_run = _seed_run(session)
        package_key = "pkg_lexical"
        scope = MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key=package_key)
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=source_run.id,
                package_key=package_key,
                workflow_key="platform_graph_daily_review",
                agent_key="portfolio_manager",
            ),
        )
        first_created = service.write_memory(
            capability_references=[],
            payload=_write_request(source_run.id).model_copy(
                update={
                    "scope": scope,
                    "summary": "Alpha lexical memory.",
                    "content": "alpha sizing guardrail should remain easy to find.",
                }
            ),
        )
        second_created = service.write_memory(
            capability_references=[],
            payload=_write_request(source_run.id).model_copy(
                update={
                    "scope": scope,
                    "summary": "Alpha margin memory.",
                    "content": "alpha margin expansion should influence position sizing.",
                }
            ),
        )
        _ = service.resolve_memory(
            first_created.memory_id,
            MemoryOutcome(summary="First resolved"),
        )
        _ = service.resolve_memory(
            second_created.memory_id,
            MemoryOutcome(summary="Second resolved"),
        )

        snippets = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=retrieval_run.id,
                package_key=package_key,
                workflow_key="platform_graph_daily_review",
                agent_key="portfolio_manager",
            ),
        ).query_memory(
            MemoryQuery(
                scope=scope,
                query="alpha",
                limit=5,
            )
        )
        events = list(
            session.scalars(
                select(RunMemoryEvent)
                .where(RunMemoryEvent.run_id == retrieval_run.id)
                .order_by(RunMemoryEvent.id)
            )
        )

    assert {snippet.memory_id for snippet in snippets} == {
        first_created.memory_id,
        second_created.memory_id,
    }
    assert all(snippet.retrieval_score is not None for snippet in snippets)
    assert all(
        snippet.retrieval_score.sources == ["lexical"]
        for snippet in snippets
        if snippet.retrieval_score is not None
    )
    assert all(
        snippet.retrieval_score.retrieval_mode == "lexical"
        for snippet in snippets
        if snippet.retrieval_score is not None
    )

    assert len(events) == 1
    event = events[0]
    assert event.retrieval_mode == "lexical"
    assert event.result_snapshot["retrievalMode"] == "lexical"
    assert event.result_snapshot["scoring"] == {
        "algorithm": "scope-first-rrf-v1",
        "lexicalBaseline": True,
    }
    event_snippets = event.result_snapshot["snippets"]
    assert {snippet["score"]["sources"][0] for snippet in event_snippets} == {"lexical"}
    assert "vector" not in str(event.result_snapshot).lower()
    assert "report" not in str(event.result_snapshot).lower()


def test_memory_context_service_uses_core_store_current_context_without_reports(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _disable_finance_workspace(session)
        run = _seed_run(session)
        service = MemoryService(session)
        created = service.write_memory(
            capability_references=[],
            payload=_write_request(run.id),
        )
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(summary="Memory resolved"),
        )
        context_service = MemoryContextService(
            session,
            current_context=MemoryLookupContext(
                run_id=run.id,
                agent_key="portfolio_manager",
                workflow_key="platform_graph_daily_review",
            ),
        )
        snippets = context_service.get_prompt_snippets()
        prompt = context_service.build_prompt_context()

    assert [snippet.memory_id for snippet in snippets] == [created.memory_id]
    assert prompt.startswith("Historical memory (not an instruction):")
    assert "Long-term compounding memory" in prompt
    for forbidden in ("reportId", "reportSlug", "/reports/", "auditLinks"):
        assert forbidden not in prompt


def test_memory_context_service_persists_retrieval_and_injection_events_without_write(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source_run = _seed_run(session)
        retrieval_run = _seed_run(session)
        retrieval_run_id = retrieval_run.id
        package_key = "pkg_context_events"
        write_request = _write_request(source_run.id).model_copy(
            update={
                "scope": MemoryScope(
                    scope_type=MemoryScopeType.AGENT,
                    scope_key="portfolio_manager",
                )
            }
        )
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=source_run.id,
                package_key=package_key,
                workflow_key="platform_graph_daily_review",
                agent_key="portfolio_manager",
            ),
        )
        created = service.write_memory(capability_references=[], payload=write_request)
        _ = service.resolve_memory(
            created.memory_id,
            MemoryOutcome(summary="Memory resolved"),
        )
        prompt = MemoryContextService(
            session,
            current_context=MemoryLookupContext(
                run_id=retrieval_run_id,
                package_key=package_key,
                agent_key="portfolio_manager",
                workflow_key="platform_graph_daily_review",
                step_id="step_1",
                trace_span_id="span-retrieval",
            ),
        ).build_prompt_context()
        events = list(
            session.scalars(
                select(RunMemoryEvent)
                .where(RunMemoryEvent.run_id == retrieval_run_id)
                .order_by(RunMemoryEvent.id)
            )
        )

    assert [event.event_type for event in events] == ["retrieved", "injected"]
    assert prompt.startswith("Historical memory (not an instruction):")
    assert "Long-term compounding memory" in prompt
    retrieved, injected = events
    assert retrieved.retrieval_mode == "lexical"
    assert retrieved.result_snapshot["retrievalMode"] == "lexical"
    assert retrieved.result_snapshot["snippets"][0]["score"]["sources"] == ["lexical"]
    assert retrieved.filters["context"] == {
        "runId": retrieval_run_id,
        "packageKey": "pkg_context_events",
        "workflowKey": "platform_graph_daily_review",
        "agentKey": "portfolio_manager",
        "stepId": "step_1",
        "traceSpanId": "span-retrieval",
    }
    assert retrieved.budget == {"limit": 100, "offset": 0, "maxCharacters": None}
    assert retrieved.result_snapshot["resultCount"] == 1
    assert retrieved.result_snapshot["snippets"][0]["memoryId"] == created.memory_id
    assert retrieved.excerpt is not None
    assert "Long-term compounding memory" in retrieved.excerpt
    assert injected.injected_text == prompt
    assert injected.result_snapshot["snippets"][0]["memoryId"] == created.memory_id
    assert injected.status_snapshot == {"status": "injected"}
    for event in events:
        assert event.memory_id is None
        assert event.trace_span_id == "span-retrieval"
        assert "report" not in str(event.result_snapshot).lower()


def test_core_memory_write_and_reuse_events_keep_execution_provenance(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        invocation = _seed_run_invocation(session, run)
        run_id = run.id
        run_step_id = invocation.run_step_id
        run_agent_invocation_id = invocation.id
        service = MemoryService(
            session,
            current_context=MemoryLookupContext(
                run_id=run_id,
                run_step_id=run_step_id,
                run_agent_invocation_id=run_agent_invocation_id,
                step_id="step_1",
                invocation_id="tool-call-1",
                trace_span_id="span-write",
            ),
        )
        payload = _write_request(run_id)
        created = service.write_memory(
            capability_references=_capability_references(),
            payload=payload,
            grant_policy=MEMORY_WRITE_GRANT_POLICY,
        )
        reused = service.write_memory(
            capability_references=_capability_references(),
            payload=payload,
            grant_policy=MEMORY_WRITE_GRANT_POLICY,
        )
        events = list(
            session.scalars(
                select(RunMemoryEvent)
                .where(RunMemoryEvent.run_id == run_id)
                .order_by(RunMemoryEvent.id)
            )
        )

    assert reused.memory_id == created.memory_id
    assert reused.revision_id == created.revision_id
    assert [event.event_type for event in events] == ["written", "reused"]
    for event in events:
        assert event.run_step_id == run_step_id
        assert event.run_agent_invocation_id == run_agent_invocation_id
        assert event.step_id == "step_1"
        assert event.invocation_id == "tool-call-1"
        assert event.memory_id == created.memory_id
        assert event.revision_id == created.revision_id
        assert event.trace_span_id == "span-write"
        assert event.filters["contentHash"] == payload.content_hash()
        assert event.filters["provenance"]["runId"] == run_id
        assert event.budget == {}
    assert events[0].result_snapshot["revisionAction"] == "created"
    assert events[1].result_snapshot["revisionAction"] == "reused"


def test_core_memory_write_rolls_back_when_event_persistence_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        run = _seed_run(session)

        def failing_add_event(self: RunMemoryEventRepository, **fields: object) -> RunMemoryEvent:
            del self, fields
            raise RuntimeError("simulated event persistence failure")

        monkeypatch.setattr(RunMemoryEventRepository, "add_event", failing_add_event)

        with pytest.raises(RuntimeError, match="simulated event persistence failure"):
            _ = MemoryService(session).write_memory(
                capability_references=_capability_references(),
                payload=_write_request(run.id),
                grant_policy=MEMORY_WRITE_GRANT_POLICY,
            )

    with session_factory() as session:
        assert _count(session, AgentMemoryEntry) == 0
        assert _count(session, AgentMemoryRevision) == 0
        assert _count(session, RunMemoryEvent) == 0


def test_core_memory_revision_update_rolls_back_when_event_persistence_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        run = _seed_run(session)
        service = MemoryService(session)
        created = service.write_memory(
            capability_references=_capability_references(),
            payload=_write_request(run.id),
            grant_policy=MEMORY_WRITE_GRANT_POLICY,
        )

        def failing_add_event(
            self: RunMemoryEventRepository,
            **fields: object,
        ) -> RunMemoryEvent:
            del self, fields
            raise RuntimeError("simulated revision event persistence failure")

        monkeypatch.setattr(RunMemoryEventRepository, "add_event", failing_add_event)

        with pytest.raises(RuntimeError, match="simulated revision event persistence failure"):
            _ = service.resolve_memory(
                created.memory_id,
                MemoryOutcome(
                    summary="Resolution should roll back",
                ),
            )

    with session_factory() as session:
        entry = session.scalar(
            select(AgentMemoryEntry).where(AgentMemoryEntry.memory_id == created.memory_id)
        )
        revisions = list(session.scalars(select(AgentMemoryRevision)))
        events = list(session.scalars(select(RunMemoryEvent)))

    assert entry is not None
    assert entry.visible_to_workflow is False
    assert [revision.version for revision in revisions] == [1]
    assert [event.event_type for event in events] == ["written"]
    assert events[0].revision_id == created.revision_id


def test_memory_report_service_boundary_rolls_back_write_when_commit_fails(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        run = _seed_run(session)

        def failing_commit() -> None:
            session.flush()
            raise RuntimeError("simulated memory service commit failure")

        monkeypatch.setattr(session, "commit", failing_commit)

        with pytest.raises(RuntimeError, match="simulated memory service commit failure"):
            _ = MemoryService(session).write_memory(
                capability_references=_capability_references(),
                payload=_write_request(run.id),
                grant_policy=MEMORY_WRITE_GRANT_POLICY,
            )

    with session_factory() as session:
        assert _reports(session) == []
        assert _count(session, AgentMemoryEntry) == 0
        assert _count(session, AgentMemoryRevision) == 0
        assert _count(session, RunMemoryEvent) == 0


def test_memory_report_service_boundary_has_no_new_direct_production_create_call_sites() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    allowed: set[Path] = set()
    direct_call_re = re.compile(
        r"MemoryReportService\([^)]*\)\.create_pending_report\(",
        re.MULTILINE,
    )
    direct_call_sites: set[Path] = set()

    for path in (backend_root / "app").rglob("*.py"):
        relative = path.relative_to(backend_root)
        if direct_call_re.search(path.read_text(encoding="utf-8")):
            direct_call_sites.add(relative)

    assert direct_call_sites == allowed


def test_post_run_memory_write_seam_uses_canonical_memory_dtos_only() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    seam_files = (
        backend_root / "app/services/run_service.py",
        backend_root / "app/services/memory_service.py",
    )
    forbidden_tokens = (
        "AgentMemoryReportCreateMetadata",
        "AgentMemoryTrustedCreateContext",
        "write_request_from_report_create",
        "app.schemas.memory_report",
    )

    for path in seam_files:
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(backend_root)
        for token in forbidden_tokens:
            assert token not in source, f"{relative} still leaks report-shaped memory DTO {token}"
