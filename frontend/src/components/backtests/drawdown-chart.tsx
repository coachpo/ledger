import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { formatDate, formatPercent } from "@/lib/format";
import type { BacktestCurvePoint } from "@/lib/types/backtest";

export function DrawdownChart({ curve }: { curve: BacktestCurvePoint[] }) {
  const data = curve.map((point) => ({ date: point.date, value: Number(point.value) }));

  return (
    <ChartContainer
      config={{ drawdown: { label: "Drawdown", color: "#dc2626" } }}
      className="h-72 w-full"
    >
      <AreaChart data={data}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" tickFormatter={(value) => formatDate(String(value))} />
        <YAxis tickFormatter={(value) => formatPercent(Number(value))} width={96} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Area
          dataKey="value"
          fill="var(--color-drawdown)"
          fillOpacity={0.2}
          stroke="var(--color-drawdown)"
          type="monotone"
        />
      </AreaChart>
    </ChartContainer>
  );
}
