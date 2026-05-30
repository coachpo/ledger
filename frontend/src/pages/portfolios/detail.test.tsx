import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioDetailPage } from "./detail";

const {
  deletePortfolioMock,
  navigateMock,
  updatePortfolioMock,
  useBalancesMock,
  useMarketQuotesMock,
  usePortfolioMock,
  usePositionsMock,
  useTradingOperationsMock,
} = vi.hoisted(() => ({
  deletePortfolioMock: vi.fn(),
  navigateMock: vi.fn(),
  updatePortfolioMock: vi.fn(),
  useBalancesMock: vi.fn(),
  useMarketQuotesMock: vi.fn(),
  usePortfolioMock: vi.fn(),
  usePositionsMock: vi.fn(),
  useTradingOperationsMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => ({ portfolioId: "42" }),
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-portfolios", () => ({
  useDeletePortfolio: () => ({ isPending: false, mutate: deletePortfolioMock }),
  usePortfolio: () => usePortfolioMock(),
  useUpdatePortfolio: () => ({ isPending: false, mutate: updatePortfolioMock }),
}));

vi.mock("@/hooks/use-balances", () => ({
  useBalances: () => useBalancesMock(),
}));

vi.mock("@/hooks/use-market-data", () => ({
  useMarketQuotes: () => useMarketQuotesMock(),
}));

vi.mock("@/hooks/use-positions", () => ({
  usePositions: () => usePositionsMock(),
}));

vi.mock("@/hooks/use-trading-operations", () => ({
  useTradingOperations: () => useTradingOperationsMock(),
}));

vi.mock("@/components/portfolios/portfolio-balances-section", () => ({
  PortfolioBalancesSection: () => <section>Balances workspace</section>,
}));

vi.mock("@/components/portfolios/portfolio-positions-section", () => ({
  PortfolioPositionsSection: () => <section>Positions workspace</section>,
}));

vi.mock("@/components/portfolios/portfolio-trades-section", () => ({
  PortfolioTradesSection: () => <section>Trades workspace</section>,
}));

vi.mock("@/components/forms/portfolio-form-dialog", () => ({
  PortfolioFormDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">Portfolio edit form</div> : null,
}));
vi.mock("@/components/portfolios/confirm-delete-dialog", () => ({
  ConfirmDeleteDialog: ({ open, title }: { open: boolean; title: string }) =>
    open ? <div role="alertdialog">{title}</div> : null,
}));

function queryResult<T>(data: T) {
  return {
    data,
    error: null,
    isError: false,
    isPending: false,
  };
}

function buildPortfolio() {
  return {
    id: 42,
    name: "Growth Fund With A Very Long Workspace Name",
    slug: "growth-fund",
    description:
      "Long-term allocation with enough strategy notes to require wrapping on small screens.",
    baseCurrency: "USD",
    positionCount: 0,
    balanceCount: 0,
    createdAt: "2026-04-01T10:00:00Z",
    updatedAt: "2026-04-20T10:00:00Z",
  };
}

describe("PortfolioDetailPage", () => {
  beforeEach(() => {
    deletePortfolioMock.mockReset();
    navigateMock.mockReset();
    updatePortfolioMock.mockReset();
    useBalancesMock.mockReset();
    useMarketQuotesMock.mockReset();
    usePortfolioMock.mockReset();
    usePositionsMock.mockReset();
    useTradingOperationsMock.mockReset();
    usePortfolioMock.mockReturnValue(queryResult(buildPortfolio()));
    useBalancesMock.mockReturnValue(queryResult([]));
    usePositionsMock.mockReturnValue(queryResult([]));
    useTradingOperationsMock.mockReturnValue(queryResult([]));
    useMarketQuotesMock.mockReturnValue(
      queryResult({ quotes: [], warnings: [] }),
    );
  });

  it("renders a named detail identity block with consistent back and action hierarchy", () => {
    render(<PortfolioDetailPage />);

    const heading = screen.getByRole("heading", {
      name: "Growth Fund With A Very Long Workspace Name",
    });
    const title = screen.getByText(
      "Growth Fund With A Very Long Workspace Name",
      {
        selector: "#portfolio-detail-title",
      },
    );
    expect(title).toHaveClass(
      "break-words",
      "text-xl",
      "font-semibold",
      "tracking-tight",
    );
    expect(heading).not.toHaveClass("truncate", "text-lg");

    const backButton = screen.getByRole("button", { name: /portfolios/i });
    fireEvent.click(backButton);
    expect(navigateMock).toHaveBeenCalledWith("/portfolios");

    const actions = screen.getByTestId("portfolio-detail-actions");
    expect(actions).toHaveClass("flex-wrap", "sm:w-auto");
    expect(
      within(actions).getByRole("button", { name: /edit/i }),
    ).toBeVisible();
    expect(
      within(actions).getByRole("button", { name: /delete/i }),
    ).toBeVisible();
  });

  it("keeps detail metadata readable with explicit evidence and tab rhythm", () => {
    render(<PortfolioDetailPage />);

    const header = screen.getByTestId("portfolio-detail-header");
    const contextBar = header.querySelector('[data-slot="page-context-bar"]');
    const identity = screen.getByTestId("portfolio-detail-identity");
    expect(contextBar).toHaveClass("rounded-xl", "border", "bg-card/95");
    expect(identity).toHaveClass("min-w-0");
    expect(within(identity).getByText("Portfolio workspace")).toHaveClass(
      "uppercase",
      "tracking-wide",
    );
    expect(screen.getByText(/Long-term allocation/)).toHaveClass(
      "break-words",
      "text-sm",
    );
    expect(within(header).getByText("Scope")).toBeVisible();
    expect(within(header).getByText("Finance Workspace")).toBeVisible();
    expect(within(header).getByText("Last updated")).toBeVisible();
    expect(within(header).getByText("Quotes")).toBeVisible();
    expect(within(header).getByText("Ready")).toBeVisible();

    const tabs = screen.getByTestId("portfolio-detail-tabs");
    expect(within(tabs).getByRole("tab", { name: "Positions" })).toBeVisible();
    expect(within(tabs).getByRole("tab", { name: "Balances" })).toBeVisible();
    expect(within(tabs).getByRole("tab", { name: "Trades" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Portfolio sections" }),
    ).toBeVisible();
  });
});
