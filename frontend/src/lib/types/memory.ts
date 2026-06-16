import type { UnknownRecord } from "./common";

export type WorkflowMemoryPolicyStatus =
  | "proposed"
  | "rejected"
  | "quarantined"
  | "review_pending"
  | "committed";

export type WorkflowMemoryProposalStatusFilter =
  | WorkflowMemoryPolicyStatus
  | "all";

export type WorkflowMemoryDecisionValue =
  | "commit"
  | "reject"
  | "quarantine"
  | "review";

export type WorkflowMemoryDecisionActor = "policy" | "review_api";

export interface WorkflowMemoryListParams {
  limit?: number;
  offset?: number;
}

export interface WorkflowMemoryProposalListParams
  extends WorkflowMemoryListParams {
  status?: WorkflowMemoryProposalStatusFilter;
}

export interface WorkflowMemoryQuarantineListParams
  extends WorkflowMemoryListParams {
  unresolvedOnly?: boolean;
}

export interface WorkflowMemoryProposalRead {
  agentKey: string;
  content: UnknownRecord;
  createdAt: string;
  detectors: UnknownRecord;
  invocationId?: string | null;
  kind: string;
  namespace: string;
  packageKey: string;
  proposalId: string;
  reason?: string | null;
  runId?: number | null;
  sourceOutputPath?: string | null;
  status: WorkflowMemoryPolicyStatus;
  stepId: string;
  updatedAt: string;
  workflowKey: string;
}

export interface WorkflowMemoryProposalListRead {
  items: WorkflowMemoryProposalRead[];
  limit: number;
  offset: number;
  status: WorkflowMemoryProposalStatusFilter;
  total: number;
}

export interface WorkflowMemoryReviewActionRequest {
  reason?: string | null;
}

export interface WorkflowMemoryDecisionRead {
  createdAt: string;
  decidedBy: WorkflowMemoryDecisionActor;
  decision: WorkflowMemoryDecisionValue;
  decisionId: string;
  policySnapshot: UnknownRecord;
  proposalId: string;
  reason?: string | null;
  reasonCode: string;
}

export interface WorkflowMemoryReviewActionRead {
  activeMemoryId?: string | null;
  decision: WorkflowMemoryDecisionRead;
  proposal: WorkflowMemoryProposalRead;
}

export interface WorkflowMemoryAuditEventRead {
  agentKey?: string | null;
  createdAt: string;
  event: UnknownRecord;
  eventId: number;
  eventType: string;
  invocationId?: string | null;
  packageKey: string;
  runId?: number | null;
  stepId?: string | null;
  targetId: string;
  targetType: string;
  workflowKey: string;
}

export interface WorkflowMemoryAuditEventListRead {
  items: WorkflowMemoryAuditEventRead[];
  limit: number;
  offset: number;
  total: number;
}

export interface WorkflowMemoryQuarantineRead {
  agentKey?: string | null;
  createdAt: string;
  detectors: UnknownRecord;
  evidence: UnknownRecord;
  invocationId?: string | null;
  kind?: string | null;
  memoryId?: string | null;
  namespace?: string | null;
  packageKey?: string | null;
  proposalId?: string | null;
  quarantineId: number;
  reason?: string | null;
  reasonCode: string;
  resolvedAt?: string | null;
  runId?: number | null;
  stepId?: string | null;
  workflowKey?: string | null;
}

export interface WorkflowMemoryQuarantineListRead {
  items: WorkflowMemoryQuarantineRead[];
  limit: number;
  offset: number;
  total: number;
  unresolvedOnly: boolean;
}
