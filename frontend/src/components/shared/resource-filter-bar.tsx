import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/utils";

type ResourceFilterBarItem = {
  active?: boolean;
  clearLabel?: string;
  id: string;
  label: ReactNode;
  value?: ReactNode;
  onClear?: () => void;
};

export type ResourceFilterBarProps = {
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  clearAllLabel?: string;
  items?: readonly ResourceFilterBarItem[];
  summary?: ReactNode;
  testId?: string;
  onClearAll?: () => void;
};

export function ResourceFilterBar({
  actions,
  children,
  className,
  clearAllLabel = "Clear filters",
  items = [],
  summary,
  testId,
  onClearAll,
}: ResourceFilterBarProps) {
  const hasContent = summary || items.length > 0 || actions || children || onClearAll;

  if (!hasContent) {
    return null;
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/70 bg-ui-surface-grouped/70 px-3 py-2 shadow-inner shadow-black/[0.02] dark:shadow-black/20",
        className,
      )}
      data-testid={testId}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {summary ? (
          <span className="text-xs text-muted-foreground">{summary}</span>
        ) : null}
        {items.map((item) => (
          <Badge
            className="gap-1.5"
            data-active={item.active ? "true" : undefined}
            key={item.id}
            variant={item.active ? "default" : "outline"}
          >
            <span>{item.label}</span>
            {item.value ? (
              <span className="font-normal opacity-80">{item.value}</span>
            ) : null}
            {item.onClear ? (
              <Button
                aria-label={item.clearLabel ?? `Clear ${String(item.label)}`}
                className="h-5 px-1 text-xs"
                size="sm"
                type="button"
                variant="ghost"
                onClick={item.onClear}
              >
                Clear
              </Button>
            ) : null}
          </Badge>
        ))}
        {children}
      </div>
      {(actions || onClearAll) ? (
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          {onClearAll ? (
            <Button size="sm" type="button" variant="ghost" onClick={onClearAll}>
              {clearAllLabel}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
