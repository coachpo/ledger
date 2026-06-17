from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import func, or_, select

from app.core.formatting import utcnow
from app.models.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
    WorkflowMemoryAuditEvent,
    WorkflowMemoryConsolidationRun,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
    WorkflowMemoryRevision,
)
from app.repositories.base import BaseRepository
from app.schemas.workflow_memory import WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX


def _canonicalize_workflow_memory_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if isinstance(value, list):
        return [_canonicalize_workflow_memory_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: canonicalized
            for key, raw_value in sorted(value.items())
            if (canonicalized := _canonicalize_workflow_memory_value(raw_value)) is not None
        }
    return value


def _content_fingerprint(*, kind: str, namespace: str, content_json: dict[str, Any]) -> str:
    payload = {
        "kind": kind.strip().lower(),
        "namespace": namespace.strip().lower(),
        "content": _canonicalize_workflow_memory_value(content_json),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _proposal_idempotency_key(
    *,
    package_key: str,
    workflow_key: str,
    agent_key: str,
    step_id: str,
    run_id: int | None,
    invocation_id: str | None,
    source_output_path: str | None,
    namespace: str,
    kind: str,
    content_fingerprint: str,
) -> str:
    payload = [
        _canonicalize_workflow_memory_value(package_key),
        _canonicalize_workflow_memory_value(workflow_key),
        _canonicalize_workflow_memory_value(agent_key),
        _canonicalize_workflow_memory_value(step_id),
        run_id,
        _canonicalize_workflow_memory_value(invocation_id),
        _canonicalize_workflow_memory_value(source_output_path),
        namespace.strip().lower(),
        kind.strip().lower(),
        content_fingerprint,
    ]
    serialized = json.dumps(payload, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class WorkflowMemoryRepository(BaseRepository[WorkflowMemoryItem]):
    model: ClassVar[type[WorkflowMemoryItem]] = WorkflowMemoryItem

    @staticmethod
    def default_owner_type() -> str:
        return DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE

    @staticmethod
    def default_owner_id() -> str:
        return DEFAULT_WORKFLOW_MEMORY_OWNER_ID

    def create_memory_item(
        self,
        *,
        memory_id: str,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespace: str,
        kind: str,
        content_json: dict[str, Any],
        summary: str,
        content_fingerprint: str | None = None,
        provenance_json: dict[str, Any] | None = None,
        policy_status: str = "committed",
        lifecycle_status: str = "active",
        valid_from: datetime | None = None,
        expires_at: datetime | None = None,
        superseded_by_id: int | None = None,
        deleted_at: datetime | None = None,
        proposal_id: int | None = None,
        decision_id: int | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
    ) -> WorkflowMemoryItem:
        item = self.model(
            memory_id=memory_id,
            owner_type=owner_type,
            owner_id=owner_id,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace,
            kind=kind,
            content_fingerprint=content_fingerprint
            or _content_fingerprint(kind=kind, namespace=namespace, content_json=content_json),
            content_json=content_json,
            summary=summary,
            provenance_json=provenance_json or {},
            policy_status=policy_status,
            lifecycle_status=lifecycle_status,
            valid_from=valid_from or utcnow(),
            expires_at=expires_at,
            superseded_by_id=superseded_by_id,
            deleted_at=deleted_at,
            proposal_id=proposal_id,
            decision_id=decision_id,
            run_id=run_id,
            invocation_id=invocation_id,
        )
        return self.add(item)

    def list_active_memory(
        self,
        *,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespaces: Sequence[str],
        now: datetime,
        limit: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowMemoryItem]:
        resolved_namespaces = tuple(dict.fromkeys(namespaces))
        if not resolved_namespaces or limit <= 0:
            return []
        unresolved_quarantine_exists = (
            select(WorkflowMemoryQuarantine.id)
            .where(
                WorkflowMemoryQuarantine.memory_item_id == self.model.id,
                WorkflowMemoryQuarantine.owner_type == owner_type,
                WorkflowMemoryQuarantine.owner_id == owner_id,
                WorkflowMemoryQuarantine.resolved_at.is_(None),
            )
            .exists()
        )
        statement = (
            select(self.model)
            .where(
                self.model.package_key == package_key,
                self.model.owner_type == owner_type,
                self.model.owner_id == owner_id,
                self.model.workflow_key == workflow_key,
                self.model.agent_key == agent_key,
                self.model.step_id == step_id,
                self.model.namespace.in_(resolved_namespaces),
                self.model.policy_status == "committed",
                self.model.lifecycle_status == "active",
                self.model.valid_from <= now,
                or_(self.model.expires_at.is_(None), self.model.expires_at > now),
                self.model.deleted_at.is_(None),
                self.model.superseded_by_id.is_(None),
                ~unresolved_quarantine_exists,
            )
            .order_by(
                self.model.valid_from.desc(),
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
            .limit(min(limit, WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX))
        )
        return self._list(statement)

    def create_proposal(
        self,
        *,
        proposal_id: str,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        run_id: int | None,
        invocation_id: str | None,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespace: str,
        kind: str,
        content_json: dict[str, Any],
        content_fingerprint: str | None = None,
        idempotency_key: str | None = None,
        reason: str | None = None,
        source_output_path: str | None = None,
        detectors_json: dict[str, Any] | None = None,
        status: str = "proposed",
    ) -> WorkflowMemoryProposal:
        resolved_content_fingerprint = content_fingerprint or _content_fingerprint(
            kind=kind,
            namespace=namespace,
            content_json=content_json,
        )
        proposal = WorkflowMemoryProposal(
            proposal_id=proposal_id,
            owner_type=owner_type,
            owner_id=owner_id,
            run_id=run_id,
            invocation_id=invocation_id,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace,
            kind=kind,
            content_fingerprint=resolved_content_fingerprint,
            idempotency_key=idempotency_key
            or _proposal_idempotency_key(
                package_key=package_key,
                workflow_key=workflow_key,
                agent_key=agent_key,
                step_id=step_id,
                run_id=run_id,
                invocation_id=invocation_id,
                source_output_path=source_output_path,
                namespace=namespace,
                kind=kind,
                content_fingerprint=resolved_content_fingerprint,
            ),
            content_json=content_json,
            reason=reason,
            source_output_path=source_output_path,
            detectors_json=detectors_json or {},
            status=status,
        )
        self.session.add(proposal)
        return proposal

    def get_proposal_by_idempotency_key(
        self,
        idempotency_key: str,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryProposal | None:
        statement = select(WorkflowMemoryProposal).where(
            WorkflowMemoryProposal.idempotency_key == idempotency_key,
            WorkflowMemoryProposal.owner_type == owner_type,
            WorkflowMemoryProposal.owner_id == owner_id,
        )
        return self.session.scalar(statement)

    def record_decision(
        self,
        *,
        decision_id: str,
        proposal: WorkflowMemoryProposal,
        decision: str,
        reason_code: str,
        decided_by: str,
        reason: str | None = None,
        policy_snapshot_json: dict[str, Any] | None = None,
    ) -> WorkflowMemoryDecision:
        if proposal.id is None:
            self.session.flush()
        decision_row = WorkflowMemoryDecision(
            decision_id=decision_id,
            proposal_id=proposal.id,
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            policy_snapshot_json=policy_snapshot_json or {},
            decided_by=decided_by,
        )
        self.session.add(decision_row)
        self.session.flush()
        return decision_row

    def record_audit_event(
        self,
        *,
        event_type: str,
        target_type: str,
        target_id: str,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        package_key: str,
        workflow_key: str,
        agent_key: str | None = None,
        step_id: str | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
        event_json: dict[str, Any] | None = None,
    ) -> WorkflowMemoryAuditEvent:
        event = WorkflowMemoryAuditEvent(
            event_type=event_type,
            owner_type=owner_type,
            owner_id=owner_id,
            target_type=target_type,
            target_id=target_id,
            run_id=run_id,
            invocation_id=invocation_id,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            event_json=event_json or {},
        )
        self.session.add(event)
        return event

    def record_revision(
        self,
        *,
        memory_item: WorkflowMemoryItem,
        revision_id: str,
        version: int,
        content_json: dict[str, Any],
        summary: str,
        provenance_json: dict[str, Any] | None = None,
        supersedes_revision_id: str | None = None,
    ) -> WorkflowMemoryRevision:
        if memory_item.id is None:
            self.session.flush()
        revision = WorkflowMemoryRevision(
            memory_item_id=memory_item.id,
            revision_id=revision_id,
            version=version,
            content_json=content_json,
            summary=summary,
            provenance_json=provenance_json or {},
            supersedes_revision_id=supersedes_revision_id,
        )
        self.session.add(revision)
        return revision

    def quarantine_memory_item(
        self,
        *,
        memory_item: WorkflowMemoryItem,
        reason_code: str,
        reason: str | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
        detectors_json: dict[str, Any] | None = None,
    ) -> WorkflowMemoryQuarantine:
        if memory_item.id is None:
            self.session.flush()
        quarantine = WorkflowMemoryQuarantine(
            owner_type=memory_item.owner_type,
            owner_id=memory_item.owner_id,
            memory_item_id=memory_item.id,
            proposal_id=None,
            run_id=run_id,
            invocation_id=invocation_id,
            reason_code=reason_code,
            reason=reason,
            detectors_json=detectors_json or {},
        )
        self.session.add(quarantine)
        return quarantine

    def quarantine_proposal(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        reason_code: str,
        reason: str | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
        detectors_json: dict[str, Any] | None = None,
    ) -> WorkflowMemoryQuarantine:
        if proposal.id is None:
            self.session.flush()
        quarantine = WorkflowMemoryQuarantine(
            owner_type=proposal.owner_type,
            owner_id=proposal.owner_id,
            memory_item_id=None,
            proposal_id=proposal.id,
            run_id=run_id,
            invocation_id=invocation_id,
            reason_code=reason_code,
            reason=reason,
            detectors_json=detectors_json or {},
        )
        self.session.add(quarantine)
        return quarantine

    def record_consolidation_run(
        self,
        *,
        consolidation_id: str,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        package_key: str,
        workflow_key: str,
        namespace: str,
        status: str,
        started_at: datetime,
        finished_at: datetime | None = None,
        source_memory_ids_json: Sequence[str] | None = None,
        output_memory_ids_json: Sequence[str] | None = None,
        stats_json: dict[str, Any] | None = None,
    ) -> WorkflowMemoryConsolidationRun:
        consolidation = WorkflowMemoryConsolidationRun(
            consolidation_id=consolidation_id,
            owner_type=owner_type,
            owner_id=owner_id,
            package_key=package_key,
            workflow_key=workflow_key,
            namespace=namespace,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            source_memory_ids_json=list(source_memory_ids_json or []),
            output_memory_ids_json=list(output_memory_ids_json or []),
            stats_json=stats_json or {},
        )
        self.session.add(consolidation)
        return consolidation

    def get_consolidation_run_by_public_id(
        self,
        consolidation_id: str,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryConsolidationRun | None:
        statement = select(WorkflowMemoryConsolidationRun).where(
            WorkflowMemoryConsolidationRun.consolidation_id == consolidation_id,
            WorkflowMemoryConsolidationRun.owner_type == owner_type,
            WorkflowMemoryConsolidationRun.owner_id == owner_id,
        )
        return self.session.scalar(statement)

    def list_run_end_consolidation_sources(
        self,
        run_id: int,
        *,
        now: datetime,
    ) -> list[WorkflowMemoryItem]:
        unresolved_quarantine_exists = (
            select(WorkflowMemoryQuarantine.id)
            .where(
                WorkflowMemoryQuarantine.memory_item_id == self.model.id,
                WorkflowMemoryQuarantine.owner_type == self.model.owner_type,
                WorkflowMemoryQuarantine.owner_id == self.model.owner_id,
                WorkflowMemoryQuarantine.resolved_at.is_(None),
            )
            .exists()
        )
        statement = (
            select(self.model)
            .where(
                self.model.run_id == run_id,
                self.model.policy_status == "committed",
                self.model.lifecycle_status == "active",
                self.model.valid_from <= now,
                or_(self.model.expires_at.is_(None), self.model.expires_at > now),
                self.model.deleted_at.is_(None),
                self.model.superseded_by_id.is_(None),
                ~unresolved_quarantine_exists,
            )
            .order_by(
                self.model.owner_type.asc(),
                self.model.owner_id.asc(),
                self.model.package_key.asc(),
                self.model.workflow_key.asc(),
                self.model.namespace.asc(),
                self.model.kind.asc(),
                self.model.content_fingerprint.asc(),
                self.model.id.asc(),
            )
        )
        return self._list(statement)

    def list_active_committed_exact_duplicate_peers(
        self,
        *,
        owner_type: str,
        owner_id: str,
        package_key: str,
        workflow_key: str,
        namespace: str,
        kind: str,
        content_fingerprint: str,
        now: datetime,
    ) -> list[WorkflowMemoryItem]:
        unresolved_quarantine_exists = (
            select(WorkflowMemoryQuarantine.id)
            .where(
                WorkflowMemoryQuarantine.memory_item_id == self.model.id,
                WorkflowMemoryQuarantine.owner_type == owner_type,
                WorkflowMemoryQuarantine.owner_id == owner_id,
                WorkflowMemoryQuarantine.resolved_at.is_(None),
            )
            .exists()
        )
        statement = (
            select(self.model)
            .where(
                self.model.owner_type == owner_type,
                self.model.owner_id == owner_id,
                self.model.package_key == package_key,
                self.model.workflow_key == workflow_key,
                self.model.namespace == namespace,
                self.model.kind == kind,
                self.model.content_fingerprint == content_fingerprint,
                self.model.policy_status == "committed",
                self.model.lifecycle_status == "active",
                self.model.valid_from <= now,
                or_(self.model.expires_at.is_(None), self.model.expires_at > now),
                self.model.deleted_at.is_(None),
                self.model.superseded_by_id.is_(None),
                ~unresolved_quarantine_exists,
            )
            .order_by(self.model.id.asc())
        )
        return self._list(statement)

    def get_proposal_by_public_id(
        self,
        proposal_id: str,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryProposal | None:
        statement = select(WorkflowMemoryProposal).where(
            WorkflowMemoryProposal.proposal_id == proposal_id,
            WorkflowMemoryProposal.owner_type == owner_type,
            WorkflowMemoryProposal.owner_id == owner_id,
        )
        return self.session.scalar(statement)

    def list_proposals(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> tuple[list[WorkflowMemoryProposal], int]:
        filters = [
            WorkflowMemoryProposal.owner_type == owner_type,
            WorkflowMemoryProposal.owner_id == owner_id,
        ]
        if status is not None:
            filters.append(WorkflowMemoryProposal.status == status)
        total = self.session.scalar(
            select(func.count()).select_from(WorkflowMemoryProposal).where(*filters)
        )
        statement = (
            select(WorkflowMemoryProposal)
            .where(*filters)
            .order_by(WorkflowMemoryProposal.created_at.desc(), WorkflowMemoryProposal.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement)), int(total or 0)

    def list_proposals_for_run(
        self,
        run_id: int,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowMemoryProposal]:
        statement = (
            select(WorkflowMemoryProposal)
            .where(
                WorkflowMemoryProposal.run_id == run_id,
                WorkflowMemoryProposal.owner_type == owner_type,
                WorkflowMemoryProposal.owner_id == owner_id,
            )
            .order_by(WorkflowMemoryProposal.created_at.asc(), WorkflowMemoryProposal.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_decisions_for_run(
        self,
        run_id: int,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[tuple[WorkflowMemoryDecision, WorkflowMemoryProposal]]:
        statement = (
            select(WorkflowMemoryDecision, WorkflowMemoryProposal)
            .join(
                WorkflowMemoryProposal,
                WorkflowMemoryProposal.id == WorkflowMemoryDecision.proposal_id,
            )
            .where(
                WorkflowMemoryProposal.run_id == run_id,
                WorkflowMemoryProposal.owner_type == owner_type,
                WorkflowMemoryProposal.owner_id == owner_id,
            )
            .order_by(WorkflowMemoryDecision.created_at.asc(), WorkflowMemoryDecision.id.asc())
        )
        return list(self.session.execute(statement).tuples())

    def list_memory_items_for_run(
        self,
        run_id: int,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowMemoryItem]:
        statement = (
            select(WorkflowMemoryItem)
            .where(
                WorkflowMemoryItem.run_id == run_id,
                WorkflowMemoryItem.owner_type == owner_type,
                WorkflowMemoryItem.owner_id == owner_id,
            )
            .order_by(WorkflowMemoryItem.created_at.asc(), WorkflowMemoryItem.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_audit_events_for_run(
        self,
        run_id: int,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowMemoryAuditEvent]:
        statement = (
            select(WorkflowMemoryAuditEvent)
            .where(
                WorkflowMemoryAuditEvent.run_id == run_id,
                WorkflowMemoryAuditEvent.owner_type == owner_type,
                WorkflowMemoryAuditEvent.owner_id == owner_id,
            )
            .order_by(WorkflowMemoryAuditEvent.created_at.asc(), WorkflowMemoryAuditEvent.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_quarantine_for_run(
        self,
        run_id: int,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowMemoryQuarantine]:
        statement = (
            select(WorkflowMemoryQuarantine)
            .where(
                WorkflowMemoryQuarantine.run_id == run_id,
                WorkflowMemoryQuarantine.owner_type == owner_type,
                WorkflowMemoryQuarantine.owner_id == owner_id,
            )
            .order_by(WorkflowMemoryQuarantine.created_at.asc(), WorkflowMemoryQuarantine.id.asc())
        )
        return list(self.session.scalars(statement))

    def latest_decision_for_proposal(
        self,
        proposal: WorkflowMemoryProposal,
    ) -> WorkflowMemoryDecision | None:
        if proposal.id is None:
            return None
        statement = (
            select(WorkflowMemoryDecision)
            .where(WorkflowMemoryDecision.proposal_id == proposal.id)
            .order_by(WorkflowMemoryDecision.created_at.desc(), WorkflowMemoryDecision.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_audit_events(
        self,
        *,
        limit: int,
        offset: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> tuple[list[WorkflowMemoryAuditEvent], int]:
        filters = [
            WorkflowMemoryAuditEvent.owner_type == owner_type,
            WorkflowMemoryAuditEvent.owner_id == owner_id,
        ]
        total = self.session.scalar(
            select(func.count()).select_from(WorkflowMemoryAuditEvent).where(*filters)
        )
        statement = (
            select(WorkflowMemoryAuditEvent)
            .where(*filters)
            .order_by(
                WorkflowMemoryAuditEvent.created_at.desc(),
                WorkflowMemoryAuditEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement)), int(total or 0)

    def list_quarantine(
        self,
        *,
        unresolved_only: bool,
        limit: int,
        offset: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> tuple[list[WorkflowMemoryQuarantine], int]:
        filters = [
            WorkflowMemoryQuarantine.owner_type == owner_type,
            WorkflowMemoryQuarantine.owner_id == owner_id,
        ]
        if unresolved_only:
            filters.append(WorkflowMemoryQuarantine.resolved_at.is_(None))
        total = self.session.scalar(
            select(func.count()).select_from(WorkflowMemoryQuarantine).where(*filters)
        )
        statement = (
            select(WorkflowMemoryQuarantine)
            .where(*filters)
            .order_by(
                WorkflowMemoryQuarantine.created_at.desc(),
                WorkflowMemoryQuarantine.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement)), int(total or 0)

    def get_proposal_by_id(
        self,
        proposal_id: int | None,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryProposal | None:
        if proposal_id is None:
            return None
        statement = select(WorkflowMemoryProposal).where(WorkflowMemoryProposal.id == proposal_id)
        if owner_type is not None:
            statement = statement.where(WorkflowMemoryProposal.owner_type == owner_type)
        if owner_id is not None:
            statement = statement.where(WorkflowMemoryProposal.owner_id == owner_id)
        return self.session.scalar(statement)

    def get_memory_item_by_id(
        self,
        memory_item_id: int | None,
        *,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryItem | None:
        if memory_item_id is None:
            return None
        statement = select(WorkflowMemoryItem).where(WorkflowMemoryItem.id == memory_item_id)
        if owner_type is not None:
            statement = statement.where(WorkflowMemoryItem.owner_type == owner_type)
        if owner_id is not None:
            statement = statement.where(WorkflowMemoryItem.owner_id == owner_id)
        return self.session.scalar(statement)

    def get_memory_item_by_public_id(
        self,
        memory_id: str,
        *,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryItem | None:
        statement = select(WorkflowMemoryItem).where(
            WorkflowMemoryItem.memory_id == memory_id,
            WorkflowMemoryItem.owner_type == owner_type,
            WorkflowMemoryItem.owner_id == owner_id,
        )
        return self.session.scalar(statement)

    def get_memory_item_for_proposal(
        self,
        proposal: WorkflowMemoryProposal,
    ) -> WorkflowMemoryItem | None:
        if proposal.id is None:
            return None
        statement = (
            select(WorkflowMemoryItem)
            .where(
                WorkflowMemoryItem.proposal_id == proposal.id,
                WorkflowMemoryItem.owner_type == proposal.owner_type,
                WorkflowMemoryItem.owner_id == proposal.owner_id,
            )
            .order_by(WorkflowMemoryItem.created_at.desc(), WorkflowMemoryItem.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)


__all__ = ["WorkflowMemoryRepository"]
