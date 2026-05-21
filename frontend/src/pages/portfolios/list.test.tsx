import type { ComponentProps } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioListPage } from "./list";

const {
  createPortfolioMock,
  deletePortfolioMock,
  navigateMock,
  toastErrorMock,
  toastSuccessMock,
  updatePortfolioMock,
  usePortfoliosMock,
} = vi.hoisted(() => ({
  createPortfolioMock: vi.fn(),
  deletePortfolioMock: vi.fn(),
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
  useCreatePortfolio: () => ({ isPending: false, mutateAsync: createPortfolioMock }),
  useDeletePortfolio: () => ({ isPending: false, mutate: deletePortfolioMock }),
  usePortfolios: () => usePortfoliosMock(),
  useUpdatePortfolio: () => ({ isPending: false, mutate: updatePortfolioMock }),
}));

describe("PortfolioListPage", () => {
  beforeEach(() => {
    createPortfolioMock.mockReset();
    deletePortfolioMock.mockReset();
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

  it("renders the empty state with compact typography and preserved page actions", () => {
    render(<PortfolioListPage />);

    const emptyState = screen.getByText("No portfolios yet.");
    expect(emptyState).toBeVisible();
    expect(emptyState).toHaveClass(
      "py-8",
      "text-center",
      "text-xs",
      "text-muted-foreground",
    );
    expect(emptyState).not.toHaveClass("text-sm");
    expect(screen.queryByText("Loading portfolios...")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Search portfolios")).toBeVisible();
    expect(screen.getByRole("button", { name: /new portfolio/i })).toBeVisible();
  });

  it("renders a filtered-empty state while preserving the full empty-state copy", () => {
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

    expect(screen.getByText("No portfolios match your search.")).toBeVisible();
    expect(screen.queryByText("No portfolios yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Growth Fund")).not.toBeInTheDocument();
  });

  it("renders portfolio card navigation as links and keeps menu actions isolated", () => {
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

    const primaryLink = screen.getByRole("link", { name: "Open portfolio Growth Fund" });
    const card = primaryLink.closest("[data-slot='card']");
    expect(primaryLink).toHaveAttribute("href", "/portfolios/42");
    expect(card).not.toBeNull();

    const visibleOpen = within(card as HTMLElement).getByRole("link", { name: "Open" });
    expect(visibleOpen).toHaveAttribute("href", "/portfolios/42");
    expect(within(card as HTMLElement).queryByRole("button", { name: "Open" })).not.toBeInTheDocument();

    const menuButton = within(card as HTMLElement).getByRole("button", {
      name: "Open actions for Growth Fund",
    });
    fireEvent.click(menuButton);

    expect(menuButton.closest("a")).toBeNull();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
