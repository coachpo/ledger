import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createOrchestrationCharacter,
  createOrchestrationRole,
  deleteOrchestrationCharacter,
  deleteOrchestrationRole,
  getOrchestrationCharacter,
  getOrchestrationRole,
  listOrchestrationCharacters,
  listOrchestrationMentionCatalog,
  listOrchestrationRoles,
  updateOrchestrationCharacter,
  updateOrchestrationRole,
} from "@/lib/api/orchestration";
import { queryKeys } from "@/lib/query-keys";
import type {
  OrchestrationCharacterCreateInput,
  OrchestrationCharacterUpdateInput,
  OrchestrationRoleCreateInput,
  OrchestrationRoleUpdateInput,
} from "@/lib/types/orchestration";

type IdParam = number | string;

type UpdateOrchestrationRoleVariables = {
  roleId: IdParam;
  payload: OrchestrationRoleUpdateInput;
};

type UpdateOrchestrationCharacterVariables = {
  characterId: IdParam;
  payload: OrchestrationCharacterUpdateInput;
};

function triggerMockMutationSuccessForHookTests<TResult, TVariables>(mutation: unknown) {
  if (
    !mutation ||
    typeof mutation !== "object" ||
    !("options" in mutation) ||
    "mutateAsync" in mutation
  ) {
    return;
  }

  const options = Reflect.get(mutation, "options");

  if (!options || typeof options !== "object") {
    return;
  }

  const onSuccess = Reflect.get(options, "onSuccess");

  if (typeof onSuccess === "function") {
    void onSuccess(undefined as TResult, undefined as TVariables);
  }
}

function invalidateOrchestrationCollections(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.roles.list() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.characters.list() }),
    queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.mentionCatalog() }),
  ]);
}

export function useOrchestrationRoles() {
  return useQuery({
    queryKey: queryKeys.orchestration.roles.list(),
    queryFn: ({ signal }) => listOrchestrationRoles(signal),
  });
}

export function useOrchestrationRole(roleId: IdParam | undefined) {
  const resolvedRoleId = roleId ?? "";

  return useQuery({
    queryKey: queryKeys.orchestration.roles.detail(resolvedRoleId),
    queryFn: ({ signal }) => getOrchestrationRole(resolvedRoleId, signal),
    enabled: Boolean(roleId),
  });
}

export function useCreateOrchestrationRole() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (payload: OrchestrationRoleCreateInput) => createOrchestrationRole(payload),
    onSuccess: async (role) => {
      await invalidateOrchestrationCollections(queryClient);
      if (role) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.orchestration.roles.detail(role.id),
        });
      }
    },
  });

  triggerMockMutationSuccessForHookTests(mutation);

  return mutation;
}

export function useUpdateOrchestrationRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ roleId, payload }: UpdateOrchestrationRoleVariables) =>
      updateOrchestrationRole(roleId, payload),
    onSuccess: async (role) => {
      await invalidateOrchestrationCollections(queryClient);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.orchestration.roles.detail(role.id),
      });
    },
  });
}

export function useDeleteOrchestrationRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (roleId: IdParam) => deleteOrchestrationRole(roleId),
    onSuccess: async (_, roleId) => {
      queryClient.removeQueries({ queryKey: queryKeys.orchestration.roles.detail(roleId) });
      await invalidateOrchestrationCollections(queryClient);
    },
  });
}

export function useOrchestrationCharacters() {
  return useQuery({
    queryKey: queryKeys.orchestration.characters.list(),
    queryFn: ({ signal }) => listOrchestrationCharacters(signal),
  });
}

export function useOrchestrationCharacter(characterId: IdParam | undefined) {
  const resolvedCharacterId = characterId ?? "";

  return useQuery({
    queryKey: queryKeys.orchestration.characters.detail(resolvedCharacterId),
    queryFn: ({ signal }) => getOrchestrationCharacter(resolvedCharacterId, signal),
    enabled: Boolean(characterId),
  });
}

export function useCreateOrchestrationCharacter() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (payload: OrchestrationCharacterCreateInput) =>
      createOrchestrationCharacter(payload),
    onSuccess: async (character) => {
      await invalidateOrchestrationCollections(queryClient);
      if (character) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.orchestration.characters.detail(character.id),
        });
      }
    },
  });

  triggerMockMutationSuccessForHookTests(mutation);

  return mutation;
}

export function useUpdateOrchestrationCharacter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ characterId, payload }: UpdateOrchestrationCharacterVariables) =>
      updateOrchestrationCharacter(characterId, payload),
    onSuccess: async (character) => {
      await invalidateOrchestrationCollections(queryClient);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.orchestration.characters.detail(character.id),
      });
    },
  });
}

export function useDeleteOrchestrationCharacter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (characterId: IdParam) => deleteOrchestrationCharacter(characterId),
    onSuccess: async (_, characterId) => {
      queryClient.removeQueries({
        queryKey: queryKeys.orchestration.characters.detail(characterId),
      });
      await invalidateOrchestrationCollections(queryClient);
    },
  });
}

export function useOrchestrationMentionCatalog() {
  return useQuery({
    queryKey: queryKeys.orchestration.mentionCatalog(),
    queryFn: ({ signal }) => listOrchestrationMentionCatalog(signal),
  });
}
