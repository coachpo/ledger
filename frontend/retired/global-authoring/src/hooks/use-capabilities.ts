import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activateCapability,
  archiveCapability,
  createCapability,
  getCapability,
  listCapabilities,
  listCapabilityTools,
  updateCapability,
} from "@/lib/api/capabilities";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { CapabilityCreateInput, CapabilityListParams, CapabilityUpdateInput } from "@/lib/types/capability";

type UpdateCapabilityVariables = {
  payload: CapabilityUpdateInput;
  capabilityId: IdParam;
};

function invalidateCapabilityScope(queryClient: QueryClient, capabilityId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.capabilities.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.capabilities.detail(capabilityId) }),
  ]);
}

export function useCapabilities(params: CapabilityListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.capabilities.list(params),
    queryFn: ({ signal }) => listCapabilities(params, signal),
  });
}

export function useCapabilityTools() {
  return useQuery({
    queryKey: queryKeys.platform.capabilities.tools(),
    queryFn: ({ signal }) => listCapabilityTools(signal),
  });
}

export function useCapability(capabilityId: IdParam | undefined) {
  const resolvedCapabilityId = capabilityId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.capabilities.detail(resolvedCapabilityId),
    queryFn: ({ signal }) => getCapability(resolvedCapabilityId, signal),
    enabled: Boolean(capabilityId),
  });
}

export function useCreateCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CapabilityCreateInput) => createCapability(payload),
    onSuccess: async (capability) => {
      await invalidateCapabilityScope(queryClient, capability.id);
    },
  });
}

export function useUpdateCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, capabilityId }: UpdateCapabilityVariables) => updateCapability(capabilityId, payload),
    onSuccess: async (capability, { capabilityId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.capabilities.detail(capabilityId) });
      await invalidateCapabilityScope(queryClient, capability.id);
    },
  });
}

export function useActivateCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (capabilityId: IdParam) => activateCapability(capabilityId),
    onSuccess: async (capability) => {
      await invalidateCapabilityScope(queryClient, capability.id);
    },
  });
}

export function useArchiveCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (capabilityId: IdParam) => archiveCapability(capabilityId),
    onSuccess: async (capability, capabilityId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.capabilities.detail(capabilityId) });
      await invalidateCapabilityScope(queryClient, capability.id);
    },
  });
}
