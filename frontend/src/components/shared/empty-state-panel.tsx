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
  title: ReactNode;
  tone?: EmptyStatePanelTone;
};

const alertVariantByTone: Record<EmptyStatePanelTone, "default" | "destructive"> = {
  neutral: "default",
  warning: "default",
  danger: "destructive",
};

const panelClassByTone: Record<EmptyStatePanelTone, string> = {
  neutral: "",
  warning: "border-muted-foreground/40",
  danger: "border-destructive/40",
};

export function EmptyStatePanel({
  action,
  className,
  description,
  icon,
  title,
  tone = "neutral",
}: EmptyStatePanelProps) {
  return (
    <Card className={cn("border-dashed", panelClassByTone[tone], className)}>
      <CardContent className="p-4">
        <Alert
          className={cn(
            "border-0 bg-transparent p-0",
            icon ? "grid-cols-[calc(var(--spacing)*4)_1fr] gap-x-3" : null,
          )}
          data-tone={tone}
          variant={alertVariantByTone[tone]}
        >
          {icon ? (
            <div aria-hidden="true" className="col-start-1 row-start-1 size-4 translate-y-0.5 text-current [&>svg]:size-4">
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
