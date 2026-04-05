import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { PortfolioTradesSection } from "./portfolio-trades-section";

describe("PortfolioTradesSection", () => {
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

  it("allows recording the first buy before the portfolio has positions", async () => {
    render(
      <PortfolioTradesSection
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
        hasPositions={false}
        operations={[]}
        portfolioId={1}
        positions={[]}
      />,
    );

    const addButton = screen.getByRole("button", { name: /add operation/i });
    expect(addButton).toBeEnabled();

    fireEvent.click(addButton);

    fireEvent.change(await screen.findByLabelText("Symbol"), { target: { value: "tsla" } });
    fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "120" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Operation" }).closest("form")!);

    await waitFor(() =>
      expect(mutateMock).toHaveBeenCalledWith(
        expect.objectContaining({ symbol: "TSLA" }),
        expect.any(Object),
      ),
    );
  });
});
