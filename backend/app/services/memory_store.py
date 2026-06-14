from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Final, Protocol, cast
from uuid import uuid4

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.formatting import to_utc, utcnow
from app.models.agent_memory import AgentMemoryEntry, AgentMemoryRevision, RunMemoryEvent
from app.repositories.agent_memory import (
    AgentMemoryEntryRepository,
    AgentMemoryRevisionRepository,
    RunMemoryEventRepository,
)
from app.schemas.memory import (
    MEMORY_API_MAX_EVENTS,
    MEMORY_API_MAX_REVISIONS,
    MEMORY_IDEMPOTENCY_FALLBACK_FIELDS,
    MemoryApiEventRead,
    MemoryApiRevisionRead,
    MemoryArtifactRead,
    MemoryAttributes,
    MemoryAuditLinks,
    MemoryEntryRead,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryRetrievalScore,
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

_LOOKUP_CANDIDATE_MULTIPLIER: Final = 4
_LOOKUP_MAX_CANDIDATES: Final = 200
_MEMORY_SCOPE_KEY_MAX_CHARACTERS: Final = 160
_MEMORY_SCOPE_KEY_HASH_CHARACTERS: Final = 16
_POSTGRES_LOCK_NOT_AVAILABLE_SQLSTATE: Final = "55P03"
_RRF_K: Final = 60.0
_SCOPE_SPECIFICITY: Final[dict[str, int]] = {
    "agent": 5,
    "run": 4,
    "workflow": 3,
    "namespace": 2,
    "package": 2,
}


def canonical_package_qualified_scope_key(*, package_key: str, local_key: str) -> str:
    normalized_package_key = package_key.strip()
    normalized_local_key = local_key.strip()
    candidate = f"{normalized_package_key}:{normalized_local_key}"
    if len(candidate) <= _MEMORY_SCOPE_KEY_MAX_CHARACTERS:
        return candidate

    package_hash = _scope_key_hash(normalized_package_key)
    hashed_candidate = f"{package_hash}:{normalized_local_key}"
    if len(hashed_candidate) <= _MEMORY_SCOPE_KEY_MAX_CHARACTERS:
        return hashed_candidate
    return f"{package_hash}:{_scope_key_hash(normalized_local_key)}"


def _scope_key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_MEMORY_SCOPE_KEY_HASH_CHARACTERS]


@dataclass(frozen=True, slots=True)
class MemoryEventContext:
    run_id: int | None = None
    run_step_id: int | None = None
    run_agent_invocation_id: int | None = None
    run_operation_invocation_id: int | None = None
    step_id: str | None = None
    invocation_id: str | None = None
    trace_span_id: str | None = None


@dataclass(slots=True)
class _RankedLookupCandidate:
    entry: AgentMemoryEntry
    revision: AgentMemoryRevision
    lexical_rank: int
    lexical_score: float | None = None
    score: float = 0.0


class MemoryStore(Protocol):
    def create_hidden(
        self,
        payload: MemoryWriteRequest,
        *,
        event_context: MemoryEventContext | None = None,
    ) -> MemoryWriteResult:
        """Stage a hidden memory write and return the memory-domain result."""
        ...

    def get(self, memory_id: str) -> MemoryEntryRead:
        """Return a memory entry by opaque memory id."""
        ...

    def list_revisions(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[MemoryApiRevisionRead]:
        """Return bounded canonical revisions for a memory entry."""
        ...

    def list_events(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[MemoryApiEventRead]:
        """Return bounded canonical events for a memory entry."""
        ...

    def query(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        """Return bounded model-visible memory snippets."""
        ...

    def resolve(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        """Stage a workflow-visible outcome for an existing memory."""
        ...

    def append_reflection(self, memory_id: str, reflection: MemoryReflection) -> MemoryEntryRead:
        """Stage a reflection append for an existing workflow-visible memory."""
        ...

    def record_review(
        self,
        memory_id: str,
        *,
        event_context: MemoryEventContext | None = None,
        filters: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        result_snapshot: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
    ) -> MemoryEntryRead:
        """Stage a review event for an existing memory without changing content."""
        ...

    def list_artifacts_for_run(self, run_id: int) -> list[MemoryArtifactRead]:
        """Return UI/API-visible memory artifacts for a run."""
        ...

    def audit_links(self, memory_id: str) -> MemoryAuditLinks:
        """Return audit-only links for a memory entry."""
        ...


class PostgresMemoryStore:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.entries = AgentMemoryEntryRepository(session)
        self.revisions = AgentMemoryRevisionRepository(session)
        self.events = RunMemoryEventRepository(session)

    def create_hidden(
        self,
        payload: MemoryWriteRequest,
        *,
        event_context: MemoryEventContext | None = None,
    ) -> MemoryWriteResult:
        existing = self._existing_entry_for_payload(payload)
        if existing is not None:
            revision = self._latest_revision(existing)
            if revision.content_hash != payload.content_hash():
                raise self._memory_conflict()
            self._append_event(
                event_type="reused",
                entry=existing,
                revision=revision,
                event_context=event_context,
                filters=self._write_filters(payload),
                result_snapshot=self._result_snapshot(
                    existing,
                    revision,
                    MemoryRevisionAction.REUSED,
                ),
            )
            self.session.flush()
            return self._write_result(
                existing,
                revision,
                MemoryRevisionAction.REUSED,
                action="existing",
            )

        subject_refs = self._payload_subject_refs(payload)
        attributes = self._attributes_payload(payload.attributes)
        entry = AgentMemoryEntry(
            memory_id=self._new_memory_id(),
            scope_type=payload.scope.scope_type.value,
            scope_key=payload.scope.scope_key,
            kind=payload.kind,
            visible_to_workflow=False,
            summary=payload.summary,
            subject_refs=subject_refs,
            attributes=attributes,
            content_hash=payload.content_hash(),
            idempotency_key=payload.idempotency_key,
            created_by_type=payload.provenance.created_by_type,
            source_run_id=payload.provenance.run_id,
            source_agent_key=payload.provenance.agent_key,
            source_agent_version=payload.provenance.agent_version,
            source_agent_name=payload.provenance.agent_name,
            source_workflow_key=payload.provenance.workflow_key,
            source_workflow_version=payload.provenance.workflow_version,
            source_step_id=payload.provenance.step_id,
            source_slot=payload.provenance.slot,
            source_trace_id=payload.provenance.trace_id,
        )
        self.entries.add(entry)
        self.session.flush()
        self.session.refresh(entry)

        revision = self._create_revision(
            entry,
            summary=payload.summary,
            content=payload.content,
            subject_refs=subject_refs,
            attributes=attributes,
            revision_action=MemoryRevisionAction.CREATED.value,
            supersedes_revision_id=payload.revision.supersedes_revision_id,
            source_run_id=payload.provenance.run_id,
            source_agent_key=payload.provenance.agent_key,
            source_step_id=payload.provenance.step_id,
            source_slot=payload.provenance.slot,
            trace_span_id=payload.provenance.trace_id,
        )
        self._append_event(
            event_type="written",
            entry=entry,
            revision=revision,
            event_context=event_context,
            filters=self._write_filters(payload),
            result_snapshot=self._result_snapshot(
                entry,
                revision,
                MemoryRevisionAction.CREATED,
            ),
        )
        self.session.flush()
        return self._write_result(entry, revision, MemoryRevisionAction.CREATED, action="created")

    def get(self, memory_id: str) -> MemoryEntryRead:
        entry = self._entry_by_memory_id(memory_id)
        revision = self._latest_revision(entry)
        return self._entry_read(entry, revision)

    def list_revisions(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[MemoryApiRevisionRead]:
        entry = self._entry_by_memory_id(memory_id)
        bounded_limit = min(limit, MEMORY_API_MAX_REVISIONS)
        statement = (
            select(AgentMemoryRevision)
            .where(AgentMemoryRevision.memory_entry_id == entry.id)
            .order_by(AgentMemoryRevision.version.asc(), AgentMemoryRevision.id.asc())
            .offset(offset)
            .limit(bounded_limit)
        )
        return [self._api_revision_read(revision) for revision in self.session.scalars(statement)]

    def list_events(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[MemoryApiEventRead]:
        entry = self._entry_by_memory_id(memory_id)
        bounded_limit = min(limit, MEMORY_API_MAX_EVENTS)
        statement = (
            select(RunMemoryEvent)
            .where(
                or_(
                    RunMemoryEvent.memory_entry_id == entry.id,
                    RunMemoryEvent.memory_id == entry.memory_id,
                )
            )
            .order_by(RunMemoryEvent.created_at.asc(), RunMemoryEvent.id.asc())
            .offset(offset)
            .limit(bounded_limit)
        )
        return [self._api_event_read(event) for event in self.session.scalars(statement)]

    def query(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        if not self._has_lookup_selector(query):
            return []
        ranked_candidates = self._rank_lookup_candidates(query)
        snippets: list[MemoryPromptSnippet] = []
        used_characters = 0
        max_characters = cast(int | None, query.max_characters)
        for candidate in ranked_candidates[query.offset :]:
            snippet = self._prompt_snippet(
                candidate.entry,
                candidate.revision,
                retrieval_score=self._retrieval_score(candidate),
            )
            separator_characters = 2 if snippets else 0
            next_size = used_characters + separator_characters + len(snippet.text)
            if max_characters is not None and next_size > max_characters:
                break
            snippets.append(snippet)
            used_characters = next_size
            if len(snippets) >= query.limit:
                break
        return snippets

    def resolve(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        entry = self._locked_entry_by_memory_id(memory_id)
        latest = self._latest_revision(entry)
        attributes = self._attributes_payload(latest.attributes)
        attributes["outcome"] = self._outcome_payload(outcome)
        entry.visible_to_workflow = True
        entry.attributes = attributes
        entry.updated_at = utcnow()
        revision = self._create_revision(
            entry,
            summary=latest.summary,
            content=latest.content,
            subject_refs=self._subject_refs_payload(latest.subject_refs),
            attributes=attributes,
            revision_action=MemoryRevisionAction.SUPERSEDED.value,
            supersedes_revision_id=latest.revision_id,
            source_run_id=entry.source_run_id,
            source_agent_key=entry.source_agent_key,
            source_step_id=entry.source_step_id,
            source_slot=entry.source_slot,
            trace_span_id=entry.source_trace_id,
        )
        self._append_event(
            event_type="reviewed",
            entry=entry,
            revision=revision,
            result_snapshot={
                "memoryId": entry.memory_id,
                "visibleToWorkflow": entry.visible_to_workflow,
            },
        )
        self.session.flush()
        self.session.refresh(entry)
        return self._entry_read(entry, revision)

    def append_reflection(self, memory_id: str, reflection: MemoryReflection) -> MemoryEntryRead:
        entry = self._locked_entry_by_memory_id(memory_id)
        latest = self._latest_revision(entry)
        attributes = self._attributes_payload(latest.attributes)
        reflections = self._stored_reflections(attributes)
        reflections.append(self._reflection_payload(reflection))
        attributes["reflections"] = cast(Any, reflections)
        entry.attributes = attributes
        entry.updated_at = utcnow()
        revision = self._create_revision(
            entry,
            summary=latest.summary,
            content=latest.content,
            subject_refs=self._subject_refs_payload(latest.subject_refs),
            attributes=attributes,
            revision_action=MemoryRevisionAction.SUPERSEDED.value,
            supersedes_revision_id=latest.revision_id,
            source_run_id=entry.source_run_id,
            source_agent_key=entry.source_agent_key,
            source_step_id=entry.source_step_id,
            source_slot=entry.source_slot,
            trace_span_id=entry.source_trace_id,
        )
        self._append_event(
            event_type="reviewed",
            entry=entry,
            revision=revision,
            result_snapshot={"memoryId": entry.memory_id, "reflectionCount": len(reflections)},
        )
        self.session.flush()
        self.session.refresh(entry)
        return self._entry_read(entry, revision)

    def record_review(
        self,
        memory_id: str,
        *,
        event_context: MemoryEventContext | None = None,
        filters: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        result_snapshot: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
    ) -> MemoryEntryRead:
        entry = self._entry_by_memory_id(memory_id)
        revision = self._latest_revision(entry)
        self._append_event(
            event_type="reviewed",
            entry=entry,
            revision=revision,
            event_context=event_context,
            filters=filters,
            budget=budget,
            result_snapshot=result_snapshot,
            status_snapshot=status_snapshot,
        )
        self.session.flush()
        return self._entry_read(entry, revision)

    def list_artifacts_for_run(self, run_id: int) -> list[MemoryArtifactRead]:
        events = self.events.list_artifact_events_for_run(run_id)
        first_event_by_memory_id: dict[str, RunMemoryEvent] = {}
        for event in events:
            if event.memory_id is None or event.memory_id in first_event_by_memory_id:
                continue
            first_event_by_memory_id[event.memory_id] = event
        entries = self.entries.list_by_memory_ids(tuple(first_event_by_memory_id))
        entry_by_memory_id = {entry.memory_id: entry for entry in entries}
        revisions = self.revisions.list_latest_for_entry_ids([entry.id for entry in entries])
        revision_by_entry_id = {revision.memory_entry_id: revision for revision in revisions}

        artifacts: list[MemoryArtifactRead] = []
        for memory_id, event in first_event_by_memory_id.items():
            entry = entry_by_memory_id.get(memory_id)
            if entry is None:
                continue
            revision = revision_by_entry_id.get(entry.id)
            if revision is None:
                continue
            artifacts.append(self._artifact_read(entry, revision, event))
        return artifacts

    def audit_links(self, memory_id: str) -> MemoryAuditLinks:
        _ = self._entry_by_memory_id(memory_id)
        return MemoryAuditLinks()

    def _rank_lookup_candidates(self, query: MemoryQuery) -> list[_RankedLookupCandidate]:
        candidate_limit = self._lookup_candidate_limit(query)
        lookup_kwargs = self._lookup_filter_kwargs(query)
        lexical_candidates = self.entries.list_lexical_lookup_candidates(
            query_text=query.query,
            limit=candidate_limit,
            offset=0,
            **lookup_kwargs,
        )
        return [
            _RankedLookupCandidate(
                entry=candidate.entry,
                revision=candidate.revision,
                lexical_rank=rank,
                lexical_score=candidate.lexical_score,
                score=self._reciprocal_rank_score(rank),
            )
            for rank, candidate in enumerate(lexical_candidates, start=1)
        ]

    def _lookup_filter_kwargs(self, query: MemoryQuery) -> dict[str, Any]:
        return {
            "scope_type": query.scope.scope_type.value if query.scope is not None else None,
            "scope_key": query.scope.scope_key if query.scope is not None else None,
            "subject_refs": self._query_subject_refs(query.subject_refs),
            "kind": query.kind,
            "visible_to_workflow": True,
            "agent_key": query.agent_key,
            "workflow_key": query.workflow_key,
            "tags": query.tags,
        }

    @staticmethod
    def _lookup_candidate_limit(query: MemoryQuery) -> int:
        requested_window = max(query.limit, query.limit + query.offset)
        return min(requested_window * _LOOKUP_CANDIDATE_MULTIPLIER, _LOOKUP_MAX_CANDIDATES)

    @staticmethod
    def _scope_specificity(entry: AgentMemoryEntry) -> int:
        return _SCOPE_SPECIFICITY.get(entry.scope_type, 0)

    def _retrieval_score(self, candidate: _RankedLookupCandidate) -> MemoryRetrievalScore:
        return MemoryRetrievalScore(
            retrieval_mode="lexical",
            rank=candidate.lexical_rank,
            score=self._rounded_score(candidate.score),
            scope_specificity=self._scope_specificity(candidate.entry),
            lexical_rank=candidate.lexical_rank,
            lexical_score=self._rounded_optional_score(candidate.lexical_score),
            sources=["lexical"],
        )

    @staticmethod
    def _reciprocal_rank_score(rank: int) -> float:
        return 1.0 / (_RRF_K + rank)

    @staticmethod
    def _rounded_score(value: float) -> float:
        return round(value, 9)

    @classmethod
    def _rounded_optional_score(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return cls._rounded_score(value)

    def _existing_entry_for_payload(
        self,
        payload: MemoryWriteRequest,
    ) -> AgentMemoryEntry | None:
        if payload.idempotency_key is not None:
            return self.entries.get_by_idempotency_key(payload.idempotency_key)
        identity = payload.idempotency_fallback_identity()
        return self.entries.get_by_fallback_identity(
            scope_type=cast(str, identity["scope_type"]),
            scope_key=cast(str, identity["scope_key"]),
            kind=cast(str, identity["kind"]),
            content_hash=cast(str, identity["content_hash"]),
            source_run_id=cast(int, identity["source_run_id"]),
            source_agent_key=cast(str, identity["source_agent_key"]),
            source_step_id=cast(str | None, identity["source_step_id"]),
            source_slot=cast(str | None, identity["source_slot"]),
        )

    def _entry_by_memory_id(self, memory_id: str) -> AgentMemoryEntry:
        normalized = self._normalize_memory_id(memory_id)
        entry = self.entries.get_by_memory_id(normalized)
        if entry is None:
            raise memory_not_found_error()
        return entry

    def _locked_entry_by_memory_id(self, memory_id: str) -> AgentMemoryEntry:
        normalized = self._normalize_memory_id(memory_id)
        try:
            entry = self.entries.get_by_memory_id_for_update(normalized, nowait=True)
        except OperationalError as exc:
            if self._is_lock_not_available(exc):
                raise self._memory_revision_conflict() from exc
            raise
        if entry is None:
            raise memory_not_found_error()
        return entry

    def _latest_revision(self, entry: AgentMemoryEntry) -> AgentMemoryRevision:
        revision = self.revisions.get_latest_for_entry(entry.id)
        if revision is None:
            raise memory_not_found_error()
        return revision

    def _create_revision(
        self,
        entry: AgentMemoryEntry,
        *,
        summary: str,
        content: str,
        subject_refs: list[dict[str, Any]],
        attributes: MemoryAttributes,
        revision_action: str,
        supersedes_revision_id: str | None,
        source_run_id: int,
        source_agent_key: str,
        source_step_id: str | None,
        source_slot: str | None,
        trace_span_id: str | None,
    ) -> AgentMemoryRevision:
        latest = self.revisions.get_latest_for_entry(entry.id)
        revision = AgentMemoryRevision(
            memory_entry_id=entry.id,
            revision_id=self._new_revision_id(),
            version=1 if latest is None else latest.version + 1,
            visible_to_workflow=entry.visible_to_workflow,
            revision_action=revision_action,
            summary=summary,
            content=content,
            content_hash=self._content_hash(content),
            subject_refs=subject_refs,
            attributes=attributes,
            supersedes_revision_id=supersedes_revision_id,
            source_run_id=source_run_id,
            source_agent_key=source_agent_key,
            source_step_id=source_step_id,
            source_slot=source_slot,
            trace_span_id=trace_span_id,
        )
        self.revisions.add(revision)
        self.session.flush()
        self.session.refresh(revision)
        return revision

    def _append_event(
        self,
        *,
        event_type: str,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        event_context: MemoryEventContext | None = None,
        retrieval_mode: str | None = None,
        filters: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        excerpt: str | None = None,
        injected_text: str | None = None,
        result_snapshot: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
    ) -> RunMemoryEvent:
        return self.events.add_event(
            run_id=(
                event_context.run_id
                if event_context is not None and event_context.run_id is not None
                else entry.source_run_id
            ),
            run_step_id=None if event_context is None else event_context.run_step_id,
            run_agent_invocation_id=(
                None if event_context is None else event_context.run_agent_invocation_id
            ),
            run_operation_invocation_id=(
                None if event_context is None else event_context.run_operation_invocation_id
            ),
            step_id=(
                event_context.step_id
                if event_context is not None and event_context.step_id is not None
                else entry.source_step_id
            ),
            invocation_id=None if event_context is None else event_context.invocation_id,
            event_type=event_type,
            memory_entry_id=entry.id,
            memory_revision_id=revision.id,
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            retrieval_mode=retrieval_mode,
            filters=filters or {},
            budget=budget or {},
            excerpt=excerpt,
            injected_text=injected_text,
            result_snapshot=result_snapshot or {},
            status_snapshot=status_snapshot or {"visibleToWorkflow": entry.visible_to_workflow},
            trace_span_id=(
                event_context.trace_span_id
                if event_context is not None and event_context.trace_span_id is not None
                else entry.source_trace_id
            ),
        )

    def _write_result(
        self,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        revision_action: MemoryRevisionAction,
        *,
        action: str,
    ) -> MemoryWriteResult:
        return MemoryWriteResult(
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            visible_to_workflow=entry.visible_to_workflow,
            revision_action=revision_action,
            created_at=revision.created_at,
            provenance=self._provenance(entry),
            revision=self._revision_read(revision),
            idempotency_key=entry.idempotency_key,
            idempotency_fallback_fields=MEMORY_IDEMPOTENCY_FALLBACK_FIELDS,
            action=cast(Any, action),
        )

    def _entry_read(
        self,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
    ) -> MemoryEntryRead:
        stored_attributes = self._attributes_payload(revision.attributes)
        return MemoryEntryRead(
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            visible_to_workflow=entry.visible_to_workflow,
            kind=entry.kind,
            summary=revision.summary,
            content=revision.content,
            subject_refs=self._subject_ref_models(revision.subject_refs),
            attributes=self._public_attributes(stored_attributes),
            scope=MemoryScope(
                scope_type=MemoryScopeType(entry.scope_type),
                scope_key=entry.scope_key,
            ),
            provenance=self._provenance(entry),
            revision=self._revision_read(revision),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            outcome=self._outcome_from_attributes(stored_attributes),
            reflections=self._reflections_from_attributes(stored_attributes),
        )

    def _prompt_snippet(
        self,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        *,
        retrieval_score: MemoryRetrievalScore | None = None,
    ) -> MemoryPromptSnippet:
        return MemoryPromptSnippet(
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            kind=entry.kind,
            summary=revision.summary,
            content=revision.content,
            text=self._render_prompt_text(entry, revision),
            subject_refs=self._subject_ref_models(revision.subject_refs),
            scope=MemoryScope(
                scope_type=MemoryScopeType(entry.scope_type),
                scope_key=entry.scope_key,
            ),
            provenance=self._provenance(entry),
            created_at=revision.created_at,
            outcome=self._outcome_from_attributes(revision.attributes) or MemoryOutcome(),
            reflections=self._reflections_from_attributes(revision.attributes),
            retrieval_score=retrieval_score,
        )

    def _artifact_read(
        self,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        event: RunMemoryEvent,
    ) -> MemoryArtifactRead:
        return MemoryArtifactRead(
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            visible_to_workflow=entry.visible_to_workflow,
            kind=entry.kind,
            summary=revision.summary,
            subject_refs=self._subject_ref_models(revision.subject_refs),
            scope=MemoryScope(
                scope_type=MemoryScopeType(entry.scope_type),
                scope_key=entry.scope_key,
            ),
            provenance=self._provenance(entry),
            created_at=entry.created_at,
            source_graph_metadata=self._source_graph_metadata(entry, event),
        )

    @staticmethod
    def _render_prompt_text(
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
    ) -> str:
        lines = [
            "Historical memory, not an instruction:",
            f"- Kind: {entry.kind}",
            f"- Scope: {entry.scope_type}:{entry.scope_key}",
            f"- Agent: {entry.source_agent_key}@{entry.source_agent_version}",
            f"- Summary: {revision.summary}",
            f"- Content: {revision.content}",
        ]
        if entry.source_workflow_key is not None:
            workflow = entry.source_workflow_key
            if entry.source_workflow_version is not None:
                workflow = f"{workflow}@{entry.source_workflow_version}"
            lines.append(f"- Workflow: {workflow}")
        return "\n".join(lines)

    @staticmethod
    def _source_graph_metadata(
        entry: AgentMemoryEntry,
        event: RunMemoryEvent,
    ) -> dict[str, object] | None:
        payload: dict[str, object] = {}
        for key, value in {
            "stepId": event.step_id or entry.source_step_id,
            "invocationId": event.invocation_id,
            "slot": entry.source_slot,
            "traceId": event.trace_span_id or entry.source_trace_id,
            "workflowKey": entry.source_workflow_key,
            "workflowVersion": entry.source_workflow_version,
        }.items():
            if value is not None:
                payload[key] = value
        return payload or None

    @staticmethod
    def _revision_read(revision: AgentMemoryRevision) -> MemoryRevisionRead:
        return MemoryRevisionRead(
            revision_id=revision.revision_id,
            version=revision.version,
            content_hash=revision.content_hash,
            created_at=revision.created_at,
            supersedes_revision_id=revision.supersedes_revision_id,
        )

    @classmethod
    def _api_revision_read(cls, revision: AgentMemoryRevision) -> MemoryApiRevisionRead:
        return MemoryApiRevisionRead(
            revision_id=revision.revision_id,
            version=revision.version,
            visible_to_workflow=revision.visible_to_workflow,
            revision_action=MemoryRevisionAction(revision.revision_action),
            summary=revision.summary,
            content=revision.content,
            content_hash=revision.content_hash,
            subject_refs=cls._subject_ref_models(revision.subject_refs),
            attributes=cls._public_attributes(cls._attributes_payload(revision.attributes)),
            supersedes_revision_id=revision.supersedes_revision_id,
            source_run_id=revision.source_run_id,
            source_agent_key=revision.source_agent_key,
            source_step_id=revision.source_step_id,
            source_slot=revision.source_slot,
            trace_span_id=revision.trace_span_id,
            created_at=revision.created_at,
        )

    @classmethod
    def _api_event_read(cls, event: RunMemoryEvent) -> MemoryApiEventRead:
        return MemoryApiEventRead(
            event_id=event.id,
            run_id=event.run_id,
            event_type=event.event_type,
            memory_id=event.memory_id,
            revision_id=event.revision_id,
            retrieval_mode=event.retrieval_mode,
            filters=cast(dict[str, object], cls._attributes_payload(event.filters)),
            budget=cast(dict[str, object], cls._attributes_payload(event.budget)),
            excerpt=event.excerpt,
            injected_text=event.injected_text,
            result_snapshot=cast(dict[str, object], cls._attributes_payload(event.result_snapshot)),
            status_snapshot=cast(dict[str, object], cls._attributes_payload(event.status_snapshot)),
            step_id=event.step_id,
            invocation_id=event.invocation_id,
            trace_span_id=event.trace_span_id,
            created_at=event.created_at,
        )

    @staticmethod
    def _provenance(entry: AgentMemoryEntry) -> MemoryProvenance:
        return MemoryProvenance(
            run_id=entry.source_run_id,
            agent_key=entry.source_agent_key,
            agent_version=entry.source_agent_version,
            created_by_type=cast(Any, entry.created_by_type),
            agent_name=entry.source_agent_name,
            workflow_key=entry.source_workflow_key,
            workflow_version=entry.source_workflow_version,
            step_id=entry.source_step_id,
            slot=entry.source_slot,
            trace_id=entry.source_trace_id,
        )

    @staticmethod
    def _payload_subject_refs(payload: MemoryWriteRequest) -> list[dict[str, Any]]:
        return PostgresMemoryStore._subject_refs_payload(payload.subject_refs)

    @staticmethod
    def _query_subject_refs(subject_refs: list[MemorySubjectRef]) -> list[dict[str, str]]:
        return [{"kind": item.kind, "id": item.id} for item in subject_refs]

    @staticmethod
    def _subject_refs_payload(
        subject_refs: list[MemorySubjectRef] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for item in subject_refs:
            if isinstance(item, MemorySubjectRef):
                payloads.append(item.model_dump(mode="json", by_alias=True, exclude_none=True))
            else:
                payloads.append(deepcopy(item))
        return payloads

    @staticmethod
    def _subject_ref_models(raw_refs: list[dict[str, Any]]) -> list[MemorySubjectRef]:
        return [MemorySubjectRef.model_validate(item) for item in raw_refs]

    @staticmethod
    def _attributes_payload(attributes: object) -> MemoryAttributes:
        if not isinstance(attributes, dict):
            return {}
        return cast(MemoryAttributes, deepcopy(attributes))

    @staticmethod
    def _public_attributes(attributes: MemoryAttributes) -> MemoryAttributes:
        payload = dict(attributes)
        _ = payload.pop("outcome", None)
        _ = payload.pop("reflections", None)
        for key in tuple(payload):
            if key.startswith("_"):
                _ = payload.pop(key, None)
        return payload

    @staticmethod
    def _outcome_payload(outcome: MemoryOutcome) -> dict[str, Any]:
        payload = outcome.model_dump(mode="json", by_alias=True, exclude_none=True)
        payload.update(
            {
                "summary": outcome.summary,
                "observedAt": PostgresMemoryStore._datetime_payload(outcome.observed_at),
                "attributes": deepcopy(outcome.attributes),
            }
        )
        return payload

    @staticmethod
    def _outcome_from_attributes(attributes: object) -> MemoryOutcome | None:
        if not isinstance(attributes, dict):
            return None
        outcome = attributes.get("outcome")
        if not isinstance(outcome, dict):
            return None
        return MemoryOutcome.model_validate(outcome)

    @staticmethod
    def _reflection_payload(reflection: MemoryReflection) -> dict[str, Any]:
        return reflection.model_dump(mode="json", by_alias=True, exclude_none=True)

    @staticmethod
    def _stored_reflections(attributes: MemoryAttributes) -> list[dict[str, Any]]:
        raw_reflections = cast(object, attributes.get("reflections"))
        if not isinstance(raw_reflections, list):
            return []
        reflections: list[dict[str, Any]] = []
        for item in raw_reflections:
            if isinstance(item, dict):
                reflections.append({str(key): value for key, value in item.items()})
        return reflections

    @staticmethod
    def _reflections_from_attributes(attributes: object) -> list[MemoryReflection]:
        if not isinstance(attributes, dict):
            return []
        raw_reflections = attributes.get("reflections")
        if not isinstance(raw_reflections, list):
            return []
        return [
            MemoryReflection.model_validate(item)
            for item in raw_reflections
            if isinstance(item, dict)
        ]

    @staticmethod
    def _result_snapshot(
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        revision_action: MemoryRevisionAction,
    ) -> dict[str, Any]:
        return {
            "memoryId": entry.memory_id,
            "revisionId": revision.revision_id,
            "visibleToWorkflow": entry.visible_to_workflow,
            "revisionAction": revision_action.value,
        }

    @staticmethod
    def _write_filters(payload: MemoryWriteRequest) -> dict[str, Any]:
        return {
            "kind": payload.kind,
            "scope": payload.scope.model_dump(mode="json", by_alias=True),
            "subjectRefs": [
                subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                for subject_ref in payload.subject_refs
            ],
            "idempotencyKey": payload.idempotency_key,
            "idempotencyFallbackFields": list(payload.idempotency_fallback_fields),
            "contentHash": payload.content_hash(),
            "provenance": payload.provenance.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        }

    @staticmethod
    def _has_lookup_selector(query: MemoryQuery) -> bool:
        return any(
            (
                query.scope is not None,
                bool(query.subject_refs),
                query.kind is not None,
                query.agent_key is not None,
                query.workflow_key is not None,
                bool(query.tags),
            )
        )

    @staticmethod
    def _datetime_payload(value: object) -> str:
        return to_utc(cast(Any, value)).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_memory_id(memory_id: str) -> str:
        if not isinstance(memory_id, str):
            raise invalid_memory_id_error()
        normalized = memory_id.strip()
        if not normalized:
            raise invalid_memory_id_error()
        return normalized

    @staticmethod
    def _new_memory_id() -> str:
        return f"memory_{uuid4().hex}"

    @staticmethod
    def _new_revision_id() -> str:
        return f"revision_{uuid4().hex}"

    @staticmethod
    def _is_lock_not_available(error: OperationalError) -> bool:
        original = getattr(error, "orig", None)
        sqlstate = getattr(original, "sqlstate", None) or getattr(
            original,
            "pgcode",
            None,
        )
        return isinstance(sqlstate, str) and sqlstate == _POSTGRES_LOCK_NOT_AVAILABLE_SQLSTATE

    @staticmethod
    def _memory_revision_conflict() -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="memory_revision_conflict",
            message="Memory is being updated by another transaction; retry the mutation",
        )

    @staticmethod
    def _memory_conflict() -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="memory_conflict",
            message="Memory identity conflicts with an existing record",
        )


__all__ = [
    "MemoryEventContext",
    "MemoryStore",
    "PostgresMemoryStore",
    "canonical_package_qualified_scope_key",
]
