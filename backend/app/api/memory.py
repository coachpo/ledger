from __future__ import annotations

from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_workflow_memory_policy_service
from app.schemas.workflow_memory import (
    WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT,
    WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT,
    WorkflowMemoryAuditEventListRead,
    WorkflowMemoryPolicyStatus,
    WorkflowMemoryProposalListRead,
    WorkflowMemoryQuarantineListRead,
    WorkflowMemoryReviewActionRead,
    WorkflowMemoryReviewActionRequest,
)

router = APIRouter(prefix="/memory", tags=["memory"])


class WorkflowMemoryReviewService(Protocol):
    def list_review_proposals(
        self,
        *,
        status: WorkflowMemoryPolicyStatus | None,
        limit: int,
        offset: int,
    ) -> WorkflowMemoryProposalListRead: ...

    def approve_review_pending_proposal(
        self,
        *,
        proposal_id: str,
        reason: str | None,
    ) -> WorkflowMemoryReviewActionRead: ...

    def reject_review_pending_proposal(
        self,
        *,
        proposal_id: str,
        reason: str | None,
    ) -> WorkflowMemoryReviewActionRead: ...

    def list_audit_events(
        self,
        *,
        limit: int,
        offset: int,
    ) -> WorkflowMemoryAuditEventListRead: ...

    def list_quarantine(
        self,
        *,
        unresolved_only: bool,
        limit: int,
        offset: int,
    ) -> WorkflowMemoryQuarantineListRead: ...


@router.get("/proposals", response_model=WorkflowMemoryProposalListRead)
def list_memory_proposals(
    service: Annotated[WorkflowMemoryReviewService, Depends(get_workflow_memory_policy_service)],
    status: Annotated[WorkflowMemoryPolicyStatus | Literal["all"], Query()] = (
        WorkflowMemoryPolicyStatus.REVIEW_PENDING
    ),
    limit: Annotated[int, Query(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)] = (
        WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT
    ),
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowMemoryProposalListRead:
    return service.list_review_proposals(
        status=None if status == "all" else status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/proposals/{proposal_id}/actions/approve",
    response_model=WorkflowMemoryReviewActionRead,
)
def approve_memory_proposal(
    proposal_id: str,
    payload: WorkflowMemoryReviewActionRequest,
    service: Annotated[WorkflowMemoryReviewService, Depends(get_workflow_memory_policy_service)],
) -> WorkflowMemoryReviewActionRead:
    return service.approve_review_pending_proposal(
        proposal_id=proposal_id,
        reason=payload.reason,
    )


@router.post(
    "/proposals/{proposal_id}/actions/reject",
    response_model=WorkflowMemoryReviewActionRead,
)
def reject_memory_proposal(
    proposal_id: str,
    payload: WorkflowMemoryReviewActionRequest,
    service: Annotated[WorkflowMemoryReviewService, Depends(get_workflow_memory_policy_service)],
) -> WorkflowMemoryReviewActionRead:
    return service.reject_review_pending_proposal(
        proposal_id=proposal_id,
        reason=payload.reason,
    )


@router.get("/audit-events", response_model=WorkflowMemoryAuditEventListRead)
def list_memory_audit_events(
    service: Annotated[WorkflowMemoryReviewService, Depends(get_workflow_memory_policy_service)],
    limit: Annotated[int, Query(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)] = (
        WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT
    ),
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowMemoryAuditEventListRead:
    return service.list_audit_events(limit=limit, offset=offset)


@router.get("/quarantine", response_model=WorkflowMemoryQuarantineListRead)
def list_memory_quarantine(
    service: Annotated[WorkflowMemoryReviewService, Depends(get_workflow_memory_policy_service)],
    unresolved_only: Annotated[bool, Query(alias="unresolvedOnly")] = True,
    limit: Annotated[int, Query(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)] = (
        WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT
    ),
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WorkflowMemoryQuarantineListRead:
    return service.list_quarantine(
        unresolved_only=unresolved_only,
        limit=limit,
        offset=offset,
    )
