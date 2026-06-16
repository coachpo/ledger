import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import {
  approveWorkflowMemoryProposal,
  listWorkflowMemoryAuditEvents,
  listWorkflowMemoryProposals,
  listWorkflowMemoryQuarantine,
  rejectWorkflowMemoryProposal,
} from "@/lib/api/memory";
import { queryKeys } from "@/lib/query-keys";
import type {
  WorkflowMemoryAuditEventListRead,
  WorkflowMemoryListParams,
  WorkflowMemoryProposalListParams,
  WorkflowMemoryProposalListRead,
  WorkflowMemoryQuarantineListParams,
  WorkflowMemoryQuarantineListRead,
  WorkflowMemoryReviewActionRead,
  WorkflowMemoryReviewActionRequest,
} from "@/lib/types/memory";

type MemoryQueryOptions = {
  enabled?: boolean;
};

export type WorkflowMemoryReviewActionVariables = {
  payload?: WorkflowMemoryReviewActionRequest;
  proposalId: string;
};

function useInvalidateWorkflowMemoryReview() {
  const queryClient = useQueryClient();

  return () =>
    Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.platform.memory.proposalsScope(),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.platform.memory.auditEventsScope(),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.platform.memory.quarantineScope(),
      }),
    ]);
}

export function useWorkflowMemoryProposals(
  params: WorkflowMemoryProposalListParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<WorkflowMemoryProposalListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.memory.proposals(params),
    queryFn: ({ signal }) => listWorkflowMemoryProposals(params, signal),
    enabled: options.enabled ?? true,
  });
}

export function useWorkflowMemoryAuditEvents(
  params: WorkflowMemoryListParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<WorkflowMemoryAuditEventListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.memory.auditEvents(params),
    queryFn: ({ signal }) => listWorkflowMemoryAuditEvents(params, signal),
    enabled: options.enabled ?? true,
  });
}

export function useWorkflowMemoryQuarantine(
  params: WorkflowMemoryQuarantineListParams = {},
  options: MemoryQueryOptions = {},
): UseQueryResult<WorkflowMemoryQuarantineListRead, Error> {
  return useQuery({
    queryKey: queryKeys.platform.memory.quarantine(params),
    queryFn: ({ signal }) => listWorkflowMemoryQuarantine(params, signal),
    enabled: options.enabled ?? true,
  });
}

export function useApproveWorkflowMemoryProposal() {
  const invalidateReview = useInvalidateWorkflowMemoryReview();

  return useMutation<
    WorkflowMemoryReviewActionRead,
    Error,
    WorkflowMemoryReviewActionVariables
  >({
    mutationFn: ({ payload = {}, proposalId }) =>
      approveWorkflowMemoryProposal(proposalId, payload),
    onSuccess: invalidateReview,
  });
}

export function useRejectWorkflowMemoryProposal() {
  const invalidateReview = useInvalidateWorkflowMemoryReview();

  return useMutation<
    WorkflowMemoryReviewActionRead,
    Error,
    WorkflowMemoryReviewActionVariables
  >({
    mutationFn: ({ payload = {}, proposalId }) =>
      rejectWorkflowMemoryProposal(proposalId, payload),
    onSuccess: invalidateReview,
  });
}
