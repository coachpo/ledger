import { RefreshCw, TriangleAlert } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { Button } from "@/components/ui/button";
import { usePortfolios } from "@/hooks/use-portfolios";

function DashboardHeader() {
  return (
    <PageContextBar
      description="Portfolio overview."
      layout="toolbar"
      title="Dashboard"
    />
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

  void portfolios;

  if (isPending) {
    return (
      <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
        <DashboardHeader />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex max-w-7xl flex-col gap-4 p-4" data-testid="dashboard-page">
        <DashboardHeader />

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
      <DashboardHeader />
    </div>
  );
}
