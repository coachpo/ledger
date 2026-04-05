import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mutateMock = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-trading-operations", () => ({
  useCreateTradingOperation: () => ({
    isPending: false,
    mutate: mutateMock,
  }),
}));

import { RecordTradingOperationDialog } from "./record-trading-operation-dialog";

describe("RecordTradingOperationDialog", () => {
  beforeEach(() => {
    mutateMock.mockReset();

    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
      configurable: true,
      value: () => false,
    });
    Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, "releasePointerCapture", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("includes symbols beyond the first positions page in the symbol options", async () => {
    const positions = [
      { name: "Adobe Inc.", symbol: "ADBE" },
      { name: "Alphabet Inc.", symbol: "GOOGL" },
      { name: "Amazon.com, Inc.", symbol: "AMZN" },
      { name: "Apple Inc.", symbol: "AAPL" },
      { name: "ASML Holding N.V.", symbol: "ASML" },
      { name: "Broadcom Inc.", symbol: "AVGO" },
      { name: "Costco Wholesale Corporation", symbol: "COST" },
      { name: "Meta Platforms, Inc.", symbol: "META" },
      { name: "Microsoft Corporation", symbol: "MSFT" },
      { name: "Netflix, Inc.", symbol: "NFLX" },
      { name: "NVIDIA Corporation", symbol: "NVDA" },
    ];

    render(
      <RecordTradingOperationDialog
        balances={[
          {
            amount: "1000.00",
            createdAt: "2026-03-15T10:00:00Z",
            currency: "USD",
            hasTradingOperations: false,
            id: 1,
            label: "Brokerage Cash",
            operationType: "DEPOSIT",
            portfolioId: 1,
            updatedAt: "2026-03-15T10:00:00Z",
          },
        ]}
        initialSymbol="NVDA"
        open
        onOpenChange={() => {}}
        portfolioId={1}
        positions={positions}
      />,
    );

    const symbolInput = screen.getByLabelText("Symbol");
    expect(symbolInput).toHaveValue("NVDA");

    fireEvent.focus(symbolInput);

    expect(screen.getByText("AAPL (Apple Inc.)")).toBeInTheDocument();
    expect(screen.getByText("NVDA (NVIDIA Corporation)")).toBeInTheDocument();
  });

  it("defaults to the largest deposit balance in the dialog", () => {
    render(
      <RecordTradingOperationDialog
        balances={[
          {
            amount: "229.00",
            createdAt: "2026-03-15T10:00:00Z",
            currency: "USD",
            hasTradingOperations: true,
            id: 1,
            label: "Primary Cash",
            operationType: "DEPOSIT",
            portfolioId: 1,
            updatedAt: "2026-03-15T10:00:00Z",
          },
          {
            amount: "125.00",
            createdAt: "2026-03-15T10:00:00Z",
            currency: "USD",
            hasTradingOperations: false,
            id: 2,
            label: "Cash Withdrawal",
            operationType: "WITHDRAWAL",
            portfolioId: 1,
            updatedAt: "2026-03-15T10:00:00Z",
          },
          {
            amount: "10271.00",
            createdAt: "2026-03-15T10:00:00Z",
            currency: "USD",
            hasTradingOperations: false,
            id: 3,
            label: "Reserve Cash",
            operationType: "DEPOSIT",
            portfolioId: 1,
            updatedAt: "2026-03-15T10:00:00Z",
          },
        ]}
        open
        onOpenChange={() => {}}
        portfolioId={1}
        positions={[]}
      />,
    );

    expect(screen.getByRole("combobox", { name: "Balance" })).toHaveTextContent("Reserve Cash · $10,271.00");
    expect(screen.getByText("Available in selected balance: $10,271.00")).toBeInTheDocument();
  });
});
