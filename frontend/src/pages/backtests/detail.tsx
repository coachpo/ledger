import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { BacktestStatusBadge } from "@/components/backtests/backtest-status-badge";
import { DrawdownChart } from "@/components/backtests/drawdown-chart";
import { EquityCurveChart } from "@/components/backtests/equity-curve-chart";
import { MetricsSummary } from "@/components/backtests/metrics-summary";
import { TradeLogTable } from "@/components/backtests/trade-log-table";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useBacktest, useCancelBacktest, useDeleteBacktest } from "@/hooks/use-backtests";
import { formatDate, formatDateTime } from "@/lib/format";

export function BacktestDetailPage() {
  const { backtestId } = useParams<{ backtestId: string }>();
  const navigate = useNavigate();
  const backtestQuery = useBacktest(backtestId);
  const cancelMutation = useCancelBacktest();
  const deleteMutation = useDeleteBacktest();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const reportSlugs = useMemo(
    () =>
      Array.from(
        new Set(
          (backtestQuery.data?.results?.trades ?? [])
            .map((trade) => trade.reportSlug)
            .filter((slug): slug is string => Boolean(slug)),
        ),
      ),
    [backtestQuery.data?.results?.trades],
  );

  if (backtestQuery.isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading backtest...</div>;
  }

  const backtest = backtestQuery.data;
  if (!backtest) {
    return <div className="p-4 text-sm text-muted-foreground">Backtest not found.</div>;
  }

  const progress =
    backtest.totalCycles > 0 ? (backtest.completedCycles / backtest.totalCycles) * 100 : 0;
  const isRunning =
    backtest.status === "PENDING" ||
    backtest.status === "RUNNING" ||
    backtest.status === "AWAITING_CALLBACK" ||
    backtest.status === "PROCESSING_CALLBACK";
  const elapsedTime = getElapsedTimeLabel(backtest.createdAt);

  return (
    <div className="max-w-6xl space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{backtest.name}</h1>
            <BacktestStatusBadge status={backtest.status} />
          </div>
          <p className="text-xs text-muted-foreground">
            {backtest.frequency} · {formatDate(backtest.startDate)} - {formatDate(backtest.endDate)}
          </p>
        </div>
        <div className="flex gap-2">
          {isRunning ? (
            <Button
              variant="outline"
              onClick={() => cancelMutation.mutate(backtest.id)}
              disabled={cancelMutation.isPending}
            >
              Cancel
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setDeleteOpen(true)}>
              Delete
            </Button>
          )}
        </div>
      </div>

      {isRunning ? (
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 p-4">
              <div className="space-y-1">
                <p className="text-sm font-medium">Current simulation date</p>
                <p className="text-sm text-muted-foreground">
                  {backtest.currentCycleDate ? formatDate(backtest.currentCycleDate) : "Waiting to start"}
                </p>
              </div>
              <Progress value={progress} />
              {(backtest.status === "RUNNING" ||
                backtest.status === "AWAITING_CALLBACK" ||
                backtest.status === "PROCESSING_CALLBACK") &&
                backtest.currentCycleStatus && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {backtest.currentCycleStatus === "AWAITING_CALLBACK"
                      ? "Waiting for client callback..."
                      : backtest.currentCycleStatus === "PROCESSING_CALLBACK"
                        ? "Processing client callback..."
                        : "Running cycle..."}
                  </p>
                )}
              <p className="text-xs text-muted-foreground">
                {backtest.completedCycles} / {backtest.totalCycles} cycles · Started {formatDateTime(backtest.createdAt)}
              </p>
              <p className="text-xs text-muted-foreground">Elapsed time · {elapsedTime}</p>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 p-4">
              <CardTitle className="text-base">Recent Activity</CardTitle>
              {(backtest.recentActivity ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No activity yet.</p>
              ) : (
                (backtest.recentActivity ?? []).map((entry) => (
                  <div key={entry.cycleDate} className="space-y-1 rounded-md border p-3">
                    <p className="text-sm font-medium">{formatDate(entry.cycleDate)}</p>
                    <ul className="space-y-1 text-sm text-muted-foreground">
                      {entry.decisions.map((decision) => (
                        <li
                          key={`${entry.cycleDate}-${decision.symbol}-${decision.action}-${decision.reasoning}`}
                        >
                          {decision.symbol} · {decision.action}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      ) : backtest.results ? (
        <div className="space-y-4">
          <MetricsSummary portfolio={backtest.results.portfolio} />
          <Card>
            <CardContent className="space-y-4 p-4">
              <CardTitle className="text-base">Equity Curve</CardTitle>
              <EquityCurveChart
                curve={backtest.results.equityCurve}
                benchmarkCurves={backtest.results.benchmarkCurves}
                selectedBenchmarks={backtest.benchmarkSymbols}
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-4 p-4">
              <CardTitle className="text-base">Drawdown</CardTitle>
              <DrawdownChart curve={backtest.results.drawdownCurve} />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-4 p-4">
              <CardTitle className="text-base">Trade Log</CardTitle>
              <TradeLogTable trades={backtest.results.trades} />
            </CardContent>
          </Card>
          {reportSlugs.length > 0 ? (
            <Card>
              <CardContent className="space-y-2 p-4">
                <CardTitle className="text-base">Analysis Reports</CardTitle>
                <div className="flex flex-wrap gap-2">
                  {reportSlugs.map((slug) => (
                    <Button
                      key={slug}
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(`/reports/${slug}`)}
                    >
                      {slug}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No results available.
          </CardContent>
        </Card>
      )}

      <ConfirmDeleteDialog
        open={deleteOpen}
        title="Delete backtest"
        description={`Delete ${backtest.name}? This cannot be undone.`}
        isPending={deleteMutation.isPending}
        onOpenChange={setDeleteOpen}
        onConfirm={() => {
          deleteMutation.mutate(backtest.id, {
            onError: (error) =>
              toast.error(error instanceof Error ? error.message : "Failed to delete backtest"),
            onSuccess: () => {
              toast.success("Backtest deleted");
              navigate("/backtests");
            },
          });
        }}
      />
    </div>
  );
}

function getElapsedTimeLabel(createdAt: string): string {
  const createdAtMs = Date.parse(createdAt);
  if (Number.isNaN(createdAtMs)) {
    return "0m";
  }

  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - createdAtMs) / 60000));
  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}
