import type { QueryClient } from "@tanstack/react-query";
import type { GetMarketHistoryParams, GetMarketQuotesParams } from "./types/market-data";
import type { ModelConnectionListParams } from "./types/model-connection";
import type { RunListParams } from "./types/run";
import type { WorkflowPackageListParams } from "./types/workflow-package";

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
  return [...new Set(symbols.map((symbol) => symbol.trim()).filter(Boolean))].sort();
}

function normalizePositionSymbol(symbol: string) {
  return symbol.trim().toUpperCase();
}
function normalizeOptionalText(value: string | null | undefined) {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function normalizeOptionalVersion(value: number | string | null | undefined) {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }

  return Number(value);
}

function omitUndefined<T extends Record<string, unknown>>(value: T) {
  return Object.fromEntries(
    Object.entries(value).filter(([, entryValue]) => entryValue !== undefined),
  ) as Partial<T>;
}

function normalizeHistoryParams(params: GetMarketHistoryParams) {
  return {
    range: params.range ?? "3mo",
    symbols: normalizeSymbols(params.symbols),
  };
}
function normalizeModelConnectionListParams(params: ModelConnectionListParams = {}) {
  return omitUndefined({
    status: params.status,
  });
}

function normalizeWorkflowPackageListParams(params: WorkflowPackageListParams = {}) {
  return omitUndefined({
    includeArchived: params.includeArchived,
    status: params.status,
  });
}

function normalizeRunListParams(params: RunListParams = {}) {
  return omitUndefined({
    limit: params.limit,
    modelConnectionKey: normalizeOptionalText(params.modelConnectionKey),
    offset: params.offset ?? 0,
    status: params.status,
    targetId: params.targetId,
    targetKey: normalizeOptionalText(params.targetKey),
    targetKind: params.targetKind,
    targetVersion: params.targetVersion,
    workflowKey: normalizeOptionalText(params.workflowKey),
    workflowPackageId: params.workflowPackageId,
    workflowPackageKey: normalizeOptionalText(params.workflowPackageKey),
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
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "balances"] as const,
  detail: (portfolioId: IdParam, balanceId: IdParam) =>
    [...portfolioRoot(portfolioId), "balances", "detail", normalizeId(balanceId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "balances", "list"] as const,
} as const;

const positionsQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "positions"] as const,
  detail: (portfolioId: IdParam, positionId: IdParam) =>
    [...portfolioRoot(portfolioId), "positions", "detail", normalizeId(positionId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "positions", "list"] as const,
  lookup: (portfolioId: IdParam, symbol: string) =>
    [...portfolioRoot(portfolioId), "positions", "lookup", normalizePositionSymbol(symbol)] as const,
} as const;

const tradesQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "trades"] as const,
  detail: (portfolioId: IdParam, tradeId: IdParam) =>
    [...portfolioRoot(portfolioId), "trades", "detail", normalizeId(tradeId)] as const,
  list: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "trades", "list"] as const,
} as const;

const marketDataQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "marketData"] as const,
  quotes: (portfolioId: IdParam, params: GetMarketQuotesParams) =>
    [...portfolioRoot(portfolioId), "marketData", "quotes", normalizeSymbols(params.symbols)] as const,
} as const;
const marketHistoryQueryKeys = {
  all: (portfolioId: IdParam) => [...portfolioRoot(portfolioId), "marketHistory"] as const,
  series: (portfolioId: IdParam, params: GetMarketHistoryParams) =>
    [...portfolioRoot(portfolioId), "marketHistory", "series", normalizeHistoryParams(params)] as const,
} as const;

const templatesQueryKeys = {
  all: [...apiRoot, "templates"] as const,
  compile: (templateId: IdParam) =>
    [...apiRoot, "templates", "compile", normalizeId(templateId)] as const,
  list: () => [...apiRoot, "templates", "list"] as const,
} as const;

const reportsQueryKeys = {
  all: [...apiRoot, "reports"] as const,
  detail: (reportId: IdParam) => [...apiRoot, "reports", "detail", normalizeId(reportId)] as const,
  list: () => [...apiRoot, "reports", "list"] as const,
} as const;
const workflowPackagesRoot = [...platformApiRoot, "workflowPackages"] as const;

const workflowPackagesQueryKeys = {
  all: workflowPackagesRoot,
  detail: (packageId: IdParam) =>
    [...workflowPackagesRoot, "detail", normalizeId(packageId)] as const,
  export: (packageId: IdParam, version?: number | string) => {
    const normalizedVersion = normalizeOptionalVersion(version);
    if (normalizedVersion === undefined) {
      return [...workflowPackagesRoot, "export", normalizeId(packageId)] as const;
    }
    return [...workflowPackagesRoot, "export", normalizeId(packageId), { version: normalizedVersion }] as const;
  },
  launch: (packageId: IdParam, version?: number | string, workflowKey?: string | null) => {
    const normalizedVersion = normalizeOptionalVersion(version);
    const normalizedWorkflowKey = normalizeOptionalText(workflowKey);
    return [
      ...workflowPackagesRoot,
      "launch",
      normalizeId(packageId),
      omitUndefined({ version: normalizedVersion, workflowKey: normalizedWorkflowKey }),
    ] as const;
  },
  list: (params: WorkflowPackageListParams = {}) =>
    [...workflowPackagesRoot, "list", normalizeWorkflowPackageListParams(params)] as const,
  preflight: (packageId: IdParam, version?: number | string, workflowKey?: string | null) => {
    const normalizedVersion = normalizeOptionalVersion(version);
    const normalizedWorkflowKey = normalizeOptionalText(workflowKey);
    return [
      ...workflowPackagesRoot,
      "preflight",
      normalizeId(packageId),
      omitUndefined({ version: normalizedVersion, workflowKey: normalizedWorkflowKey }),
    ] as const;
  },
  validation: () => [...workflowPackagesRoot, "validation"] as const,
  versions: (packageId: IdParam) =>
    [...workflowPackagesRoot, "versions", normalizeId(packageId)] as const,
} as const;
const platformQueryKeys = {
  all: [...platformApiRoot] as const,
  modelConnections: {
    all: [...platformApiRoot, "modelConnections"] as const,
    detail: (modelConnectionId: IdParam) =>
      [...platformApiRoot, "modelConnections", "detail", normalizeId(modelConnectionId)] as const,
    list: (params: ModelConnectionListParams = {}) =>
      [...platformApiRoot, "modelConnections", "list", normalizeModelConnectionListParams(params)] as const,
  },
  tools: {
    all: [...platformApiRoot, "tools"] as const,
    list: () => [...platformApiRoot, "tools", "list"] as const,
  },
  runs: {
    all: [...platformApiRoot, "runs"] as const,
    detail: (runId: IdParam) =>
      [...platformApiRoot, "runs", "detail", normalizeId(runId)] as const,
    rerunDraft: (runId: IdParam) =>
      [...platformApiRoot, "runs", "rerunDraft", normalizeId(runId)] as const,
    stepReplayDraft: (runId: IdParam, stepIndex: number) =>
      [...platformApiRoot, "runs", "stepReplayDraft", normalizeId(runId), { stepIndex }] as const,
    list: (params: RunListParams = {}) =>
      [...platformApiRoot, "runs", "list", normalizeRunListParams(params)] as const,
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
