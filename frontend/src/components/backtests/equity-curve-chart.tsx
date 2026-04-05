import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { formatDate, formatPercent } from "@/lib/format";
import type { BacktestCurvePoint } from "@/lib/types/backtest";

const BENCHMARK_COLORS = ["#2563eb", "#7c3aed", "#ea580c"] as const;

function toBenchmarkSeriesKey(symbol: string) {
  return `benchmark_${symbol.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

function getBenchmarkLabel(symbol: string) {
  return (
    {
      "^GSPC": "S&P 500",
      "^IXIC": "NASDAQ",
      "^DJI": "Dow Jones",
    }[symbol] ?? symbol
  );
}

type EquityCurveChartProps = {
  curve: BacktestCurvePoint[];
  benchmarkCurves: Record<string, BacktestCurvePoint[]>;
  selectedBenchmarks: string[];
};

export function EquityCurveChart({
  curve,
  benchmarkCurves,
  selectedBenchmarks,
}: EquityCurveChartProps) {
  const startingPortfolioValue = curve[0]?.value ? Number(curve[0].value) : 0;
  const [visibleSeries, setVisibleSeries] = useState<Record<string, boolean>>(
    Object.fromEntries(selectedBenchmarks.map((symbol) => [symbol, true])),
  );

  const data = useMemo(() => {
    const byDate = new Map<string, Record<string, string | number>>();

    for (const point of curve) {
      byDate.set(point.date, {
        date: point.date,
        portfolio:
          startingPortfolioValue > 0 ? Number(point.value) / startingPortfolioValue : 0,
      });
    }

    for (const [symbol, series] of Object.entries(benchmarkCurves)) {
      const seriesKey = toBenchmarkSeriesKey(symbol);
      for (const point of series) {
        const existing = byDate.get(point.date) ?? { date: point.date };
        existing[seriesKey] = Number(point.value);
        byDate.set(point.date, existing);
      }
    }

    return Array.from(byDate.values()).sort((left, right) =>
      String(left.date).localeCompare(String(right.date)),
    );
  }, [benchmarkCurves, curve, startingPortfolioValue]);

  const chartConfig = useMemo(
    () => ({
      portfolio: { label: "Portfolio", color: "#0f766e" },
      ...Object.fromEntries(
        selectedBenchmarks.map((symbol, index) => [
          toBenchmarkSeriesKey(symbol),
          {
            label: getBenchmarkLabel(symbol),
            color: BENCHMARK_COLORS[index % BENCHMARK_COLORS.length],
          },
        ]),
      ),
    }),
    [selectedBenchmarks],
  );

  return (
    <div className="space-y-3">
      <ChartContainer config={chartConfig} className="h-72 w-full">
        <LineChart data={data}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="date" tickFormatter={(value) => formatDate(String(value))} />
          <YAxis tickFormatter={(value) => formatPercent(Number(value) - 1)} width={96} />
          <ChartTooltip
            content={<ChartTooltipContent formatter={(value) => formatPercent(Number(value) - 1)} />}
          />
          <Line
            dataKey="portfolio"
            dot={false}
            stroke="var(--color-portfolio)"
            strokeWidth={2}
            type="monotone"
          />
          {selectedBenchmarks.map((symbol) =>
            visibleSeries[symbol] ? (
              <Line
                key={symbol}
                dataKey={toBenchmarkSeriesKey(symbol)}
                dot={false}
                stroke={`var(--color-${toBenchmarkSeriesKey(symbol)})`}
                strokeWidth={1.5}
                type="monotone"
              />
            ) : null,
          )}
        </LineChart>
      </ChartContainer>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input aria-label="Portfolio" checked disabled type="checkbox" />
          <span>Portfolio</span>
        </label>
        {selectedBenchmarks.map((symbol) => (
          <label key={symbol} className="flex items-center gap-2">
            <input
              aria-label={symbol}
              checked={visibleSeries[symbol] ?? false}
              onChange={() =>
                setVisibleSeries((current) => ({
                  ...current,
                  [symbol]: !current[symbol],
                }))
              }
              type="checkbox"
            />
            <span>{symbol}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
