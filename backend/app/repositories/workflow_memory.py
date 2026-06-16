from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import func, or_, select

from app.core.formatting import utcnow
from app.models.workflow_memory import (
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


class WorkflowMemoryRepository(BaseRepository[WorkflowMemoryItem]):
    model: ClassVar[type[WorkflowMemoryItem]] = WorkflowMemoryItem

    def create_memory_item(
        self,
        *,
        memory_id: str,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespace: str,
        kind: str,
        content_json: dict[str, Any],
        summary: str,
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
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace,
            kind=kind,
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
    ) -> list[WorkflowMemoryItem]:
        resolved_namespaces = tuple(dict.fromkeys(namespaces))
        if not resolved_namespaces or limit <= 0:
            return []
        unresolved_quarantine_exists = (
            select(WorkflowMemoryQuarantine.id)
            .where(
                WorkflowMemoryQuarantine.memory_item_id == self.model.id,
                WorkflowMemoryQuarantine.resolved_at.is_(None),
            )
            .exists()
        )
        statement = (
            select(self.model)
            .where(
                self.model.package_key == package_key,
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
        run_id: int | None,
        invocation_id: str | None,
        package_key: str,
        workflow_key: str,
        agent_key: str,
        step_id: str,
        namespace: str,
        kind: str,
        content_json: dict[str, Any],
        reason: str | None = None,
        source_output_path: str | None = None,
        detectors_json: dict[str, Any] | None = None,
        status: str = "proposed",
    ) -> WorkflowMemoryProposal:
        proposal = WorkflowMemoryProposal(
            proposal_id=proposal_id,
            run_id=run_id,
            invocation_id=invocation_id,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            namespace=namespace,
            kind=kind,
            content_json=content_json,
            reason=reason,
            source_output_path=source_output_path,
            detectors_json=detectors_json or {},
            status=status,
        )
        self.session.add(proposal)
        return proposal

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

    def get_proposal_by_public_id(self, proposal_id: str) -> WorkflowMemoryProposal | None:
        statement = select(WorkflowMemoryProposal).where(
            WorkflowMemoryProposal.proposal_id == proposal_id
        )
        return self.session.scalar(statement)

    def list_proposals(
        self,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[WorkflowMemoryProposal], int]:
        filters = [] if status is None else [WorkflowMemoryProposal.status == status]
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

    def list_proposals_for_run(self, run_id: int) -> list[WorkflowMemoryProposal]:
        statement = (
            select(WorkflowMemoryProposal)
            .where(WorkflowMemoryProposal.run_id == run_id)
            .order_by(WorkflowMemoryProposal.created_at.asc(), WorkflowMemoryProposal.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_decisions_for_run(
        self,
        run_id: int,
    ) -> list[tuple[WorkflowMemoryDecision, WorkflowMemoryProposal]]:
        statement = (
            select(WorkflowMemoryDecision, WorkflowMemoryProposal)
            .join(
                WorkflowMemoryProposal,
                WorkflowMemoryProposal.id == WorkflowMemoryDecision.proposal_id,
            )
            .where(WorkflowMemoryProposal.run_id == run_id)
            .order_by(WorkflowMemoryDecision.created_at.asc(), WorkflowMemoryDecision.id.asc())
        )
        return list(self.session.execute(statement).tuples())

    def list_memory_items_for_run(self, run_id: int) -> list[WorkflowMemoryItem]:
        statement = (
            select(WorkflowMemoryItem)
            .where(WorkflowMemoryItem.run_id == run_id)
            .order_by(WorkflowMemoryItem.created_at.asc(), WorkflowMemoryItem.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_audit_events_for_run(self, run_id: int) -> list[WorkflowMemoryAuditEvent]:
        statement = (
            select(WorkflowMemoryAuditEvent)
            .where(WorkflowMemoryAuditEvent.run_id == run_id)
            .order_by(WorkflowMemoryAuditEvent.created_at.asc(), WorkflowMemoryAuditEvent.id.asc())
        )
        return list(self.session.scalars(statement))

    def list_quarantine_for_run(self, run_id: int) -> list[WorkflowMemoryQuarantine]:
        statement = (
            select(WorkflowMemoryQuarantine)
            .where(WorkflowMemoryQuarantine.run_id == run_id)
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
    ) -> tuple[list[WorkflowMemoryAuditEvent], int]:
        total = self.session.scalar(select(func.count()).select_from(WorkflowMemoryAuditEvent))
        statement = (
            select(WorkflowMemoryAuditEvent)
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
    ) -> tuple[list[WorkflowMemoryQuarantine], int]:
        filters = [WorkflowMemoryQuarantine.resolved_at.is_(None)] if unresolved_only else []
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

    def get_proposal_by_id(self, proposal_id: int | None) -> WorkflowMemoryProposal | None:
        if proposal_id is None:
            return None
        return self.session.get(WorkflowMemoryProposal, proposal_id)

    def get_memory_item_by_id(self, memory_item_id: int | None) -> WorkflowMemoryItem | None:
        if memory_item_id is None:
            return None
        return self.session.get(WorkflowMemoryItem, memory_item_id)

    def get_memory_item_for_proposal(
        self,
        proposal: WorkflowMemoryProposal,
    ) -> WorkflowMemoryItem | None:
        if proposal.id is None:
            return None
        statement = (
            select(WorkflowMemoryItem)
            .where(WorkflowMemoryItem.proposal_id == proposal.id)
            .order_by(WorkflowMemoryItem.created_at.desc(), WorkflowMemoryItem.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)


__all__ = ["WorkflowMemoryRepository"]
