from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import business_rule_error, not_found_error
from app.core.formatting import utcnow
from app.models.workflow_memory import (
    WorkflowMemoryAuditEvent,
    WorkflowMemoryDecision,
    WorkflowMemoryItem,
    WorkflowMemoryProposal,
    WorkflowMemoryQuarantine,
)
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import (
    WorkflowMemoryAuditEventListRead,
    WorkflowMemoryAuditEventRead,
    WorkflowMemoryDecisionActor,
    WorkflowMemoryDecisionRead,
    WorkflowMemoryDecisionValue,
    WorkflowMemoryPolicyStatus,
    WorkflowMemoryProposalListRead,
    WorkflowMemoryProposalRead,
    WorkflowMemoryQuarantineListRead,
    WorkflowMemoryQuarantineRead,
    WorkflowMemoryReviewActionRead,
)
from app.services.execution_plan import PackageResolvedMemoryPolicy
from app.services.workflow_memory_detection import (
    detect_workflow_memory_policy_hits,
    merge_detector_hits,
)


class WorkflowMemoryPolicyService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

    def evaluate_proposal(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        policy: PackageResolvedMemoryPolicy,
    ) -> WorkflowMemoryDecision:
        existing_decision = self.repository.latest_decision_for_proposal(proposal)
        if proposal.status != "proposed" and existing_decision is not None:
            if proposal.status != "committed":
                return existing_decision
            if self.repository.get_memory_item_for_proposal(proposal) is not None:
                return existing_decision
        detectors_json = merge_detector_hits(
            proposal.detectors_json,
            detect_workflow_memory_policy_hits(proposal.content_json),
        )
        proposal.detectors_json = detectors_json
        decision, reason_code, reason = self._resolve_decision(proposal=proposal, policy=policy)
        decision_row = self.repository.record_decision(
            decision_id=f"decision_{uuid4().hex}",
            proposal=proposal,
            decision=decision,
            reason_code=reason_code,
            reason=reason,
            policy_snapshot_json=self._policy_snapshot(policy),
            decided_by="policy",
        )
        proposal.status = self._proposal_status(decision)
        if decision == "quarantine":
            _ = self.repository.quarantine_proposal(
                proposal=proposal,
                reason_code=reason_code,
                reason=reason,
                run_id=proposal.run_id,
                invocation_id=proposal.invocation_id,
                detectors_json=detectors_json,
            )
        if decision == "commit":
            _ = self._activate_committed_memory(
                proposal=proposal,
                decision=decision_row,
                policy=policy,
            )
        _ = self.repository.record_audit_event(
            event_type=f"memory_policy_{decision}",
            target_type="proposal",
            target_id=proposal.proposal_id,
            owner_type=proposal.owner_type,
            owner_id=proposal.owner_id,
            package_key=proposal.package_key,
            workflow_key=proposal.workflow_key,
            agent_key=proposal.agent_key,
            step_id=proposal.step_id,
            run_id=proposal.run_id,
            invocation_id=proposal.invocation_id,
            event_json={"decisionId": decision_row.decision_id, "reasonCode": reason_code},
        )
        self.session.flush()
        return decision_row

    def list_review_proposals(
        self,
        *,
        status: WorkflowMemoryPolicyStatus | None,
        limit: int,
        offset: int,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryProposalListRead:
        proposals, total = self.repository.list_proposals(
            status=status.value if status is not None else None,
            limit=limit,
            offset=offset,
            owner_type=owner_type or self.repository.default_owner_type(),
            owner_id=owner_id or self.repository.default_owner_id(),
        )
        return WorkflowMemoryProposalListRead(
            items=[self._proposal_read(proposal) for proposal in proposals],
            total=total,
            limit=limit,
            offset=offset,
            status=status or "all",
        )

    def list_audit_events(
        self,
        *,
        limit: int,
        offset: int,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryAuditEventListRead:
        events, total = self.repository.list_audit_events(
            limit=limit,
            offset=offset,
            owner_type=owner_type or self.repository.default_owner_type(),
            owner_id=owner_id or self.repository.default_owner_id(),
        )
        return WorkflowMemoryAuditEventListRead(
            items=[self._audit_event_read(event) for event in events],
            total=total,
            limit=limit,
            offset=offset,
        )

    def list_quarantine(
        self,
        *,
        unresolved_only: bool,
        limit: int,
        offset: int,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryQuarantineListRead:
        quarantines, total = self.repository.list_quarantine(
            unresolved_only=unresolved_only,
            limit=limit,
            offset=offset,
            owner_type=owner_type or self.repository.default_owner_type(),
            owner_id=owner_id or self.repository.default_owner_id(),
        )
        return WorkflowMemoryQuarantineListRead(
            items=[self._quarantine_read(quarantine) for quarantine in quarantines],
            total=total,
            limit=limit,
            offset=offset,
            unresolved_only=unresolved_only,
        )

    def approve_review_pending_proposal(
        self,
        *,
        proposal_id: str,
        reason: str | None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryReviewActionRead:
        return self._review_proposal(
            proposal_id=proposal_id,
            approve=True,
            reason=reason,
            owner_type=owner_type,
            owner_id=owner_id,
        )

    def reject_review_pending_proposal(
        self,
        *,
        proposal_id: str,
        reason: str | None,
        owner_type: str | None = None,
        owner_id: str | None = None,
    ) -> WorkflowMemoryReviewActionRead:
        return self._review_proposal(
            proposal_id=proposal_id,
            approve=False,
            reason=reason,
            owner_type=owner_type,
            owner_id=owner_id,
        )

    def _review_proposal(
        self,
        *,
        proposal_id: str,
        approve: bool,
        reason: str | None,
        owner_type: str | None,
        owner_id: str | None,
    ) -> WorkflowMemoryReviewActionRead:
        proposal = self.repository.get_proposal_by_public_id(
            proposal_id,
            owner_type=owner_type or self.repository.default_owner_type(),
            owner_id=owner_id or self.repository.default_owner_id(),
        )
        if proposal is None:
            raise not_found_error("Workflow memory proposal")
        if proposal.status != "review_pending":
            raise business_rule_error(
                "workflow_memory_proposal_not_review_pending",
                "Only review-pending workflow memory proposals can be reviewed.",
                details=[{"proposalId": proposal.proposal_id, "status": proposal.status}],
            )

        prior_decision = self.repository.latest_decision_for_proposal(proposal)
        policy_snapshot = prior_decision.policy_snapshot_json if prior_decision is not None else {}
        decision_value = "commit" if approve else "reject"
        decision_row = self.repository.record_decision(
            decision_id=f"decision_{uuid4().hex}",
            proposal=proposal,
            decision=decision_value,
            reason_code="review_approved" if approve else "review_rejected",
            reason=reason
            or ("Approved by memory review API." if approve else "Rejected by memory review API."),
            policy_snapshot_json=policy_snapshot,
            decided_by="review_api",
        )
        proposal.status = "committed" if approve else "rejected"
        active_item = None
        if approve:
            active_item = self._activate_review_committed_memory(
                proposal=proposal,
                decision=decision_row,
                policy_snapshot=policy_snapshot,
            )
        _ = self.repository.record_audit_event(
            event_type=f"memory_review_{decision_value}",
            target_type="proposal",
            target_id=proposal.proposal_id,
            owner_type=proposal.owner_type,
            owner_id=proposal.owner_id,
            package_key=proposal.package_key,
            workflow_key=proposal.workflow_key,
            agent_key=proposal.agent_key,
            step_id=proposal.step_id,
            run_id=proposal.run_id,
            invocation_id=proposal.invocation_id,
            event_json={"decisionId": decision_row.decision_id, "decidedBy": "review_api"},
        )
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return WorkflowMemoryReviewActionRead(
            proposal=self._proposal_read(proposal),
            decision=self._decision_read(decision_row, proposal=proposal),
            active_memory_id=active_item.memory_id if active_item is not None else None,
        )

    def _resolve_decision(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        policy: PackageResolvedMemoryPolicy,
    ) -> tuple[str, str, str]:
        if not policy.enabled or policy.writes is None or not policy.writes.proposals:
            return "reject", "memory_writes_disabled", "Memory writes are disabled by policy."
        if proposal.kind not in policy.writes.allowed_kinds:
            return "reject", "kind_not_allowed", "Proposal kind is not allowed by policy."
        if not self._is_scope_authorized(proposal=proposal, policy=policy):
            return "reject", "unauthorized_scope", "Proposal scope is outside the resolved policy."
        if proposal.detectors_json.get("secrets"):
            action = policy.policy.secrets if policy.policy is not None else "quarantine"
            return self._detector_decision(action, "secret_detected")
        if proposal.detectors_json.get("sensitiveData"):
            action = policy.policy.sensitive_data if policy.policy is not None else "review"
            if action == "reject":
                return "reject", "sensitive_data_detected", "Sensitive data requires rejection."
            if action == "quarantine":
                return (
                    "quarantine",
                    "sensitive_data_detected",
                    "Sensitive data requires quarantine.",
                )
            return "review", "sensitive_data_detected", "Sensitive data requires review."
        if (
            proposal.kind in policy.writes.auto_commit_kinds
            and policy.writes.default_decision == "commit"
        ):
            return "commit", "auto_commit_allowed", "Policy allowed automatic commit."
        if policy.writes.default_decision == "reject":
            return "reject", "default_reject", "Policy default rejects proposals."
        return "review", "default_review", "Policy default requires review."

    def _detector_decision(self, action: str, reason_code: str) -> tuple[str, str, str]:
        if action == "reject":
            return "reject", reason_code, "Detector policy rejected the proposal."
        if action == "review":
            return "review", reason_code, "Detector policy requires review."
        return "quarantine", reason_code, "Detector policy quarantined the proposal."

    def _is_scope_authorized(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        policy: PackageResolvedMemoryPolicy,
    ) -> bool:
        retrieval = policy.retrieval
        if retrieval is None or not retrieval.enabled:
            return False
        if proposal.namespace not in retrieval.namespaces:
            return False
        if retrieval.include_kinds and proposal.kind not in retrieval.include_kinds:
            return False
        return True

    def _activate_committed_memory(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        decision: WorkflowMemoryDecision,
        policy: PackageResolvedMemoryPolicy,
    ) -> WorkflowMemoryItem:
        existing = self.repository.get_memory_item_for_proposal(proposal)
        if existing is not None:
            return existing
        now = utcnow()
        expires_at = None
        if policy.policy is not None and policy.policy.expiration_days is not None:
            expires_at = now + timedelta(days=policy.policy.expiration_days)
        return self._create_memory_item_for_proposal(
            proposal=proposal,
            decision=decision,
            expires_at=expires_at,
            valid_from=now,
            provenance_json={
                "proposalId": proposal.proposal_id,
                "runId": proposal.run_id,
                "invocationId": proposal.invocation_id,
            },
        )

    def _activate_review_committed_memory(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        decision: WorkflowMemoryDecision,
        policy_snapshot: dict[str, Any],
    ) -> WorkflowMemoryItem:
        existing = self.repository.get_memory_item_for_proposal(proposal)
        if existing is not None:
            return existing
        now = utcnow()
        expires_at = None
        detector_policy = policy_snapshot.get("policy")
        if isinstance(detector_policy, dict):
            expiration_days = detector_policy.get("expiration_days")
            if isinstance(expiration_days, int):
                expires_at = now + timedelta(days=expiration_days)
        return self._create_memory_item_for_proposal(
            proposal=proposal,
            decision=decision,
            expires_at=expires_at,
            valid_from=now,
            provenance_json={
                "proposalId": proposal.proposal_id,
                "runId": proposal.run_id,
                "invocationId": proposal.invocation_id,
                "reviewDecisionId": decision.decision_id,
            },
        )

    def _create_memory_item_for_proposal(
        self,
        *,
        proposal: WorkflowMemoryProposal,
        decision: WorkflowMemoryDecision,
        expires_at: datetime | None,
        valid_from: datetime,
        provenance_json: dict[str, Any],
    ) -> WorkflowMemoryItem:
        try:
            with self.session.begin_nested():
                item = self.repository.create_memory_item(
                    memory_id=f"workflow_memory_{uuid4().hex}",
                    owner_type=proposal.owner_type,
                    owner_id=proposal.owner_id,
                    package_key=proposal.package_key,
                    workflow_key=proposal.workflow_key,
                    agent_key=proposal.agent_key,
                    step_id=proposal.step_id,
                    namespace=proposal.namespace,
                    kind=proposal.kind,
                    content_fingerprint=proposal.content_fingerprint,
                    content_json=proposal.content_json,
                    summary=self._summary(proposal.content_json),
                    provenance_json=provenance_json,
                    policy_status="committed",
                    lifecycle_status="active",
                    valid_from=valid_from,
                    expires_at=expires_at,
                    proposal_id=proposal.id,
                    decision_id=decision.id,
                    run_id=proposal.run_id,
                    invocation_id=proposal.invocation_id,
                )
                _ = self.repository.record_revision(
                    memory_item=item,
                    revision_id=f"{item.memory_id}:rev-1",
                    version=1,
                    content_json=proposal.content_json,
                    summary=item.summary,
                    provenance_json=item.provenance_json,
                )
                self.session.flush()
                return item
        except IntegrityError:
            existing = self.repository.get_memory_item_for_proposal(proposal)
            if existing is None:
                raise
            return existing

    def _proposal_read(self, proposal: WorkflowMemoryProposal) -> WorkflowMemoryProposalRead:
        return WorkflowMemoryProposalRead(
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            invocation_id=proposal.invocation_id,
            package_key=proposal.package_key,
            workflow_key=proposal.workflow_key,
            agent_key=proposal.agent_key,
            step_id=proposal.step_id,
            namespace=proposal.namespace,
            kind=proposal.kind,
            content=proposal.content_json,
            reason=proposal.reason,
            source_output_path=proposal.source_output_path,
            detectors=proposal.detectors_json,
            status=WorkflowMemoryPolicyStatus(proposal.status),
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
        )

    def _decision_read(
        self,
        decision: WorkflowMemoryDecision,
        *,
        proposal: WorkflowMemoryProposal,
    ) -> WorkflowMemoryDecisionRead:
        return WorkflowMemoryDecisionRead(
            decision_id=decision.decision_id,
            proposal_id=proposal.proposal_id,
            decision=WorkflowMemoryDecisionValue(decision.decision),
            reason_code=decision.reason_code,
            reason=decision.reason,
            policy_snapshot=decision.policy_snapshot_json,
            decided_by=WorkflowMemoryDecisionActor(decision.decided_by),
            created_at=decision.created_at,
        )

    def _audit_event_read(self, event: WorkflowMemoryAuditEvent) -> WorkflowMemoryAuditEventRead:
        return WorkflowMemoryAuditEventRead(
            event_id=event.id,
            event_type=event.event_type,
            target_type=event.target_type,
            target_id=event.target_id,
            run_id=event.run_id,
            invocation_id=event.invocation_id,
            package_key=event.package_key,
            workflow_key=event.workflow_key,
            agent_key=event.agent_key,
            step_id=event.step_id,
            event=event.event_json,
            created_at=event.created_at,
        )

    def _quarantine_read(
        self,
        quarantine: WorkflowMemoryQuarantine,
    ) -> WorkflowMemoryQuarantineRead:
        proposal = self.repository.get_proposal_by_id(
            quarantine.proposal_id,
            owner_type=quarantine.owner_type,
            owner_id=quarantine.owner_id,
        )
        memory_item = self.repository.get_memory_item_by_id(
            quarantine.memory_item_id,
            owner_type=quarantine.owner_type,
            owner_id=quarantine.owner_id,
        )
        evidence: dict[str, Any] = {}
        if proposal is not None:
            evidence = proposal.content_json
        elif memory_item is not None:
            evidence = memory_item.content_json
        target = proposal if proposal is not None else memory_item
        return WorkflowMemoryQuarantineRead(
            quarantine_id=quarantine.id,
            proposal_id=proposal.proposal_id if proposal is not None else None,
            memory_id=memory_item.memory_id if memory_item is not None else None,
            run_id=quarantine.run_id,
            invocation_id=quarantine.invocation_id,
            package_key=target.package_key if target is not None else None,
            workflow_key=target.workflow_key if target is not None else None,
            agent_key=target.agent_key if target is not None else None,
            step_id=target.step_id if target is not None else None,
            namespace=target.namespace if target is not None else None,
            kind=target.kind if target is not None else None,
            evidence=evidence,
            reason_code=quarantine.reason_code,
            reason=quarantine.reason,
            detectors=quarantine.detectors_json,
            resolved_at=quarantine.resolved_at,
            created_at=quarantine.created_at,
        )

    def _summary(self, content_json: dict[str, Any]) -> str:
        for key in ("summary", "text", "title"):
            value = content_json.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
        return "Workflow memory item"

    def _proposal_status(self, decision: str) -> str:
        if decision == "commit":
            return "committed"
        if decision == "quarantine":
            return "quarantined"
        if decision == "review":
            return "review_pending"
        return "rejected"

    def _policy_snapshot(self, policy: PackageResolvedMemoryPolicy) -> dict[str, Any]:
        return {
            "enabled": policy.enabled,
            "retrieval": policy.retrieval.__dict__ if policy.retrieval is not None else None,
            "writes": policy.writes.__dict__ if policy.writes is not None else None,
            "policy": policy.policy.__dict__ if policy.policy is not None else None,
            "checkpoints": policy.checkpoints.__dict__ if policy.checkpoints is not None else None,
        }


__all__ = ["WorkflowMemoryPolicyService"]
