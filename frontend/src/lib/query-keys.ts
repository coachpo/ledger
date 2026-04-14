import type { QueryClient } from "@tanstack/react-query";
import type { GetMarketHistoryParams, GetMarketQuotesParams } from "./types/market-data";
import type {
  RuntimeApprovalListParams,
  RuntimeRunListParams,
  RuntimeTraceEventListParams,
} from "./types/runtime";
import type {
  CapabilityListParams,
  PersonaProfileListParams,
  StudioArtifactListParams,
  StudioSpecListParams,
} from "./types/studio";

const apiRoot = ["api"] as const;
const v2ApiRoot = [...apiRoot, "v2"] as const;
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

function normalizeRuntimeRunParams(params: RuntimeRunListParams = {}) {
  return omitUndefined({
    callerId: params.callerId,
    callerIdentityKey: normalizeOptionalText(params.callerIdentityKey),
    callerScopeKey: normalizeOptionalText(params.callerScopeKey),
    callerType: params.callerType,
    workflowSpecKey: normalizeOptionalText(params.workflowSpecKey),
  });
}

function normalizeRuntimeApprovalParams(params: RuntimeApprovalListParams = {}) {
  return omitUndefined({
    callerId: params.callerId,
    callerType: params.callerType,
    capabilityKey: normalizeOptionalText(params.capabilityKey),
    runId: params.runId,
    status: params.status,
    workflowSpecKey: normalizeOptionalText(params.workflowSpecKey),
  });
}

function normalizeRuntimeTraceEventParams(params: RuntimeTraceEventListParams = {}) {
  return omitUndefined({
    callerId: params.callerId,
    callerType: params.callerType,
    capabilityKey: normalizeOptionalText(params.capabilityKey),
    eventType: params.eventType,
    runId: params.runId,
    workflowSpecKey: normalizeOptionalText(params.workflowSpecKey),
  });
}

function normalizeStudioArtifactParams(params: StudioArtifactListParams = {}) {
  return omitUndefined({
    callerId: params.callerId,
    callerType: params.callerType,
    capabilityKey: normalizeOptionalText(params.capabilityKey),
    personaProfileKey: normalizeOptionalText(params.personaProfileKey),
    runId: params.runId,
    workflowSpecKey: normalizeOptionalText(params.workflowSpecKey),
  });
}

function normalizeStudioSpecListParams(params: StudioSpecListParams = {}) {
  return omitUndefined({
    origin: params.origin,
    status: params.status,
  });
}

function normalizeCapabilityListParams(params: CapabilityListParams = {}) {
  return omitUndefined({
    origin: params.origin,
    status: params.status,
    type: params.type,
  });
}

function normalizePersonaListParams(params: PersonaProfileListParams = {}) {
  return omitUndefined({
    enabled: params.enabled,
    kind: params.kind,
    origin: params.origin,
    status: params.status,
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
  detail: (reportId: IdParam) =>
    [...apiRoot, "reports", "detail", normalizeId(reportId)] as const,
  list: () => [...apiRoot, "reports", "list"] as const,
} as const;

const backtestsQueryKeys = {
  all: [...apiRoot, "backtests"] as const,
  detail: (backtestId: IdParam) =>
    [...apiRoot, "backtests", "detail", normalizeId(backtestId)] as const,
  list: () => [...apiRoot, "backtests", "list"] as const,
} as const;

const orchestrationQueryKeys = {
  all: [...apiRoot, "orchestration"] as const,
  roles: {
    all: [...apiRoot, "orchestration", "roles"] as const,
    detail: (roleId: IdParam) =>
      [...apiRoot, "orchestration", "roles", "detail", normalizeId(roleId)] as const,
    list: () => [...apiRoot, "orchestration", "roles", "list"] as const,
  },
  characters: {
    all: [...apiRoot, "orchestration", "characters"] as const,
    detail: (characterId: IdParam) =>
      [...apiRoot, "orchestration", "characters", "detail", normalizeId(characterId)] as const,
    list: () => [...apiRoot, "orchestration", "characters", "list"] as const,
  },
  mentionCatalog: () => [...apiRoot, "orchestration", "mentionCatalog"] as const,
} as const;

const runtimeQueryKeys = {
  all: [...v2ApiRoot, "runtime"] as const,
  runs: {
    all: [...v2ApiRoot, "runtime", "runs"] as const,
    artifact: (runId: IdParam) =>
      [...v2ApiRoot, "runtime", "runs", "artifact", normalizeId(runId)] as const,
    detail: (runId: IdParam) =>
      [...v2ApiRoot, "runtime", "runs", "detail", normalizeId(runId)] as const,
    list: (params: RuntimeRunListParams = {}) =>
      [...v2ApiRoot, "runtime", "runs", "list", normalizeRuntimeRunParams(params)] as const,
    trace: (runId: IdParam) =>
      [...v2ApiRoot, "runtime", "runs", "trace", normalizeId(runId)] as const,
  },
  approvals: {
    all: [...v2ApiRoot, "runtime", "approvals"] as const,
    detail: (approvalId: IdParam) =>
      [...v2ApiRoot, "runtime", "approvals", "detail", normalizeId(approvalId)] as const,
    list: (params: RuntimeApprovalListParams = {}) =>
      [
        ...v2ApiRoot,
        "runtime",
        "approvals",
        "list",
        normalizeRuntimeApprovalParams(params),
      ] as const,
  },
  traceEvents: {
    all: [...v2ApiRoot, "runtime", "traceEvents"] as const,
    list: (params: RuntimeTraceEventListParams = {}) =>
      [
        ...v2ApiRoot,
        "runtime",
        "traceEvents",
        "list",
        normalizeRuntimeTraceEventParams(params),
      ] as const,
  },
} as const;

const studioQueryKeys = {
  all: [...v2ApiRoot, "studio"] as const,
  runs: {
    all: [...v2ApiRoot, "studio", "runs"] as const,
    artifact: (runId: IdParam) =>
      [...v2ApiRoot, "studio", "runs", "artifact", normalizeId(runId)] as const,
    detail: (runId: IdParam) =>
      [...v2ApiRoot, "studio", "runs", "detail", normalizeId(runId)] as const,
    list: (params: RuntimeRunListParams = {}) =>
      [...v2ApiRoot, "studio", "runs", "list", normalizeRuntimeRunParams(params)] as const,
    trace: (runId: IdParam) =>
      [...v2ApiRoot, "studio", "runs", "trace", normalizeId(runId)] as const,
  },
  artifacts: {
    all: [...v2ApiRoot, "studio", "artifacts"] as const,
    list: (params: StudioArtifactListParams = {}) =>
      [...v2ApiRoot, "studio", "artifacts", "list", normalizeStudioArtifactParams(params)] as const,
  },
  approvals: {
    all: [...v2ApiRoot, "studio", "approvals"] as const,
    detail: (approvalId: IdParam) =>
      [...v2ApiRoot, "studio", "approvals", "detail", normalizeId(approvalId)] as const,
    list: (params: RuntimeApprovalListParams = {}) =>
      [
        ...v2ApiRoot,
        "studio",
        "approvals",
        "list",
        normalizeRuntimeApprovalParams(params),
      ] as const,
  },
  traceEvents: {
    all: [...v2ApiRoot, "studio", "traceEvents"] as const,
    list: (params: RuntimeTraceEventListParams = {}) =>
      [
        ...v2ApiRoot,
        "studio",
        "traceEvents",
        "list",
        normalizeRuntimeTraceEventParams(params),
      ] as const,
  },
  agentSpecs: {
    all: [...v2ApiRoot, "studio", "agentSpecs"] as const,
    detail: (specId: IdParam) =>
      [...v2ApiRoot, "studio", "agentSpecs", "detail", normalizeId(specId)] as const,
    list: (params: StudioSpecListParams = {}) =>
      [...v2ApiRoot, "studio", "agentSpecs", "list", normalizeStudioSpecListParams(params)] as const,
  },
  workflowSpecs: {
    all: [...v2ApiRoot, "studio", "workflowSpecs"] as const,
    detail: (specId: IdParam) =>
      [...v2ApiRoot, "studio", "workflowSpecs", "detail", normalizeId(specId)] as const,
    list: (params: StudioSpecListParams = {}) =>
      [
        ...v2ApiRoot,
        "studio",
        "workflowSpecs",
        "list",
        normalizeStudioSpecListParams(params),
      ] as const,
  },
   personas: {
     all: [...v2ApiRoot, "studio", "personas"] as const,
     detail: (personaKey: IdParam) =>
       [...v2ApiRoot, "studio", "personas", "detail", normalizeId(personaKey)] as const,
     list: (params: PersonaProfileListParams = {}) =>
       [...v2ApiRoot, "studio", "personas", "list", normalizePersonaListParams(params)] as const,
     version: (personaKey: IdParam, version: number | string) =>
       [...v2ApiRoot, "studio", "personas", "version", normalizeId(personaKey), String(version)] as const,
     versions: (personaKey: IdParam) =>
       [...v2ApiRoot, "studio", "personas", "versions", normalizeId(personaKey)] as const,
   },
  capabilities: {
    all: [...v2ApiRoot, "studio", "capabilities"] as const,
    detail: (specId: IdParam) =>
      [...v2ApiRoot, "studio", "capabilities", "detail", normalizeId(specId)] as const,
    list: (params: CapabilityListParams = {}) =>
      [...v2ApiRoot, "studio", "capabilities", "list", normalizeCapabilityListParams(params)] as const,
  },
} as const;

const tryoutsQueryKeys = {
  all: [...v2ApiRoot, "tryouts"] as const,
  detail: (runId: IdParam) => [...v2ApiRoot, "tryouts", "detail", normalizeId(runId)] as const,
} as const;

export const queryKeys = {
  backtests: backtestsQueryKeys,
  portfolios: portfoliosQueryKeys,
  balances: balancesQueryKeys,
  positions: positionsQueryKeys,
  trades: tradesQueryKeys,
  tradingOperations: tradesQueryKeys,
  marketData: marketDataQueryKeys,
  marketHistory: marketHistoryQueryKeys,
  templates: templatesQueryKeys,
  reports: reportsQueryKeys,
  orchestration: orchestrationQueryKeys,
  runtime: runtimeQueryKeys,
  studio: studioQueryKeys,
  tryouts: tryoutsQueryKeys,
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
