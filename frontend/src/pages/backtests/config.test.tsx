import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BacktestConfigPage } from "./config";

const navigateMock = vi.fn();
const createBacktestMock = vi.fn();
const createPortfolioMock = vi.fn();
const createBalanceMock = vi.fn();
const portfoliosData = [
  {
    id: 1,
    name: "Core Portfolio",
    slug: "core_portfolio",
    description: null,
    baseCurrency: "USD",
    positionCount: 0,
    balanceCount: 1,
    createdAt: "2026-03-20T10:00:00Z",
    updatedAt: "2026-03-20T10:00:00Z",
  },
];

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
  useCreateBacktest: () => ({
    isPending: false,
    mutateAsync: createBacktestMock,
  }),
}));

vi.mock("@/hooks/use-portfolios", () => ({
  usePortfolios: () => ({
    data: portfoliosData,
    isPending: false,
  }),
  useCreatePortfolio: () => ({
    isPending: false,
    mutateAsync: createPortfolioMock,
  }),
}));

vi.mock("@/hooks/use-templates", () => ({
  useTemplates: () => ({
    data: [{ id: 8, name: "Backtest Template", content: "# Template" }],
    isPending: false,
  }),
}));

vi.mock("@/lib/api/balances", () => ({
  createBalance: (...args: unknown[]) => createBalanceMock(...args),
}));

describe("BacktestConfigPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    createBacktestMock.mockReset();
    createPortfolioMock.mockReset();
    createBalanceMock.mockReset();
    portfoliosData.splice(0, portfoliosData.length, {
      id: 1,
      name: "Core Portfolio",
      slug: "core_portfolio",
      description: null,
      baseCurrency: "USD",
      positionCount: 0,
      balanceCount: 1,
      createdAt: "2026-03-20T10:00:00Z",
      updatedAt: "2026-03-20T10:00:00Z",
    });
  });

  it("blocks submit when the validation summary is incomplete", async () => {
    render(<BacktestConfigPage />);

    fireEvent.click(screen.getByRole("button", { name: /launch backtest/i }));

    expect(
      await screen.findByText(/select a template or create a default one/i),
    ).toBeInTheDocument();
    expect(createBacktestMock).not.toHaveBeenCalled();
  });

  it("creates a portfolio and deposit balance before launching a backtest", async () => {
    createPortfolioMock.mockResolvedValue({
      id: 12,
      name: "Sandbox",
      slug: "sandbox",
      description: null,
      baseCurrency: "USD",
      positionCount: 0,
      balanceCount: 0,
      createdAt: "2026-03-20T10:00:00Z",
      updatedAt: "2026-03-20T10:00:00Z",
    });
    createBalanceMock.mockResolvedValue({
      id: 55,
      portfolioId: 12,
      label: "Initial Cash",
      amount: "25000.00",
      currency: "USD",
      operationType: "DEPOSIT",
      hasTradingOperations: false,
      createdAt: "2026-03-20T10:01:00Z",
      updatedAt: "2026-03-20T10:01:00Z",
    });
    createBacktestMock.mockResolvedValue({ id: 99, name: "Sandbox Backtest" });

    render(<BacktestConfigPage />);

    fireEvent.click(screen.getByLabelText(/create new/i));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Sandbox" } });
    fireEvent.change(screen.getByLabelText(/^slug$/i), { target: { value: "sandbox" } });
    fireEvent.change(screen.getByLabelText(/initial cash/i), { target: { value: "25000" } });
    fireEvent.change(screen.getByLabelText(/backtest name/i), {
      target: { value: "Sandbox Backtest" },
    });
    fireEvent.change(screen.getByLabelText(/start date/i), {
      target: { value: "2024-01-02" },
    });
    fireEvent.change(screen.getByLabelText(/end date/i), {
      target: { value: "2024-12-31" },
    });
    fireEvent.change(screen.getByLabelText(/client endpoint url/i), {
      target: { value: "http://localhost:5678/webhook/backtest" },
    });
    fireEvent.click(screen.getByLabelText(/s&p 500/i));
    fireEvent.click(screen.getByLabelText(/create default template/i));
    fireEvent.click(screen.getByRole("button", { name: /launch backtest/i }));

    await waitFor(() => expect(createPortfolioMock).toHaveBeenCalled());
    expect(createBalanceMock).toHaveBeenCalledWith(12, {
      amount: "25000",
      label: "Initial Cash",
      operationType: "DEPOSIT",
    });
    expect(createBacktestMock).toHaveBeenCalledWith(
      expect.objectContaining({ portfolioId: 12 }),
    );
  });

  it("blocks existing portfolios that have no balances and no positions", async () => {
    portfoliosData.splice(0, portfoliosData.length, {
      id: 1,
      name: "Empty Portfolio",
      slug: "empty_portfolio",
      description: null,
      baseCurrency: "USD",
      positionCount: 0,
      balanceCount: 0,
      createdAt: "2026-03-20T10:00:00Z",
      updatedAt: "2026-03-20T10:00:00Z",
    });

    render(<BacktestConfigPage />);

    fireEvent.change(screen.getByLabelText(/backtest name/i), {
      target: { value: "Empty Portfolio Backtest" },
    });
    fireEvent.change(screen.getByLabelText(/portfolio/i), { target: { value: "1" } });
    fireEvent.click(screen.getByLabelText(/create default template/i));
    fireEvent.change(screen.getByLabelText(/start date/i), {
      target: { value: "2024-01-02" },
    });
    fireEvent.change(screen.getByLabelText(/end date/i), {
      target: { value: "2024-03-29" },
    });
    fireEvent.change(screen.getByLabelText(/client endpoint url/i), {
      target: { value: "http://localhost:5678/webhook/backtest" },
    });
    fireEvent.click(screen.getByLabelText(/s&p 500/i));
    fireEvent.click(screen.getByRole("button", { name: /launch backtest/i }));

    expect(
      await screen.findByText(/selected portfolio must have at least one balance or position/i),
    ).toBeInTheDocument();
    expect(createBacktestMock).not.toHaveBeenCalled();
  });
});
