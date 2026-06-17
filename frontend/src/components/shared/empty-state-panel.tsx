import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type EmptyStatePanelTone = "neutral" | "warning" | "danger";

export type EmptyStatePanelProps = {
  action?: ReactNode;
  className?: string;
  description?: ReactNode;
  icon?: ReactNode;
  testId?: string;
  title: ReactNode;
  tone?: EmptyStatePanelTone;
};

const alertVariantByTone: Record<EmptyStatePanelTone, "default" | "destructive"> = {
  neutral: "default",
  warning: "default",
  danger: "destructive",
};

const panelClassByTone: Record<EmptyStatePanelTone, string> = {
  neutral: "border-border/70 bg-card/95",
  warning: "border-chart-3/35 bg-chart-3/10",
  danger: "border-destructive/35 bg-destructive/5",
};

export function EmptyStatePanel({
  action,
  className,
  description,
  icon,
  testId,
  title,
  tone = "neutral",
}: EmptyStatePanelProps) {
  return (
    <Card className={cn(panelClassByTone[tone], className)} data-testid={testId}>
      <CardContent className="p-4">
        <Alert
          className={cn(
            "border-0 bg-transparent p-0",
            icon ? "grid-cols-[calc(var(--spacing)*7)_1fr] gap-x-3" : null,
          )}
          data-tone={tone}
          variant={alertVariantByTone[tone]}
        >
          {icon ? (
            <div
              aria-hidden="true"
              className="col-start-1 row-start-1 flex size-7 items-center justify-center rounded-lg bg-muted/50 text-current [&>svg]:size-4"
            >
              {icon}
            </div>
          ) : null}
          <AlertTitle>{title}</AlertTitle>
          {description ? <AlertDescription>{description}</AlertDescription> : null}
        </Alert>
        {action ? <div className="mt-3 flex flex-wrap items-center gap-2">{action}</div> : null}
      </CardContent>
    </Card>
  );
}
