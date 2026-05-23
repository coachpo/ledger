from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.repositories.agent_memory import RunMemoryEventRepository
from app.schemas.memory import (
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryDecision,
    MemoryEntryRead,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryReflection,
    MemoryScope,
    MemoryScopeType,
    MemoryWriteRequest,
    MemoryWriteResult,
)
from app.schemas.memory_report import (
    AgentMemoryReportCreateMetadata,
    AgentMemoryTrustedCreateContext,
)
from app.services.capability_service import CapabilityService, RuntimeToolGrantPolicy
from app.services.memory_store import (
    MemoryEventContext,
    MemoryStore,
    PostgresMemoryStore,
    canonical_package_qualified_scope_key,
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
        return canonical_package_qualified_scope_key(
            package_key=package_key,
            local_key=local_key,
        )

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
        self.capability_service: CapabilityService = CapabilityService(
            session,
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
            self.capability_service.require_runtime_tool_grant(
                capability_references=capability_references,
                grant_policy=grant_policy,
            )
        effective_payload = self._canonicalize_write_payload(payload)
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

    def query_memory(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None = None,
        record_event: bool = True,
        commit_event: bool = True,
    ) -> list[MemoryPromptSnippet]:
        context = current_context or self.current_context
        effective_query = self._canonicalize_query(query, current_context=context)
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
        vector_distance = None if score is None else score.vector_distance
        return (
            0 if score is None else -score.scope_specificity,
            0.0 if score is None else -score.score,
            0.0 if score is None or score.lexical_score is None else -score.lexical_score,
            float("inf") if vector_distance is None else vector_distance,
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
        for snippet in snippets:
            score = snippet.retrieval_score
            if score is not None and "vector" in score.sources:
                return "hybrid"
        return "lexical"

    @staticmethod
    def _bounded_text(text: str, *, max_characters: int) -> str | None:
        if not text:
            return None
        if len(text) <= max_characters:
            return text
        return f"{text[: max_characters - 1]}…"

    def _canonicalize_write_payload(self, payload: MemoryWriteRequest) -> MemoryWriteRequest:
        if self.current_context is None:
            return payload
        canonical_scope = self.current_context.canonicalize_scope(payload.scope)
        if canonical_scope == payload.scope:
            return payload
        return payload.model_copy(update={"scope": canonical_scope})

    @staticmethod
    def _canonicalize_query(
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None,
    ) -> MemoryQuery:
        if current_context is None or query.scope is None:
            return query
        canonical_scope = current_context.canonicalize_scope(query.scope)
        if canonical_scope == query.scope:
            return query
        return query.model_copy(update={"scope": canonical_scope})

    def _lookup_queries(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None,
    ) -> list[MemoryQuery]:
        if self._has_explicit_selectors(query):
            return [query]
        context = current_context or self.current_context
        if context is None or not context.has_values():
            return [query]

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
    def _has_explicit_selectors(query: MemoryQuery) -> bool:
        return query.scope is not None or bool(query.subject_refs) or query.kind is not None

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

    @staticmethod
    def write_request_from_report_create(
        *,
        payload: AgentMemoryReportCreateMetadata,
        trusted_context: AgentMemoryTrustedCreateContext,
    ) -> MemoryWriteRequest:
        analysis = payload.analysis
        return MemoryWriteRequest(
            ticker=analysis.ticker,
            portfolio_slug=analysis.portfolio_slug,
            horizon_days=analysis.horizon_days,
            confidence=analysis.confidence,
            decision_summary=analysis.decision_summary,
            benchmark_symbol=analysis.benchmark_symbol,
            decision=MemoryDecision(
                action=analysis.decision.action,
                rationale=analysis.decision.rationale,
                risk_summary=analysis.decision.risk_summary,
                execution_plan=analysis.decision.execution_plan,
            ),
            provenance=MemoryProvenance(
                run_id=trusted_context.run_id,
                agent_key=trusted_context.agent_key,
                agent_version=trusted_context.agent_version,
                agent_name=trusted_context.agent_name,
                workflow_key=trusted_context.workflow_key,
                workflow_version=trusted_context.workflow_version,
                step_id=trusted_context.step_id,
                slot=trusted_context.slot,
                trace_id=trusted_context.trace_id,
            ),
        )


__all__ = ["MemoryLookupContext", "MemoryService"]
