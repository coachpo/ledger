import type { QueryClient } from "@tanstack/react-query";
import type { GetMarketHistoryParams, GetMarketQuotesParams } from "./types/market-data";
import type { AgentListParams } from "./types/agent";
import type { McpServerListParams } from "./types/mcp-server";
import type { ModelConnectionListParams } from "./types/model-connection";
import type { OutputSchemaListParams } from "./types/output-schema";
import type { RunListParams } from "./types/run";
import type { SkillListParams } from "./types/skill";
import type { WorkflowListParams } from "./types/workflow";

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

function buildVersionedPlatformDetailKey(
  resourceRoot: readonly unknown[],
  id: IdParam,
  version?: number | string,
) {
  const normalizedVersion = normalizeOptionalVersion(version);

  if (normalizedVersion === undefined) {
    return [...resourceRoot, "detail", normalizeId(id)] as const;
  }

  return [...resourceRoot, "detail", normalizeId(id), { version: normalizedVersion }] as const;
}

function normalizeHistoryParams(params: GetMarketHistoryParams) {
  return {
    range: params.range ?? "3mo",
    symbols: normalizeSymbols(params.symbols),
  };
}

function normalizeAgentListParams(params: AgentListParams = {}) {
  return omitUndefined({
    status: params.status,
  });
}

function normalizeSkillListParams(params: SkillListParams = {}) {
  return omitUndefined({
    status: params.status,
  });
}

function normalizeMcpServerListParams(params: McpServerListParams = {}) {
  return omitUndefined({
    enabled: params.enabled,
    status: params.status,
    transport: params.transport,
  });
}

function normalizeModelConnectionListParams(params: ModelConnectionListParams = {}) {
  return omitUndefined({
    status: params.status,
  });
}

function normalizeOutputSchemaListParams(params: OutputSchemaListParams = {}) {
  return omitUndefined({
    kind: params.kind,
    status: params.status,
  });
}

function normalizeWorkflowListParams(params: WorkflowListParams = {}) {
  return omitUndefined({
    status: params.status,
  });
}

function normalizeRunListParams(params: RunListParams = {}) {
  return omitUndefined({
    limit: params.limit,
    offset: params.offset ?? 0,
    status: params.status,
    workflowId: params.workflowId,
    workflowKey: normalizeOptionalText(params.workflowKey),
    workflowVersion: params.workflowVersion,
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

const platformQueryKeys = {
  all: [...platformApiRoot] as const,
  agents: {
    all: [...platformApiRoot, "agents"] as const,
    detail: (agentId: IdParam, version?: number | string) =>
      buildVersionedPlatformDetailKey([...platformApiRoot, "agents"] as const, agentId, version),
    list: (params: AgentListParams = {}) =>
      [...platformApiRoot, "agents", "list", normalizeAgentListParams(params)] as const,
  },
  skills: {
    all: [...platformApiRoot, "skills"] as const,
    detail: (skillId: IdParam) =>
      [...platformApiRoot, "skills", "detail", normalizeId(skillId)] as const,
    list: (params: SkillListParams = {}) =>
      [...platformApiRoot, "skills", "list", normalizeSkillListParams(params)] as const,
  },
  mcpServers: {
    all: [...platformApiRoot, "mcpServers"] as const,
    detail: (serverId: IdParam) =>
      [...platformApiRoot, "mcpServers", "detail", normalizeId(serverId)] as const,
    list: (params: McpServerListParams = {}) =>
      [...platformApiRoot, "mcpServers", "list", normalizeMcpServerListParams(params)] as const,
  },
  modelConnections: {
    all: [...platformApiRoot, "modelConnections"] as const,
    detail: (modelConnectionId: IdParam) =>
      [...platformApiRoot, "modelConnections", "detail", normalizeId(modelConnectionId)] as const,
    list: (params: ModelConnectionListParams = {}) =>
      [...platformApiRoot, "modelConnections", "list", normalizeModelConnectionListParams(params)] as const,
  },
  outputSchemas: {
    all: [...platformApiRoot, "outputSchemas"] as const,
    detail: (schemaId: IdParam) =>
      [...platformApiRoot, "outputSchemas", "detail", normalizeId(schemaId)] as const,
    list: (params: OutputSchemaListParams = {}) =>
      [...platformApiRoot, "outputSchemas", "list", normalizeOutputSchemaListParams(params)] as const,
  },
  workflows: {
    all: [...platformApiRoot, "workflows"] as const,
    detail: (workflowId: IdParam, version?: number | string) =>
      buildVersionedPlatformDetailKey(
        [...platformApiRoot, "workflows"] as const,
        workflowId,
        version,
      ),
    list: (params: WorkflowListParams = {}) =>
      [...platformApiRoot, "workflows", "list", normalizeWorkflowListParams(params)] as const,
  },
  runs: {
    all: [...platformApiRoot, "runs"] as const,
    detail: (runId: IdParam) =>
      [...platformApiRoot, "runs", "detail", normalizeId(runId)] as const,
    list: (params: RunListParams = {}) =>
      [...platformApiRoot, "runs", "list", normalizeRunListParams(params)] as const,
  },
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
