import type { ReportCompileInput, ReportRead, ReportUpdateInput } from "../types/report";
import { type IdParam, buildApiUrl, request, toPathSegment } from "../api-client";

function reportPath(slug: IdParam): string {
  return `/reports/${toPathSegment(slug)}`;
}

export function listReports(signal?: AbortSignal): Promise<ReportRead[]> {
  return request<ReportRead[]>("/reports", { signal });
}

export function getReport(
  slug: IdParam,
  signal?: AbortSignal,
): Promise<ReportRead> {
  return request<ReportRead>(reportPath(slug), { signal });
}

export function compileReport(
  templateId: IdParam,
  input?: ReportCompileInput,
  signal?: AbortSignal,
): Promise<ReportRead> {
  return request<ReportRead>(`/reports/compile/${toPathSegment(templateId)}`, {
    body: input,
    method: "POST",
    signal,
  });
}

export function uploadReport(
  formData: FormData,
  signal?: AbortSignal,
): Promise<ReportRead> {
  return request<ReportRead>("/reports/upload", {
    method: "POST",
    body: formData,
    signal,
  });
}

export function updateReport(
  slug: IdParam,
  input: ReportUpdateInput,
  signal?: AbortSignal,
): Promise<ReportRead> {
  return request<ReportRead>(reportPath(slug), {
    body: input,
    method: "PATCH",
    signal,
  });
}

export function deleteReport(
  slug: IdParam,
  signal?: AbortSignal,
): Promise<void> {
  return request<void>(reportPath(slug), {
    method: "DELETE",
    signal,
  });
}

export function downloadReportUrl(slug: IdParam): string {
  return buildApiUrl(`${reportPath(slug)}/download`);
}

export const reportsApi = {
  compile: compileReport,
  delete: deleteReport,
  downloadUrl: downloadReportUrl,
  get: getReport,
  list: listReports,
  update: updateReport,
  upload: uploadReport,
} as const;
