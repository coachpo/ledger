import { useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { BacktestStatusBadge } from "@/components/backtests/backtest-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useBacktests, useDeleteBacktest } from "@/hooks/use-backtests";
import { formatDate, formatPercent } from "@/lib/format";
import type { BacktestRead } from "@/lib/types/backtest";

export function BacktestListPage() {
  const navigate = useNavigate();
  const backtestsQuery = useBacktests();
  const deleteMutation = useDeleteBacktest();
  const [deleting, setDeleting] = useState<BacktestRead | null>(null);

  const backtests = useMemo(
    () => [...(backtestsQuery.data ?? [])].sort((left, right) => right.id - left.id),
    [backtestsQuery.data],
  );

  const completedSummary = (backtest: BacktestRead) => {
    if (!backtest.results) {
      return null;
    }
    const benchmarkSymbol = backtest.benchmarkSymbols[0];
    const benchmark = benchmarkSymbol ? backtest.results.benchmarks[benchmarkSymbol] : undefined;
    if (!benchmarkSymbol || !benchmark) {
      return `Total return ${formatPercent(backtest.results.portfolio.totalReturn)}`;
    }
    return `Total return ${formatPercent(backtest.results.portfolio.totalReturn)} vs ${benchmarkSymbol} ${formatPercent(benchmark.totalReturn)}`;
  };

  return (
    <div className="max-w-6xl space-y-3 p-4">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <h1 className="text-xl font-semibold tracking-tight">Backtests</h1>
          <p className="text-xs text-muted-foreground">
            Launch, monitor, and review historical portfolio simulations.
          </p>
        </div>
        <Button size="sm" onClick={() => navigate("/backtests/new")}>
          <Plus className="mr-1 size-3.5" /> New Backtest
        </Button>
      </div>

      <div className="space-y-2">
        {backtestsQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              Loading backtests...
            </CardContent>
          </Card>
        ) : null}
        {backtestsQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              {backtestsQuery.error instanceof Error
                ? backtestsQuery.error.message
                : "Failed to load backtests."}
            </CardContent>
          </Card>
        ) : null}
        {!backtestsQuery.isPending && !backtestsQuery.isError && backtests.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No backtests yet.
            </CardContent>
          </Card>
        ) : null}
        {backtests.map((backtest) => {
          const progress =
            backtest.totalCycles > 0
              ? (backtest.completedCycles / backtest.totalCycles) * 100
              : 0;
          const isTerminal = ["COMPLETED", "FAILED", "CANCELLED"].includes(backtest.status);

          return (
            <Card key={backtest.id} className="transition-colors hover:bg-accent/50">
              <CardContent className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-sm font-medium tracking-tight">
                      {backtest.name}
                    </CardTitle>
                    <BacktestStatusBadge status={backtest.status} />
                    <span className="text-xs text-muted-foreground">{backtest.frequency}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(backtest.startDate)} - {formatDate(backtest.endDate)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Portfolio {backtest.portfolioName ?? `#${backtest.portfolioId}`}
                  </p>
                  {backtest.status === "RUNNING" || backtest.status === "PENDING" ? (
                    <div className="space-y-1">
                      <Progress value={progress} />
                      <p className="text-[11px] text-muted-foreground">
                        {backtest.completedCycles} / {backtest.totalCycles} cycles
                      </p>
                    </div>
                  ) : null}
                  {backtest.status === "COMPLETED" && backtest.results ? (
                    <p className="text-xs text-muted-foreground">
                      {completedSummary(backtest)}
                    </p>
                  ) : null}
                  {backtest.status === "FAILED" && backtest.errorMessage ? (
                    <p className="text-xs text-red-600">{backtest.errorMessage}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {isTerminal ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setDeleting(backtest)}
                    >
                      <Trash2 className="mr-1 size-3.5" /> Delete
                    </Button>
                  ) : null}
                  <Button size="sm" variant="secondary" onClick={() => navigate(`/backtests/${backtest.id}`)}>
                    Open
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        title="Delete backtest"
        description={`Delete ${deleting?.name ?? "this backtest"}? This cannot be undone.`}
        isPending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        onConfirm={() => {
          if (!deleting) return;
          deleteMutation.mutate(deleting.id, {
            onError: (error) =>
              toast.error(error instanceof Error ? error.message : "Failed to delete backtest"),
            onSuccess: () => {
              toast.success("Backtest deleted");
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}
