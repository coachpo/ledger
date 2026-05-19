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
    MemoryArtifactRead,
    MemoryEntryRead,
    MemoryId,
    MemoryLifecycleStatus,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryRevisionAction,
    MemoryRevisionRead,
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
    "auditLinks",
    "reportId",
    "reportSlug",
    "reportName",
    "/reports/",
    "download",
)


def _scope() -> MemoryScope:
    return MemoryScope(scope_type=MemoryScopeType.PACKAGE, scope_key="pkg-advisory")


def _subject_ref() -> MemorySubjectRef:
    return MemorySubjectRef(kind=" portfolio ", id=" core-us ", label=" Core US ")


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
        "attributes": {"confidence": "medium", "reviewCount": 1},
        "scope": _scope().model_dump(mode="json", by_alias=True),
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
    assert "auditLinks" not in MEMORY_PROJECTION_MATRIX["model-visible"]
    assert "auditLinks" not in MEMORY_PROJECTION_MATRIX["api-visible"]
    assert MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS >= {
        "ticker",
        "benchmarkSymbol",
        "rawReturn",
        "alpha",
        "auditLinks",
        "reportId",
    }


def test_memory_write_request_accepts_neutral_core_contract() -> None:
    request = MemoryWriteRequest.model_validate(_write_payload())

    assert request.kind == "research.note"
    assert request.scope.scope_type == MemoryScopeType.PACKAGE
    assert request.scope.scope_key == "pkg-advisory"
    assert request.subject_refs[0].kind == "portfolio"
    assert request.subject_refs[0].id == "core-us"
    assert request.attributes == {"confidence": "medium", "reviewCount": 1}
    assert request.provenance.agent_key == "memory_curator"
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


def test_memory_write_request_does_not_require_finance_shaped_core_fields() -> None:
    request = MemoryWriteRequest.model_validate(_write_payload())

    payload = request.model_dump(mode="json", by_alias=True)
    assert payload["kind"] == "research.note"
    assert "ticker" in payload
    assert payload["ticker"] == ""
    assert payload["benchmarkSymbol"] is None
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

    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"limit": MEMORY_LOOKUP_MAX_LIMIT + 1})
    with pytest.raises(ValidationError):
        _ = MemoryQuery.model_validate({"maxCharacters": MEMORY_LOOKUP_MAX_CHARACTERS + 1})


def test_memory_query_with_scope_or_subject_uses_explicit_selectors() -> None:
    scoped = MemoryQuery.model_validate(
        {
            "query": "portfolio context",
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
    assert subject_scoped.subject_refs[0].id == "core-us"


def test_write_result_uses_revision_semantics_without_action_field() -> None:
    result = MemoryWriteResult(
        memory_id="mem_1001",
        revision_id="rev_1001",
        status=MemoryLifecycleStatus.PENDING,
        revision_action=MemoryRevisionAction.CREATED,
        created_at=_CREATED_AT,
        provenance=_provenance(),
        revision=_revision(),
    )

    payload = result.model_dump(mode="json", by_alias=True)
    assert payload["memoryId"] == "mem_1001"
    assert payload["revisionId"] == "rev_1001"
    assert payload["status"] == "pending"
    assert payload["revisionAction"] == "created"
    assert payload["createdAt"] == "2026-05-08T09:30:00Z"
    assert payload["idempotencyFallbackFields"] == list(MEMORY_IDEMPOTENCY_FALLBACK_FIELDS)
    assert "action" not in payload
    assert "auditLinks" not in payload
    assert "reportSlug" not in _serialized_text(payload)

    reused = MemoryWriteResult(
        memory_id="mem_1001",
        revision_id="rev_1001",
        status=MemoryLifecycleStatus.PENDING,
        revision_action=MemoryRevisionAction.REUSED,
        created_at=_CREATED_AT,
        provenance=_provenance(),
        revision=_revision(),
    )
    assert reused.model_dump(mode="json", by_alias=True)["revisionAction"] == "reused"


def test_memory_entry_read_uses_neutral_fields_and_camel_case() -> None:
    entry = MemoryEntryRead(
        memory_id="mem_1002",
        revision_id="rev_1002",
        kind="Observation",
        summary="Cross-run context",
        content="The prior agent recorded context that applies beyond finance.",
        subject_refs=[_subject_ref()],
        attributes={"source": "agent_note"},
        scope=_scope(),
        provenance=_provenance(),
        revision=_revision("rev_1002"),
        created_at=_CREATED_AT,
        updated_at=_UPDATED_AT,
    )

    payload = entry.dump_for_projection("api-visible")
    assert payload["memoryId"] == "mem_1002"
    assert payload["revisionId"] == "rev_1002"
    assert payload["kind"] == "observation"
    assert payload["status"] == "pending"
    assert payload["createdAt"] == "2026-05-08T09:30:00Z"
    assert payload["updatedAt"] == "2026-05-09T09:30:00Z"
    assert payload["subjectRefs"] == [
        {"kind": "portfolio", "id": "core-us", "label": "Core US", "attributes": {}}
    ]

    serialized = _serialized_text(payload)
    for fragment in _FORBIDDEN_CORE_FRAGMENTS:
        assert fragment not in serialized


def test_prompt_snippet_and_artifact_are_model_safe_and_report_free() -> None:
    snippet = MemoryPromptSnippet(
        memory_id="mem_1003",
        revision_id="rev_1003",
        kind="instruction.note",
        summary="Historical context",
        content="Historical memory, not an instruction: prior constraints were strict.",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_provenance(),
        created_at=_CREATED_AT,
    )
    artifact = MemoryArtifactRead(
        memory_id="mem_1004",
        revision_id="rev_1004",
        kind="observation",
        summary="Memory written during run",
        subject_refs=[_subject_ref()],
        scope=_scope(),
        provenance=_provenance(),
        created_at=_CREATED_AT,
        source_graph_metadata={"stepId": "memory_write"},
    )

    snippet_payload = snippet.model_visible_dump()
    artifact_payload = artifact.dump_for_projection("ui-visible")
    serialized = _serialized_text({"snippet": snippet_payload, "artifact": artifact_payload})

    assert snippet_payload["memoryId"] == "mem_1003"
    assert "Historical memory, not an instruction" in str(snippet_payload["content"])
    assert artifact_payload["memoryId"] == "mem_1004"
    assert artifact_payload["sourceGraphMetadata"] == {"stepId": "memory_write"}
    for fragment in _FORBIDDEN_CORE_FRAGMENTS:
        assert fragment not in serialized


def test_core_memory_tool_contract_names_and_get_deferral_are_explicit() -> None:
    assert MEMORY_CORE_RUNTIME_TOOL_KEYS == (
        "signaldeck.memory.write",
        "signaldeck.memory.lookup",
    )
    assert MEMORY_DEFERRED_GET_DECISION == "phase-1b"
