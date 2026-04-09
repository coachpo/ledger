import { Badge } from "@/components/ui/badge";

import type { BacktestStatus } from "@/lib/types/backtest";

const statusConfig: Record<BacktestStatus, { className: string; label: string }> = {
  PENDING: {
    className: "bg-slate-100 text-slate-700 border-slate-200",
    label: "PENDING",
  },
  RUNNING: {
    className: "bg-blue-100 text-blue-700 border-blue-200",
    label: "RUNNING",
  },
  AWAITING_CALLBACK: {
    className: "bg-indigo-100 text-indigo-700 border-indigo-200",
    label: "ANALYZING",
  },
  PROCESSING_CALLBACK: {
    className: "bg-cyan-100 text-cyan-700 border-cyan-200",
    label: "APPLYING",
  },
  COMPLETED: {
    className: "bg-emerald-100 text-emerald-700 border-emerald-200",
    label: "COMPLETED",
  },
  FAILED: {
    className: "bg-red-100 text-red-700 border-red-200",
    label: "FAILED",
  },
  CANCELLED: {
    className: "bg-amber-100 text-amber-700 border-amber-200",
    label: "CANCELLED",
  },
};

export function BacktestStatusBadge({ status }: { status: BacktestStatus }) {
  return (
    <Badge variant="outline" className={statusConfig[status].className}>
      {statusConfig[status].label}
    </Badge>
  );
}
