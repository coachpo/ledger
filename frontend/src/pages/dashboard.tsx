import {
  ArrowUpRight,
  BarChart3,
  Briefcase,
  DollarSign,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";

import { usePortfolios } from "@/hooks/use-portfolios";

import { MetricCard } from "@/components/shared/metric-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function formatDateLabel(value: string | null) {
  if (!value) {
    return "No updates yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function DashboardHeader() {
  return (
    <div className="space-y-0.5">
      <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
      <p className="text-sm text-muted-foreground">
        Singleton landing summary for portfolio inventory, position coverage, and
        workspace health.
      </p>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="max-w-7xl space-y-4 p-4" data-testid="dashboard-page">
      <DashboardHeader />

      <section className="space-y-2" aria-labelledby="dashboard-kpi-heading">
        <h2 id="dashboard-kpi-heading" className="text-sm font-medium text-foreground">
          Portfolio summary
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Card key={index}>
              <CardContent className="space-y-3 p-4">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-7 w-24" />
                <Skeleton className="h-3 w-32" />
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-2" aria-labelledby="dashboard-context-heading">
        <h2 id="dashboard-context-heading" className="text-sm font-medium text-foreground">
          Operational context
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Card key={index}>
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <Skeleton className="size-8 rounded-md" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-6 w-16" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

export function Dashboard() {
  const {
    data: portfolios = [],
    error,
    isError,
    isFetching,
    isPending,
    refetch,
  } = usePortfolios();

  const portfolioCount = portfolios.length;
  const totalPositions = portfolios.reduce(
    (sum, portfolio) => sum + portfolio.positionCount,
    0,
  );
  const totalBalances = portfolios.reduce(
    (sum, portfolio) => sum + portfolio.balanceCount,
    0,
  );
  const currencies = new Set(portfolios.map((portfolio) => portfolio.baseCurrency));
  const averagePositions = portfolioCount
    ? (totalPositions / portfolioCount).toFixed(1)
    : "0.0";
  const mostPositionedPortfolio = portfolios.reduce<(typeof portfolios)[number] | null>(
    (current, portfolio) => {
      if (!current || portfolio.positionCount > current.positionCount) {
        return portfolio;
      }

      return current;
    },
    null,
  );
  const mostRecentlyUpdatedPortfolio = [...portfolios].sort((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  )[0] ?? null;
  if (isPending) {
    return <DashboardSkeleton />;
  }

  if (isError) {
    return (
      <div className="max-w-7xl space-y-4 p-4" data-testid="dashboard-page">
        <DashboardHeader />

        <Card role="alert" aria-live="polite">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-start gap-3">
              <TriangleAlert
                className="mt-0.5 size-4 shrink-0 text-destructive"
                aria-hidden="true"
              />
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  Unable to load the dashboard summary.
                </p>
                <p className="text-xs text-muted-foreground">
                  {error instanceof Error
                    ? error.message
                    : "Check the backend connection and try again."}
                </p>
              </div>
            </div>
            <Button
              className="cursor-pointer"
              disabled={isFetching}
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
            >
              <RefreshCw className="mr-1.5 size-3.5" />
              {isFetching ? "Retrying" : "Retry"}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-7xl space-y-4 p-4" data-testid="dashboard-page">
      <DashboardHeader />

      <section className="space-y-2" aria-labelledby="dashboard-kpi-heading">
        <h2 id="dashboard-kpi-heading" className="text-sm font-medium text-foreground">
          Portfolio summary
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            icon={Briefcase}
            iconClassName="bg-primary/10 text-primary"
            note="Portfolio records syncing from the API"
            title="Active Portfolios"
            to="/portfolios"
            value={String(portfolioCount)}
          />
          <MetricCard
            icon={BarChart3}
            iconClassName="bg-primary/10 text-primary"
            note={`${averagePositions} positions per portfolio on average`}
            title="Total Positions"
            value={String(totalPositions)}
          />
          <MetricCard
            icon={DollarSign}
            iconClassName="bg-primary/10 text-primary"
            note="Cash and settlement balances tracked across portfolios"
            title="Balance Accounts"
            value={String(totalBalances)}
          />
          <MetricCard
            icon={ArrowUpRight}
            iconClassName="bg-primary/10 text-primary"
            note={formatDateLabel(mostRecentlyUpdatedPortfolio?.updatedAt ?? null)}
            title="Latest Update"
            to={mostRecentlyUpdatedPortfolio ? `/portfolios/${mostRecentlyUpdatedPortfolio.id}` : undefined}
            value={mostRecentlyUpdatedPortfolio?.name ?? "No portfolio data"}
            valueClassName="text-lg leading-tight"
          />
        </div>
      </section>

      <section className="space-y-2" aria-labelledby="dashboard-context-heading">
        <h2 id="dashboard-context-heading" className="text-sm font-medium text-foreground">
          Operational context
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            icon={Briefcase}
            iconClassName="bg-muted text-muted-foreground"
            title="Tracked Currencies"
            value={String(currencies.size)}
          />
          <MetricCard
            icon={BarChart3}
            iconClassName="bg-muted text-muted-foreground"
            title="Average Position Load"
            value={String(averagePositions)}
          />
          <MetricCard
            icon={ArrowUpRight}
            iconClassName="bg-muted text-muted-foreground"
            title="Largest Portfolio Footprint"
            value={`${mostPositionedPortfolio?.positionCount ?? 0} positions`}
          />
        </div>
      </section>
    </div>
  );
}
