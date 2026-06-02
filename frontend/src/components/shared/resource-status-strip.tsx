import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

export type ResourceStatusTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "muted";
export type ResourceStatusStripDensity = "compact" | "comfortable" | "toolbar";

export type ResourceStatusBadgeProps = {
  className?: string;
  label: ReactNode;
  testId?: string;
  tone?: ResourceStatusTone;
};

export type ResourceStatusStripItem = {
  description?: ReactNode;
  label: string;
  tone?: ResourceStatusTone;
  value?: ReactNode;
};

export type ResourceStatusStripProps = {
  className?: string;
  density?: ResourceStatusStripDensity;
  emptyLabel?: string;
  items: readonly ResourceStatusStripItem[];
};

const badgeVariantByTone: Record<
  ResourceStatusTone,
  "default" | "secondary" | "outline" | "destructive"
> = {
  neutral: "outline",
  success: "secondary",
  warning: "outline",
  danger: "destructive",
  muted: "secondary",
};

const densityClass: Record<ResourceStatusStripDensity, string> = {
  compact: "gap-2 px-3 py-2 text-xs",
  comfortable: "gap-3 px-4 py-3 text-sm",
  toolbar: "gap-1.5 rounded-md px-2 py-0.5 text-xs",
};

export function ResourceStatusBadge({
  className,
  label,
  testId,
  tone = "neutral",
}: ResourceStatusBadgeProps) {
  return (
    <Badge
      className={className}
      data-testid={testId}
      data-tone={tone}
      variant={badgeVariantByTone[tone]}
    >
      {label}
    </Badge>
  );
}

export function ResourceStatusStrip({
  className,
  density = "compact",
  emptyLabel = "No status available",
  items,
}: ResourceStatusStripProps) {
  if (items.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground",
          className,
        )}
      >
        {emptyLabel}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center rounded-lg border bg-card text-card-foreground",
        densityClass[density],
        className,
      )}
      role="list"
    >
      {items.map((item, index) => (
        <div
          className="flex min-w-0 items-center gap-2"
          key={`${item.label}-${index}`}
          role="listitem"
        >
          {index > 0 ? (
            <Separator className="hidden h-4 sm:block" orientation="vertical" />
          ) : null}
          <ResourceStatusBadge label={item.label} tone={item.tone} />
          {item.value || item.value === 0 ? (
            <span className="min-w-0 truncate font-medium">{item.value}</span>
          ) : null}
          {item.description ? (
            <span className="min-w-0 truncate text-muted-foreground">
              {item.description}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
