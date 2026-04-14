import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BacktestListPage } from "./list";

const navigateMock = vi.fn();
const deleteMutateMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-backtests", () => ({
  useBacktests: () => ({
    data: [
      {
        id: 4,
        name: "Completed Backtest",
        portfolioName: "Core Portfolio",
        status: "COMPLETED",
        frequency: "MONTHLY",
        startDate: "2024-01-02",
        endDate: "2024-03-29",
        totalCycles: 3,
        completedCycles: 3,
        currentCycleStatus: null,
        benchmarkSymbols: ["^GSPC"],
        results: {
          portfolio: { totalReturn: "0.1845" },
          benchmarks: { "^GSPC": { totalReturn: "0.2332" } },
        },
      },
      {
        id: 3,
        name: "Runtime Approval Backtest",
        portfolioName: "Growth Portfolio",
        status: "RUNNING",
        frequency: "DAILY",
        startDate: "2024-01-02",
        endDate: "2024-03-29",
        totalCycles: 20,
        completedCycles: 5,
        currentCycleStatus: "WAITING_APPROVAL",
        results: null,
        benchmarkSymbols: ["^GSPC"],
      },
      {
        id: 2,
        name: "Legacy Callback Backtest",
        portfolioName: "Compatibility Portfolio",
        status: "AWAITING_CALLBACK",
        frequency: "WEEKLY",
        startDate: "2024-01-02",
        endDate: "2024-03-29",
        totalCycles: 12,
        completedCycles: 6,
        currentCycleStatus: "AWAITING_CALLBACK",
        results: null,
        benchmarkSymbols: ["^GSPC"],
      },
      {
        id: 1,
        name: "Failed Backtest",
        portfolioName: "Income Portfolio",
        status: "FAILED",
        frequency: "WEEKLY",
        startDate: "2024-01-02",
        endDate: "2024-03-29",
        totalCycles: 10,
        completedCycles: 4,
        currentCycleStatus: null,
        errorMessage: "Model provider unavailable",
        results: null,
        benchmarkSymbols: ["^GSPC"],
      },
    ],
    isPending: false,
    isError: false,
  }),
  useDeleteBacktest: () => ({
    isPending: false,
    mutate: deleteMutateMock,
  }),
}));

describe("BacktestListPage", () => {
  it("renders mixed-mode backtests with runtime approval, callback compatibility, completed summary, and failed error state", async () => {
    render(<BacktestListPage />);

    expect(screen.getByText(/internal runtime and retained legacy callback compatibility flow/i)).toBeInTheDocument();
    expect(screen.getByText(/completed backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/runtime approval backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/legacy callback backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/failed backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/core portfolio/i)).toBeInTheDocument();
    expect(screen.getByText(/waiting approval/i)).toBeInTheDocument();
    expect(screen.getByText(/waiting for runtime approval before the current cycle can continue/i)).toBeInTheDocument();
    expect(screen.getAllByText(/legacy callback/i)).not.toHaveLength(0);
    expect(screen.getByText(/awaiting callback/i)).toBeInTheDocument();
    expect(screen.getByText(/waiting for the legacy callback response before this cycle can continue/i)).toBeInTheDocument();
    expect(screen.getByText(/5 \/ 20 cycles/i)).toBeInTheDocument();
    expect(screen.getByText(/total return 18.45% vs \^GSPC 23.32%/i)).toBeInTheDocument();
    expect(screen.getByText(/model provider unavailable/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /open/i })).toHaveLength(4);
  });
});
