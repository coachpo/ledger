import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BalanceRead } from "@/lib/types/balance";

import { BalanceFormDialog } from "./balance-form-dialog";

function expectSharedDialogShell(dialog: HTMLElement) {
  const body = dialog.querySelector('[data-slot="entity-dialog-body"]');
  const footer = dialog.querySelector('[data-slot="dialog-footer"]');

  expect(
    dialog.querySelector('[data-slot="entity-dialog-constraint-strip"]'),
  ).toBeNull();
  expect(body).toBeTruthy();
  expect(footer).toBeTruthy();
  expect(
    Array.from(
      dialog.querySelectorAll(
        '[data-slot="entity-dialog-body"], [data-slot="dialog-footer"]',
      ),
    ),
  ).toEqual([body, footer]);
}

function makeBalance(overrides: Partial<BalanceRead> = {}): BalanceRead {
  return {
    amount: "2500.00",
    createdAt: "2026-03-15T10:00:00Z",
    currency: "USD",
    hasTradingOperations: false,
    id: 1,
    label: "Brokerage Cash",
    operationType: "DEPOSIT",
    portfolioId: 1,
    updatedAt: "2026-03-15T10:00:00Z",
    ...overrides,
  };
}

describe("BalanceFormDialog", () => {
  it("renders create copy in the shared dialog shell order", () => {
    render(
      <BalanceFormDialog
        open
        initial={undefined}
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Add Balance");
    expect(dialog).toHaveTextContent("Operation Type");
    expect(dialog).toHaveTextContent("Label");
    expect(dialog).toHaveTextContent("Amount");
    expectSharedDialogShell(dialog);
  });

  it("submits a trimmed label and amount with the selected operation type", async () => {
    const onSave = vi.fn();

    render(
      <BalanceFormDialog
        open
        initial={undefined}
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={onSave}
      />,
    );

    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "  Brokerage Cash  " },
    });
    fireEvent.change(screen.getByLabelText("Amount"), {
      target: { value: "  1250.50  " },
    });
    fireEvent.submit(screen.getByLabelText("Label").closest("form")!);

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        amount: "1250.50",
        label: "Brokerage Cash",
        operationType: "DEPOSIT",
      }),
    );
  });

  it("calls onOpenChange(false) from cancel", () => {
    const onOpenChange = vi.fn();

    render(
      <BalanceFormDialog
        open
        initial={undefined}
        isPending={false}
        onOpenChange={onOpenChange}
        onSave={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables controls and actions while pending", () => {
    render(
      <BalanceFormDialog
        open
        initial={undefined}
        isPending
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("combobox", { name: "Operation Type" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Label")).toBeDisabled();
    expect(screen.getByLabelText("Amount")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("locks the operation type when the balance has trading operations", () => {
    render(
      <BalanceFormDialog
        open
        initial={makeBalance({
          hasTradingOperations: true,
          operationType: "WITHDRAWAL",
        })}
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    const operationType = screen.getByRole("combobox", {
      name: "Operation Type",
    });
    expect(operationType).toBeDisabled();
    expect(operationType).toHaveTextContent("WITHDRAWAL");
    expect(
      screen.getByText(
        "Operation type is locked once this balance has trading history.",
      ),
    ).toBeInTheDocument();
  });
});
