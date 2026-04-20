import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { activateSkill, archiveSkill, createSkill, getSkill, listSkills, updateSkill } from "@/lib/api/skills";
import type { IdParam } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import type { SkillCreateInput, SkillListParams, SkillUpdateInput } from "@/lib/types/skill";

type UpdateSkillVariables = {
  payload: SkillUpdateInput;
  skillId: IdParam;
};

function invalidateSkillScope(queryClient: QueryClient, skillId: IdParam) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.skills.all }),
    queryClient.invalidateQueries({ queryKey: queryKeys.platform.skills.detail(skillId) }),
  ]);
}

export function useSkills(params: SkillListParams = {}) {
  return useQuery({
    queryKey: queryKeys.platform.skills.list(params),
    queryFn: ({ signal }) => listSkills(params, signal),
  });
}

export function useSkill(skillId: IdParam | undefined) {
  const resolvedSkillId = skillId ?? "";

  return useQuery({
    queryKey: queryKeys.platform.skills.detail(resolvedSkillId),
    queryFn: ({ signal }) => getSkill(resolvedSkillId, signal),
    enabled: Boolean(skillId),
  });
}

export function useCreateSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: SkillCreateInput) => createSkill(payload),
    onSuccess: async (skill) => {
      await invalidateSkillScope(queryClient, skill.id);
    },
  });
}

export function useUpdateSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ payload, skillId }: UpdateSkillVariables) => updateSkill(skillId, payload),
    onSuccess: async (skill, { skillId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.skills.detail(skillId) });
      await invalidateSkillScope(queryClient, skill.id);
    },
  });
}

export function useActivateSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: IdParam) => activateSkill(skillId),
    onSuccess: async (skill) => {
      await invalidateSkillScope(queryClient, skill.id);
    },
  });
}

export function useArchiveSkill() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (skillId: IdParam) => archiveSkill(skillId),
    onSuccess: async (skill, skillId) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.platform.skills.detail(skillId) });
      await invalidateSkillScope(queryClient, skill.id);
    },
  });
}
