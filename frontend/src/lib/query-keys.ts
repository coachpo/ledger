import type { QueryClient } from "@tanstack/react-query";
import type {
  GetMarketHistoryParams,
  GetMarketQuotesParams,
} from "./types/market-data";
import type {
  MemoryAdminHistoryParams,
  MemoryAdminListParams,
  MemoryApiAccessRequest,
  MemoryApiListRequest,
  MemoryScope,
  MemorySubjectRef,
} from "./types/memory";
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

function portfolioRoot(portfolioId: IdParam) {
  return [...apiRoot, "portfolios", normalizeId(portfolioId)] as const;
}

function normalizeSymbols(symbols: readonly string[]) {
  return [
    ...new Set(symbols.map((symbol) => symbol.trim()).filter(Boolean)),
  ].sort();
}

function normalizePositionSymbol(symbol: string) {
  return symbol.trim().toUpperCase();
}
function normalizeOptionalText(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function normalizeOptionalKind(value: string | null | undefined) {
  return normalizeOptionalText(value)?.toLowerCase();
}

function omitUndefined<T extends Record<string, unknown>>(value: T) {
  return Object.fromEntries(
    Object.entries(value).filter(([, entryValue]) => entryValue !== undefined),
  ) as Partial<T>;
}

function normalizeMemoryScope(scope: MemoryScope) {
  return {
    scopeKey: scope.scopeKey.trim(),
    scopeType: scope.scopeType,
  };
}

function normalizeMemorySubjectRefs(
  subjectRefs: readonly MemorySubjectRef[] = [],
) {
  return subjectRefs.map((subjectRef) =>
    omitUndefined({
      attributes: subjectRef.attributes,
      id: subjectRef.id.trim(),
      kind: subjectRef.kind.trim().toLowerCase(),
      label: normalizeOptionalText(subjectRef.label),
    }),
  );
}

function normalizeMemoryAccessRequest(payload: MemoryApiAccessRequest) {
  return {
    accessContext: omitUndefined({
      agentKey: normalizeOptionalText(payload.accessContext.agentKey),
      packageKey: payload.accessContext.packageKey.trim(),
      runId: payload.accessContext.runId ?? undefined,
      workflowKey: normalizeOptionalText(payload.accessContext.workflowKey),
    }),
  };
}

function normalizeMemoryListRequest(payload: MemoryApiListRequest) {
  return omitUndefined({
    ...normalizeMemoryAccessRequest(payload),
    kind: normalizeOptionalKind(payload.kind),
    limit: payload.limit ?? 5,
    maxCharacters: payload.maxCharacters ?? 4_000,
    offset: payload.offset ?? 0,
    query: normalizeOptionalText(payload.query),
    scope: normalizeMemoryScope(payload.scope),
    subjectRefs: normalizeMemorySubjectRefs(payload.subjectRefs),
    tags: normalizeSymbols(payload.tags ?? []),
    visibility: payload.visibility ?? "explicit-scope",
  });
}

function normalizeMemoryAdminListParams(params: MemoryAdminListParams = {}) {
  return omitUndefined({
    agentKey: normalizeOptionalText(params.agentKey),
    kind: normalizeOptionalKind(params.kind),
    limit: params.limit ?? 50,
    offset: params.offset ?? 0,
    packageKey: normalizeOptionalText(params.packageKey),
    query: normalizeOptionalText(params.query),
    runId: params.runId ?? undefined,
    scopeType: params.scopeType ?? undefined,
    sort: params.sort ?? "updatedAtDesc",
    visibleToWorkflow: params.visibleToWorkflow ?? undefined,
    workflowKey: normalizeOptionalText(params.workflowKey),
  });
}

function normalizeMemoryAdminHistoryParams(
  params: MemoryAdminHistoryParams = {},
) {
  return omitUndefined({
    limit: params.limit,
    offset: params.offset ?? 0,
  });
}

function normalizeHistoryParams(params: GetMarketHistoryParams) {
  return {
    range: params.range ?? "3mo",
    symbols: normalizeSymbols(params.symbols),
  };
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
const portfoliosQueryKeys = {
  all: [...apiRoot, "portfolios"] as const,
  detail: (portfolioId: IdParam) =>
    [...apiRoot, "portfolios", "detail", normalizeId(portfolioId)] as const,
  details: () => [...apiRoot, "portfolios", "detail"] as const,
  list: () => [...apiRoot, "portfolios", "list"] as const,
  lists: () => [...apiRoot, "portfolios", "list"] as const,
} as const;

const balancesQueryKeys = {
  all: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "balances"] as const,
  detail: (portfolioId: IdParam, balanceId: IdParam) =>
    [
      ...portfolioRoot(portfolioId),
      "balances",
      "detail",
      normalizeId(balanceId),
    ] as const,
  list: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "balances", "list"] as const,
} as const;

const positionsQueryKeys = {
  all: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "positions"] as const,
  detail: (portfolioId: IdParam, positionId: IdParam) =>
    [
      ...portfolioRoot(portfolioId),
      "positions",
      "detail",
      normalizeId(positionId),
    ] as const,
  list: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "positions", "list"] as const,
  lookup: (portfolioId: IdParam, symbol: string) =>
    [
      ...portfolioRoot(portfolioId),
      "positions",
      "lookup",
      normalizePositionSymbol(symbol),
    ] as const,
} as const;

const tradesQueryKeys = {
  all: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "trades"] as const,
  detail: (portfolioId: IdParam, tradeId: IdParam) =>
    [
      ...portfolioRoot(portfolioId),
      "trades",
      "detail",
      normalizeId(tradeId),
    ] as const,
  list: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "trades", "list"] as const,
} as const;

const marketDataQueryKeys = {
  all: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "marketData"] as const,
  quotes: (portfolioId: IdParam, params: GetMarketQuotesParams) =>
    [
      ...portfolioRoot(portfolioId),
      "marketData",
      "quotes",
      normalizeSymbols(params.symbols),
    ] as const,
} as const;
const marketHistoryQueryKeys = {
  all: (portfolioId: IdParam) =>
    [...portfolioRoot(portfolioId), "marketHistory"] as const,
  series: (portfolioId: IdParam, params: GetMarketHistoryParams) =>
    [
      ...portfolioRoot(portfolioId),
      "marketHistory",
      "series",
      normalizeHistoryParams(params),
    ] as const,
} as const;

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

function workflowPackageRuntimeInputRegistryRoot(packageId: IdParam) {
  return [
    ...workflowPackagesRoot,
    "runtimeInputRegistry",
    normalizeId(packageId),
  ] as const;
}

function normalizeWorkflowKey(workflowKey: string | null | undefined) {
  return workflowKey?.trim() ?? "";
}

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
  runtimeInputRegistry: (
    packageId: IdParam,
    workflowKey: string | null | undefined,
  ) =>
    [
      ...workflowPackageRuntimeInputRegistryRoot(packageId),
      { workflowKey: normalizeWorkflowKey(workflowKey) },
    ] as const,
  runtimeInputRegistryScope: (packageId: IdParam) =>
    workflowPackageRuntimeInputRegistryRoot(packageId),
  secretBindings: (packageId: IdParam) =>
    [
      ...workflowPackagesRoot,
      "secretBindings",
      normalizeId(packageId),
    ] as const,
  validation: () => [...workflowPackagesRoot, "validation"] as const,
} as const;
const memoryRoot = [...platformApiRoot, "memory"] as const;
const memoryAdminEntriesRoot = [...memoryRoot, "admin", "entries"] as const;

const memoryQueryKeys = {
  admin: {
    all: memoryAdminEntriesRoot,
    detail: (memoryId: IdParam) =>
      [...memoryAdminEntriesRoot, "detail", normalizeId(memoryId)] as const,
    details: () => [...memoryAdminEntriesRoot, "detail"] as const,
    events: (memoryId: IdParam, params: MemoryAdminHistoryParams = {}) =>
      [
        ...memoryAdminEntriesRoot,
        "events",
        normalizeId(memoryId),
        normalizeMemoryAdminHistoryParams(params),
      ] as const,
    eventsScope: (memoryId: IdParam) =>
      [...memoryAdminEntriesRoot, "events", normalizeId(memoryId)] as const,
    list: (params: MemoryAdminListParams = {}) =>
      [
        ...memoryAdminEntriesRoot,
        "list",
        normalizeMemoryAdminListParams(params),
      ] as const,
    lists: () => [...memoryAdminEntriesRoot, "list"] as const,
    revisions: (memoryId: IdParam, params: MemoryAdminHistoryParams = {}) =>
      [
        ...memoryAdminEntriesRoot,
        "revisions",
        normalizeId(memoryId),
        normalizeMemoryAdminHistoryParams(params),
      ] as const,
    revisionsScope: (memoryId: IdParam) =>
      [...memoryAdminEntriesRoot, "revisions", normalizeId(memoryId)] as const,
  },
  all: memoryRoot,
  detail: (memoryId: IdParam, payload?: MemoryApiAccessRequest) => {
    const base = [...memoryRoot, "detail", normalizeId(memoryId)] as const;
    if (!payload) {
      return base;
    }
    return [...base, normalizeMemoryAccessRequest(payload)] as const;
  },
  events: (memoryId: IdParam, payload?: MemoryApiAccessRequest) => {
    const base = [...memoryRoot, "events", normalizeId(memoryId)] as const;
    if (!payload) {
      return base;
    }
    return [...base, normalizeMemoryAccessRequest(payload)] as const;
  },
  list: (params: MemoryApiListRequest) =>
    [...memoryRoot, "list", normalizeMemoryListRequest(params)] as const,
  revisions: (memoryId: IdParam, payload?: MemoryApiAccessRequest) => {
    const base = [...memoryRoot, "revisions", normalizeId(memoryId)] as const;
    if (!payload) {
      return base;
    }
    return [...base, normalizeMemoryAccessRequest(payload)] as const;
  },
} as const;

const platformQueryKeys = {
  all: [...platformApiRoot] as const,
  memory: memoryQueryKeys,
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
  extensions: {
    all: [...platformApiRoot, "extensions"] as const,
    detail: (extensionKey: IdParam) =>
      [
        ...platformApiRoot,
        "extensions",
        "detail",
        normalizeId(extensionKey),
      ] as const,
    list: () => [...platformApiRoot, "extensions", "list"] as const,
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
    forkDraft: (runId: IdParam, sourceInvocationId: number) =>
      [
        ...platformApiRoot,
        "runs",
        "forkDraft",
        normalizeId(runId),
        { sourceInvocationId },
      ] as const,
    forkDrafts: () => [...platformApiRoot, "runs", "forkDraft"] as const,
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
  portfolios: portfoliosQueryKeys,
  balances: balancesQueryKeys,
  positions: positionsQueryKeys,
  trades: tradesQueryKeys,
  tradingOperations: tradesQueryKeys,
  marketData: marketDataQueryKeys,
  marketHistory: marketHistoryQueryKeys,
  templates: templatesQueryKeys,
  reports: reportsQueryKeys,
  platform: platformQueryKeys,
} as const;

export function invalidatePortfolioScope(
  queryClient: QueryClient,
  portfolioId: number | string,
) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: portfolioRoot(portfolioId) }),
    queryClient.invalidateQueries({ queryKey: portfoliosQueryKeys.all }),
  ]);
}
