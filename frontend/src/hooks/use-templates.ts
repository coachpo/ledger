import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  compileTemplate,
  compileTemplateInline,
  createTemplate,
  deleteTemplate,
  getPlaceholders,
  getTemplate,
  listTemplates,
  updateTemplate,
} from "@/lib/api/templates";
import { queryKeys } from "@/lib/query-keys";
import type {
  TextTemplateInlineCompileInput,
  TextTemplateStoredCompileInput,
  TextTemplateUpdateInput,
  TextTemplateWriteInput,
} from "@/lib/types/text-template";

type IdParam = number | string;

type UpdateTemplateVariables = {
  templateId: IdParam;
  data: TextTemplateUpdateInput;
};

function clearDeletedTemplateQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  templateId: IdParam,
) {
  queryClient.removeQueries({
    queryKey: queryKeys.templates.detail(templateId),
  });
  queryClient.removeQueries({
    queryKey: queryKeys.templates.compile(templateId),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: queryKeys.templates.list(),
    queryFn: ({ signal }) => listTemplates(signal),
  });
}

export function useCreateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TextTemplateWriteInput) => createTemplate(data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.templates.list() }),
  });
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ templateId, data }: UpdateTemplateVariables) =>
      updateTemplate(templateId, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.templates.list() }),
  });
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (templateId: IdParam) => deleteTemplate(templateId),
    onSuccess: async (_result, templateId) => {
      clearDeletedTemplateQueries(queryClient, templateId);
      await queryClient.invalidateQueries({ queryKey: queryKeys.templates.list() });
    },
  });
}

export function useDeleteTemplates() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (templateIds: IdParam[]) => {
      const results = await Promise.allSettled(
        templateIds.map((templateId) => deleteTemplate(templateId)),
      );
      const firstRejected = results.find((result) => result.status === "rejected");

      if (firstRejected?.status === "rejected") {
        throw firstRejected.reason;
      }
    },
    onSettled: async (_result, _error, templateIds) => {
      templateIds.forEach((templateId) => {
        clearDeletedTemplateQueries(queryClient, templateId);
      });
      await queryClient.invalidateQueries({ queryKey: queryKeys.templates.list() });
    },
  });
}

export function useCompileTemplate(templateId: IdParam | undefined) {
  const resolvedId = templateId ?? "";

  return useQuery({
    queryKey: queryKeys.templates.compile(resolvedId),
    queryFn: ({ signal }) => compileTemplate(resolvedId, undefined, signal),
    enabled: Boolean(templateId),
  });
}

export function useTemplate(templateId: IdParam | undefined) {
  const resolvedId = templateId ?? "";

  return useQuery({
    queryKey: queryKeys.templates.detail(resolvedId),
    queryFn: ({ signal }) => getTemplate(resolvedId, signal),
    enabled: Boolean(templateId),
  });
}

export function useCompileInline() {
  return useMutation({
    mutationFn: (input: TextTemplateInlineCompileInput | string) =>
      compileTemplateInline(input),
  });
}

export type CompileStoredTemplateVariables = {
  templateId: IdParam;
  input?: TextTemplateStoredCompileInput;
};

export function usePlaceholders() {
  return useQuery({
    queryKey: [...queryKeys.templates.all, "placeholders"],
    queryFn: ({ signal }) => getPlaceholders(signal),
  });
}
