import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioDetailPage } from "./detail";

const {
  deletePortfolioMock,
  navigateMock,
  portfolioPositionsSectionMock,
  updatePortfolioMock,
  useBalancesMock,
  useMarketQuotesMock,
  usePortfolioMock,
  usePositionsMock,
  useTradingOperationsMock,
} = vi.hoisted(() => ({
  deletePortfolioMock: vi.fn(),
  navigateMock: vi.fn(),
  portfolioPositionsSectionMock: vi.fn(),
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
  PortfolioPositionsSection: (props: { quoteWarnings: string[] }) => {
    portfolioPositionsSectionMock(props);
    return <section>Positions workspace</section>;
  },
}));

vi.mock("@/components/portfolios/portfolio-trades-section", () => ({
  PortfolioTradesSection: () => <section>Trades workspace</section>,
}));

vi.mock("@/components/forms/portfolio-form-dialog", () => ({
  PortfolioFormDialog: ({ open }: { open: boolean }) =>
    open ? <div role="dialog">Portfolio edit form</div> : null,
}));
vi.mock("@/components/shared/confirm-delete-dialog", () => ({
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
    portfolioPositionsSectionMock.mockReset();
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
    expect(contextBar).toHaveClass("border-b", "border-border", "pb-3");
    expect(contextBar).not.toHaveClass("rounded-xl", "bg-card/95");
    expect(identity).toHaveClass("min-w-0", "break-words", "text-sm");
    expect(identity).toHaveTextContent(/Long-term allocation/);
    expect(within(header).queryByText("Base currency")).not.toBeInTheDocument();
    expect(within(header).getByText("Portfolio ID")).toBeVisible();
    expect(within(header).getByText("#42")).toBeVisible();
    expect(within(header).getByText("Last updated")).toBeVisible();

    const statusList = within(header).getByRole("list", {
      name: "Portfolio resource status",
    });
    expect(within(statusList).getAllByRole("listitem")).toHaveLength(3);
    expect(within(statusList).getByText("Positions")).toBeVisible();
    expect(within(statusList).getByText("Balances")).toBeVisible();
    expect(within(statusList).getByText("Trades")).toBeVisible();
    expect(within(statusList).queryByText("Quotes")).not.toBeInTheDocument();
    expect(within(statusList).queryByText("Ready")).not.toBeInTheDocument();
    expect(screen.queryByTestId("portfolio-detail-quote-warnings")).not.toBeInTheDocument();

    const metrics = screen.getByLabelText("Portfolio metrics");
    expect(metrics).toHaveClass(
      "grid",
      "min-w-0",
      "gap-3",
      "sm:grid-cols-2",
      "xl:grid-cols-4",
    );
    expect(metrics).not.toHaveClass("border-y", "divide-border");
    expect(metrics.querySelectorAll('[data-slot="card"]')).toHaveLength(4);
    expect(within(metrics).getByText("Total Value")).toBeVisible();
    expect(within(metrics).getByText("Cash Balances")).toBeVisible();
    expect(within(metrics).getByText("Unrealized P&L")).toBeVisible();
    expect(within(metrics).getByText("Latest Activity")).toBeVisible();
    expect(within(metrics).getAllByText("$0.00")).toHaveLength(3);
    expect(within(metrics).getByText("None")).toBeVisible();
    expect(
      within(metrics).getByText("Balances plus marked positions"),
    ).toBeVisible();
    expect(within(metrics).getByText("0 balance accounts")).toBeVisible();
    expect(within(metrics).getByText("0 tracked positions")).toBeVisible();
    expect(within(metrics).getByText("No operations yet")).toBeVisible();

    const tabs = screen.getByTestId("portfolio-detail-tabs");
    expect(within(tabs).getByRole("tab", { name: "Positions" })).toBeVisible();
    expect(within(tabs).getByRole("tab", { name: "Balances" })).toBeVisible();
    expect(within(tabs).getByRole("tab", { name: "Trades" })).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Portfolio sections" }),
    ).toBeVisible();
  });

  it("renders quote warnings as an inline banner while preserving positions section props", () => {
    const quoteWarnings = [
      "AAPL quote is delayed by 15 minutes.",
      "MSFT quote unavailable; using last cached mark.",
    ];
    useMarketQuotesMock.mockReturnValue(
      queryResult({ quotes: [], warnings: quoteWarnings }),
    );

    render(<PortfolioDetailPage />);

    const banner = screen.getByTestId("portfolio-detail-quote-warnings");
    expect(banner).toBeVisible();
    expect(within(banner).getByText("Quote warnings")).toBeVisible();
    for (const warning of quoteWarnings) {
      expect(within(banner).getByText(warning)).toBeVisible();
    }

    expect(portfolioPositionsSectionMock).toHaveBeenCalled();
    const [positionsProps] = portfolioPositionsSectionMock.mock.calls[0];
    expect(positionsProps.quoteWarnings).toBe(quoteWarnings);
  });
});
