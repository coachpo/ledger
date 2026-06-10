from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.core.errors import ApiError
from app.repositories.agent_memory import RunMemoryEventRepository
from app.schemas.memory import (
    MEMORY_NAMESPACE_ACCESS_DENIED_CODE,
    MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE,
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
    MemoryQuery,
    MemoryReflection,
    MemoryScope,
    MemoryScopeType,
    MemoryWriteRequest,
    MemoryWriteResult,
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
            result = self.store.create_pending(
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
