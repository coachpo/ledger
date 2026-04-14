import type { BacktestRead, BacktestStatus } from "@/lib/types/backtest";

type BacktestDisplayStateKind =
  | "pending"
  | "running"
  | "waiting_approval"
  | "awaiting_callback"
  | "processing_callback"
  | "completed"
  | "failed"
  | "cancelled";

type BacktestDisplayStateInput = Pick<BacktestRead, "status" | "currentCycleStatus">;

export type BacktestDisplayState = {
  kind: BacktestDisplayStateKind;
  badgeClassName: string;
  badgeLabel: string;
  cardTitle: string;
  modeLabel: string;
  stageLabel: string;
};

export function isActiveBacktestStatus(status: BacktestStatus | undefined) {
  return (
    status === "PENDING" ||
    status === "RUNNING" ||
    status === "AWAITING_CALLBACK" ||
    status === "PROCESSING_CALLBACK"
  );
}

export function getBacktestDisplayState({
  status,
  currentCycleStatus,
}: BacktestDisplayStateInput): BacktestDisplayState {
  if (status === "COMPLETED") {
    return {
      kind: "completed",
      badgeClassName: "bg-emerald-100 text-emerald-700 border-emerald-200",
      badgeLabel: "COMPLETED",
      cardTitle: "Backtest completed",
      modeLabel: "Completed",
      stageLabel: "The backtest finished and the final results are ready.",
    };
  }

  if (status === "FAILED") {
    return {
      kind: "failed",
      badgeClassName: "bg-red-100 text-red-700 border-red-200",
      badgeLabel: "FAILED",
      cardTitle: "Backtest failed",
      modeLabel: "Failed",
      stageLabel: "The backtest stopped because the current run failed.",
    };
  }

  if (status === "CANCELLED") {
    return {
      kind: "cancelled",
      badgeClassName: "bg-amber-100 text-amber-700 border-amber-200",
      badgeLabel: "CANCELLED",
      cardTitle: "Backtest cancelled",
      modeLabel: "Cancelled",
      stageLabel: "The backtest was cancelled before the remaining cycles completed.",
    };
  }

  if (status === "AWAITING_CALLBACK" || currentCycleStatus === "AWAITING_CALLBACK") {
    return {
      kind: "awaiting_callback",
      badgeClassName: "bg-indigo-100 text-indigo-700 border-indigo-200",
      badgeLabel: "AWAITING CALLBACK",
      cardTitle: "Legacy callback pending",
      modeLabel: "Legacy callback",
      stageLabel: "Waiting for the legacy callback response before this cycle can continue.",
    };
  }

  if (status === "PROCESSING_CALLBACK" || currentCycleStatus === "PROCESSING_CALLBACK") {
    return {
      kind: "processing_callback",
      badgeClassName: "bg-cyan-100 text-cyan-700 border-cyan-200",
      badgeLabel: "PROCESSING CALLBACK",
      cardTitle: "Legacy callback processing",
      modeLabel: "Legacy callback",
      stageLabel: "Applying the legacy callback response for the current cycle.",
    };
  }

  if (currentCycleStatus === "WAITING_APPROVAL") {
    return {
      kind: "waiting_approval",
      badgeClassName: "bg-violet-100 text-violet-700 border-violet-200",
      badgeLabel: "WAITING APPROVAL",
      cardTitle: "Runtime approval required",
      modeLabel: "Internal runtime",
      stageLabel: "Waiting for runtime approval before the current cycle can continue.",
    };
  }

  if (status === "PENDING") {
    return {
      kind: "pending",
      badgeClassName: "bg-slate-100 text-slate-700 border-slate-200",
      badgeLabel: "PENDING",
      cardTitle: "LangGraph internal",
      modeLabel: "LangGraph internal",
      stageLabel: "Queueing the next internal analysis cycle.",
    };
  }

  return {
    kind: "running",
    badgeClassName: "bg-blue-100 text-blue-700 border-blue-200",
    badgeLabel: "RUNNING",
    cardTitle: "LangGraph internal",
    modeLabel: "LangGraph internal",
    stageLabel: "Running the current internal analysis cycle.",
  };
}
