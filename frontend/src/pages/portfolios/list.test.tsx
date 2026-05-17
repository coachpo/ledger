import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
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
    expect(emptyState).toHaveClass("py-8", "text-center", "text-xs", "text-muted-foreground");
    expect(emptyState).not.toHaveClass("text-sm");
    expect(screen.queryByText("Loading portfolios...")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new portfolio/i })).toBeVisible();
  });
});
