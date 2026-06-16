from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Final, Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.services.execution_plan import PackageResolvedMemoryPolicy


class WorkflowMemoryPolicyStatus(str, Enum):  # noqa: UP042
    PROPOSED = "proposed"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    REVIEW_PENDING = "review_pending"
    COMMITTED = "committed"


class WorkflowMemoryLifecycleStatus(str, Enum):  # noqa: UP042
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"


class WorkflowMemoryDecisionValue(str, Enum):  # noqa: UP042
    COMMIT = "commit"
    REJECT = "reject"
    QUARANTINE = "quarantine"
    REVIEW = "review"


class WorkflowMemoryDecisionActor(str, Enum):  # noqa: UP042
    POLICY = "policy"
    REVIEW_API = "review_api"


class WorkflowMemoryConsolidationStatus(str, Enum):  # noqa: UP042
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX: Final = 50
WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT: Final = 50
WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT: Final = 200


class WorkflowMemoryScope(CamelModel):
    package_key: str = Field(min_length=1, max_length=120)
    workflow_key: str = Field(min_length=1, max_length=120)
    agent_key: str = Field(min_length=1, max_length=120)
    step_id: str = Field(min_length=1, max_length=160)
    namespace: str = Field(min_length=1, max_length=120)


class WorkflowMemoryProposalCandidate(CamelModel):
    kind: str = Field(min_length=1, max_length=80)
    namespace: str | None = Field(default=None, max_length=120)
    content: dict[str, Any] | str
    reason: str | None = None
    source_output_path: str | None = Field(default=None, max_length=255)


@dataclass(frozen=True)
class WorkflowMemoryContextRequest:
    scope: WorkflowMemoryScope
    policy: PackageResolvedMemoryPolicy


class WorkflowMemoryContextItem(CamelModel):
    item_id: str
    content: dict[str, Any]
    kind: str
    namespace: str
    provenance: dict[str, Any]
    created_at: datetime
    valid_from: datetime
    expires_at: datetime | None = None
    scope: WorkflowMemoryScope
    authoritative: bool = False


class WorkflowMemoryContextPack(CamelModel):
    items: list[WorkflowMemoryContextItem]
    policy_scope: WorkflowMemoryScope
    authoritative: bool = False


class WorkflowCheckpointScope(CamelModel):
    package_key: str = Field(min_length=1, max_length=120)
    workflow_key: str = Field(min_length=1, max_length=120)
    run_id: int = Field(gt=0)
    agent_key: str | None = Field(default=None, max_length=120)
    step_id: str | None = Field(default=None, max_length=160)
    invocation_id: str | None = Field(default=None, max_length=160)


class WorkflowCheckpointRecord(CamelModel):
    checkpoint_type: str = Field(min_length=1, max_length=80)
    sequence: int = Field(gt=0)
    state: dict[str, Any]
    retention: str = Field(min_length=1, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowCheckpointRead(CamelModel):
    checkpoint_id: str
    checkpoint_type: str
    sequence: int
    state: dict[str, Any]
    retention: str
    metadata: dict[str, Any]
    scope: WorkflowCheckpointScope
    created_at: datetime


class WorkflowMemoryProposalRead(CamelModel):
    proposal_id: str
    run_id: int | None = None
    invocation_id: str | None = None
    package_key: str
    workflow_key: str
    agent_key: str
    step_id: str
    namespace: str
    kind: str
    content: dict[str, Any]
    reason: str | None = None
    source_output_path: str | None = None
    detectors: dict[str, Any]
    status: WorkflowMemoryPolicyStatus
    created_at: datetime
    updated_at: datetime


class WorkflowMemoryProposalListRead(CamelModel):
    items: list[WorkflowMemoryProposalRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)
    offset: int = Field(ge=0)
    status: WorkflowMemoryPolicyStatus | Literal["all"]


class WorkflowMemoryReviewActionRequest(CamelModel):
    reason: str | None = Field(default=None, max_length=1_000)


class WorkflowMemoryDecisionRead(CamelModel):
    decision_id: str
    proposal_id: str
    decision: WorkflowMemoryDecisionValue
    reason_code: str
    reason: str | None = None
    policy_snapshot: dict[str, Any]
    decided_by: WorkflowMemoryDecisionActor
    created_at: datetime


class WorkflowMemoryReviewActionRead(CamelModel):
    proposal: WorkflowMemoryProposalRead
    decision: WorkflowMemoryDecisionRead
    active_memory_id: str | None = None


class WorkflowMemoryAuditEventRead(CamelModel):
    event_id: int = Field(ge=1)
    event_type: str
    target_type: str
    target_id: str
    run_id: int | None = None
    invocation_id: str | None = None
    package_key: str
    workflow_key: str
    agent_key: str | None = None
    step_id: str | None = None
    event: dict[str, Any]
    created_at: datetime


class WorkflowMemoryAuditEventListRead(CamelModel):
    items: list[WorkflowMemoryAuditEventRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)
    offset: int = Field(ge=0)


class WorkflowMemoryQuarantineRead(CamelModel):
    quarantine_id: int = Field(ge=1)
    proposal_id: str | None = None
    memory_id: str | None = None
    run_id: int | None = None
    invocation_id: str | None = None
    package_key: str | None = None
    workflow_key: str | None = None
    agent_key: str | None = None
    step_id: str | None = None
    namespace: str | None = None
    kind: str | None = None
    evidence: dict[str, Any]
    reason_code: str
    reason: str | None = None
    detectors: dict[str, Any]
    resolved_at: datetime | None = None
    created_at: datetime


class WorkflowMemoryQuarantineListRead(CamelModel):
    items: list[WorkflowMemoryQuarantineRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT)
    offset: int = Field(ge=0)
    unresolved_only: bool


__all__ = [
    "WORKFLOW_MEMORY_ACTIVE_LIMIT_MAX",
    "WORKFLOW_MEMORY_REVIEW_LIST_DEFAULT_LIMIT",
    "WORKFLOW_MEMORY_REVIEW_LIST_MAX_LIMIT",
    "WorkflowCheckpointRead",
    "WorkflowCheckpointRecord",
    "WorkflowCheckpointScope",
    "WorkflowMemoryAuditEventListRead",
    "WorkflowMemoryAuditEventRead",
    "WorkflowMemoryConsolidationStatus",
    "WorkflowMemoryContextItem",
    "WorkflowMemoryContextPack",
    "WorkflowMemoryContextRequest",
    "WorkflowMemoryDecisionActor",
    "WorkflowMemoryDecisionRead",
    "WorkflowMemoryDecisionValue",
    "WorkflowMemoryLifecycleStatus",
    "WorkflowMemoryPolicyStatus",
    "WorkflowMemoryProposalListRead",
    "WorkflowMemoryProposalCandidate",
    "WorkflowMemoryProposalRead",
    "WorkflowMemoryQuarantineListRead",
    "WorkflowMemoryQuarantineRead",
    "WorkflowMemoryReviewActionRead",
    "WorkflowMemoryReviewActionRequest",
    "WorkflowMemoryScope",
]
