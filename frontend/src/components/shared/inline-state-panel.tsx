import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/components/ui/utils";

type InlineStatePanelTone = "neutral" | "warning" | "danger";

export type InlineStatePanelProps = {
  children?: ReactNode;
  className?: string;
  description?: ReactNode;
  icon?: ReactNode;
  testId?: string;
  title?: ReactNode;
  tone?: InlineStatePanelTone;
};

const alertVariantByTone: Record<InlineStatePanelTone, "default" | "destructive"> = {
  neutral: "default",
  warning: "default",
  danger: "destructive",
};

const panelClassByTone: Record<InlineStatePanelTone, string> = {
  neutral: "border-border/70 bg-card/70",
  warning: "border-chart-3/35 bg-chart-3/10",
  danger: "border-destructive/35 bg-destructive/5 text-destructive",
};

export function InlineStatePanel({
  children,
  className,
  description,
  icon,
  testId,
  title,
  tone = "neutral",
}: InlineStatePanelProps) {
  const hasBody = Boolean(title || description || icon);

  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2 text-sm text-muted-foreground shadow-ui-xs",
        "flex flex-col gap-3",
        panelClassByTone[tone],
        className,
      )}
      data-testid={testId}
    >
      {hasBody ? (
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
              className="col-start-1 row-start-1 flex size-7 items-center justify-center rounded-lg bg-muted/50 text-current [&_svg]:size-4"
            >
              {icon}
            </div>
          ) : null}
          {title ? <AlertTitle className={description ? undefined : "line-clamp-none"}>{title}</AlertTitle> : null}
          {description ? <AlertDescription>{description}</AlertDescription> : null}
        </Alert>
      ) : null}
      {children ? <div>{children}</div> : null}
    </div>
  );
}
