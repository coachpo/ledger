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
  neutral: "",
  warning: "border-muted-foreground/40",
  danger: "border-destructive/40",
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
      className={cn("border-dashed", panelClassByTone[tone], className)}
      data-testid={testId}
    >
      <CardContent className="p-4">
        <Alert
          className="border-0 bg-transparent p-0"
          data-tone={tone}
          variant={alertVariantByTone[tone]}
        >
          <AlertTitle>{title}</AlertTitle>
          {description ? <AlertDescription>{description}</AlertDescription> : null}
        </Alert>
        {action ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">{action}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}
