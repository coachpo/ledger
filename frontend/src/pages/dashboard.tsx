import {
  ArrowUpRight,
  BarChart3,
  Briefcase,
  DollarSign,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { MetricCard } from "@/components/shared/metric-card";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { ConsoleSection } from "@/components/shared/console-section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolios } from "@/hooks/use-portfolios";

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

function DashboardHeader({
  isFetching = false,
  portfolioCount,
  state,
}: {
  isFetching?: boolean;
  portfolioCount?: number;
  state: "loading" | "ready" | "error";
}) {
  const statusItems =
    state === "loading"
      ? [
          { label: "Portfolio API", tone: "warning" as const, value: "Loading" },
          { label: "Workspace", tone: "neutral" as const, value: "Finance owned" },
        ]
      : state === "error"
        ? [
            { label: "Portfolio API", tone: "danger" as const, value: "Unavailable" },
            { label: "Workspace", tone: "warning" as const, value: "Retry required" },
          ]
        : [
            {
              label: "Portfolios",
              tone: portfolioCount ? ("success" as const) : ("muted" as const),
              value: String(portfolioCount ?? 0),
            },
            {
              label: "Refresh",
              tone: isFetching ? ("warning" as const) : ("neutral" as const),
              value: isFetching ? "Syncing" : "Ready",
            },
          ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Singleton landing summary for portfolio inventory, position coverage, and workspace health.
        </p>
      </div>
      <PageContextBar
        description="Finance Workspace portfolio telemetry, grouped into compact KPI and operational status bands."
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <ProvenanceBadge detail="portfolio API" label="Data source" tone="verified" />
            <ProvenanceBadge detail="extension-owned" label="Route owner" />
          </div>
        }
        status={<ResourceStatusStrip items={statusItems} />}
        title="Dashboard context"
      />
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
      <DashboardHeader state="loading" />

      <ConsoleSection
        description="Loading the portfolio KPI band without introducing additional data sources."
        title="Portfolio summary"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="rounded-xl border bg-card p-3" key={index}>
              <div className="flex flex-col gap-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-7 w-24" />
                <Skeleton className="h-3 w-32" />
              </div>
            </div>
          ))}
        </div>
      </ConsoleSection>

      <ConsoleSection
        description="Preparing compact operating-status cues for the dashboard shell."
        title="Operational context"
        tone="muted"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div className="rounded-xl border bg-card p-3" key={index}>
              <div className="flex items-center gap-3">
                <Skeleton className="size-8 rounded-md" />
                <div className="flex flex-col gap-1.5">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-6 w-16" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </ConsoleSection>
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
  const mostRecentlyUpdatedPortfolio = portfolios.reduce<(typeof portfolios)[number] | null>(
    (current, portfolio) => {
      if (!current || portfolio.updatedAt.localeCompare(current.updatedAt) > 0) {
        return portfolio;
      }

      return current;
    },
    null,
  );

  if (isPending) {
    return <DashboardSkeleton />;
  }

  if (isError) {
    return (
      <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
        <DashboardHeader state="error" />

        <EmptyStatePanel
          action={
            <Button
              className="cursor-pointer"
              disabled={isFetching}
              onClick={() => void refetch()}
              size="sm"
              variant="outline"
            >
              <RefreshCw data-icon="inline-start" />
              {isFetching ? "Retrying" : "Retry"}
            </Button>
          }
          description={
            error instanceof Error
              ? error.message
              : "Check the backend connection and try again."
          }
          icon={<TriangleAlert className="size-4 text-destructive" />}
          title="Unable to load the dashboard summary."
          tone="danger"
        />
      </div>
    );
  }

  return (
    <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
      <DashboardHeader
        isFetching={isFetching}
        portfolioCount={portfolioCount}
        state="ready"
      />

      <ConsoleSection
        description="Portfolio counts, position coverage, and latest update from the existing portfolio query."
        title="Portfolio summary"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            density="compact"
            icon={Briefcase}
            iconClassName="bg-primary/10 text-primary"
            note="Portfolio records syncing from the API"
            provenance={<ProvenanceBadge detail="live query" label="Source" tone="verified" />}
            status={<ResourceStatusStrip items={[{ label: "State", tone: portfolioCount ? "success" : "muted", value: portfolioCount ? "Ready" : "Empty" }]} />}
            title="Active Portfolios"
            to="/portfolios"
            value={String(portfolioCount)}
          />
          <MetricCard
            density="compact"
            icon={BarChart3}
            iconClassName="bg-primary/10 text-primary"
            note={`${averagePositions} positions per portfolio on average`}
            title="Total Positions"
            value={String(totalPositions)}
          />
          <MetricCard
            density="compact"
            icon={DollarSign}
            iconClassName="bg-primary/10 text-primary"
            note="Cash and settlement balances tracked across portfolios"
            title="Balance Accounts"
            value={String(totalBalances)}
          />
          <MetricCard
            density="compact"
            icon={ArrowUpRight}
            iconClassName="bg-primary/10 text-primary"
            note={formatDateLabel(mostRecentlyUpdatedPortfolio?.updatedAt ?? null)}
            title="Latest Update"
            to={mostRecentlyUpdatedPortfolio ? `/portfolios/${mostRecentlyUpdatedPortfolio.id}` : undefined}
            value={mostRecentlyUpdatedPortfolio?.name ?? "No portfolio data"}
            valueClassName="text-lg leading-tight"
          />
        </div>
        {portfolioCount === 0 ? (
          <EmptyStatePanel
            className="mt-3"
            description="Create or import a portfolio from the Finance Workspace to populate this dashboard band."
            icon={<Briefcase className="size-4" />}
            title="No portfolio records are available yet."
          />
        ) : null}
      </ConsoleSection>

      <ConsoleSection
        description="Operational cues derived from the same portfolio list; no separate health endpoint is queried."
        title="Operational context"
        tone="muted"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <MetricCard
            density="compact"
            icon={Briefcase}
            iconClassName="bg-muted text-muted-foreground"
            title="Tracked Currencies"
            value={String(currencies.size)}
          />
          <MetricCard
            density="compact"
            icon={BarChart3}
            iconClassName="bg-muted text-muted-foreground"
            title="Average Position Load"
            value={String(averagePositions)}
          />
          <MetricCard
            density="compact"
            icon={ArrowUpRight}
            iconClassName="bg-muted text-muted-foreground"
            title="Largest Portfolio Footprint"
            value={`${mostPositionedPortfolio?.positionCount ?? 0} positions`}
          />
        </div>
      </ConsoleSection>
    </div>
  );
}
