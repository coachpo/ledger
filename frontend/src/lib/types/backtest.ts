export type BacktestStatus =
  | "PENDING"
  | "RUNNING"
  | "AWAITING_CALLBACK"
  | "PROCESSING_CALLBACK"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type BacktestFrequency = "DAILY" | "WEEKLY" | "MONTHLY";
export type BacktestPriceMode = "CLOSING_PRICE";
export type BacktestCommissionMode = "ZERO" | "FIXED" | "PERCENTAGE";
export type BacktestTradeAction = "BUY" | "SELL" | "HOLD";

export interface BacktestDecisionSummary {
  symbol: string;
  action: BacktestTradeAction;
  reasoning?: string | null;
  quantity?: number | null;
  targetPrice?: string | null;
  executed?: boolean | null;
  failureReason?: string | null;
}

export interface BacktestRecentActivityEntry {
  cycleDate: string;
  decisions: BacktestDecisionSummary[];
}

export interface BacktestCurvePoint {
  date: string;
  value: string;
}

export interface BacktestPortfolioResults {
  startingValue: string;
  endingValue: string;
  totalReturn: string;
  annualizedReturn: string;
  maxDrawdown: string;
  sharpeRatio: string | null;
  totalTrades: number;
  winRate: string;
  totalCommission: string;
}

export interface BacktestBenchmarkResult {
  startingPrice: string;
  endingPrice: string;
  totalReturn: string;
}

export interface BacktestTradeLogEntry {
  cycleDate: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: string | null;
  requestedPrice: string | null;
  executedPrice: string | null;
  executed: boolean;
  reportSlug: string | null;
  failureReason?: string | null;
  commission?: string | null;
  profit?: string | null;
}

export interface BacktestResults {
  portfolio: BacktestPortfolioResults;
  benchmarks: Record<string, BacktestBenchmarkResult>;
  equityCurve: BacktestCurvePoint[];
  benchmarkCurves: Record<string, BacktestCurvePoint[]>;
  drawdownCurve: BacktestCurvePoint[];
  trades: BacktestTradeLogEntry[];
}

export interface BacktestRead {
  id: number;
  portfolioId: number;
  portfolioName: string | null;
  templateId: number;
  depositBalanceId: number;
  name: string;
  status: BacktestStatus;
  frequency: BacktestFrequency;
  startDate: string;
  endDate: string;
  currentCycleDate: string | null;
  totalCycles: number;
  completedCycles: number;
  webhookUrl: string;
  webhookTimeout: number;
  currentCycleStatus: string | null;
  priceMode: BacktestPriceMode;
  commissionMode: BacktestCommissionMode;
  commissionValue: string;
  benchmarkSymbols: string[];
  recentActivity: BacktestRecentActivityEntry[] | null;
  results: BacktestResults | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface BacktestCreateInput {
  name: string;
  portfolioId: number;
  templateId: number | null;
  createTemplate: boolean;
  templateName: string | null;
  frequency: BacktestFrequency;
  startDate: string;
  endDate: string;
  webhookUrl: string;
  webhookTimeout?: number;
  priceMode: BacktestPriceMode;
  commissionMode: BacktestCommissionMode;
  commissionValue: string;
  benchmarkSymbols: string[];
}
