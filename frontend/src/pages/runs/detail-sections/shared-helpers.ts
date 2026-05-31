import type { ReactNode } from "react";

import { formatDateTime } from "@/lib/format";
import type { RunStatus, RunStepStatus } from "@/lib/types/run";

export function formatOptional(value: ReactNode | null | undefined): ReactNode {
  if (value === null || value === undefined || value === "") {
    return "Not recorded";
  }

  return value;
}

export function formatTimestamp(value: string | null): string {
  return value ? formatDateTime(value) : "Not recorded";
}

export function statusVariant(
  status: RunStatus | RunStepStatus,
): "secondary" | "destructive" | "outline" {
  if (status === "failed") {
    return "destructive";
  }

  if (status === "pending" || status === "skipped") {
    return "outline";
  }

  return "secondary";
}
