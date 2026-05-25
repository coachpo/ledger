import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/utils";

export type EvidenceClusterLayout = "grid" | "list" | "inline";
export type EvidenceClusterTone = "neutral" | "verified" | "warning" | "danger";

export type EvidenceClusterItem = {
  description?: ReactNode;
  label: ReactNode;
  tone?: EvidenceClusterTone;
  value: ReactNode;
};

export type EvidenceClusterProps = {
  className?: string;
  emptyLabel?: string;
  items: readonly EvidenceClusterItem[];
  layout?: EvidenceClusterLayout;
};

const clusterClassByLayout: Record<EvidenceClusterLayout, string> = {
  grid: "grid gap-2 sm:grid-cols-2",
  list: "flex flex-col gap-2",
  inline: "flex flex-wrap items-center gap-2",
};

const badgeVariantByTone: Record<EvidenceClusterTone, "secondary" | "outline" | "destructive"> = {
  neutral: "outline",
  verified: "secondary",
  warning: "outline",
  danger: "destructive",
};

export function EvidenceCluster({
  className,
  emptyLabel = "No evidence available",
  items,
  layout = "grid",
}: EvidenceClusterProps) {
  if (items.length === 0) {
    return <div className={cn("rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground", className)}>{emptyLabel}</div>;
  }

  return (
    <div className={cn(clusterClassByLayout[layout], className)} role="list">
      {items.map((item, index) => (
        <div className="min-w-0 rounded-lg border bg-card px-3 py-2" key={index} role="listitem">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge data-tone={item.tone ?? "neutral"} variant={badgeVariantByTone[item.tone ?? "neutral"]}>{item.label}</Badge>
            <span className="min-w-0 break-words text-sm font-medium text-foreground">{item.value}</span>
          </div>
          {item.description ? <div className="mt-1 min-w-0 break-words text-xs text-muted-foreground">{item.description}</div> : null}
        </div>
      ))}
    </div>
  );
}
