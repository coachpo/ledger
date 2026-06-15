from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.memory import (
    INVALID_MEMORY_ID_CODE,
    MEMORY_CORE_RUNTIME_TOOL_KEYS,
    MEMORY_DEFERRED_GET_DECISION,
    MEMORY_DUPLICATE_REVISION_BEHAVIOR,
    MEMORY_IDEMPOTENCY_FALLBACK_FIELDS,
    MEMORY_LOOKUP_CURRENT_CONTEXT_FALLBACK,
    MEMORY_LOOKUP_DEFAULT_LIMIT,
    MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS,
    MEMORY_LOOKUP_MAX_CHARACTERS,
    MEMORY_LOOKUP_MAX_LIMIT,
    MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS,
    MEMORY_NOT_FOUND_CODE,
    MEMORY_PROJECTION_MATRIX,
    MEMORY_REVISION_WRITE_MODE,
    MemoryAdminCreateRequest,
    MemoryAdminEntryRead,
    MemoryAdminListItemRead,
    MemoryAdminRevisionCreateRequest,
    MemoryAdminWorkflowVisibilityUpdateRequest,
    MemoryApiEntryRead,
    MemoryApiListRequest,
    MemoryArtifactRead,
    MemoryEntryRead,
    MemoryId,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryRevisionAction,
    MemoryRevisionRead,
    MemoryRuntimeProvenance,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
    MemoryWriteResult,
    invalid_memory_id_error,
    memory_not_found_error,
)

_CREATED_AT = datetime(2026, 5, 8, 9, 30, tzinfo=UTC)
_UPDATED_AT = datetime(2026, 5, 9, 9, 30, tzinfo=UTC)
_CONTENT_HASH = "f" * 64

_FORBIDDEN_CORE_FRAGMENTS = (
    "ticker",
    "benchmarkSymbol",
    "rawReturn",
    "alpha",
    "attributes",
    "auditLinks",
    "reportId",
    "reportSlug",
    "reportName",
    "/reports/",
    "download",
    "tags",
    "agentVersion",
    "workflowVersion",
)


def _scope() -> MemoryScope:
    return MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key="pkg-advisory")


def _subject_ref() -> MemorySubjectRef:
    return MemorySubjectRef(kind=" topic ", id=" drawdown-risk ", label=" Drawdown Risk ")


def _provenance() -> MemoryProvenance:
    return MemoryProvenance.model_validate(
        {
            "runId": 42,
            "agentKey": " memory_curator ",
            "agentVersion": 3,
            "agentName": "Memory Curator",
            "workflowKey": "daily_review",
            "workflowVersion": 7,
            "stepId": "memory_write",
            "slot": "post_run_note",
            "traceId": "trace-abc123",
        }
    )


def _runtime_provenance() -> MemoryRuntimeProvenance:
    return MemoryRuntimeProvenance.model_validate(
        {
            "runId": 42,
            "agentKey": " memory_curator ",
            "workflowKey": "daily_review",
            "stepId": "memory_write",
            "slot": "post_run_note",
        }
    )


def _revision(revision_id: str = "rev_1001") -> MemoryRevisionRead:
    return MemoryRevisionRead(
        revision_id=revision_id,
        version=1,
        content_hash=_CONTENT_HASH,
        created_at=_CREATED_AT,
    )


def _write_payload() -> dict[str, object]:
    return {
        "kind": " Research.Note ",
        "summary": "Reusable risk-context note.",
        "content": "Historical drawdown context should be reviewed before sizing.",
        "subjectRefs": [
            _subject_ref().model_dump(mode="json", by_alias=True),
        ],
        "scope": _scope().model_dump(mode="json", by_alias=True),
        "provenance": _runtime_provenance().model_dump(mode="json", by_alias=True),
    }


def _admin_write_payload() -> dict[str, object]:
    return {
        **_write_payload(),
        "provenance": _provenance().model_dump(mode="json", by_alias=True),
    }


def _serialized_text(payload: object) -> str:
    return str(payload)


def test_memory_id_is_opaque_phase_1_identity() -> None:
    memory_id = MemoryId(value=" mem_123 ")
    future_memory_id = MemoryId(value="memory-provider-token")

    assert memory_id.value == "mem_123"
    assert memory_id.model_dump(mode="json", by_alias=True) == {"value": "mem_123"}
    assert future_memory_id.value == "memory-provider-token"


def test_memory_domain_errors_are_sanitized() -> None:
    invalid_error = invalid_memory_id_error()
    not_found_error = memory_not_found_error()

    assert invalid_error.code == INVALID_MEMORY_ID_CODE
    assert invalid_error.status_code == 400
    assert invalid_error.message == "Invalid memory id"
    assert invalid_error.details == []
    assert not_found_error.code == MEMORY_NOT_FOUND_CODE
    assert not_found_error.status_code == 404
    assert not_found_error.message == "Memory not found"

    serialized = _serialized_text(
        {
            "invalid": invalid_error.__dict__,
            "notFound": not_found_error.__dict__,
        }
    )
    assert "report" not in serialized.lower()
    assert "/reports/" not in serialized


def test_projection_matrix_documents_neutral_visibility_surfaces() -> None:
    assert set(MEMORY_PROJECTION_MATRIX) == {"model-visible", "api-visible", "ui-visible"}
    assert "kind" in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "summary" in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "content" in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "status" not in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "visibleToWorkflow" not in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "visibleToWorkflow" in MEMORY_PROJECTION_MATRIX["api-visible"]
    assert "visibleToWorkflow" in MEMORY_PROJECTION_MATRIX["ui-visible"]
    assert "status" not in MEMORY_PROJECTION_MATRIX["api-visible"]
    assert "status" not in MEMORY_PROJECTION_MATRIX["ui-visible"]
    assert "auditLinks" not in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "auditLinks" not in MEMORY_PROJECTION_MATRIX["api-visible"]
    assert MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS >= {"reportId", "reportSlug", "reportName"}
    assert "auditLinks" not in MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS
    assert "ticker" not in MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS
    assert "portfolioSlug" not in MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS


def test_memory_write_request_accepts_neutral_core_contract() -> None:
    request = MemoryWriteRequest.model_validate(_write_payload())

    assert request.kind == "research.note"
    assert request.scope.scope_type == MemoryScopeType.PACKAGE
    assert request.scope.scope_key == "pkg-advisory"
    assert request.subject_refs[0].kind == "topic"
    assert request.subject_refs[0].id == "drawdown-risk"
    assert request.provenance.agent_key == "memory_curator"
    assert not hasattr(request.provenance, "agent_version")
    assert request.revision.mode == MEMORY_REVISION_WRITE_MODE
    assert request.revision.duplicate_content == MEMORY_DUPLICATE_REVISION_BEHAVIOR
    assert request.idempotency_key is None
    assert request.idempotency_fallback_fields == MEMORY_IDEMPOTENCY_FALLBACK_FIELDS

    identity = request.idempotency_fallback_identity()
    assert tuple(identity) == MEMORY_IDEMPOTENCY_FALLBACK_FIELDS
    assert identity["scope_type"] == "package"
    assert identity["scope_key"] == "pkg-advisory"
    assert identity["kind"] == "research.note"
    assert isinstance(identity["content_hash"], str)
    assert len(identity["content_hash"]) == 64
    assert identity["source_run_id"] == 42
    assert identity["source_agent_key"] == "memory_curator"
    assert identity["source_step_id"] == "memory_write"
    assert identity["source_slot"] == "post_run_note"

    with pytest.raises(ValidationError):
        _ = MemorySubjectRef.model_validate(
            {"kind": "topic", "id": "drawdown-risk", "attributes": {"ticker": "SPY"}}
        )
    with pytest.raises(ValidationError):
        _ = MemoryWriteRequest.model_validate(
            {**_write_payload(), "attributes": {"confidence": "medium"}}
        )
    with pytest.raises(ValidationError):
        _ = MemoryWriteRequest.model_validate(
            {
                **_write_payload(),
                "provenance": _provenance().model_dump(mode="json", by_alias=True),
            }
        )


def test_memory_write_request_forbidden_core_fields_are_absent() -> None:
    request = MemoryWriteRequest.model_validate(_write_payload())

    payload = request.model_dump(mode="json", by_alias=True)
    assert payload["kind"] == "research.note"
    assert "attributes" not in payload
    assert "ticker" not in payload
    assert "benchmarkSymbol" not in payload
    assert "portfolioSlug" not in payload
    assert "tags" not in payload
    assert request.idempotency_fallback_fields == MEMORY_IDEMPOTENCY_FALLBACK_FIELDS


def test_memory_query_defaults_to_current_context_fallback_and_budgets() -> None:
    query = MemoryQuery.model_validate({"query": " drawdown "})
    payload = query.model_dump(mode="json", by_alias=True)

    assert query.query == "drawdown"
    assert query.scope is None
    assert query.subject_refs == []
    assert query.scope_mode == "current-context-fallback"
    assert query.fallback_scope == MEMORY_LOOKUP_CURRENT_CONTEXT_FALLBACK
    assert query.limit == MEMORY_LOOKUP_DEFAULT_LIMIT
    assert query.max_characters == MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS
    assert payload["scopeMode"] == "current-context-fallback"
    assert payload["fallbackScope"] == "current-run-package-agent"
    assert "status" not in payload
    assert "visibleToWorkflow" not in payload
    assert "tags" not in payload

    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"limit": MEMORY_LOOKUP_MAX_LIMIT + 1})
    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"maxCharacters": MEMORY_LOOKUP_MAX_CHARACTERS + 1})
    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"status": "approved"})
    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"tags": ["finance"]})


def test_memory_query_with_scope_or_subject_uses_explicit_selectors() -> None:
    scoped = MemoryQuery.model_validate(
        {
            "query": "risk context",
            "scope": _scope().model_dump(mode="json", by_alias=True),
        }
    )
    subject_scoped = MemoryQuery.model_validate(
        {
            "subjectRefs": [_subject_ref().model_dump(mode="json", by_alias=True)],
            "kind": "Research.Note",
        }
    )

    assert scoped.scope_mode == "explicit-selectors"
    assert scoped.scope is not None
    assert subject_scoped.scope_mode == "explicit-selectors"
    assert subject_scoped.kind == "research.note"
    assert subject_scoped.subject_refs[0].id == "drawdown-risk"


def test_api_list_request_removes_status_filter_from_query_contract() -> None:
    request = MemoryApiListRequest.model_validate(
        {
            "accessContext": {"packageKey": "pkg", "workflowKey": None, "agentKey": None},
            "scope": _scope().model_dump(mode="json", by_alias=True),
            "query": "risk",
        }
    )
    query = request.to_query()
    payload = request.model_dump(mode="json", by_alias=True)
    query_payload = query.model_dump(mode="json", by_alias=True)

    assert payload["visibility"] == "explicit-scope"
    assert query.scope_mode == "explicit-selectors"
    assert "status" not in payload
    assert "status" not in query_payload
    assert "visibleToWorkflow" not in query_payload
    assert "tags" not in payload
    assert "tags" not in query_payload
    with pytest.raises(ValidationError):
        _ = MemoryApiListRequest.model_validate(
            {
                "accessContext": {"packageKey": "pkg", "workflowKey": None, "agentKey": None},
                "scope": _scope().model_dump(mode="json", by_alias=True),
                "status": "approved",
            }
        )
    with pytest.raises(ValidationError):
        _ = MemoryApiListRequest.model_validate(
            {
                "accessContext": {"packageKey": "pkg", "workflowKey": None, "agentKey": None},
                "scope": _scope().model_dump(mode="json", by_alias=True),
                "tags": ["finance"],
            }
        )


def test_write_result_uses_revision_semantics_without_action_field() -> None:
    result = MemoryWriteResult(
        memory_id="mem_1001",
        revision_id="rev_1001",
        visible_to_workflow=True,
        revision_action=MemoryRevisionAction.CREATED,
        created_at=_CREATED_AT,
        provenance=_runtime_provenance(),
        revision=_revision(),
    )

    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["memoryId"] == "mem_1001"
    assert payload["revisionId"] == "rev_1001"
    assert payload["visibleToWorkflow"] is True
    assert "status" not in payload
    assert payload["revisionAction"] == "created"
    assert payload["createdAt"] == "2026-05-08T09:30:00Z"
    assert payload["idempotencyFallbackFields"] == list(MEMORY_IDEMPOTENCY_FALLBACK_FIELDS)
    assert "action" not in payload
    assert "auditLinks" not in payload
    assert "reportSlug" not in _serialized_text(payload)

    with pytest.raises(ValidationError):
        _ = MemoryWriteResult.model_validate(
            {
                "memoryId": "mem_1001",
                "revisionId": "rev_1001",
                "status": "pending",
                "revisionAction": "created",
                "createdAt": _CREATED_AT,
                "provenance": _runtime_provenance().model_dump(mode="json", by_alias=True),
                "revision": _revision().model_dump(mode="json", by_alias=True),
            }
        )

    reused = MemoryWriteResult(
        memory_id="mem_1001",
        revision_id="rev_1001",
        revision_action=MemoryRevisionAction.REUSED,
        created_at=_CREATED_AT,
        provenance=_runtime_provenance(),
        revision=_revision(),
    )
    reused_payload = reused.model_dump(mode="json", by_alias=True)
    assert reused_payload["revisionAction"] == "reused"
    assert reused_payload["visibleToWorkflow"] is False


def test_memory_entry_read_uses_neutral_fields_and_camel_case() -> None:
    entry = MemoryEntryRead(
        memory_id="mem_1002",
        revision_id="rev_1002",
        visible_to_workflow=True,
        kind="Observation",
        summary="Cross-run context",
        content="The prior agent recorded context that applies across workflows.",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_runtime_provenance(),
        revision=_revision("rev_1002"),
        created_at=_CREATED_AT,
        updated_at=_UPDATED_AT,
    )

    payload = entry.dump_for_projection("api-visible")
    assert payload["memoryId"] == "mem_1002"
    assert payload["revisionId"] == "rev_1002"
    assert payload["kind"] == "observation"
    assert payload["visibleToWorkflow"] is True
    assert "status" not in payload
    assert payload["createdAt"] == "2026-05-08T09:30:00Z"
    assert payload["updatedAt"] == "2026-05-09T09:30:00Z"
    assert payload["subjectRefs"] == [
        {"kind": "topic", "id": "drawdown-risk", "label": "Drawdown Risk"}
    ]
    assert "attributes" not in payload
    model_payload = entry.model_visible_dump()
    assert "visibleToWorkflow" not in model_payload
    assert "status" not in model_payload
    assert "attributes" not in model_payload

    api_entry_payload = MemoryApiEntryRead.from_entry(entry).model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    assert "attributes" not in api_entry_payload

    serialized = _serialized_text(payload)
    for fragment in _FORBIDDEN_CORE_FRAGMENTS:
        assert fragment not in serialized

    with pytest.raises(ValidationError):
        _ = MemoryEntryRead.model_validate(
            {
                **entry.model_dump(mode="json", by_alias=True),
                "attributes": {"source": "agent_note"},
            }
        )
    with pytest.raises(ValidationError):
        _ = MemoryApiEntryRead.model_validate(
            {
                **api_entry_payload,
                "attributes": {"source": "agent_note"},
            }
        )


def test_admin_memory_dtos_forbidden_metadata_fields_are_absent() -> None:
    entry = MemoryAdminEntryRead(
        memory_id="memory_admin_1001",
        revision_id="revision_admin_1001",
        visible_to_workflow=True,
        kind="research.note",
        summary="Admin canonical memory.",
        content="Operator managed canonical memory without report history.",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_runtime_provenance(),
        revision=_revision("revision_admin_1001"),
        created_at=_CREATED_AT,
        updated_at=_UPDATED_AT,
    )
    item = MemoryAdminListItemRead(
        memory_id=entry.memory_id,
        revision_id=entry.revision_id,
        visible_to_workflow=entry.visible_to_workflow,
        kind=entry.kind,
        summary=entry.summary,
        excerpt="Operator managed canonical memory excerpt.",
        subject_refs=entry.subject_refs,
        scope=entry.scope,
        provenance=entry.provenance,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        last_event_type="operator_created",
    )

    payload = {
        "entry": entry.model_dump(mode="json", by_alias=True, exclude_none=True),
        "item": item.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    serialized = _serialized_text(payload)

    assert payload["entry"]["memoryId"] == "memory_admin_1001"
    assert payload["entry"]["visibleToWorkflow"] is True
    assert payload["item"]["visibleToWorkflow"] is True
    assert "status" not in payload["entry"]
    assert "status" not in payload["item"]
    assert "attributes" not in payload["entry"]
    assert "auditLinks" not in payload["entry"]
    assert payload["item"]["lastEventType"] == "operator_created"
    forbidden_fragments = (
        *_FORBIDDEN_CORE_FRAGMENTS,
        "rawMarkdown",
        "reportHistory",
        "downloadUrl",
    )
    for fragment in forbidden_fragments:
        assert fragment not in serialized

    with pytest.raises(ValidationError):
        _ = MemoryAdminEntryRead.model_validate(
            {
                **payload["entry"],
                "attributes": {"confidence": "high"},
            }
        )

    with pytest.raises(ValidationError):
        _ = MemoryAdminEntryRead.model_validate(
            {
                **payload["entry"],
                "auditLinks": {"references": []},
            }
        )


def test_admin_create_and_visibility_update_use_visible_to_workflow_contract() -> None:
    create_request = MemoryAdminCreateRequest.model_validate(_admin_write_payload())
    create_payload = create_request.model_dump(mode="json", by_alias=True)

    assert create_request.visible_to_workflow is True
    assert create_payload["visibleToWorkflow"] is True
    assert create_payload["provenance"]["agentVersion"] == 3
    assert "attributes" not in create_payload
    assert "status" not in create_payload
    with pytest.raises(ValidationError):
        _ = MemoryAdminCreateRequest.model_validate(
            {**_admin_write_payload(), "status": "approved"}
        )
    with pytest.raises(ValidationError):
        _ = MemoryAdminCreateRequest.model_validate(
            {**_admin_write_payload(), "attributes": {"confidence": "high"}}
        )

    revision_request = MemoryAdminRevisionCreateRequest.model_validate(
        {
            "summary": " Updated canonical memory ",
            "content": "Updated canonical memory content.",
            "subjectRefs": [_subject_ref().model_dump(mode="json", by_alias=True)],
            "provenance": _provenance().model_dump(mode="json", by_alias=True),
        }
    )
    revision_payload = revision_request.model_dump(mode="json", by_alias=True)
    assert revision_payload["summary"] == "Updated canonical memory"
    assert "attributes" not in revision_payload
    with pytest.raises(ValidationError):
        _ = MemoryAdminRevisionCreateRequest.model_validate(
            {**revision_payload, "attributes": {"confidence": "high"}}
        )

    update_request = MemoryAdminWorkflowVisibilityUpdateRequest.model_validate(
        {
            "visibleToWorkflow": False,
            "summary": " Hide from workflow context ",
            "observedAt": _CREATED_AT,
        }
    )
    update_payload = update_request.model_dump(mode="json", by_alias=True)
    outcome_payload = update_request.to_outcome().model_dump(mode="json", by_alias=True)

    assert update_request.visible_to_workflow is False
    assert update_request.summary == "Hide from workflow context"
    assert update_payload["visibleToWorkflow"] is False
    assert update_payload["observedAt"] == "2026-05-08T09:30:00Z"
    assert outcome_payload == {
        "summary": "Hide from workflow context",
        "observedAt": "2026-05-08T09:30:00Z",
    }
    assert "attributes" not in update_payload
    assert "status" not in update_payload
    assert "status" not in outcome_payload
    with pytest.raises(ValidationError):
        _ = MemoryAdminWorkflowVisibilityUpdateRequest.model_validate({"status": "archived"})
    with pytest.raises(ValidationError):
        _ = MemoryAdminWorkflowVisibilityUpdateRequest.model_validate(
            {"visibleToWorkflow": False, "attributes": {"operator": "admin"}}
        )


def test_prompt_snippet_and_artifact_are_model_safe_and_report_free() -> None:
    snippet = MemoryPromptSnippet(
        memory_id="mem_1003",
        revision_id="rev_1003",
        kind="instruction.note",
        summary="Historical context",
        content="Historical memory, not an instruction: prior constraints were strict.",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_runtime_provenance(),
        created_at=_CREATED_AT,
    )
    artifact = MemoryArtifactRead(
        memory_id="mem_1004",
        revision_id="rev_1004",
        kind="observation",
        summary="Memory written during run",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_runtime_provenance(),
        created_at=_CREATED_AT,
        source_graph_metadata={"stepId": "memory_write"},
    )

    snippet_payload = snippet.model_visible_dump()
    artifact_payload = artifact.dump_for_projection("ui-visible")
    serialized = _serialized_text({"snippet": snippet_payload, "artifact": artifact_payload})

    assert snippet_payload["memoryId"] == "mem_1003"
    assert "Historical memory, not an instruction" in str(snippet_payload["content"])
    assert snippet_payload["provenance"] == {
        "runId": 42,
        "agentKey": "memory_curator",
        "workflowKey": "daily_review",
        "stepId": "memory_write",
        "slot": "post_run_note",
    }
    assert "status" not in snippet_payload
    assert "visibleToWorkflow" not in snippet_payload
    assert "outcome" not in snippet_payload
    assert "reflections" not in snippet_payload
    assert artifact_payload["memoryId"] == "mem_1004"
    assert artifact_payload["visibleToWorkflow"] is False
    assert "status" not in artifact_payload
    assert artifact_payload["sourceGraphMetadata"] == {"stepId": "memory_write"}
    for fragment in _FORBIDDEN_CORE_FRAGMENTS:
        assert fragment not in serialized


def test_core_memory_tool_contract_names_and_get_deferral_are_explicit() -> None:
    assert MEMORY_CORE_RUNTIME_TOOL_KEYS == (
        "signaldeck.core.memory.write",
        "signaldeck.core.memory.lookup",
    )
    assert MEMORY_DEFERRED_GET_DECISION == "phase-1b"
