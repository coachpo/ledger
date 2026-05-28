import type { ReactNode } from "react";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type PageContextBarDensity = "compact" | "comfortable";
export type PageContextBarLayout = "stacked" | "toolbar";
export type PageContextBarToolbarMetaPlacement = "below" | "middle";

export type PageContextBarProps = {
  actions?: ReactNode;
  className?: string;
  description?: ReactNode;
  density?: PageContextBarDensity;
  layout?: PageContextBarLayout;
  meta?: ReactNode;
  status?: ReactNode;
  title: ReactNode;
  toolbarMetaPlacement?: PageContextBarToolbarMetaPlacement;
};

const contentClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "px-4 pb-3",
  comfortable: "px-5 pb-4",
};

const headerClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "gap-1.5 px-4 pt-4",
  comfortable: "gap-2 px-5 pt-5",
};

const toolbarContentClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "gap-3 p-3 sm:px-4",
  comfortable: "gap-4 p-4 sm:px-5",
};

export function PageContextBar({
  actions,
  className,
  density = "compact",
  description,
  layout = "stacked",
  meta,
  status,
  title,
  toolbarMetaPlacement = "below",
}: PageContextBarProps) {
  if (layout === "toolbar") {
    const placesMetaInMiddle = toolbarMetaPlacement === "middle";

    return (
      <Card className={cn("gap-0", className)}>
        <CardContent
          className={cn(
            "flex min-w-0 flex-col",
            placesMetaInMiddle
              ? "gap-3 lg:flex-row lg:items-center lg:justify-between"
              : "sm:flex-row sm:items-center sm:justify-between",
            toolbarContentClassByDensity[density],
          )}
        >
          <div
            className={cn(
              "min-w-0 flex-1 space-y-0.5",
              placesMetaInMiddle ? "lg:basis-0" : undefined,
            )}
          >
            <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-3">
              <CardTitle className="shrink-0 text-base font-semibold leading-6 tracking-tight">
                {title}
              </CardTitle>
              {description ? (
                <CardDescription
                  className={cn(
                    "min-w-0 text-xs leading-5 sm:text-[13px]",
                    placesMetaInMiddle ? "text-pretty" : "truncate",
                  )}
                >
                  {description}
                </CardDescription>
              ) : null}
            </div>
            {meta && !placesMetaInMiddle ? (
              <div className="truncate text-xs text-muted-foreground">
                {meta}
              </div>
            ) : null}
          </div>
          {meta && placesMetaInMiddle ? (
            <div className="flex min-w-0 flex-wrap items-center gap-2 lg:shrink-0 lg:justify-center">
              {meta}
            </div>
          ) : null}
          {(status || actions) ? (
            <div
              className={cn(
                "flex min-w-0 flex-wrap items-center gap-2",
                placesMetaInMiddle
                  ? "lg:ml-3 lg:shrink-0 lg:justify-end"
                  : "sm:ml-3 sm:justify-end",
              )}
            >
              {status ? <div className="min-w-0">{status}</div> : null}
              {actions ? <div className="shrink-0">{actions}</div> : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={cn("gap-3", className)}>
      <CardHeader className={headerClassByDensity[density]}>
        <div className="min-w-0">
          <CardTitle className="text-base font-semibold tracking-tight">
            {title}
          </CardTitle>
          {description ? (
            <CardDescription className="mt-1 text-xs leading-5">
              {description}
            </CardDescription>
          ) : null}
        </div>
        {actions ? <CardAction>{actions}</CardAction> : null}
      </CardHeader>
      {meta || status ? (
        <CardContent className={contentClassByDensity[density]}>
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            {meta ? (
              <div className="min-w-0 text-xs text-muted-foreground">
                {meta}
              </div>
            ) : null}
            {status ? (
              <div className="min-w-0 sm:shrink-0">{status}</div>
            ) : null}
          </div>
        </CardContent>
      ) : null}
    </Card>
  );
}
