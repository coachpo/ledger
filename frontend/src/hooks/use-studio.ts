import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activateAgentSpec,
  archiveAgentSpec,
  createAgentSpec,
  deprecateAgentSpec,
  getAgentSpec,
  listAgentSpecs,
  updateAgentSpec,
} from "@/lib/api/agent-specs";
import {
  activateCapability,
  createCapability,
  getCapability,
  listCapabilities,
  updateCapability,
} from "@/lib/api/capabilities";
import {
  activatePersonaVersion,
  archivePersonaVersion,
  createPersona,
  deprecatePersonaVersion,
  getPersona,
  getPersonaVersion,
  listPersonas,
  listPersonaVersions,
  updatePersonaVersion,
} from "@/lib/api/personas";
import {
  getStudioApproval,
  getStudioRun,
  getStudioRunArtifact,
  getStudioRunTrace,
  listStudioApprovals,
  listStudioArtifacts,
  listStudioRuns,
  listStudioTraceEvents,
} from "@/lib/api/studio";
import {
  activateWorkflowSpec,
  archiveWorkflowSpec,
  createWorkflowSpec,
  deprecateWorkflowSpec,
  getWorkflowSpec,
  listWorkflowSpecs,
  updateWorkflowSpec,
} from "@/lib/api/workflow-specs";
import { queryKeys } from "@/lib/query-keys";
import type {
  AgentSpecDraftCreateInput,
  AgentSpecDraftUpdateInput,
  CapabilityListParams,
  CapabilityRegistryEntryDraftCreateInput,
  CapabilityRegistryEntryDraftUpdateInput,
  PersonaProfileDraftCreateInput,
  PersonaProfileDraftUpdateInput,
  PersonaProfileListParams,
  RuntimeApprovalListParams,
  RuntimeRunListParams,
  RuntimeTraceEventListParams,
  StudioArtifactListParams,
  StudioSpecListParams,
  StudioVersionHistoryRead,
  WorkflowSpecDraftCreateInput,
  WorkflowSpecDraftUpdateInput,
} from "@/lib/types/studio";

type IdParam = number | string;

type UpdateAgentSpecVariables = {
  specId: IdParam;
  payload: AgentSpecDraftUpdateInput;
};

type UpdateWorkflowSpecVariables = {
  specId: IdParam;
  payload: WorkflowSpecDraftUpdateInput;
};

type UpdateCapabilityVariables = {
  specId: IdParam;
  payload: CapabilityRegistryEntryDraftUpdateInput;
};

type UpdatePersonaVariables = {
  personaKey: string;
  payload: PersonaProfileDraftUpdateInput;
  version: number;
};

function invalidateStudioSpecDetail(
  queryClient: QueryClient,
  detailKey: readonly unknown[],
  rootKey: readonly unknown[],
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: rootKey }),
    queryClient.invalidateQueries({ queryKey: detailKey }),
  ]);
}

export function useStudioRuns(params: RuntimeRunListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.runs.list(params),
    queryFn: ({ signal }) => listStudioRuns(params, signal),
  });
}

export function useStudioRun(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.runs.detail(resolvedRunId),
    queryFn: ({ signal }) => getStudioRun(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useStudioRunArtifact(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.runs.artifact(resolvedRunId),
    queryFn: ({ signal }) => getStudioRunArtifact(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useStudioRunTrace(runId: IdParam | undefined) {
  const resolvedRunId = runId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.runs.trace(resolvedRunId),
    queryFn: ({ signal }) => getStudioRunTrace(resolvedRunId, signal),
    enabled: Boolean(runId),
  });
}

export function useStudioArtifacts(params: StudioArtifactListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.artifacts.list(params),
    queryFn: ({ signal }) => listStudioArtifacts(params, signal),
  });
}

export function useStudioApprovals(params: RuntimeApprovalListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.approvals.list(params),
    queryFn: ({ signal }) => listStudioApprovals(params, signal),
  });
}

export function useStudioApproval(approvalId: IdParam | undefined) {
  const resolvedApprovalId = approvalId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.approvals.detail(resolvedApprovalId),
    queryFn: ({ signal }) => getStudioApproval(resolvedApprovalId, signal),
    enabled: Boolean(approvalId),
  });
}

export function useStudioTraceEvents(params: RuntimeTraceEventListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.traceEvents.list(params),
    queryFn: ({ signal }) => listStudioTraceEvents(params, signal),
  });
}

export function useStudioAgentSpecs(params: StudioSpecListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.agentSpecs.list(params),
    queryFn: ({ signal }) => listAgentSpecs(params, signal),
  });
}

export function useStudioAgentSpec(specId: IdParam | undefined) {
  const resolvedSpecId = specId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.agentSpecs.detail(resolvedSpecId),
    queryFn: ({ signal }) => getAgentSpec(resolvedSpecId, signal),
    enabled: Boolean(specId),
  });
}

export function useCreateStudioAgentSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AgentSpecDraftCreateInput) => createAgentSpec(payload),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.agentSpecs.detail(spec.id),
        queryKeys.studio.agentSpecs.all,
      );
    },
  });
}

export function useUpdateStudioAgentSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ specId, payload }: UpdateAgentSpecVariables) => updateAgentSpec(specId, payload),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.agentSpecs.detail(spec.id),
        queryKeys.studio.agentSpecs.all,
      );
    },
  });
}

export function useActivateStudioAgentSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => activateAgentSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.agentSpecs.detail(spec.id),
        queryKeys.studio.agentSpecs.all,
      );
    },
  });
}

export function useDeprecateStudioAgentSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => deprecateAgentSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.agentSpecs.detail(spec.id),
        queryKeys.studio.agentSpecs.all,
      );
    },
  });
}

export function useArchiveStudioAgentSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => archiveAgentSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.agentSpecs.detail(spec.id),
        queryKeys.studio.agentSpecs.all,
      );
    },
  });
}

export function useStudioWorkflowSpecs(params: StudioSpecListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.workflowSpecs.list(params),
    queryFn: ({ signal }) => listWorkflowSpecs(params, signal),
  });
}

export function useStudioWorkflowSpec(specId: IdParam | undefined) {
  const resolvedSpecId = specId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.workflowSpecs.detail(resolvedSpecId),
    queryFn: ({ signal }) => getWorkflowSpec(resolvedSpecId, signal),
    enabled: Boolean(specId),
  });
}

export function useStudioAgentSpecByKey(agentKey: string | undefined) {
  const listQuery = useStudioAgentSpecs();
  const matchedItem = listQuery.data?.items.find((item) => item.key === agentKey);
  const detailQuery = useStudioAgentSpec(matchedItem?.id);

  return {
    detailQuery,
    isMissing: Boolean(agentKey) && !listQuery.isPending && !matchedItem,
    listQuery,
    matchedItem,
  };
}

export function useStudioWorkflowSpecByKey(workflowKey: string | undefined) {
  const listQuery = useStudioWorkflowSpecs();
  const matchedItem = listQuery.data?.items.find((item) => item.key === workflowKey);
  const detailQuery = useStudioWorkflowSpec(matchedItem?.id);

  return {
    detailQuery,
    isMissing: Boolean(workflowKey) && !listQuery.isPending && !matchedItem,
    listQuery,
    matchedItem,
  };
}

export function useStudioPersonas(params: PersonaProfileListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.personas.list(params),
    queryFn: ({ signal }) => listPersonas(params, signal),
  });
}

export function useStudioPersona(personaKey: string | undefined) {
  const resolvedPersonaKey = personaKey ?? "";

  return useQuery({
    queryKey: queryKeys.studio.personas.detail(resolvedPersonaKey),
    queryFn: ({ signal }) => getPersona(resolvedPersonaKey, signal),
    enabled: Boolean(personaKey),
  });
}

export function useStudioPersonaByKey(personaKey: string | undefined) {
  const detailQuery = useStudioPersona(personaKey);

  return {
    detailQuery,
    isMissing:
      Boolean(personaKey) && !detailQuery.isPending && !detailQuery.data && !detailQuery.isError,
  };
}

export function useStudioPersonaVersions(personaKey: string | undefined) {
  const resolvedPersonaKey = personaKey ?? "";

  return useQuery<StudioVersionHistoryRead>({
    queryKey: queryKeys.studio.personas.versions(resolvedPersonaKey),
    queryFn: ({ signal }) => listPersonaVersions(resolvedPersonaKey, signal),
    enabled: Boolean(personaKey),
  });
}

export function useStudioPersonaVersion(
  personaKey: string | undefined,
  version: number | undefined,
) {
  const resolvedPersonaKey = personaKey ?? "";
  const resolvedVersion = version ?? 0;

  return useQuery({
    queryKey: queryKeys.studio.personas.version(resolvedPersonaKey, resolvedVersion),
    queryFn: ({ signal }) => getPersonaVersion(resolvedPersonaKey, resolvedVersion, signal),
    enabled: Boolean(personaKey) && Boolean(version),
  });
}

function invalidateStudioPersonaScope(queryClient: QueryClient, personaKey: string) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.personas.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.personas.detail(personaKey) }),
    queryClient.invalidateQueries({ queryKey: queryKeys.studio.personas.versions(personaKey) }),
  ]);
}

export function useCreateStudioPersona() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: PersonaProfileDraftCreateInput) => createPersona(payload),
    onSuccess: async (persona) => {
      await invalidateStudioPersonaScope(queryClient, persona.key);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.studio.personas.version(persona.key, persona.version),
      });
    },
  });
}

export function useUpdateStudioPersona() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ personaKey, payload, version }: UpdatePersonaVariables) =>
      updatePersonaVersion(personaKey, version, payload),
    onSuccess: async (persona) => {
      await invalidateStudioPersonaScope(queryClient, persona.key);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.studio.personas.version(persona.key, persona.version),
      });
    },
  });
}

export function useActivateStudioPersona() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ personaKey, version }: { personaKey: string; version: number }) =>
      activatePersonaVersion(personaKey, version),
    onSuccess: async (persona) => {
      await invalidateStudioPersonaScope(queryClient, persona.key);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.studio.personas.version(persona.key, persona.version),
      });
    },
  });
}

export function useDeprecateStudioPersona() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ personaKey, version }: { personaKey: string; version: number }) =>
      deprecatePersonaVersion(personaKey, version),
    onSuccess: async (persona) => {
      await invalidateStudioPersonaScope(queryClient, persona.key);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.studio.personas.version(persona.key, persona.version),
      });
    },
  });
}

export function useArchiveStudioPersona() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ personaKey, version }: { personaKey: string; version: number }) =>
      archivePersonaVersion(personaKey, version),
    onSuccess: async (persona) => {
      await invalidateStudioPersonaScope(queryClient, persona.key);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.studio.personas.version(persona.key, persona.version),
      });
    },
  });
}

export function useCreateStudioWorkflowSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WorkflowSpecDraftCreateInput) => createWorkflowSpec(payload),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.workflowSpecs.detail(spec.id),
        queryKeys.studio.workflowSpecs.all,
      );
    },
  });
}

export function useUpdateStudioWorkflowSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ specId, payload }: UpdateWorkflowSpecVariables) =>
      updateWorkflowSpec(specId, payload),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.workflowSpecs.detail(spec.id),
        queryKeys.studio.workflowSpecs.all,
      );
    },
  });
}

export function useActivateStudioWorkflowSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => activateWorkflowSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.workflowSpecs.detail(spec.id),
        queryKeys.studio.workflowSpecs.all,
      );
    },
  });
}

export function useDeprecateStudioWorkflowSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => deprecateWorkflowSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.workflowSpecs.detail(spec.id),
        queryKeys.studio.workflowSpecs.all,
      );
    },
  });
}

export function useArchiveStudioWorkflowSpec() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => archiveWorkflowSpec(specId),
    onSuccess: async (spec) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.workflowSpecs.detail(spec.id),
        queryKeys.studio.workflowSpecs.all,
      );
    },
  });
}

export function useStudioCapabilities(params: CapabilityListParams = {}) {
  return useQuery({
    queryKey: queryKeys.studio.capabilities.list(params),
    queryFn: ({ signal }) => listCapabilities(params, signal),
  });
}

export function useStudioCapability(specId: IdParam | undefined) {
  const resolvedSpecId = specId ?? "";

  return useQuery({
    queryKey: queryKeys.studio.capabilities.detail(resolvedSpecId),
    queryFn: ({ signal }) => getCapability(resolvedSpecId, signal),
    enabled: Boolean(specId),
  });
}

export function useStudioCapabilityByKey(capabilityKey: string | undefined) {
  const listQuery = useStudioCapabilities();
  const matchedItem = listQuery.data?.items.find((item) => item.key === capabilityKey);
  const detailQuery = useStudioCapability(matchedItem?.id);

  return {
    detailQuery,
    isMissing: Boolean(capabilityKey) && !listQuery.isPending && !matchedItem,
    listQuery,
    matchedItem,
  };
}

export function useCreateStudioCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CapabilityRegistryEntryDraftCreateInput) => createCapability(payload),
    onSuccess: async (capability) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.capabilities.detail(capability.id),
        queryKeys.studio.capabilities.all,
      );
    },
  });
}

export function useUpdateStudioCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ specId, payload }: UpdateCapabilityVariables) => updateCapability(specId, payload),
    onSuccess: async (capability) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.capabilities.detail(capability.id),
        queryKeys.studio.capabilities.all,
      );
    },
  });
}

export function useActivateStudioCapability() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (specId: IdParam) => activateCapability(specId),
    onSuccess: async (capability) => {
      await invalidateStudioSpecDetail(
        queryClient,
        queryKeys.studio.capabilities.detail(capability.id),
        queryKeys.studio.capabilities.all,
      );
    },
  });
}
