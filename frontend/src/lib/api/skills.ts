import { requestPlatform, toPathSegment, toQueryRecord, type IdParam } from "../api-client";
import type { SkillCreateInput, SkillListParams, SkillListRead, SkillRead, SkillUpdateInput } from "../types/skill";

function skillPath(skillId: IdParam): string {
  return `/skills/${toPathSegment(skillId)}`;
}

export function listSkills(
  params?: SkillListParams,
  signal?: AbortSignal,
): Promise<SkillListRead> {
  return requestPlatform<SkillListRead>("/skills", {
    query: toQueryRecord(params),
    signal,
  });
}

export function getSkill(skillId: IdParam, signal?: AbortSignal): Promise<SkillRead> {
  return requestPlatform<SkillRead>(skillPath(skillId), { signal });
}

export function createSkill(
  payload: SkillCreateInput,
  signal?: AbortSignal,
): Promise<SkillRead> {
  return requestPlatform<SkillRead>("/skills", {
    body: payload,
    method: "POST",
    signal,
  });
}

export function updateSkill(
  skillId: IdParam,
  payload: SkillUpdateInput,
  signal?: AbortSignal,
): Promise<SkillRead> {
  return requestPlatform<SkillRead>(skillPath(skillId), {
    body: payload,
    method: "PATCH",
    signal,
  });
}

export function activateSkill(skillId: IdParam, signal?: AbortSignal): Promise<SkillRead> {
  return requestPlatform<SkillRead>(`${skillPath(skillId)}/activate`, {
    method: "POST",
    signal,
  });
}

export function archiveSkill(skillId: IdParam, signal?: AbortSignal): Promise<SkillRead> {
  return requestPlatform<SkillRead>(skillPath(skillId), {
    method: "DELETE",
    signal,
  });
}

export const skillsApi = {
  activate: activateSkill,
  archive: archiveSkill,
  create: createSkill,
  get: getSkill,
  list: listSkills,
  update: updateSkill,
} as const;
