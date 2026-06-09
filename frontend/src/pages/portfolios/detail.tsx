import { useMemo, useState } from "react";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { useBalances } from "@/hooks/use-balances";
import { useMarketQuotes } from "@/hooks/use-market-data";
import {
  useDeletePortfolio,
  usePortfolio,
  useUpdatePortfolio,
} from "@/hooks/use-portfolios";
import { usePositions } from "@/hooks/use-positions";
import { useTradingOperations } from "@/hooks/use-trading-operations";
import { formatCurrency, formatDateTime } from "@/lib/format";
import {
  computePortfolioTotalValue,
  getSignedBalanceAmount,
  computePositionPnl,
  enrichPositionsWithQuotes,
} from "@/lib/portfolio-analytics";
import type { PortfolioUpdateInput } from "@/lib/types/portfolio";

import { ConsoleSection } from "@/components/shared/console-section";
import { MetricCard } from "@/components/shared/metric-card";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { PortfolioBalancesSection } from "@/components/portfolios/portfolio-balances-section";
import { PortfolioFormDialog } from "@/components/forms/portfolio-form-dialog";
import { PortfolioPositionsSection } from "@/components/portfolios/portfolio-positions-section";
import { PortfolioTradesSection } from "@/components/portfolios/portfolio-trades-section";

export function PortfolioDetailPage() {
  const navigate = useNavigate();
  const { portfolioId } = useParams();
  const portfolioQuery = usePortfolio(portfolioId);
  const positionsQuery = usePositions(portfolioId);
  const balancesQuery = useBalances(portfolioId);
  const tradingQuery = useTradingOperations(portfolioId);
  const updateMutation = useUpdatePortfolio();
  const deleteMutation = useDeletePortfolio();
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const positions = useMemo(
    () => positionsQuery.data ?? [],
    [positionsQuery.data],
  );
  const balances = useMemo(
    () => balancesQuery.data ?? [],
    [balancesQuery.data],
  );
  const operations = useMemo(
    () => tradingQuery.data ?? [],
    [tradingQuery.data],
  );
  const symbols = useMemo(
    () => positions.map((position) => position.symbol),
    [positions],
  );
  const quotesQuery = useMarketQuotes(portfolioId, symbols);
  const enrichedPositions = useMemo(
    () => enrichPositionsWithQuotes(positions, quotesQuery.data?.quotes ?? []),
    [positions, quotesQuery.data?.quotes],
  );
  const portfolio = portfolioQuery.data;
  const totalValue = computePortfolioTotalValue(enrichedPositions, balances);
  const cashValue = balances.reduce(
    (sum, balance) => sum + (getSignedBalanceAmount(balance) ?? 0),
    0,
  );
  const unrealizedPnl = enrichedPositions.reduce(
    (sum, position) => sum + (computePositionPnl(position).unrealized ?? 0),
    0,
  );
  const latestOperation = [...operations].sort((left, right) =>
    right.executedAt.localeCompare(left.executedAt),
  )[0];
  const quoteWarnings = quotesQuery.data?.warnings ?? [];

  if (!portfolioId) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        Portfolio route is missing an id.
      </div>
    );
  }

  if (portfolioQuery.isPending) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        Loading portfolio...
      </div>
    );
  }

  if (portfolioQuery.isError || !portfolio) {
    return (
      <div className="flex max-w-4xl flex-col gap-4 p-4">
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate("/portfolios")}
        >
          <ArrowLeft className="mr-1 size-4" /> Back
        </Button>
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {portfolioQuery.error instanceof Error
              ? portfolioQuery.error.message
              : "Portfolio not found."}
          </CardContent>
        </Card>
      </div>
    );
  }

  const portfolioMetadataItems = [
    { label: "Base currency", value: portfolio.baseCurrency },
    { label: "Portfolio ID", value: `#${portfolio.id}` },
    { label: "Last updated", value: formatDateTime(portfolio.updatedAt) },
  ];
  const portfolioStatusItems = [
    { label: "Positions", value: positions.length.toLocaleString() },
    { label: "Balances", value: balances.length.toLocaleString() },
    { label: "Trades", value: operations.length.toLocaleString() },
    {
      label: "Quotes",
      value:
        quoteWarnings.length > 0
          ? `${quoteWarnings.length.toLocaleString()} quote warnings`
          : "Ready",
    },
  ];
  const portfolioMetricItems = [
    {
      label: "Total Value",
      value: formatCurrency(totalValue, portfolio.baseCurrency),
      note: "Balances plus marked positions",
    },
    {
      label: "Cash Balances",
      value: formatCurrency(cashValue, portfolio.baseCurrency),
      note: `${balances.length.toLocaleString()} balance accounts`,
    },
    {
      label: "Unrealized P&L",
      value: formatCurrency(unrealizedPnl, portfolio.baseCurrency),
      note: `${positions.length.toLocaleString()} tracked positions`,
    },
    {
      label: "Latest Activity",
      value: latestOperation ? latestOperation.side : "None",
      note: latestOperation
        ? formatDateTime(latestOperation.executedAt)
        : "No operations yet",
    },
  ];

  return (
    <div className="flex min-w-0 flex-col gap-3 p-4">
      <div
        aria-labelledby="portfolio-detail-title"
        data-testid="portfolio-detail-header"
      >
        <PageContextBar
          actions={
            <div
              className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end"
              data-testid="portfolio-detail-actions"
            >
              <Button
                size="sm"
                variant="ghost"
                className="h-8 px-2 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => navigate("/portfolios")}
              >
                <ArrowLeft className="mr-1 size-3.5" /> Portfolios
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs"
                onClick={() => setShowEditForm(true)}
              >
                <Pencil className="mr-1 size-3" /> Edit
              </Button>
              <Button
                size="sm"
                variant="destructive"
                className="h-8 text-xs"
                onClick={() => setShowDeleteDialog(true)}
              >
                <Trash2 className="mr-1 size-3" /> Delete
              </Button>
            </div>
          }
          className="border-b border-border pb-3"
          description={
            <span
              className="block min-w-0 break-words text-sm text-muted-foreground"
              data-testid="portfolio-detail-identity"
            >
              {portfolio.description || "No description"}
            </span>
          }
          meta={
            <div
              className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
              role="list"
              aria-label="Portfolio metadata"
            >
              {portfolioMetadataItems.map((item) => (
                <span
                  className="flex min-w-0 items-baseline gap-1.5 border-r border-border pr-3 last:border-r-0 last:pr-0"
                  key={item.label}
                  role="listitem"
                >
                  <span className="shrink-0 text-muted-foreground">
                    {item.label}
                  </span>
                  <span className="min-w-0 break-words font-medium text-foreground">
                    {item.value}
                  </span>
                </span>
              ))}
            </div>
          }
          status={
            <div
              className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
              role="list"
              aria-label="Portfolio resource status"
            >
              {portfolioStatusItems.map((item) => (
                <span
                  className="flex min-w-0 items-baseline gap-1.5 border-r border-border pr-3 last:border-r-0 last:pr-0"
                  key={item.label}
                  role="listitem"
                >
                  <span className="shrink-0 text-muted-foreground">
                    {item.label}
                  </span>
                  <span className="min-w-0 break-words font-medium text-foreground">
                    {item.value}
                  </span>
                </span>
              ))}
            </div>
          }
          title={
            <span
              id="portfolio-detail-title"
              className="block break-words text-xl font-semibold tracking-tight"
            >
              {portfolio.name}
            </span>
          }
        />
      </div>

      <div
        className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4"
        aria-label="Portfolio metrics"
      >
        {portfolioMetricItems.map((metric) => (
          <MetricCard
            density="compact"
            key={metric.label}
            note={metric.note}
            title={metric.label}
            value={metric.value}
          />
        ))}
      </div>

      {positionsQuery.isError ||
      balancesQuery.isError ||
      tradingQuery.isError ? (
        <Card>
          <CardContent className="py-3 text-sm text-muted-foreground">
            Some portfolio sections could not be refreshed. Cached data may
            still be visible.
          </CardContent>
        </Card>
      ) : null}

      <Tabs defaultValue="positions" className="min-w-0">
        <ConsoleSection
          actions={
            <TabsList className="h-8" data-testid="portfolio-detail-tabs">
              <TabsTrigger value="positions" className="text-xs">
                Positions
              </TabsTrigger>
              <TabsTrigger value="balances" className="text-xs">
                Balances
              </TabsTrigger>
              <TabsTrigger value="trades" className="text-xs">
                Trades
              </TabsTrigger>
            </TabsList>
          }
          description="Positions, balances, and trades keep their own mutation controls inside each tabbed section."
          title="Portfolio sections"
        >
          <TabsContent value="positions" className="mt-0 min-w-0">
            <PortfolioPositionsSection
              balances={balances}
              portfolioId={portfolio.id}
              positions={enrichedPositions}
              quoteWarnings={quoteWarnings}
            />
          </TabsContent>
          <TabsContent value="balances" className="mt-0 min-w-0">
            <PortfolioBalancesSection
              portfolioId={portfolio.id}
              balances={balances}
            />
          </TabsContent>
          <TabsContent value="trades" className="mt-0 min-w-0">
            <PortfolioTradesSection
              portfolioId={portfolio.id}
              balances={balances}
              operations={operations}
              hasPositions={positions.length > 0}
              positions={positions}
            />
          </TabsContent>
        </ConsoleSection>
      </Tabs>

      <PortfolioFormDialog
        open={showEditForm}
        initial={portfolio}
        isPending={updateMutation.isPending}
        onOpenChange={setShowEditForm}
        onSave={(data) => {
          updateMutation.mutate(
            { portfolioId: portfolio.id, data: data as PortfolioUpdateInput },
            {
              onError: (error) =>
                toast.error(
                  error instanceof Error
                    ? error.message
                    : "Failed to update portfolio",
                ),
              onSuccess: () => {
                toast.success("Portfolio updated");
                setShowEditForm(false);
              },
            },
          );
        }}
      />

      <ConfirmDeleteDialog
        open={showDeleteDialog}
        title="Delete portfolio"
        description={`Delete ${portfolio.name}? This removes the portfolio shell and invalidates its detail route.`}
        isPending={deleteMutation.isPending}
        onOpenChange={setShowDeleteDialog}
        onConfirm={() => {
          deleteMutation.mutate(portfolio.id, {
            onError: (error) =>
              toast.error(
                error instanceof Error
                  ? error.message
                  : "Failed to delete portfolio",
              ),
            onSuccess: () => {
              toast.success("Portfolio deleted");
              navigate("/portfolios");
            },
          });
        }}
      />
    </div>
  );
}
