import { type IdParam, request, toPathSegment } from "../api-client";
import type {
  OrchestrationCharacterCreateInput,
  OrchestrationCharacterRead,
  OrchestrationCharacterUpdateInput,
  OrchestrationMentionCatalogItem,
  OrchestrationRoleCreateInput,
  OrchestrationRoleRead,
  OrchestrationRoleUpdateInput,
} from "../types/orchestration";

type OrchestrationMentionCatalogResponse = {
  targets: OrchestrationMentionCatalogItem[];
};

function orchestrationRolePath(roleId: IdParam): string {
  return `/orchestration/roles/${toPathSegment(roleId)}`;
}

function orchestrationCharacterPath(characterId: IdParam): string {
  return `/orchestration/characters/${toPathSegment(characterId)}`;
}

export function listOrchestrationRoles(signal?: AbortSignal): Promise<OrchestrationRoleRead[]> {
  return request<OrchestrationRoleRead[]>("/orchestration/roles", { signal });
}

export function getOrchestrationRole(
  roleId: IdParam,
  signal?: AbortSignal,
): Promise<OrchestrationRoleRead> {
  return request<OrchestrationRoleRead>(orchestrationRolePath(roleId), { signal });
}

export function createOrchestrationRole(
  payload: OrchestrationRoleCreateInput,
  signal?: AbortSignal,
): Promise<OrchestrationRoleRead> {
  return request<OrchestrationRoleRead>("/orchestration/roles", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateOrchestrationRole(
  roleId: IdParam,
  payload: OrchestrationRoleUpdateInput,
  signal?: AbortSignal,
): Promise<OrchestrationRoleRead> {
  return request<OrchestrationRoleRead>(orchestrationRolePath(roleId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function deleteOrchestrationRole(
  roleId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(orchestrationRolePath(roleId), {
    method: "DELETE",
    signal,
  });
}

export function listOrchestrationCharacters(
  signal?: AbortSignal,
): Promise<OrchestrationCharacterRead[]> {
  return request<OrchestrationCharacterRead[]>("/orchestration/characters", { signal });
}

export function getOrchestrationCharacter(
  characterId: IdParam,
  signal?: AbortSignal,
): Promise<OrchestrationCharacterRead> {
  return request<OrchestrationCharacterRead>(orchestrationCharacterPath(characterId), {
    signal,
  });
}

export function createOrchestrationCharacter(
  payload: OrchestrationCharacterCreateInput,
  signal?: AbortSignal,
): Promise<OrchestrationCharacterRead> {
  return request<OrchestrationCharacterRead>("/orchestration/characters", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateOrchestrationCharacter(
  characterId: IdParam,
  payload: OrchestrationCharacterUpdateInput,
  signal?: AbortSignal,
): Promise<OrchestrationCharacterRead> {
  return request<OrchestrationCharacterRead>(orchestrationCharacterPath(characterId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function deleteOrchestrationCharacter(
  characterId: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(orchestrationCharacterPath(characterId), {
    method: "DELETE",
    signal,
  });
}

export function listOrchestrationMentionCatalog(
  signal?: AbortSignal,
): Promise<OrchestrationMentionCatalogItem[]> {
  return request<OrchestrationMentionCatalogResponse>("/orchestration/mentions/catalog", {
    signal,
  }).then((response) => response.targets);
}

export const orchestrationApi = {
  roles: {
    create: createOrchestrationRole,
    delete: deleteOrchestrationRole,
    get: getOrchestrationRole,
    list: listOrchestrationRoles,
    update: updateOrchestrationRole,
  },
  characters: {
    create: createOrchestrationCharacter,
    delete: deleteOrchestrationCharacter,
    get: getOrchestrationCharacter,
    list: listOrchestrationCharacters,
    update: updateOrchestrationCharacter,
  },
  mentionCatalog: {
    list: listOrchestrationMentionCatalog,
  },
} as const;
