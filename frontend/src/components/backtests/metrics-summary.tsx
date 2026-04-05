import { MetricCard } from "@/components/shared/metric-card";
import { formatCurrency, formatDecimal, formatPercent } from "@/lib/format";
import type { BacktestPortfolioResults } from "@/lib/types/backtest";

export function MetricsSummary({ portfolio }: { portfolio: BacktestPortfolioResults }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <MetricCard title="Total Return" value={formatPercent(portfolio.totalReturn)} />
      <MetricCard title="Max Drawdown" value={formatPercent(portfolio.maxDrawdown)} />
      <MetricCard
        title="Sharpe Ratio"
        value={formatDecimal(portfolio.sharpeRatio ?? "0", 2)}
      />
      <MetricCard title="Total Trades" value={String(portfolio.totalTrades)} />
      <MetricCard title="Win Rate" value={formatPercent(portfolio.winRate)} />
      <MetricCard
        title="Total Commission"
        value={formatCurrency(portfolio.totalCommission)}
      />
    </div>
  );
}
