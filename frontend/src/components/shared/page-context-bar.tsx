import type { ReactNode } from "react";

import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type PageContextBarDensity = "compact" | "comfortable";

export type PageContextBarProps = {
  actions?: ReactNode;
  className?: string;
  description?: ReactNode;
  density?: PageContextBarDensity;
  meta?: ReactNode;
  status?: ReactNode;
  title: ReactNode;
};

const contentClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "px-4 pb-3",
  comfortable: "px-5 pb-4",
};

const headerClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "gap-1.5 px-4 pt-4",
  comfortable: "gap-2 px-5 pt-5",
};

export function PageContextBar({
  actions,
  className,
  density = "compact",
  description,
  meta,
  status,
  title,
}: PageContextBarProps) {
  return (
    <Card className={cn("gap-3", className)}>
      <CardHeader className={headerClassByDensity[density]}>
        <div className="min-w-0">
          <CardTitle className="text-base font-semibold tracking-tight">{title}</CardTitle>
          {description ? (
            <CardDescription className="mt-1 text-xs leading-5">{description}</CardDescription>
          ) : null}
        </div>
        {actions ? <CardAction>{actions}</CardAction> : null}
      </CardHeader>
      {(meta || status) ? (
        <CardContent className={contentClassByDensity[density]}>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            {meta ? <div className="min-w-0 text-xs text-muted-foreground">{meta}</div> : null}
            {status ? <div className="min-w-0 sm:shrink-0">{status}</div> : null}
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}
