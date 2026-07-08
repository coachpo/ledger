import type { ModelConnectionListParams } from "./types/model-connection";
import type { RunListParams } from "./types/run";
import type {
  ScheduleFireListParams,
  ScheduleListParams,
} from "./types/schedule";

const apiRoot = ["api"] as const;
const platformApiRoot = [...apiRoot, "platform"] as const;
type IdParam = number | string;

function normalizeId(id: IdParam) {
  return String(id);
}

function normalizeOptionalText(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function omitUndefined<T extends Record<string, unknown>>(value: T) {
  return Object.fromEntries(
    Object.entries(value).filter(([, entryValue]) => entryValue !== undefined),
  ) as Partial<T>;
}

function normalizeModelConnectionListParams(
  _params: ModelConnectionListParams = {},
) {
  return {};
}

function normalizeRunListParams(params: RunListParams = {}) {
  return omitUndefined({
    limit: params.limit,
    modelConnectionKey: normalizeOptionalText(params.modelConnectionKey),
    offset: params.offset ?? 0,
    status: params.status,
    workflowKey: normalizeOptionalText(params.workflowKey),
    workflowPackageId: params.workflowPackageId,
    workflowPackageKey: normalizeOptionalText(params.workflowPackageKey),
  });
}

function normalizeScheduleListParams(params: ScheduleListParams = {}) {
  return omitUndefined({
    limit: params.limit,
    offset: params.offset ?? 0,
    packageId: params.packageId,
    packageKey: normalizeOptionalText(params.packageKey),
    status: params.status,
    workflowKey: normalizeOptionalText(params.workflowKey),
  });
}

function normalizeScheduleFireListParams(params: ScheduleFireListParams = {}) {
  return omitUndefined({
    limit: params.limit,
    offset: params.offset ?? 0,
  });
}

const templatesQueryKeys = {
  all: [...apiRoot, "templates"] as const,
  compile: (templateId: IdParam) =>
    [...apiRoot, "templates", "compile", normalizeId(templateId)] as const,
  detail: (templateId: IdParam) =>
    [...apiRoot, "templates", "detail", normalizeId(templateId)] as const,
  list: () => [...apiRoot, "templates", "list"] as const,
} as const;

const reportsQueryKeys = {
  all: [...apiRoot, "reports"] as const,
  detail: (reportId: IdParam) =>
    [...apiRoot, "reports", "detail", normalizeId(reportId)] as const,
  list: () => [...apiRoot, "reports", "list"] as const,
} as const;
const workflowPackagesRoot = [...platformApiRoot, "workflowPackages"] as const;

const schedulesRoot = [...platformApiRoot, "schedules"] as const;

const schedulesQueryKeys = {
  all: schedulesRoot,
  detail: (scheduleId: IdParam) =>
    [...schedulesRoot, "detail", normalizeId(scheduleId)] as const,
  fires: (scheduleId: IdParam, params: ScheduleFireListParams = {}) =>
    [
      ...schedulesRoot,
      "fires",
      normalizeId(scheduleId),
      normalizeScheduleFireListParams(params),
    ] as const,
  firesScope: (scheduleId: IdParam) =>
    [...schedulesRoot, "fires", normalizeId(scheduleId)] as const,
  list: (params: ScheduleListParams = {}) =>
    [...schedulesRoot, "list", normalizeScheduleListParams(params)] as const,
  lists: () => [...schedulesRoot, "list"] as const,
} as const;

const workflowPackagesQueryKeys = {
  all: workflowPackagesRoot,
  detail: (packageId: IdParam) =>
    [...workflowPackagesRoot, "detail", normalizeId(packageId)] as const,
  manifest: (packageId: IdParam) =>
    [...workflowPackagesRoot, "manifest", normalizeId(packageId)] as const,
  export: (packageId: IdParam) =>
    [...workflowPackagesRoot, "export", normalizeId(packageId)] as const,
  launch: (packageId: IdParam, workflowKey?: string | null) => {
    const normalizedWorkflowKey = normalizeOptionalText(workflowKey);
    if (normalizedWorkflowKey === undefined) {
      return [
        ...workflowPackagesRoot,
        "launch",
        normalizeId(packageId),
      ] as const;
    }
    return [
      ...workflowPackagesRoot,
      "launch",
      normalizeId(packageId),
      { workflowKey: normalizedWorkflowKey },
    ] as const;
  },
  launches: () => [...workflowPackagesRoot, "launch"] as const,
  list: () => [...workflowPackagesRoot, "list"] as const,
  preflight: (packageId: IdParam, workflowKey?: string | null) => {
    const normalizedWorkflowKey = normalizeOptionalText(workflowKey);
    if (normalizedWorkflowKey === undefined) {
      return [
        ...workflowPackagesRoot,
        "preflight",
        normalizeId(packageId),
      ] as const;
    }
    return [
      ...workflowPackagesRoot,
      "preflight",
      normalizeId(packageId),
      { workflowKey: normalizedWorkflowKey },
    ] as const;
  },
  preflights: () => [...workflowPackagesRoot, "preflight"] as const,
  secretBindings: (packageId: IdParam) =>
    [
      ...workflowPackagesRoot,
      "secretBindings",
      normalizeId(packageId),
    ] as const,
  validation: () => [...workflowPackagesRoot, "validation"] as const,
} as const;
const platformQueryKeys = {
  all: [...platformApiRoot] as const,
  modelConnections: {
    all: [...platformApiRoot, "modelConnections"] as const,
    detail: (modelConnectionId: IdParam) =>
      [
        ...platformApiRoot,
        "modelConnections",
        "detail",
        normalizeId(modelConnectionId),
      ] as const,
    list: (params: ModelConnectionListParams = {}) =>
      [
        ...platformApiRoot,
        "modelConnections",
        "list",
        normalizeModelConnectionListParams(params),
      ] as const,
  },
  tools: {
    all: [...platformApiRoot, "tools"] as const,
    list: () => [...platformApiRoot, "tools", "list"] as const,
  },
  schedules: schedulesQueryKeys,
  runs: {
    all: [...platformApiRoot, "runs"] as const,
    lists: () => [...platformApiRoot, "runs", "list"] as const,
    detail: (runId: IdParam) =>
      [...platformApiRoot, "runs", "detail", normalizeId(runId)] as const,
    rerunDraft: (runId: IdParam) =>
      [...platformApiRoot, "runs", "rerunDraft", normalizeId(runId)] as const,
    rerunDrafts: () => [...platformApiRoot, "runs", "rerunDraft"] as const,
    list: (params: RunListParams = {}) =>
      [
        ...platformApiRoot,
        "runs",
        "list",
        normalizeRunListParams(params),
      ] as const,
  },
  workflowPackages: workflowPackagesQueryKeys,
} as const;
export const queryKeys = {
  templates: templatesQueryKeys,
  reports: reportsQueryKeys,
  platform: platformQueryKeys,
} as const;
