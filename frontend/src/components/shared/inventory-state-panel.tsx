import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type InventoryStatePanelTone = "neutral" | "warning" | "danger";

export type InventoryStatePanelProps = {
  action?: ReactNode;
  className?: string;
  description?: ReactNode;
  testId?: string;
  title: ReactNode;
  tone?: InventoryStatePanelTone;
};

const alertVariantByTone: Record<InventoryStatePanelTone, "default" | "destructive"> = {
  neutral: "default",
  warning: "default",
  danger: "destructive",
};

const panelClassByTone: Record<InventoryStatePanelTone, string> = {
  neutral: "border-border/70 bg-card/95",
  warning: "border-chart-3/35 bg-chart-3/10",
  danger: "border-destructive/35 bg-destructive/5",
};

export function InventoryStatePanel({
  action,
  className,
  description,
  testId,
  title,
  tone = "neutral",
}: InventoryStatePanelProps) {
  return (
    <Card
      className={cn(panelClassByTone[tone], className)}
      data-testid={testId}
    >
      <CardContent className="p-4">
        <Alert
          className="border-0 bg-transparent p-0"
          data-tone={tone}
          variant={alertVariantByTone[tone]}
        >
          <AlertTitle className={description ? undefined : "line-clamp-none"}>
            {title}
          </AlertTitle>
          {description ? <AlertDescription>{description}</AlertDescription> : null}
        </Alert>
        {action ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">{action}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}
