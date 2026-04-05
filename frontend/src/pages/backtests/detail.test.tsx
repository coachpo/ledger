import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BacktestDetailPage } from "./detail";

const paramsMock = { backtestId: "42" };
const cancelMutateMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => vi.fn(),
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

const runningBacktest = {
  id: 42,
  portfolioId: 1,
  portfolioName: "Test Portfolio",
  templateId: 8,
  depositBalanceId: 3,
  name: "Running Backtest",
  status: "RUNNING",
  frequency: "DAILY",
  startDate: "2024-01-02",
  endDate: "2024-12-31",
  currentCycleDate: "2024-06-15",
  totalCycles: 252,
  completedCycles: 115,
  webhookUrl: "http://test.example.com/webhook",
  webhookTimeout: 600,
  currentCycleStatus: null,
  priceMode: "CLOSING_PRICE",
  commissionMode: "ZERO",
  commissionValue: "0",
  benchmarkSymbols: ["^GSPC"],
  recentActivity: [
    {
      cycleDate: "2024-06-15",
      decisions: [{ symbol: "AAPL", action: "HOLD", reasoning: "No material change." }],
    },
  ],
  results: null,
  errorMessage: null,
  createdAt: "2026-03-20T10:00:00Z",
  updatedAt: "2026-03-20T10:35:00Z",
};

const awaitingCallbackBacktest = {
  ...runningBacktest,
  status: "AWAITING_CALLBACK",
  currentCycleStatus: "AWAITING_CALLBACK",
};

const completedBacktest = {
  ...runningBacktest,
  status: "COMPLETED",
  results: {
    portfolio: {
      startingValue: "100000.00",
      endingValue: "118450.00",
      totalReturn: "0.1845",
      annualizedReturn: "0.1845",
      maxDrawdown: "-0.0823",
      sharpeRatio: "1.24",
      totalTrades: 47,
      winRate: "0.617",
      totalCommission: "47.00",
    },
    benchmarks: {
      "^GSPC": {
        startingPrice: "4769.83",
        endingPrice: "5881.63",
        totalReturn: "0.2332",
      },
    },
    equityCurve: [{ date: "2024-01-02", value: "100000.00" }],
    benchmarkCurves: { "^GSPC": [{ date: "2024-01-02", value: "1.0000" }] },
    drawdownCurve: [{ date: "2024-01-02", value: "0.0000" }],
    trades: [
      {
        cycleDate: "2024-01-15",
        symbol: "AAPL",
        side: "BUY",
        quantity: "5",
        requestedPrice: "185.50",
        executedPrice: "184.40",
        executed: true,
        reportSlug: "backtest_42_20240115",
      },
    ],
  },
};

const useBacktestMock = vi.fn();

vi.mock("@/hooks/use-backtests", () => ({
  useBacktest: (...args: unknown[]) => useBacktestMock(...args),
  useCancelBacktest: () => ({ isPending: false, mutate: cancelMutateMock }),
  useDeleteBacktest: () => ({ isPending: false, mutate: vi.fn() }),
}));

describe("BacktestDetailPage", () => {
  beforeEach(() => {
    cancelMutateMock.mockReset();
    useBacktestMock.mockReset();
    vi.spyOn(Date, "now").mockReturnValue(new Date("2026-03-20T10:35:00Z").getTime());
  });

  afterEach(() => vi.restoreAllMocks());

  it("polls while a backtest is running and shows recent activity", async () => {
    useBacktestMock.mockReturnValue({ data: runningBacktest, isLoading: false });

    render(<BacktestDetailPage />);

    expect(await screen.findByText(/current simulation date/i)).toBeInTheDocument();
    expect(screen.getByText(/elapsed time/i)).toBeInTheDocument();
    expect(screen.getByText(/35m/i)).toBeInTheDocument();
    expect(screen.getByText(/AAPL/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeEnabled();
  });

  it("shows generic callback wording while awaiting a client callback", async () => {
    useBacktestMock.mockReturnValue({ data: awaitingCallbackBacktest, isLoading: false });

    render(<BacktestDetailPage />);

    expect(await screen.findByText(/waiting for client callback/i)).toBeInTheDocument();
  });

  it("renders completed backtest summary metrics and trade rows", async () => {
    useBacktestMock.mockReturnValue({ data: completedBacktest, isLoading: false });

    render(<BacktestDetailPage />);

    expect(await screen.findByText(/total return/i)).toBeInTheDocument();
    expect(screen.getByText(/max drawdown/i)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /symbol/i })).toBeInTheDocument();
  });
});
