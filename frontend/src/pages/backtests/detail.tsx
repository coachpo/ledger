import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { BacktestStatusBadge } from "@/components/backtests/backtest-status-badge";
import { DrawdownChart } from "@/components/backtests/drawdown-chart";
import { EquityCurveChart } from "@/components/backtests/equity-curve-chart";
import { MetricsSummary } from "@/components/backtests/metrics-summary";
import { TradeLogTable } from "@/components/backtests/trade-log-table";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  const latestActivity = backtest.recentActivity?.at(-1) ?? null;
  const totalCapturedDecisions = (backtest.recentActivity ?? []).reduce(
    (count, entry) => count + entry.decisions.length,
    0,
  );
  const executedTrades = backtest.results?.trades.filter((trade) => trade.executed).length ?? 0;

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
            <CardHeader className="gap-2 p-4 pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-base">LangGraph Internal</CardTitle>
                <Badge variant="secondary">Active engine</Badge>
              </div>
              <CardDescription>
                {getInternalStageLabel(backtest.status, backtest.currentCycleStatus)}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 p-4">
              <div className="space-y-1">
                <p className="text-sm font-medium">Current simulation date</p>
                <p className="text-sm text-muted-foreground">
                  {backtest.currentCycleDate ? formatDate(backtest.currentCycleDate) : "Waiting to start"}
                </p>
              </div>
              <Progress value={progress} />
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
      ) : backtest.status === "FAILED" && backtest.errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Execution failed</AlertTitle>
          <AlertDescription>{backtest.errorMessage}</AlertDescription>
        </Alert>
      ) : backtest.results ? (
        <div className="space-y-4">
          <MetricsSummary portfolio={backtest.results.portfolio} />
          <Card>
            <CardHeader className="gap-2 p-4 pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle className="text-base">LangGraph Decision Summary</CardTitle>
                <Badge variant="secondary">Internal engine</Badge>
              </div>
              <CardDescription>
                A compact recap of the last internal analysis cycle using the existing backtest
                activity and trade data.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 p-4 md:grid-cols-3">
              <div className="flex flex-col gap-1 rounded-md border p-3">
                <p className="text-xs font-medium text-muted-foreground">Latest analysis cycle</p>
                <p className="text-sm font-medium">
                  {latestActivity ? formatDate(latestActivity.cycleDate) : "No cycle captured"}
                </p>
              </div>
              <div className="flex flex-col gap-1 rounded-md border p-3">
                <p className="text-xs font-medium text-muted-foreground">Decisions captured</p>
                <p className="text-sm font-medium">{totalCapturedDecisions}</p>
              </div>
              <div className="flex flex-col gap-1 rounded-md border p-3">
                <p className="text-xs font-medium text-muted-foreground">Executed trades</p>
                <p className="text-sm font-medium">{executedTrades}</p>
              </div>
              {latestActivity && latestActivity.decisions.length > 0 ? (
                <div className="md:col-span-3 flex flex-col gap-2 rounded-md border p-3">
                  <p className="text-xs font-medium text-muted-foreground">Latest cycle decisions</p>
                  <div className="flex flex-wrap gap-2">
                    {latestActivity.decisions.map((decision) => (
                      <Badge
                        key={`${latestActivity.cycleDate}-${decision.symbol}-${decision.action}`}
                        variant="outline"
                      >
                        {decision.symbol} · {decision.action}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
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

function getInternalStageLabel(status: string, currentCycleStatus: string | null) {
  if (currentCycleStatus === "AWAITING_CALLBACK" || status === "AWAITING_CALLBACK") {
    return "Preparing LangGraph cycle analysis...";
  }
  if (currentCycleStatus === "PROCESSING_CALLBACK" || status === "PROCESSING_CALLBACK") {
    return "Applying LangGraph cycle decisions...";
  }
  if (status === "PENDING") {
    return "Queueing LangGraph cycle analysis...";
  }

  return "Running LangGraph cycle analysis...";
}
