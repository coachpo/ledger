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
import type { TextTemplateUpdateInput, TextTemplateWriteInput } from "@/lib/types/text-template";
import type { TextTemplateInlineCompileInput, TextTemplateStoredCompileInput } from "@/lib/types/text-template";

type IdParam = number | string;

type UpdateTemplateVariables = {
  templateId: IdParam;
  data: TextTemplateUpdateInput;
};

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
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.templates.list() }),
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
    queryKey: [...queryKeys.templates.all, "detail", String(resolvedId)],
    queryFn: ({ signal }) => getTemplate(resolvedId, signal),
    enabled: Boolean(templateId),
  });
}

export function useCompileInline() {
  return useMutation({
    mutationFn: (input: TextTemplateInlineCompileInput | string) => compileTemplateInline(input),
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
