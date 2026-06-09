import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioListPage } from "./list";

const {
  createPortfolioMock,
  deletePortfolioMock,
  deletePortfoliosMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  updatePortfolioMock,
  usePortfoliosMock,
} = vi.hoisted(() => ({
  createPortfolioMock: vi.fn(),
  deletePortfolioMock: vi.fn(),
  deletePortfoliosMock: vi.fn(),
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  updatePortfolioMock: vi.fn(),
  usePortfoliosMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => navigateMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

vi.mock("@/hooks/use-portfolios", () => ({
  useCreatePortfolio: () => ({
    isPending: false,
    mutateAsync: createPortfolioMock,
  }),
  useDeletePortfolio: () => ({ isPending: false, mutate: deletePortfolioMock }),
  useDeletePortfolios: () => ({
    isPending: false,
    mutate: deletePortfoliosMock,
  }),
  usePortfolios: () => usePortfoliosMock(),
  useUpdatePortfolio: () => ({ isPending: false, mutate: updatePortfolioMock }),
}));

describe("PortfolioListPage", () => {
  beforeEach(() => {
    createPortfolioMock.mockReset();
    deletePortfolioMock.mockReset();
    deletePortfoliosMock.mockReset();
    navigateMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
    updatePortfolioMock.mockReset();
    usePortfoliosMock.mockReset();
    usePortfoliosMock.mockReturnValue({
      data: [],
      error: null,
      isError: false,
      isPending: false,
    });
  });

  it("renders the inline empty state inside the inventory hierarchy with preserved page actions", () => {
    render(<PortfolioListPage />);

    const shellRegions = Array.from(
      screen
        .getByTestId("portfolios-list-page")
        .querySelectorAll("[data-inventory-shell-region]"),
    ).map((region) => region.getAttribute("data-inventory-shell-region"));
    expect(shellRegions).toEqual(["context", "toolbar", "content"]);
    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();

    const inventory = screen.getByRole("region", {
      name: "Portfolio inventory",
    });
    const emptyState = within(inventory).getByText("No portfolios yet.");
    expect(emptyState).toBeVisible();
    expect(within(inventory).getByTestId("portfolios-empty-state")).toHaveTextContent(
      "No portfolios yet.",
    );
    expect(emptyState.closest("[data-slot='card']")).toHaveClass(
      "border-dashed",
    );
    expect(screen.queryByText("Loading portfolios...")).not.toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Search portfolios" }),
    ).toHaveClass("h-8", "pl-8", "text-xs");
    expect(screen.getByText("0 of 0 portfolios shown")).toBeVisible();
    expect(
      within(inventory).getByRole("button", { name: /new portfolio/i }),
    ).toBeVisible();
    expect(
      screen.getAllByRole("button", { name: /new portfolio/i }),
    ).toHaveLength(2);
  });

  it("renders a filtered-empty state inside the inventory region with filter controls", () => {
    usePortfoliosMock.mockReturnValue({
      data: [
        {
          balanceCount: 2,
          baseCurrency: "USD",
          description: "Long-term allocation",
          id: 42,
          name: "Growth Fund",
          positionCount: 3,
          updatedAt: "2026-04-20T10:00:00Z",
        },
      ],
      error: null,
      isError: false,
      isPending: false,
    });

    render(<PortfolioListPage />);

    fireEvent.change(screen.getByLabelText("Search portfolios"), {
      target: { value: "missing" },
    });

    const inventory = screen.getByRole("region", {
      name: "Portfolio inventory",
    });
    expect(
      within(inventory).getByText("No portfolios match your search."),
    ).toBeVisible();
    expect(within(inventory).getByTestId("portfolios-filtered-empty-state")).toHaveTextContent(
      "No portfolios match your search.",
    );
    expect(screen.getByTestId("portfolios-active-filters")).toHaveTextContent(
      "missing",
    );
    expect(screen.queryByText("No portfolios yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Growth Fund")).not.toBeInTheDocument();

    fireEvent.click(
      within(inventory).getByRole("button", { name: "Clear search" }),
    );

    expect(
      screen.queryByTestId("portfolios-active-filters"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Growth Fund")).toBeVisible();
  });

  it("renders portfolio table navigation as links and keeps row actions isolated", () => {
    usePortfoliosMock.mockReturnValue({
      data: [
        {
          balanceCount: 2,
          baseCurrency: "USD",
          description: "Long-term allocation",
          id: 42,
          name: "Growth Fund",
          positionCount: 3,
          updatedAt: "2026-04-20T10:00:00Z",
        },
      ],
      error: null,
      isError: false,
      isPending: false,
    });

    render(<PortfolioListPage />);

    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();
    const inventory = screen.getByRole("region", {
      name: "Portfolio inventory",
    });
    const table = within(inventory).getByRole("table");
    expect(table.parentElement?.parentElement).toHaveClass(
      "min-w-0",
      "max-w-full",
      "rounded-md",
      "border",
    );
    expect(
      within(table).getByRole("checkbox", { name: /select portfolio growth fund/i }),
    ).toBeVisible();

    const visibleOpen = within(table).getByRole("link", {
      name: "Open portfolio Growth Fund",
    });
    expect(visibleOpen).toHaveAttribute("href", "/portfolios/42");
    expect(within(table).queryByRole("button", { name: "Open" })).not.toBeInTheDocument();

    const editButton = within(table).getByRole("button", {
      name: "Edit portfolio Growth Fund",
    });
    fireEvent.click(editButton);

    expect(editButton.closest("a")).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("supports table-only portfolio selection, scoped bulk delete, and clear", () => {
    usePortfoliosMock.mockReturnValue({
      data: [
        {
          balanceCount: 2,
          baseCurrency: "USD",
          description: "Long-term allocation",
          id: 42,
          name: "Growth Fund",
          positionCount: 3,
          updatedAt: "2026-04-20T10:00:00Z",
        },
        {
          balanceCount: 1,
          baseCurrency: "EUR",
          description: "Income allocation",
          id: 84,
          name: "Income Fund",
          positionCount: 2,
          updatedAt: "2026-04-21T10:00:00Z",
        },
      ],
      error: null,
      isError: false,
      isPending: false,
    });

    render(<PortfolioListPage />);

    const inventory = screen.getByRole("region", {
      name: "Portfolio inventory",
    });
    expect(
      within(inventory).getByRole("table").parentElement?.parentElement,
    ).toHaveClass("min-w-0", "max-w-full", "rounded-md", "border");
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select all shown portfolios/i }),
    );

    expect(
      within(screen.getByTestId("portfolios-bulk-actions")).getByText(
        "2 of 2 portfolios selected",
      ),
    ).toBeVisible();

    fireEvent.change(screen.getByLabelText("Search portfolios"), {
      target: { value: "Income" },
    });

    const bulkActions = screen.getByTestId("portfolios-bulk-actions");
    expect(
      within(bulkActions).getByText("1 of 1 portfolios selected"),
    ).toBeVisible();
    fireEvent.click(
      within(bulkActions).getByRole("button", { name: /delete selected/i }),
    );

    expect(deletePortfoliosMock).toHaveBeenCalledWith([84], expect.any(Object));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    fireEvent.click(within(bulkActions).getByRole("button", { name: "Clear" }));
    expect(
      screen.queryByTestId("portfolios-bulk-actions"),
    ).not.toBeInTheDocument();
  });

  it("keeps portfolio selection clearable in table-only view", () => {
    usePortfoliosMock.mockReturnValue({
      data: [
        {
          balanceCount: 2,
          baseCurrency: "USD",
          description: "Long-term allocation",
          id: 42,
          name: "Growth Fund",
          positionCount: 3,
          updatedAt: "2026-04-20T10:00:00Z",
        },
      ],
      error: null,
      isError: false,
      isPending: false,
    });

    render(<PortfolioListPage />);

    expect(screen.queryByRole("radio", { name: /cards view/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /table view/i })).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /select portfolio growth fund/i }),
    );
    expect(screen.getByTestId("portfolios-bulk-actions")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(
      screen.getByRole("checkbox", { name: /select portfolio growth fund/i }),
    ).toHaveAttribute("aria-checked", "false");
  });
});
