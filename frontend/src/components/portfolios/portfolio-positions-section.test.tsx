import type { ComponentProps, PropsWithChildren } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const createPositionMutateMock = vi.fn();
const deletePositionMutateMock = vi.fn();
const updatePositionMutateMock = vi.fn();
const createTradingOperationMutateMock = vi.fn();

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-positions", () => ({
  useCreatePosition: () => ({
    isPending: false,
    mutate: createPositionMutateMock,
  }),
  useDeletePosition: () => ({
    isPending: false,
    mutate: deletePositionMutateMock,
  }),
  useUpdatePosition: () => ({
    isPending: false,
    mutate: updatePositionMutateMock,
  }),
}));

vi.mock("@/hooks/use-trading-operations", () => ({
  useCreateTradingOperation: () => ({
    isPending: false,
    mutate: createTradingOperationMutateMock,
  }),
}));

vi.mock("./position-form-dialog", () => ({
  PositionFormDialog: () => null,
}));

vi.mock("./confirm-delete-dialog", () => ({
  ConfirmDeleteDialog: () => null,
}));

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: PropsWithChildren) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onSelect, ...props }: PropsWithChildren<{ onSelect?: () => void } & Omit<ComponentProps<"button">, "onSelect">>) => (
    <button {...props} type="button" onClick={() => onSelect?.()}>
      {children}
    </button>
  ),
  DropdownMenuTrigger: ({ children }: PropsWithChildren) => <div>{children}</div>,
}));

import { PortfolioPositionsSection } from "./portfolio-positions-section";

describe("PortfolioPositionsSection", () => {
  beforeEach(() => {
    createPositionMutateMock.mockReset();
    deletePositionMutateMock.mockReset();
    updatePositionMutateMock.mockReset();
    createTradingOperationMutateMock.mockReset();

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

  it("keeps a second-page symbol available in Record Trading Operation options", async () => {
    const positions = [
      ["AAPL", "Apple Inc."],
      ["ADBE", "Adobe Inc."],
      ["AMZN", "Amazon.com, Inc."],
      ["ASML", "ASML Holding N.V."],
      ["AVGO", "Broadcom Inc."],
      ["COST", "Costco Wholesale Corporation"],
      ["GOOGL", "Alphabet Inc."],
      ["META", "Meta Platforms, Inc."],
      ["MSFT", "Microsoft Corporation"],
      ["NFLX", "Netflix, Inc."],
      ["NVDA", "NVIDIA Corporation"],
    ].map(([symbol, name], index) => ({
      averageCost: "100.00",
      createdAt: "2026-03-15T10:00:00Z",
      currency: "USD",
      id: index + 1,
      name,
      portfolioId: 1,
      quantity: "10",
      symbol,
      updatedAt: "2026-03-15T10:00:00Z",
    }));

    render(
      <PortfolioPositionsSection
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
        portfolioId={1}
        positions={positions}
        quoteWarnings={[]}
      />,
    );

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.queryByText("NVDA")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /record trading operation/i }));

    const symbolInput = await screen.findByLabelText("Symbol");
    expect(symbolInput).toHaveValue("NVDA");

    fireEvent.focus(symbolInput);

    expect(screen.getByText("AAPL (Apple Inc.)")).toBeInTheDocument();
    expect(screen.getByText("NVDA (NVIDIA Corporation)")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "120" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Operation" }).closest("form")!);

    await waitFor(() =>
      expect(createTradingOperationMutateMock).toHaveBeenCalledWith(
        expect.objectContaining({ symbol: "NVDA" }),
        expect.any(Object),
      ),
    );
  });

  it("shows a placeholder percent when unrealized percent cannot be computed", () => {
    render(
      <PortfolioPositionsSection
        balances={[]}
        portfolioId={1}
        positions={[
          {
            averageCost: "0",
            createdAt: "2026-03-15T10:00:00Z",
            currency: "USD",
            currentPrice: "175",
            id: 1,
            name: "Apple Inc.",
            portfolioId: 1,
            quantity: "10",
            symbol: "AAPL",
            updatedAt: "2026-03-15T10:00:00Z",
          },
        ]}
        quoteWarnings={[]}
      />,
    );

    const positionRow = screen.getByText("AAPL").closest("tr");
    expect(positionRow).not.toBeNull();
    expect(positionRow).toHaveTextContent("--");
    expect(positionRow).not.toHaveTextContent("0.00%");
  });
});
