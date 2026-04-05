import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TradingOperationForm } from "./trading-operation-form";

describe("TradingOperationForm", () => {
  it("shows current portfolio symbols as suggestions and still submits a new symbol", async () => {
    const onSave = vi.fn();

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

    render(
      <TradingOperationForm
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
        isPending={false}
        onCancel={() => {}}
        onSave={onSave}
        symbolOptions={[
          { label: "AAPL (Apple Inc.)", symbol: "AAPL" },
          { label: "NVDA (NVIDIA Corporation)", symbol: "NVDA" },
        ]}
      />,
    );

    const symbolInput = screen.getByLabelText("Symbol");
    expect(symbolInput).toHaveValue("NVDA");
    expect(screen.getByRole("combobox", { name: "Balance" })).toHaveTextContent("Brokerage Cash · $1,000.00");
    expect(screen.getByText("Available in selected balance: $1,000.00")).toBeInTheDocument();

    fireEvent.focus(symbolInput);

    expect(screen.getByText("AAPL (Apple Inc.)")).toBeInTheDocument();
    expect(screen.getByText("NVDA (NVIDIA Corporation)")).toBeInTheDocument();

    fireEvent.change(symbolInput, { target: { value: "tsla" } });

    await waitFor(() => expect(symbolInput).toHaveValue("TSLA"));

    fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "120" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Operation" }).closest("form")!);

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        balanceId: 1,
        commission: undefined,
        executedAt: expect.any(String),
        price: "120",
        quantity: "5",
        side: "BUY",
        symbol: "TSLA",
      }),
    );
  });

  it("supports keyboard selection and closes the suggestion menu on escape and blur", async () => {
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

    render(
      <TradingOperationForm
        balances={[]}
        initialSymbol="NVDA"
        isPending={false}
        onCancel={() => {}}
        onSave={vi.fn()}
        symbolOptions={[
          { label: "AAPL (Apple Inc.)", symbol: "AAPL" },
          { label: "NVDA (NVIDIA Corporation)", symbol: "NVDA" },
        ]}
      />,
    );

    const symbolInput = screen.getByLabelText("Symbol");

    fireEvent.focus(symbolInput);
    fireEvent.keyDown(symbolInput, { key: "ArrowDown" });

    const aaplOption = screen.getByRole("button", { name: "AAPL (Apple Inc.)" });
    expect(aaplOption).toHaveFocus();

    fireEvent.keyDown(aaplOption, { key: "Escape" });

    await waitFor(() => expect(symbolInput).toHaveFocus());
    expect(screen.queryByRole("button", { name: "AAPL (Apple Inc.)" })).not.toBeInTheDocument();

    fireEvent.keyDown(symbolInput, { key: "ArrowDown" });

    fireEvent.click(screen.getByRole("button", { name: "AAPL (Apple Inc.)" }));

    await waitFor(() => expect(symbolInput).toHaveValue("AAPL"));
    expect(screen.queryByRole("button", { name: "AAPL (Apple Inc.)" })).not.toBeInTheDocument();

    fireEvent.focus(symbolInput);
    expect(screen.getByRole("button", { name: "AAPL (Apple Inc.)" })).toBeInTheDocument();

    fireEvent.blur(symbolInput, { relatedTarget: null });

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "AAPL (Apple Inc.)" })).not.toBeInTheDocument(),
    );
  });
});
