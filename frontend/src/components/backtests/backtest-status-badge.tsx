import { Badge } from "@/components/ui/badge";

import { getBacktestDisplayState } from "@/lib/backtest-display";
import type { BacktestStatus } from "@/lib/types/backtest";

export function BacktestStatusBadge({
  status,
  currentCycleStatus = null,
}: {
  status: BacktestStatus;
  currentCycleStatus?: string | null;
}) {
  const displayState = getBacktestDisplayState({ status, currentCycleStatus });

  return (
    <Badge variant="outline" className={displayState.badgeClassName}>
      {displayState.badgeLabel}
    </Badge>
  );
}
