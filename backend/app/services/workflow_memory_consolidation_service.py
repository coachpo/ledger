from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.formatting import utcnow
from app.models.workflow_memory import WorkflowMemoryConsolidationRun, WorkflowMemoryItem
from app.repositories.workflow_memory import WorkflowMemoryRepository


@dataclass(frozen=True)
class _ConsolidationScope:
    owner_type: str
    owner_id: str
    package_key: str
    workflow_key: str
    namespace: str


class WorkflowMemoryConsolidationService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

    def consolidate_run_end(self, run_id: int) -> list[WorkflowMemoryConsolidationRun]:
        now = utcnow()
        source_items = self.repository.list_run_end_consolidation_sources(run_id, now=now)
        if not source_items:
            return []

        results: list[WorkflowMemoryConsolidationRun] = []
        try:
            for scope, scoped_sources in self._group_sources_by_scope(source_items).items():
                consolidation = self._consolidate_scope(
                    run_id=run_id,
                    scope=scope,
                    source_items=scoped_sources,
                    now=now,
                )
                results.append(consolidation)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return results

    def _consolidate_scope(
        self,
        *,
        run_id: int,
        scope: _ConsolidationScope,
        source_items: list[WorkflowMemoryItem],
        now: datetime,
    ) -> WorkflowMemoryConsolidationRun:
        consolidation_id = self._consolidation_id(run_id=run_id, scope=scope)
        consolidation = self.repository.get_consolidation_run_by_public_id(
            consolidation_id,
            owner_type=scope.owner_type,
            owner_id=scope.owner_id,
        )
        if consolidation is not None and consolidation.status == "succeeded":
            return consolidation
        if consolidation is None:
            consolidation = self.repository.record_consolidation_run(
                consolidation_id=consolidation_id,
                owner_type=scope.owner_type,
                owner_id=scope.owner_id,
                package_key=scope.package_key,
                workflow_key=scope.workflow_key,
                namespace=scope.namespace,
                status="running",
                started_at=now,
                source_memory_ids_json=[item.memory_id for item in source_items],
            )
        else:
            consolidation.status = "running"
            consolidation.started_at = now
            consolidation.finished_at = None
            consolidation.source_memory_ids_json = [item.memory_id for item in source_items]
            consolidation.output_memory_ids_json = []
            consolidation.stats_json = {}

        survivor_ids, superseded_ids, duplicate_set_count = self._supersede_exact_duplicates(
            run_id=run_id,
            scope=scope,
            source_items=source_items,
            now=now,
        )
        stats = {
            "strategy": "exact_duplicate_supersession",
            "runId": run_id,
            "sourceMemoryCount": len(source_items),
            "duplicateSetCount": duplicate_set_count,
            "survivorCount": len(survivor_ids),
            "supersededCount": len(superseded_ids),
            "supersededMemoryIds": superseded_ids,
        }
        consolidation.status = "succeeded"
        consolidation.finished_at = utcnow()
        consolidation.output_memory_ids_json = survivor_ids
        consolidation.stats_json = stats
        _ = self.repository.record_audit_event(
            event_type="memory_consolidation_run",
            target_type="consolidation_run",
            target_id=consolidation.consolidation_id,
            owner_type=scope.owner_type,
            owner_id=scope.owner_id,
            package_key=scope.package_key,
            workflow_key=scope.workflow_key,
            run_id=run_id,
            event_json=stats,
        )
        self.session.flush()
        return consolidation

    def _supersede_exact_duplicates(
        self,
        *,
        run_id: int,
        scope: _ConsolidationScope,
        source_items: list[WorkflowMemoryItem],
        now: datetime,
    ) -> tuple[list[str], list[str], int]:
        survivor_ids: set[str] = set()
        superseded_ids: list[str] = []
        duplicate_set_count = 0
        seen_keys: set[tuple[str, str]] = set()
        for source in source_items:
            peer_key = (source.kind, source.content_fingerprint)
            if peer_key in seen_keys:
                continue
            seen_keys.add(peer_key)
            peers = self.repository.list_active_committed_exact_duplicate_peers(
                owner_type=scope.owner_type,
                owner_id=scope.owner_id,
                package_key=scope.package_key,
                workflow_key=scope.workflow_key,
                namespace=scope.namespace,
                kind=source.kind,
                content_fingerprint=source.content_fingerprint,
                now=now,
            )
            if not peers:
                continue
            survivor = max(peers, key=self._survivor_sort_key)
            survivor_ids.add(survivor.memory_id)
            if len(peers) < 2:
                continue
            duplicate_set_count += 1
            for peer in peers:
                if peer.id == survivor.id:
                    continue
                peer.lifecycle_status = "superseded"
                peer.superseded_by_id = survivor.id
                peer.updated_at = utcnow()
                superseded_ids.append(peer.memory_id)
                _ = self.repository.record_audit_event(
                    event_type="memory_consolidation_supersede",
                    target_type="memory_item",
                    target_id=peer.memory_id,
                    owner_type=peer.owner_type,
                    owner_id=peer.owner_id,
                    package_key=peer.package_key,
                    workflow_key=peer.workflow_key,
                    agent_key=peer.agent_key,
                    step_id=peer.step_id,
                    run_id=run_id,
                    invocation_id=peer.invocation_id,
                    event_json={
                        "consolidationStrategy": "exact_duplicate_supersession",
                        "survivorMemoryId": survivor.memory_id,
                        "survivorId": survivor.id,
                        "contentFingerprint": peer.content_fingerprint,
                        "namespace": peer.namespace,
                        "kind": peer.kind,
                    },
                )
        return sorted(survivor_ids), superseded_ids, duplicate_set_count

    @classmethod
    def _survivor_sort_key(cls, item: WorkflowMemoryItem) -> tuple[float, float, float, float, int]:
        return (
            cls._numeric_metadata_value(item, "confidence"),
            cls._numeric_metadata_value(item, "importance"),
            item.valid_from.timestamp(),
            item.created_at.timestamp(),
            int(item.id or 0),
        )

    @staticmethod
    def _numeric_metadata_value(item: WorkflowMemoryItem, key: str) -> float:
        for payload in (item.content_json, item.provenance_json):
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"high", "strong"}:
                    return 0.9
                if normalized in {"medium", "moderate"}:
                    return 0.6
                if normalized in {"low", "weak"}:
                    return 0.3
                try:
                    return float(normalized)
                except ValueError:
                    continue
        return -1.0

    @staticmethod
    def _group_sources_by_scope(
        source_items: Iterable[WorkflowMemoryItem],
    ) -> dict[_ConsolidationScope, list[WorkflowMemoryItem]]:
        grouped: dict[_ConsolidationScope, list[WorkflowMemoryItem]] = defaultdict(list)
        for item in source_items:
            grouped[
                _ConsolidationScope(
                    owner_type=item.owner_type,
                    owner_id=item.owner_id,
                    package_key=item.package_key,
                    workflow_key=item.workflow_key,
                    namespace=item.namespace,
                )
            ].append(item)
        return dict(grouped)

    @staticmethod
    def _consolidation_id(*, run_id: int, scope: _ConsolidationScope) -> str:
        payload = {
            "ownerType": scope.owner_type,
            "ownerId": scope.owner_id,
            "packageKey": scope.package_key,
            "workflowKey": scope.workflow_key,
            "runId": run_id,
            "namespace": scope.namespace,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"wmc_run_end_{run_id}_{digest[:32]}"


__all__ = ["WorkflowMemoryConsolidationService"]
