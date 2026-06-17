from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy.orm import Session

from app.core.formatting import utcnow
from app.models.workflow_memory import WorkflowMemoryItem
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import (
    WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX,
    WorkflowMemoryContextItem,
    WorkflowMemoryContextPack,
    WorkflowMemoryContextRequest,
    WorkflowMemoryScope,
)

_TERM_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}")
_KIND_PRIORS: dict[str, float] = {
    "decision": 0.95,
    "fact": 0.85,
    "preference": 0.80,
    "observation": 0.75,
}


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rounded_score(value: float) -> float:
    return round(_clamp_score(value), 6)


@dataclass(frozen=True)
class _RankedMemoryEntry:
    record: WorkflowMemoryItem
    score: float
    components: dict[str, float]


class WorkflowMemoryContextService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

    def build_context_pack(
        self,
        *,
        request: WorkflowMemoryContextRequest,
        now: datetime | None = None,
    ) -> WorkflowMemoryContextPack:
        policy = request.policy
        retrieval = policy.retrieval
        if not policy.enabled or retrieval is None or not retrieval.enabled:
            return WorkflowMemoryContextPack(items=[], policy_scope=request.scope)
        namespaces = tuple(
            namespace for namespace in retrieval.namespaces if namespace == request.scope.namespace
        )
        ranking_now = now or utcnow()
        records = self.repository.list_active_memory(
            package_key=request.scope.package_key,
            workflow_key=request.scope.workflow_key,
            agent_key=request.scope.agent_key,
            step_id=request.scope.step_id,
            namespaces=namespaces,
            now=ranking_now,
            limit=WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX,
            owner_type=request.owner_type,
            owner_id=request.owner_id,
        )
        ranked = [
            self._rank_record(record, query_terms=request.query_terms, now=ranking_now)
            for record in records
            if not retrieval.include_kinds or record.kind in retrieval.include_kinds
        ]
        exact_candidate_count = len(ranked)
        threshold = retrieval.relevance_threshold
        if threshold is not None:
            ranked = [entry for entry in ranked if entry.score >= threshold]
        ranked.sort(key=self._ranking_sort_key)
        selected = ranked[: retrieval.max_items]
        items = [self._context_item(entry.record) for entry in selected]
        return WorkflowMemoryContextPack(
            items=items,
            policy_scope=request.scope,
            authoritative=False,
            ranking={
                "enabled": True,
                "candidateCount": exact_candidate_count,
                "thresholdedCandidateCount": len(ranked),
                "selectedCount": len(selected),
                "queryTermCount": len(request.query_terms),
                "relevanceThreshold": threshold,
                "items": [self._ranking_debug_item(entry) for entry in selected],
            },
        )

    @staticmethod
    def _context_item(record: WorkflowMemoryItem) -> WorkflowMemoryContextItem:
        return WorkflowMemoryContextItem(
            item_id=record.memory_id,
            content=record.content_json,
            kind=record.kind,
            namespace=record.namespace,
            provenance=record.provenance_json,
            created_at=record.created_at,
            valid_from=record.valid_from,
            expires_at=record.expires_at,
            scope=WorkflowMemoryScope(
                package_key=record.package_key,
                workflow_key=record.workflow_key,
                agent_key=record.agent_key,
                step_id=record.step_id,
                namespace=record.namespace,
            ),
            authoritative=False,
        )

    def _rank_record(
        self,
        record: WorkflowMemoryItem,
        *,
        query_terms: tuple[str, ...],
        now: datetime,
    ) -> _RankedMemoryEntry:
        components = self._ranking_components(record, query_terms=query_terms, now=now)
        score = _rounded_score(
            (components["keywordOverlap"] * 0.18)
            + (components["recency"] * 0.05)
            + (components["kindPrior"] * 0.10)
            + (components["importance"] * 0.10)
            + (components["confidence"] * 0.10)
            + (components["expiryFactor"] * 0.05)
            + (components["exactScope"] * 0.42)
        )
        return _RankedMemoryEntry(record=record, score=score, components=components)

    def _ranking_components(
        self,
        record: WorkflowMemoryItem,
        *,
        query_terms: tuple[str, ...],
        now: datetime,
    ) -> dict[str, float]:
        return {
            "keywordOverlap": self._keyword_overlap(record, query_terms),
            "recency": self._recency_score(record, now=now),
            "kindPrior": _KIND_PRIORS.get(str(record.kind).strip().lower(), 0.65),
            "importance": self._numeric_metadata_score(record, "importance"),
            "confidence": self._numeric_metadata_score(record, "confidence"),
            "expiryFactor": self._expiry_factor(record, now=now),
            "exactScope": 1.0,
        }

    @staticmethod
    def _keyword_overlap(record: WorkflowMemoryItem, query_terms: tuple[str, ...]) -> float:
        if not query_terms:
            return 0.0
        search_text = (
            json.dumps(record.content_json, sort_keys=True, default=str)
            + " "
            + str(record.summary or "")
        )
        searchable: set[str] = set()
        for term in cast(list[str], _TERM_RE.findall(search_text)):
            searchable.add(term.lower())
        if not searchable:
            return 0.0
        overlap = sum(1 for term in query_terms if term in searchable)
        return _rounded_score(overlap / len(query_terms))

    @staticmethod
    def _recency_score(record: WorkflowMemoryItem, *, now: datetime) -> float:
        reference = max(record.valid_from, record.created_at)
        age_seconds = max(0.0, (now - reference).total_seconds())
        age_days = age_seconds / 86_400
        return _rounded_score(1 / (1 + (age_days / 30)))

    @staticmethod
    def _expiry_factor(record: WorkflowMemoryItem, *, now: datetime) -> float:
        if record.expires_at is None:
            return 1.0
        remaining_days = max(0.0, (record.expires_at - now).total_seconds() / 86_400)
        return _rounded_score(remaining_days / (remaining_days + 30))

    @staticmethod
    def _numeric_metadata_score(record: WorkflowMemoryItem, key: str) -> float:
        for payload in (record.content_json, record.provenance_json):
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                return _rounded_score(float(value))
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"high", "strong"}:
                    return 0.9
                if normalized in {"medium", "moderate"}:
                    return 0.6
                if normalized in {"low", "weak"}:
                    return 0.3
                try:
                    return _rounded_score(float(normalized))
                except ValueError:
                    continue
        return 0.5

    @staticmethod
    def _ranking_sort_key(
        entry: _RankedMemoryEntry,
    ) -> tuple[float, float, float, float, float, float, str, int]:
        record = entry.record
        components = entry.components
        return (
            -entry.score,
            -components["keywordOverlap"],
            -components["exactScope"],
            -components["kindPrior"],
            -record.valid_from.timestamp(),
            -record.created_at.timestamp(),
            record.memory_id,
            record.id,
        )

    @staticmethod
    def _ranking_debug_item(entry: _RankedMemoryEntry) -> dict[str, object]:
        record = entry.record
        return {
            "itemId": record.memory_id,
            "score": entry.score,
            "components": entry.components,
        }


__all__ = ["WorkflowMemoryContextService"]
