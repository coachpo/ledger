from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from typing import cast as type_cast
from uuid import uuid4

from fastapi import status
from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.models.agent_memory import AgentMemoryEntry, AgentMemoryRevision, RunMemoryEvent
from app.repositories.agent_memory import (
    AgentMemoryAdminListRow,
    AgentMemoryEntryRepository,
    AgentMemoryRevisionRepository,
    RunMemoryEventRepository,
)
from app.schemas.memory import (
    MEMORY_NAMESPACE_ACCESS_DENIED_CODE,
    MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE,
    MemoryAdminCreateRequest,
    MemoryAdminEntryRead,
    MemoryAdminEventListRead,
    MemoryAdminListItemRead,
    MemoryAdminListQuery,
    MemoryAdminListRead,
    MemoryAdminRevisionCreateRequest,
    MemoryAdminRevisionListRead,
    MemoryAdminWorkflowVisibilityUpdateRequest,
    MemoryApiAccessContext,
    MemoryApiAccessRequest,
    MemoryApiEntryRead,
    MemoryApiEventListRead,
    MemoryApiListItemRead,
    MemoryApiListRead,
    MemoryApiListRequest,
    MemoryApiReflectRequest,
    MemoryApiResolveRequest,
    MemoryApiRevisionListRead,
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryEntryRead,
    MemoryNamespaceAction,
    MemoryNamespaceGrant,
    MemoryNamespaceSelector,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryScope,
    MemoryScopeType,
    MemoryWriteRequest,
    MemoryWriteResult,
    memory_not_found_error,
)
from app.services.memory_store import (
    MemoryEventContext,
    MemoryStore,
    PostgresMemoryStore,
    canonical_package_qualified_scope_key,
)
from app.services.runtime_tool_grants import (
    RuntimeToolGrantError,
    RuntimeToolGrantPolicy,
    RuntimeToolGrantService,
)

_EVENT_TEXT_SNAPSHOT_MAX_CHARACTERS = 8_000
_EVENT_SNIPPET_EXCERPT_MAX_CHARACTERS = 1_000
_OPERATOR_ACTOR = "local-instance-operator"
_OPERATOR_AGENT_NAME = "Local Instance Operator"
_OPERATOR_CHANNEL = "memory_admin"
_OPERATOR_SOURCE = "operator"


@dataclass(frozen=True, slots=True)
class MemoryLookupContext:
    run_id: int | None = None
    package_key: str | None = None
    workflow_key: str | None = None
    agent_key: str | None = None
    run_step_id: int | None = None
    run_agent_invocation_id: int | None = None
    run_operation_invocation_id: int | None = None
    step_id: str | None = None
    invocation_id: str | None = None
    trace_span_id: str | None = None
    namespace_declarations: tuple[MemoryNamespaceSelector, ...] = ()
    namespace_grants: tuple[MemoryNamespaceGrant, ...] = ()

    def has_values(self) -> bool:
        return any(
            (
                self.run_id is not None,
                self.normalized_text(self.package_key) is not None,
                self.normalized_text(self.workflow_key) is not None,
                self.normalized_text(self.agent_key) is not None,
            )
        )

    def scopes(self) -> tuple[MemoryScope, ...]:
        scopes: list[MemoryScope] = []
        if self.run_id is not None:
            scopes.append(MemoryScope(scope_type=MemoryScopeType.RUN, scope_key=str(self.run_id)))
        for scope_type in (
            MemoryScopeType.PACKAGE,
            MemoryScopeType.WORKFLOW,
            MemoryScopeType.AGENT,
        ):
            scope_key = self.scope_key_for_type(scope_type)
            if scope_key is not None:
                scopes.append(MemoryScope(scope_type=scope_type, scope_key=scope_key))
        return tuple(scopes)

    def canonicalize_scope(self, scope: MemoryScope) -> MemoryScope:
        if scope.scope_type == MemoryScopeType.RUN:
            return scope
        scope_key = self.scope_key_for_type(
            scope.scope_type,
            fallback_scope_key=scope.scope_key,
        )
        if scope_key is None or scope_key == scope.scope_key:
            return scope
        return scope.model_copy(update={"scope_key": scope_key})

    def scope_key_for_type(
        self,
        scope_type: MemoryScopeType,
        *,
        fallback_scope_key: str | None = None,
    ) -> str | None:
        fallback = self.normalized_text(fallback_scope_key)
        package_key = self.normalized_text(self.package_key)
        if scope_type == MemoryScopeType.PACKAGE:
            return package_key or fallback
        if scope_type == MemoryScopeType.WORKFLOW:
            workflow_key = self.normalized_text(self.workflow_key) or fallback
            return self._package_qualified_scope_key(
                package_key=package_key,
                local_key=workflow_key,
            )
        if scope_type == MemoryScopeType.AGENT:
            agent_key = self.normalized_text(self.agent_key) or fallback
            return self._package_qualified_scope_key(
                package_key=package_key,
                local_key=agent_key,
            )
        if scope_type == MemoryScopeType.RUN:
            if self.run_id is not None:
                return str(self.run_id)
            return fallback
        return fallback

    @staticmethod
    def _package_qualified_scope_key(
        *,
        package_key: str | None,
        local_key: str | None,
    ) -> str | None:
        if local_key is None:
            return None
        if package_key is None:
            return local_key
        if local_key == package_key or local_key.startswith(f"{package_key}:"):
            return local_key
        return canonical_package_qualified_scope_key(
            package_key=package_key,
            local_key=local_key,
        )

    def declares_namespace(self, namespace: MemoryNamespaceSelector) -> bool:
        return any(declaration == namespace for declaration in self.namespace_declarations)

    def has_namespace_grant(
        self,
        namespace: MemoryNamespaceSelector,
        action: MemoryNamespaceAction,
    ) -> bool:
        package_key = self.normalized_text(self.package_key)
        workflow_key = self.normalized_text(self.workflow_key)
        agent_key = self.normalized_text(self.agent_key)
        return any(
            grant.allows(
                namespace,
                action,
                package_key=package_key,
                workflow_key=workflow_key,
                agent_key=agent_key,
            )
            for grant in self.namespace_grants
        )

    def readable_namespaces(self) -> tuple[MemoryNamespaceSelector, ...]:
        package_key = self.normalized_text(self.package_key)
        workflow_key = self.normalized_text(self.workflow_key)
        agent_key = self.normalized_text(self.agent_key)
        namespaces: dict[str, MemoryNamespaceSelector] = {}
        for declaration in self.namespace_declarations:
            if declaration.owner_package_key == package_key:
                namespaces[declaration.qualified_key] = declaration
        for grant in self.namespace_grants:
            if grant.allows(
                grant.namespace,
                "read",
                package_key=package_key,
                workflow_key=workflow_key,
                agent_key=agent_key,
            ):
                namespaces[grant.namespace.qualified_key] = grant.namespace
        return tuple(namespaces.values())

    @staticmethod
    def normalized_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class MemoryService:
    def __init__(
        self,
        session: Session,
        store: MemoryStore | None = None,
        *,
        current_context: MemoryLookupContext | None = None,
    ) -> None:
        self.session: Session = session
        self.store: MemoryStore = store if store is not None else PostgresMemoryStore(session)
        self.current_context: MemoryLookupContext | None = current_context
        self.entry_repository: AgentMemoryEntryRepository = AgentMemoryEntryRepository(session)
        self.revision_repository: AgentMemoryRevisionRepository = AgentMemoryRevisionRepository(
            session
        )
        self.event_repository: RunMemoryEventRepository = RunMemoryEventRepository(session)
        self.runtime_tool_grant_service: RuntimeToolGrantService = RuntimeToolGrantService(
            get_default_tool_catalog(),
        )

    def write_memory(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        payload: MemoryWriteRequest,
        grant_policy: RuntimeToolGrantPolicy | None = None,
        commit: bool = True,
    ) -> MemoryWriteResult:
        if grant_policy is not None:
            self.runtime_tool_grant_service.require_runtime_tool_grant(
                capability_references=capability_references,
                grant_policy=grant_policy,
            )
        effective_payload = self._authorize_and_canonicalize_write_payload(payload)
        try:
            result = self.store.create_hidden(
                effective_payload,
                event_context=self._event_context_from_lookup(self.current_context),
            )
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except Exception:
            if commit:
                self.session.rollback()
            raise
        return result

    def get_memory(self, memory_id: str) -> MemoryEntryRead:
        return self.store.get(memory_id)

    def resolve_memory(
        self,
        memory_id: str,
        outcome: MemoryOutcome,
        *,
        commit: bool = True,
    ) -> MemoryEntryRead:
        try:
            entry = self.store.resolve(memory_id, outcome)
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except Exception:
            if commit:
                self.session.rollback()
            raise
        return entry

    def append_reflection(
        self,
        memory_id: str,
        reflection: MemoryReflection,
        *,
        commit: bool = True,
    ) -> MemoryEntryRead:
        try:
            entry = self.store.append_reflection(memory_id, reflection)
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except Exception:
            if commit:
                self.session.rollback()
            raise
        return entry

    def record_review_event(
        self,
        memory_id: str,
        *,
        filters: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        result_snapshot: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
        current_context: MemoryLookupContext | None = None,
        commit: bool = True,
    ) -> MemoryEntryRead:
        context = current_context or self.current_context
        try:
            entry = self.store.record_review(
                memory_id,
                event_context=self._event_context_from_lookup(context),
                filters=filters,
                budget=budget,
                result_snapshot=result_snapshot,
                status_snapshot=status_snapshot,
            )
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except Exception:
            if commit:
                self.session.rollback()
            raise
        return entry

    def list_run_artifacts(self, run_id: int) -> list[MemoryArtifactRead]:
        return self.store.list_artifacts_for_run(run_id)

    def list_admin_memory(self, payload: MemoryAdminListQuery) -> MemoryAdminListRead:
        query_text = payload.query.strip() if payload.query is not None else None
        rows = self.entry_repository.list_admin_latest_revisions(
            package_key=payload.package_key,
            workflow_key=payload.workflow_key,
            agent_key=payload.agent_key,
            run_id=payload.run_id,
            scope_type=payload.scope_type.value if payload.scope_type is not None else None,
            kind=payload.kind,
            visible_to_workflow=payload.visible_to_workflow,
            query_text=query_text,
            sort=payload.sort,
            limit=payload.limit,
            offset=payload.offset,
        )
        total = self.entry_repository.count_admin_latest_revisions(
            package_key=payload.package_key,
            workflow_key=payload.workflow_key,
            agent_key=payload.agent_key,
            run_id=payload.run_id,
            scope_type=payload.scope_type.value if payload.scope_type is not None else None,
            kind=payload.kind,
            visible_to_workflow=payload.visible_to_workflow,
            query_text=query_text,
        )
        return MemoryAdminListRead(
            items=[self._admin_list_item(row) for row in rows],
            total=total,
            limit=payload.limit,
            offset=payload.offset,
            sort=payload.sort,
        )

    def create_admin_memory(self, payload: MemoryAdminCreateRequest) -> MemoryAdminEntryRead:
        try:
            provenance = self._operator_provenance(payload.provenance)
            entry = self.entry_repository.add_operator_entry(
                memory_id=self._new_memory_id(),
                scope_type=payload.scope.scope_type.value,
                scope_key=payload.scope.scope_key,
                kind=payload.kind,
                visible_to_workflow=payload.visible_to_workflow,
                summary=payload.summary,
                subject_refs=self._subject_refs_payload(payload.subject_refs),
                attributes=self._admin_attributes(payload.attributes),
                content_hash=self._content_hash(payload.content),
                idempotency_key=payload.idempotency_key,
                created_by_type=provenance.created_by_type,
                source_run_id=provenance.run_id,
                source_agent_key=provenance.agent_key,
                source_agent_version=provenance.agent_version,
                source_agent_name=provenance.agent_name,
                source_workflow_key=provenance.workflow_key,
                source_workflow_version=provenance.workflow_version,
                source_step_id=provenance.step_id,
                source_slot=provenance.slot,
                source_trace_id=provenance.trace_id,
            )
            self.session.flush()
            self.session.refresh(entry)
            attributes = self._admin_attributes(payload.attributes)
            if payload.visible_to_workflow:
                attributes["outcome"] = self._outcome_payload(payload.to_outcome())
                entry.attributes = attributes
            revision = self._create_admin_revision_row(
                entry,
                summary=payload.summary,
                content=payload.content,
                subject_refs=self._subject_refs_payload(payload.subject_refs),
                attributes=attributes,
                supersedes_revision_id=None,
                provenance=provenance,
            )
            self._record_operator_event(
                event_type="operator_created",
                entry=entry,
                revision=revision,
                provenance=provenance,
                filters={
                    "kind": payload.kind,
                    "scope": payload.scope.model_dump(mode="json", by_alias=True),
                    "visibleToWorkflow": payload.visible_to_workflow,
                    "subjectRefs": [
                        subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for subject_ref in payload.subject_refs
                    ],
                    "idempotencyKey": payload.idempotency_key,
                    "contentHash": self._content_hash(payload.content),
                },
                result_snapshot=self._operator_result_snapshot(entry, revision),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return MemoryAdminEntryRead.from_entry(self.get_memory(entry.memory_id))

    def get_admin_memory(self, memory_id: str) -> MemoryAdminEntryRead:
        return MemoryAdminEntryRead.from_entry(self.get_memory(memory_id))

    def delete_admin_memory(self, memory_id: str) -> None:
        try:
            entry = self.entry_repository.get_by_memory_id_for_update(memory_id)
            if entry is None:
                raise self._memory_not_found()
            self.entry_repository.delete(entry)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def list_admin_memory_revisions(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> MemoryAdminRevisionListRead:
        revisions = self.store.list_revisions(memory_id, limit=limit, offset=offset)
        return MemoryAdminRevisionListRead(
            items=revisions,
            count=len(revisions),
            limit=limit,
            offset=offset,
        )

    def list_admin_memory_events(
        self,
        memory_id: str,
        *,
        limit: int,
        offset: int,
    ) -> MemoryAdminEventListRead:
        events = self.store.list_events(memory_id, limit=limit, offset=offset)
        return MemoryAdminEventListRead(items=events, count=len(events), limit=limit, offset=offset)

    def create_admin_memory_revision(
        self,
        memory_id: str,
        payload: MemoryAdminRevisionCreateRequest,
    ) -> MemoryAdminEntryRead:
        try:
            entry = self.entry_repository.get_by_memory_id_for_update(memory_id)
            if entry is None:
                raise self._memory_not_found()
            latest = self._latest_revision(entry)
            provenance = self._operator_provenance(payload.provenance)
            attributes = self._revision_attributes(latest.attributes, payload.attributes)
            subject_refs = self._subject_refs_payload(payload.subject_refs)
            self._apply_operator_entry_provenance(entry, provenance)
            entry.summary = payload.summary
            entry.subject_refs = subject_refs
            entry.attributes = attributes
            entry.content_hash = self._content_hash(payload.content)
            entry.updated_at = utcnow()
            revision = self._create_admin_revision_row(
                entry,
                summary=payload.summary,
                content=payload.content,
                subject_refs=subject_refs,
                attributes=attributes,
                supersedes_revision_id=latest.revision_id,
                provenance=provenance,
            )
            self._record_operator_event(
                event_type="operator_revised",
                entry=entry,
                revision=revision,
                provenance=provenance,
                filters={
                    "scope": {
                        "scopeType": entry.scope_type,
                        "scopeKey": entry.scope_key,
                    },
                    "contentHash": revision.content_hash,
                    "supersedesRevisionId": latest.revision_id,
                },
                result_snapshot=self._operator_result_snapshot(entry, revision),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return MemoryAdminEntryRead.from_entry(self.get_memory(entry.memory_id))

    def update_admin_memory_workflow_visibility(
        self,
        memory_id: str,
        payload: MemoryAdminWorkflowVisibilityUpdateRequest,
    ) -> MemoryAdminEntryRead:
        try:
            entry = self.entry_repository.get_by_memory_id_for_update(memory_id)
            if entry is None:
                raise self._memory_not_found()
            latest = self._latest_revision(entry)
            provenance = self._operator_provenance_from_entry(entry)
            attributes = self._revision_attributes(latest.attributes, {})
            attributes["outcome"] = self._outcome_payload(payload.to_outcome())
            self._apply_operator_entry_provenance(entry, provenance)
            entry.visible_to_workflow = payload.visible_to_workflow
            entry.attributes = attributes
            entry.updated_at = utcnow()
            revision = self._create_admin_revision_row(
                entry,
                summary=latest.summary,
                content=latest.content,
                subject_refs=self._subject_refs_payload(latest.subject_refs),
                attributes=attributes,
                supersedes_revision_id=latest.revision_id,
                provenance=provenance,
            )
            self._record_operator_event(
                event_type="operator_visibility_changed",
                entry=entry,
                revision=revision,
                provenance=provenance,
                filters={
                    "scope": {
                        "scopeType": entry.scope_type,
                        "scopeKey": entry.scope_key,
                    },
                    "visibleToWorkflow": payload.visible_to_workflow,
                },
                result_snapshot=self._operator_result_snapshot(entry, revision),
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return MemoryAdminEntryRead.from_entry(self.get_memory(entry.memory_id))

    def _latest_revision(self, entry: AgentMemoryEntry) -> AgentMemoryRevision:
        revision = self.revision_repository.get_latest_for_entry(entry.id)
        if revision is None:
            raise memory_not_found_error()
        return revision

    def _create_admin_revision_row(
        self,
        entry: AgentMemoryEntry,
        *,
        summary: str,
        content: str,
        subject_refs: list[dict[str, Any]],
        attributes: dict[str, Any],
        supersedes_revision_id: str | None,
        provenance: MemoryProvenance,
    ) -> AgentMemoryRevision:
        latest = self.revision_repository.get_latest_for_entry(entry.id)
        revision = self.revision_repository.add_operator_revision(
            memory_entry_id=entry.id,
            revision_id=self._new_revision_id(),
            version=1 if latest is None else latest.version + 1,
            visible_to_workflow=entry.visible_to_workflow,
            revision_action="created" if supersedes_revision_id is None else "superseded",
            summary=summary,
            content=content,
            content_hash=self._content_hash(content),
            subject_refs=subject_refs,
            attributes=attributes,
            supersedes_revision_id=supersedes_revision_id,
            source_run_id=provenance.run_id,
            source_agent_key=provenance.agent_key,
            source_step_id=provenance.step_id,
            source_slot=provenance.slot,
            trace_span_id=provenance.trace_id,
        )
        self.session.flush()
        self.session.refresh(revision)
        return revision

    def _record_operator_event(
        self,
        *,
        event_type: str,
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
        provenance: MemoryProvenance,
        filters: dict[str, Any],
        result_snapshot: dict[str, Any],
    ) -> RunMemoryEvent:
        operator_snapshot = self._operator_snapshot()
        event = self.event_repository.add_operator_event(
            run_id=provenance.run_id,
            event_type=event_type,
            memory_entry_id=entry.id,
            memory_revision_id=revision.id,
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            filters={**operator_snapshot, **filters},
            result_snapshot={**operator_snapshot, **result_snapshot},
            status_snapshot={
                **operator_snapshot,
                "visibleToWorkflow": entry.visible_to_workflow,
            },
            step_id=provenance.step_id,
            trace_span_id=provenance.trace_id,
        )
        self.session.flush()
        return event

    @staticmethod
    def _operator_snapshot() -> dict[str, str]:
        return {
            "source": _OPERATOR_SOURCE,
            "actor": _OPERATOR_ACTOR,
            "channel": _OPERATOR_CHANNEL,
        }

    @staticmethod
    def _operator_provenance(provenance: MemoryProvenance) -> MemoryProvenance:
        return MemoryProvenance(
            run_id=provenance.run_id,
            agent_key=_OPERATOR_ACTOR,
            agent_version=1,
            created_by_type="operator",
            agent_name=_OPERATOR_AGENT_NAME,
            workflow_key=provenance.workflow_key or _OPERATOR_CHANNEL,
            workflow_version=provenance.workflow_version,
            step_id=provenance.step_id or _OPERATOR_CHANNEL,
            slot=_OPERATOR_CHANNEL,
            trace_id=provenance.trace_id,
        )

    @classmethod
    def _operator_provenance_from_entry(cls, entry: AgentMemoryEntry) -> MemoryProvenance:
        return cls._operator_provenance(
            MemoryProvenance(
                run_id=entry.source_run_id,
                agent_key=entry.source_agent_key,
                agent_version=entry.source_agent_version,
                agent_name=entry.source_agent_name,
                workflow_key=entry.source_workflow_key,
                workflow_version=entry.source_workflow_version,
                step_id=entry.source_step_id,
                slot=entry.source_slot,
                trace_id=entry.source_trace_id,
            )
        )

    @staticmethod
    def _apply_operator_entry_provenance(
        entry: AgentMemoryEntry,
        provenance: MemoryProvenance,
    ) -> None:
        entry.created_by_type = provenance.created_by_type
        entry.source_run_id = provenance.run_id
        entry.source_agent_key = provenance.agent_key
        entry.source_agent_version = provenance.agent_version
        entry.source_agent_name = provenance.agent_name
        entry.source_workflow_key = provenance.workflow_key
        entry.source_workflow_version = provenance.workflow_version
        entry.source_step_id = provenance.step_id
        entry.source_slot = provenance.slot
        entry.source_trace_id = provenance.trace_id

    @classmethod
    def _revision_attributes(
        cls,
        current_attributes: object,
        replacement_attributes: dict[str, Any],
    ) -> dict[str, Any]:
        attributes = cls._admin_attributes(replacement_attributes)
        if isinstance(current_attributes, dict):
            for key in ("outcome", "reflections"):
                if key in current_attributes and key not in attributes:
                    attributes[key] = current_attributes[key]
        return attributes

    @staticmethod
    def _admin_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
        return {
            **dict(attributes),
            "_operatorProvenance": MemoryService._operator_snapshot(),
        }

    @staticmethod
    def _subject_refs_payload(subject_refs: Sequence[Any]) -> list[dict[str, Any]]:
        return [
            (
                subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                if hasattr(subject_ref, "model_dump")
                else dict(subject_ref)
            )
            for subject_ref in subject_refs
        ]

    @staticmethod
    def _outcome_payload(outcome: MemoryOutcome) -> dict[str, Any]:
        return outcome.model_dump(mode="json", by_alias=True, exclude_none=True)

    @staticmethod
    def _operator_result_snapshot(
        entry: AgentMemoryEntry,
        revision: AgentMemoryRevision,
    ) -> dict[str, Any]:
        return {
            "memoryId": entry.memory_id,
            "revisionId": revision.revision_id,
            "visibleToWorkflow": entry.visible_to_workflow,
            "revisionAction": revision.revision_action,
        }

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _new_memory_id() -> str:
        return f"memory_{uuid4().hex}"

    @staticmethod
    def _new_revision_id() -> str:
        return f"revision_{uuid4().hex}"

    @staticmethod
    def _memory_not_found() -> ApiError:
        return memory_not_found_error()

    def _admin_list_item(self, row: AgentMemoryAdminListRow) -> MemoryAdminListItemRead:
        entry = row.entry
        revision = row.revision
        return MemoryAdminListItemRead(
            memory_id=entry.memory_id,
            revision_id=revision.revision_id,
            visible_to_workflow=entry.visible_to_workflow,
            kind=entry.kind,
            summary=revision.summary,
            excerpt=row.excerpt or revision.summary,
            subject_refs=PostgresMemoryStore._subject_ref_models(revision.subject_refs),
            scope=MemoryScope(
                scope_type=MemoryScopeType(entry.scope_type),
                scope_key=entry.scope_key,
            ),
            provenance=MemoryProvenance(
                run_id=entry.source_run_id,
                agent_key=entry.source_agent_key,
                agent_version=entry.source_agent_version,
                created_by_type=type_cast(Any, entry.created_by_type),
                agent_name=entry.source_agent_name,
                workflow_key=entry.source_workflow_key,
                workflow_version=entry.source_workflow_version,
                step_id=entry.source_step_id,
                slot=entry.source_slot,
                trace_id=entry.source_trace_id,
            ),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            last_event_type=row.last_event_type,
        )

    def list_api_memory(self, payload: MemoryApiListRequest) -> MemoryApiListRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            snippets = self._query_api_memory(payload, current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        items = [MemoryApiListItemRead.from_snippet(snippet) for snippet in snippets]
        return MemoryApiListRead(
            items=items,
            count=len(items),
            limit=payload.limit,
            offset=payload.offset,
            visibility=payload.visibility,
            scope=payload.scope,
        )

    def get_api_memory(self, memory_id: str, payload: MemoryApiAccessRequest) -> MemoryApiEntryRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            entry = self._authorized_entry(memory_id, action="read", current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        return MemoryApiEntryRead.from_entry(entry)

    def list_api_memory_revisions(
        self,
        memory_id: str,
        payload: MemoryApiAccessRequest,
        *,
        limit: int,
        offset: int,
    ) -> MemoryApiRevisionListRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            _ = self._authorized_entry(memory_id, action="read", current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        revisions = self.store.list_revisions(memory_id, limit=limit, offset=offset)
        return MemoryApiRevisionListRead(
            items=revisions,
            count=len(revisions),
            limit=limit,
            offset=offset,
        )

    def list_api_memory_events(
        self,
        memory_id: str,
        payload: MemoryApiAccessRequest,
        *,
        limit: int,
        offset: int,
    ) -> MemoryApiEventListRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            _ = self._authorized_entry(memory_id, action="read", current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        events = self.store.list_events(memory_id, limit=limit, offset=offset)
        return MemoryApiEventListRead(items=events, count=len(events), limit=limit, offset=offset)

    def resolve_api_memory(
        self,
        memory_id: str,
        payload: MemoryApiResolveRequest,
    ) -> MemoryApiEntryRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            _ = self._authorized_entry(memory_id, action="write", current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        return MemoryApiEntryRead.from_entry(self.resolve_memory(memory_id, payload.outcome))

    def reflect_api_memory(
        self,
        memory_id: str,
        payload: MemoryApiReflectRequest,
    ) -> MemoryApiEntryRead:
        context = self._lookup_context_from_api_access(payload.access_context)
        try:
            _ = self._authorized_entry(memory_id, action="write", current_context=context)
        except RuntimeToolGrantError as exc:
            raise self._api_access_denied(exc) from exc
        return MemoryApiEntryRead.from_entry(self.append_reflection(memory_id, payload.reflection))

    def query_memory(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None = None,
        record_event: bool = True,
        commit_event: bool = True,
    ) -> list[MemoryPromptSnippet]:
        context = current_context or self.current_context
        effective_query = self._authorize_and_canonicalize_query(query, current_context=context)
        lookup_queries = self._lookup_queries(effective_query, current_context=context)
        if len(lookup_queries) == 1:
            snippets = self.store.query(lookup_queries[0])
        else:
            snippets = self._query_memory_across_contexts(effective_query, lookup_queries)
        if record_event:
            self._record_retrieval_event(
                query=query,
                lookup_queries=lookup_queries,
                snippets=snippets,
                current_context=context,
                commit=commit_event,
            )
        return snippets

    def _query_memory_across_contexts(
        self,
        query: MemoryQuery,
        lookup_queries: Sequence[MemoryQuery],
    ) -> list[MemoryPromptSnippet]:
        snippets: list[MemoryPromptSnippet] = []
        seen_memory_ids: set[str] = set()
        fetch_limit = query.offset + query.limit
        for lookup_query in lookup_queries:
            page_query = lookup_query.model_copy(
                update={"limit": fetch_limit, "offset": 0, "max_characters": None}
            )
            for snippet in self.store.query(page_query):
                if snippet.memory_id in seen_memory_ids:
                    continue
                snippets.append(snippet)
                seen_memory_ids.add(snippet.memory_id)
        reranked = self._rerank_lookup_snippets(snippets)
        return self._apply_lookup_window(
            reranked,
            offset=query.offset,
            limit=query.limit,
            max_characters=query.max_characters,
        )

    def record_injection_event(
        self,
        *,
        snippets: Sequence[MemoryPromptSnippet],
        injected_text: str,
        filters: dict[str, Any],
        budget: dict[str, Any],
        current_context: MemoryLookupContext | None = None,
        retrieval_mode: str = "prompt-context",
        commit: bool = True,
    ) -> None:
        context = current_context or self.current_context
        event_context = self._event_context_from_lookup(context)
        if event_context is None or event_context.run_id is None:
            return
        self._stage_event(
            event_context=event_context,
            event_type="injected",
            retrieval_mode=retrieval_mode,
            filters=filters,
            budget=budget,
            injected_text=self._bounded_text(
                injected_text,
                max_characters=_EVENT_TEXT_SNAPSHOT_MAX_CHARACTERS,
            ),
            result_snapshot=self._snippet_result_snapshot(snippets),
            status_snapshot={"status": "injected" if injected_text else "empty"},
            commit=commit,
        )

    def get_audit_links(self, memory_id: str) -> MemoryAuditLinks:
        return self.store.audit_links(memory_id)

    def _query_api_memory(
        self,
        payload: MemoryApiListRequest,
        *,
        current_context: MemoryLookupContext,
    ) -> list[MemoryPromptSnippet]:
        return self.query_memory(
            payload.to_query(),
            current_context=current_context,
            record_event=False,
        )

    def _authorized_entry(
        self,
        memory_id: str,
        *,
        action: MemoryNamespaceAction,
        current_context: MemoryLookupContext,
    ) -> MemoryEntryRead:
        entry = self.get_memory(memory_id)
        _ = self._authorize_and_canonicalize_scope(
            entry.scope,
            action=action,
            current_context=current_context,
        )
        return entry

    @staticmethod
    def _lookup_context_from_api_access(access: MemoryApiAccessContext) -> MemoryLookupContext:
        return MemoryLookupContext(
            run_id=access.run_id,
            package_key=access.package_key,
            workflow_key=access.workflow_key,
            agent_key=access.agent_key,
        )

    @staticmethod
    def _api_access_denied(error: RuntimeToolGrantError) -> ApiError:
        return ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            code=error.code,
            message=error.message,
            details=error.details,
        )

    def _record_retrieval_event(
        self,
        *,
        query: MemoryQuery,
        lookup_queries: Sequence[MemoryQuery],
        snippets: Sequence[MemoryPromptSnippet],
        current_context: MemoryLookupContext | None,
        commit: bool,
    ) -> None:
        event_context = self._event_context_from_lookup(current_context)
        if event_context is None or event_context.run_id is None:
            return
        retrieval_mode = self._snippet_retrieval_mode(snippets)
        self._stage_event(
            event_context=event_context,
            event_type="retrieved",
            retrieval_mode=retrieval_mode,
            filters={
                "requested": self._query_filter_snapshot(query),
                "effective": [
                    self._query_filter_snapshot(lookup_query) for lookup_query in lookup_queries
                ],
                "context": self._lookup_context_snapshot(current_context),
            },
            budget=self._query_budget_snapshot(query),
            excerpt=self._bounded_text(
                "\n\n".join(snippet.text for snippet in snippets),
                max_characters=self._event_text_budget(query),
            ),
            result_snapshot=self._snippet_result_snapshot(snippets),
            status_snapshot={
                "status": "completed",
                "resultCount": len(snippets),
                "retrievalMode": retrieval_mode,
                "scopeMode": query.scope_mode,
            },
            commit=commit,
        )

    def _stage_event(
        self,
        *,
        event_context: MemoryEventContext,
        event_type: str,
        retrieval_mode: str | None,
        filters: dict[str, Any],
        budget: dict[str, Any],
        excerpt: str | None = None,
        injected_text: str | None = None,
        result_snapshot: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
        commit: bool,
    ) -> None:
        try:
            _ = self.event_repository.add_event(
                run_id=event_context.run_id,
                run_step_id=event_context.run_step_id,
                run_agent_invocation_id=event_context.run_agent_invocation_id,
                run_operation_invocation_id=event_context.run_operation_invocation_id,
                step_id=event_context.step_id,
                invocation_id=event_context.invocation_id,
                event_type=event_type,
                retrieval_mode=retrieval_mode,
                filters=filters,
                budget=budget,
                excerpt=excerpt,
                injected_text=injected_text,
                result_snapshot=result_snapshot or {},
                status_snapshot=status_snapshot or {},
                trace_span_id=event_context.trace_span_id,
            )
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except Exception:
            if commit:
                self.session.rollback()
            raise

    @classmethod
    def _rerank_lookup_snippets(
        cls,
        snippets: Sequence[MemoryPromptSnippet],
    ) -> list[MemoryPromptSnippet]:
        ranked = sorted(snippets, key=cls._lookup_snippet_sort_key)
        reranked: list[MemoryPromptSnippet] = []
        for rank, snippet in enumerate(ranked, start=1):
            score = snippet.retrieval_score
            if score is None:
                reranked.append(snippet)
                continue
            reranked.append(
                snippet.model_copy(
                    update={"retrieval_score": score.model_copy(update={"rank": rank})}
                )
            )
        return reranked

    @staticmethod
    def _lookup_snippet_sort_key(snippet: MemoryPromptSnippet) -> tuple[object, ...]:
        score = snippet.retrieval_score
        return (
            0 if score is None else -score.scope_specificity,
            0.0 if score is None else -score.score,
            0.0 if score is None or score.lexical_score is None else -score.lexical_score,
            -snippet.created_at.timestamp(),
            snippet.memory_id,
        )

    @staticmethod
    def _event_context_from_lookup(
        context: MemoryLookupContext | None,
    ) -> MemoryEventContext | None:
        if context is None or context.run_id is None:
            return None
        return MemoryEventContext(
            run_id=context.run_id,
            run_step_id=context.run_step_id,
            run_agent_invocation_id=context.run_agent_invocation_id,
            run_operation_invocation_id=context.run_operation_invocation_id,
            step_id=context.step_id,
            invocation_id=context.invocation_id,
            trace_span_id=context.trace_span_id,
        )

    @staticmethod
    def _query_filter_snapshot(query: MemoryQuery) -> dict[str, Any]:
        payload = query.model_dump(mode="json", by_alias=True, exclude_none=True)
        for budget_field in ("limit", "offset", "maxCharacters"):
            _ = payload.pop(budget_field, None)
        return payload

    @staticmethod
    def _query_budget_snapshot(query: MemoryQuery) -> dict[str, Any]:
        return {
            "limit": query.limit,
            "offset": query.offset,
            "maxCharacters": query.max_characters,
        }

    @staticmethod
    def _event_text_budget(query: MemoryQuery) -> int:
        raw_budget = query.max_characters
        if raw_budget is None:
            return _EVENT_TEXT_SNAPSHOT_MAX_CHARACTERS
        return min(raw_budget, _EVENT_TEXT_SNAPSHOT_MAX_CHARACTERS)

    @staticmethod
    def _lookup_context_snapshot(context: MemoryLookupContext | None) -> dict[str, Any]:
        if context is None:
            return {}
        return {
            key: value
            for key, value in {
                "runId": context.run_id,
                "packageKey": context.package_key,
                "workflowKey": context.workflow_key,
                "agentKey": context.agent_key,
                "runStepId": context.run_step_id,
                "runAgentInvocationId": context.run_agent_invocation_id,
                "runOperationInvocationId": context.run_operation_invocation_id,
                "stepId": context.step_id,
                "invocationId": context.invocation_id,
                "traceSpanId": context.trace_span_id,
            }.items()
            if value is not None
        }

    @classmethod
    def _snippet_result_snapshot(
        cls,
        snippets: Sequence[MemoryPromptSnippet],
    ) -> dict[str, Any]:
        return {
            "resultCount": len(snippets),
            "retrievalMode": cls._snippet_retrieval_mode(snippets),
            "scoring": {
                "algorithm": "scope-first-rrf-v1",
                "lexicalBaseline": True,
            },
            "snippets": [cls._snippet_snapshot(snippet) for snippet in snippets],
        }

    @classmethod
    def _snippet_snapshot(cls, snippet: MemoryPromptSnippet) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "memoryId": snippet.memory_id,
            "revisionId": snippet.revision_id,
            "kind": snippet.kind,
            "summary": snippet.summary,
            "scope": snippet.scope.model_dump(mode="json", by_alias=True),
            "subjectRefs": [
                subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                for subject_ref in snippet.subject_refs
            ],
            "excerpt": cls._bounded_text(
                snippet.text,
                max_characters=_EVENT_SNIPPET_EXCERPT_MAX_CHARACTERS,
            ),
        }
        if snippet.retrieval_score is not None:
            payload["score"] = snippet.retrieval_score.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
        return payload

    @staticmethod
    def _snippet_retrieval_mode(snippets: Sequence[MemoryPromptSnippet]) -> str:
        del snippets
        return "lexical"

    @staticmethod
    def _bounded_text(text: str, *, max_characters: int) -> str | None:
        if not text:
            return None
        if len(text) <= max_characters:
            return text
        return f"{text[: max_characters - 1]}…"

    def _authorize_and_canonicalize_write_payload(
        self,
        payload: MemoryWriteRequest,
    ) -> MemoryWriteRequest:
        scope = self._authorize_and_canonicalize_scope(
            payload.scope,
            action="write",
            current_context=self.current_context,
        )
        if scope == payload.scope:
            return payload
        return payload.model_copy(update={"scope": scope})

    def _authorize_and_canonicalize_query(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None,
    ) -> MemoryQuery:
        if query.scope is None:
            if current_context is None or not current_context.has_values():
                raise self._namespace_access_denied(
                    "Global memory search is not supported; provide a scope or current context."
                )
            return query
        scope = self._authorize_and_canonicalize_scope(
            query.scope,
            action="read",
            current_context=current_context,
        )
        if scope == query.scope:
            return query
        return query.model_copy(update={"scope": scope})

    def _authorize_and_canonicalize_scope(
        self,
        scope: MemoryScope,
        *,
        action: MemoryNamespaceAction,
        current_context: MemoryLookupContext | None,
    ) -> MemoryScope:
        if scope.scope_type == MemoryScopeType.NAMESPACE:
            namespace = MemoryNamespaceSelector.from_scope(scope)
            self._authorize_namespace(namespace, action=action, current_context=current_context)
            return scope
        if current_context is None:
            if scope.scope_type in {
                MemoryScopeType.PACKAGE,
                MemoryScopeType.WORKFLOW,
                MemoryScopeType.AGENT,
            }:
                raise self._namespace_access_denied(
                    "Package-private memory access requires package runtime context."
                )
            return scope
        self._reject_cross_context_private_scope(scope, current_context=current_context)
        canonical_scope = current_context.canonicalize_scope(scope)
        return canonical_scope

    def _authorize_namespace(
        self,
        namespace: MemoryNamespaceSelector,
        *,
        action: MemoryNamespaceAction,
        current_context: MemoryLookupContext | None,
    ) -> None:
        package_key = (
            None
            if current_context is None
            else current_context.normalized_text(current_context.package_key)
        )
        if package_key is None:
            raise self._namespace_access_denied(
                "Shared memory namespace access requires package runtime context."
            )
        if package_key == namespace.owner_package_key and current_context is not None:
            if current_context.declares_namespace(namespace):
                return
            raise self._namespace_access_denied(
                "Shared memory namespace must be declared by the owner package."
            )
        if current_context is not None and current_context.has_namespace_grant(namespace, action):
            return
        raise self._namespace_access_denied(
            f"Package {package_key!r} is not authorized for {action} access to memory namespace "
            f"{namespace.qualified_key!r}."
        )

    @classmethod
    def _reject_cross_context_private_scope(
        cls,
        scope: MemoryScope,
        *,
        current_context: MemoryLookupContext,
    ) -> None:
        package_key = current_context.normalized_text(current_context.package_key)
        if scope.scope_type == MemoryScopeType.RUN and current_context.run_id is not None:
            if scope.scope_key != str(current_context.run_id):
                raise cls._namespace_access_denied(
                    "Cross-run private memory access is not allowed."
                )
        if package_key is None:
            package_private_scope = {
                MemoryScopeType.PACKAGE,
                MemoryScopeType.WORKFLOW,
                MemoryScopeType.AGENT,
            }
            if scope.scope_type in package_private_scope:
                raise cls._namespace_access_denied(
                    "Package-private memory access requires package runtime context."
                )
            return
        if scope.scope_type == MemoryScopeType.PACKAGE and scope.scope_key != package_key:
            raise cls._namespace_access_denied(
                "Cross-package private memory access must use an explicit shared namespace grant."
            )
        if scope.scope_type not in {MemoryScopeType.WORKFLOW, MemoryScopeType.AGENT}:
            return
        foreign_prefix = ":" in scope.scope_key and not scope.scope_key.startswith(
            f"{package_key}:"
        )
        namespace_like = "/" in scope.scope_key
        if foreign_prefix or namespace_like:
            raise cls._namespace_access_denied(
                "Cross-package private memory access must use an explicit shared namespace grant."
            )

    def _lookup_queries(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None,
    ) -> list[MemoryQuery]:
        if query.scope is not None:
            return [query]
        context = current_context or self.current_context
        if context is None or not context.has_values():
            raise self._namespace_access_denied(
                "Global memory search is not supported; provide a scope or current context."
            )

        context_updates = self._context_filter_updates(query, context)
        scopes = context.scopes()
        if not scopes:
            return [query.model_copy(update=context_updates)] if context_updates else [query]
        return [
            query.model_copy(
                update={
                    **context_updates,
                    "scope": scope,
                    "scope_mode": "explicit-selectors",
                }
            )
            for scope in scopes
        ]

    @staticmethod
    def _namespace_access_denied(message: str) -> RuntimeToolGrantError:
        return RuntimeToolGrantError(
            code=MEMORY_NAMESPACE_ACCESS_DENIED_CODE,
            message=MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE,
            details=[{"field": "namespace", "issue": message}],
        )

    @staticmethod
    def _context_filter_updates(
        query: MemoryQuery,
        context: MemoryLookupContext,
    ) -> dict[str, object]:
        updates: dict[str, object] = {}
        agent_key = MemoryLookupContext.normalized_text(context.agent_key)
        workflow_key = MemoryLookupContext.normalized_text(context.workflow_key)
        if query.agent_key is None and agent_key is not None:
            updates["agent_key"] = agent_key
        if query.workflow_key is None and workflow_key is not None:
            updates["workflow_key"] = workflow_key
        if updates:
            updates["scope_mode"] = "explicit-selectors"
        return updates

    @staticmethod
    def _apply_lookup_window(
        snippets: list[MemoryPromptSnippet],
        *,
        offset: int,
        limit: int,
        max_characters: int | None,
    ) -> list[MemoryPromptSnippet]:
        windowed: list[MemoryPromptSnippet] = []
        used_characters = 0
        for snippet in snippets[offset:]:
            if len(windowed) >= limit:
                break
            separator_characters = 2 if windowed else 0
            next_size = used_characters + separator_characters + len(snippet.text)
            if max_characters is not None and next_size > max_characters:
                break
            windowed.append(snippet)
            used_characters = next_size
        return windowed


__all__ = ["MemoryLookupContext", "MemoryService"]
