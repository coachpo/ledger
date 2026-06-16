import { requestPlatform, toPathSegment, toQueryRecord } from "../api-client";
import type {
  WorkflowMemoryAuditEventListRead,
  WorkflowMemoryListParams,
  WorkflowMemoryProposalListParams,
  WorkflowMemoryProposalListRead,
  WorkflowMemoryQuarantineListParams,
  WorkflowMemoryQuarantineListRead,
  WorkflowMemoryReviewActionRead,
  WorkflowMemoryReviewActionRequest,
} from "../types/memory";

function normalizeListParams<TParams extends WorkflowMemoryListParams>(
  params: TParams = {} as TParams,
): TParams {
  return {
    ...params,
    limit: params.limit ?? 50,
    offset: params.offset ?? 0,
  };
}

export function normalizeWorkflowMemoryProposalParams(
  params: WorkflowMemoryProposalListParams = {},
): WorkflowMemoryProposalListParams {
  return {
    ...normalizeListParams(params),
    status: params.status ?? "review_pending",
  };
}

export function normalizeWorkflowMemoryAuditParams(
  params: WorkflowMemoryListParams = {},
): WorkflowMemoryListParams {
  return normalizeListParams(params);
}

export function normalizeWorkflowMemoryQuarantineParams(
  params: WorkflowMemoryQuarantineListParams = {},
): WorkflowMemoryQuarantineListParams {
  return {
    ...normalizeListParams(params),
    unresolvedOnly: params.unresolvedOnly ?? true,
  };
}

export function listWorkflowMemoryProposals(
  params: WorkflowMemoryProposalListParams = {},
  signal?: AbortSignal,
): Promise<WorkflowMemoryProposalListRead> {
  return requestPlatform<WorkflowMemoryProposalListRead>("/memory/proposals", {
    query: toQueryRecord(normalizeWorkflowMemoryProposalParams(params)),
    signal,
  });
}

export function approveWorkflowMemoryProposal(
  proposalId: string,
  payload: WorkflowMemoryReviewActionRequest = {},
  signal?: AbortSignal,
): Promise<WorkflowMemoryReviewActionRead> {
  return requestPlatform<WorkflowMemoryReviewActionRead>(
    `/memory/proposals/${toPathSegment(proposalId)}/actions/approve`,
    { body: payload, method: "POST", signal },
  );
}

export function rejectWorkflowMemoryProposal(
  proposalId: string,
  payload: WorkflowMemoryReviewActionRequest = {},
  signal?: AbortSignal,
): Promise<WorkflowMemoryReviewActionRead> {
  return requestPlatform<WorkflowMemoryReviewActionRead>(
    `/memory/proposals/${toPathSegment(proposalId)}/actions/reject`,
    { body: payload, method: "POST", signal },
  );
}

export function listWorkflowMemoryAuditEvents(
  params: WorkflowMemoryListParams = {},
  signal?: AbortSignal,
): Promise<WorkflowMemoryAuditEventListRead> {
  return requestPlatform<WorkflowMemoryAuditEventListRead>(
    "/memory/audit-events",
    { query: toQueryRecord(normalizeWorkflowMemoryAuditParams(params)), signal },
  );
}

export function listWorkflowMemoryQuarantine(
  params: WorkflowMemoryQuarantineListParams = {},
  signal?: AbortSignal,
): Promise<WorkflowMemoryQuarantineListRead> {
  return requestPlatform<WorkflowMemoryQuarantineListRead>("/memory/quarantine", {
    query: toQueryRecord(normalizeWorkflowMemoryQuarantineParams(params)),
    signal,
  });
}

export const memoryApi = {
  approveProposal: approveWorkflowMemoryProposal,
  auditEvents: listWorkflowMemoryAuditEvents,
  proposals: listWorkflowMemoryProposals,
  quarantine: listWorkflowMemoryQuarantine,
  rejectProposal: rejectWorkflowMemoryProposal,
} as const;
