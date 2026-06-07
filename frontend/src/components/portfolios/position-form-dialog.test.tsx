import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const usePositionSymbolLookupMock = vi.fn();

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));

vi.mock("@/hooks/use-positions", () => ({
  usePositionSymbolLookup: (...args: unknown[]) =>
    usePositionSymbolLookupMock(...args),
}));

import { PositionFormDialog } from "./position-form-dialog";

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

describe("PositionFormDialog", () => {
  beforeEach(() => {
    usePositionSymbolLookupMock.mockReset();
    usePositionSymbolLookupMock.mockImplementation(
      (_portfolioId: unknown, symbol: string | undefined) => ({
        data:
          symbol === "AAPL"
            ? { symbol: "AAPL", name: "Apple Inc." }
            : { symbol: symbol ?? "", name: null },
        isError: false,
        isFetching: false,
      }),
    );
  });

  it("renders create copy in the shared dialog shell order", () => {
    render(
      <PositionFormDialog
        portfolioId={1}
        open
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Add Position");
    expect(dialog).toHaveTextContent("Symbol");
    expect(dialog).toHaveTextContent("Name");
    expect(dialog).toHaveTextContent("Quantity");
    expect(dialog).toHaveTextContent("Average Cost");
    expectSharedDialogShell(dialog);
  });

  it("auto-fills a resolved name and keeps the field editable", async () => {
    render(
      <PositionFormDialog
        portfolioId={1}
        open
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Symbol"), {
      target: { value: "aapl" },
    });

    const nameInput = screen.getByLabelText("Name");
    await waitFor(() => expect(nameInput).toHaveValue("Apple Inc."));
    expect(screen.getByText("Suggested name loaded.")).toBeInTheDocument();

    fireEvent.change(nameInput, { target: { value: "Apple Custom Name" } });
    expect(nameInput).toHaveValue("Apple Custom Name");
  });

  it("leaves the name empty and editable when lookup cannot resolve a symbol", async () => {
    render(
      <PositionFormDialog
        portfolioId={1}
        open
        isPending={false}
        onOpenChange={vi.fn()}
        onSave={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Symbol"), {
      target: { value: "unknown" },
    });

    const nameInput = screen.getByLabelText("Name");
    await waitFor(() => {
      expect(nameInput).toHaveValue("");
      expect(screen.getByText("No company name found.")).toBeInTheDocument();
    });

    fireEvent.change(nameInput, { target: { value: "Manual Name" } });
    expect(nameInput).toHaveValue("Manual Name");
  });
});
