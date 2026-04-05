import { Badge } from "@/components/ui/badge";

import type { BacktestStatus } from "@/lib/types/backtest";

const statusStyles: Record<BacktestStatus, string> = {
  PENDING: "bg-slate-100 text-slate-700 border-slate-200",
  RUNNING: "bg-blue-100 text-blue-700 border-blue-200",
  AWAITING_CALLBACK: "bg-indigo-100 text-indigo-700 border-indigo-200",
  PROCESSING_CALLBACK: "bg-cyan-100 text-cyan-700 border-cyan-200",
  COMPLETED: "bg-emerald-100 text-emerald-700 border-emerald-200",
  FAILED: "bg-red-100 text-red-700 border-red-200",
  CANCELLED: "bg-amber-100 text-amber-700 border-amber-200",
};

export function BacktestStatusBadge({ status }: { status: BacktestStatus }) {
  return (
    <Badge variant="outline" className={statusStyles[status]}>
      {status}
    </Badge>
  );
}
