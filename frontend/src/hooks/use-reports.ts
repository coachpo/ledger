import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  compileReport,
  deleteReport,
  getReport,
  listReports,
  updateReport,
  uploadReport,
} from "@/lib/api/reports";
import { queryKeys } from "@/lib/query-keys";
import type { ReportCompileInput, ReportUpdateInput } from "@/lib/types/report";

type SlugParam = string;

type UpdateReportVariables = {
  slug: SlugParam;
  data: ReportUpdateInput;
};

type CompileReportVariables = {
  templateId: number | string;
  input?: ReportCompileInput;
};

export function useReports() {
  return useQuery({
    queryKey: queryKeys.reports.list(),
    queryFn: ({ signal }) => listReports(signal),
  });
}

export function useReport(slug: SlugParam | undefined) {
  const resolvedSlug = slug ?? "";

  return useQuery({
    queryKey: queryKeys.reports.detail(resolvedSlug),
    queryFn: ({ signal }) => getReport(resolvedSlug, signal),
    enabled: Boolean(slug),
  });
}

export function useCompileReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: CompileReportVariables | number | string) => {
      if (typeof variables === "number" || typeof variables === "string") {
        return compileReport(variables);
      }

      return compileReport(variables.templateId, variables.input);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.reports.list() }),
  });
}

export function useUploadReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (formData: FormData) => uploadReport(formData),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.reports.list() }),
  });
}

export function useUpdateReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ slug, data }: UpdateReportVariables) =>
      updateReport(slug, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.reports.list() });
      queryClient.invalidateQueries({
        queryKey: queryKeys.reports.detail(variables.slug),
      });
    },
  });
}

export function useDeleteReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (slug: SlugParam) => deleteReport(slug),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.reports.list() }),
  });
}
