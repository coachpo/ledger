import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const usePositionSymbolLookupMock = vi.fn();

vi.mock("@/hooks/use-debounce", () => ({
  useDebounce: (value: string) => value,
}));

vi.mock("@/hooks/use-positions", () => ({
  usePositionSymbolLookup: (...args: unknown[]) => usePositionSymbolLookupMock(...args),
}));

import { PositionFormDialog } from "./position-form-dialog";

describe("PositionFormDialog", () => {
  beforeEach(() => {
    usePositionSymbolLookupMock.mockReset();
    usePositionSymbolLookupMock.mockImplementation((_portfolioId: unknown, symbol: string | undefined) => ({
      data: symbol === "AAPL" ? { symbol: "AAPL", name: "Apple Inc." } : { symbol: symbol ?? "", name: null },
      isError: false,
      isFetching: false,
    }));
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

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "aapl" } });

    const nameInput = screen.getByLabelText("Name");
    await waitFor(() => expect(nameInput).toHaveValue("Apple Inc."));
    expect(screen.getByText("Suggested name loaded. You can edit it before saving.")).toBeInTheDocument();

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

    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "unknown" } });

    const nameInput = screen.getByLabelText("Name");
    await waitFor(() => {
      expect(nameInput).toHaveValue("");
      expect(screen.getByText("No company name found. You can enter one manually.")).toBeInTheDocument();
    });

    fireEvent.change(nameInput, { target: { value: "Manual Name" } });
    expect(nameInput).toHaveValue("Manual Name");
  });
});
