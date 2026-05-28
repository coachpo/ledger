import type { ReactNode } from "react";

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

const rootClassByDensity: Record<PageContextBarDensity, string> = {
  compact: "gap-3",
  comfortable: "gap-4",
};

function PageContextTitle({ children }: { children: ReactNode }) {
  return (
    <h1
      className="shrink-0 text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl"
      data-slot="page-context-title"
    >
      {children}
    </h1>
  );
}

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
  const placesMetaInMiddle = layout === "toolbar" && toolbarMetaPlacement === "middle";

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col",
        placesMetaInMiddle
          ? "lg:flex-row lg:items-center lg:justify-between"
          : "sm:flex-row sm:items-start sm:justify-between",
        rootClassByDensity[density],
        className,
      )}
      data-slot="page-context-bar"
    >
      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col gap-2",
          placesMetaInMiddle ? "lg:basis-0" : undefined,
        )}
      >
        <div className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-baseline md:gap-4">
          <PageContextTitle>{title}</PageContextTitle>
          {description ? (
            <p
              className={cn(
                "min-w-0 max-w-3xl text-sm leading-6 text-muted-foreground",
                placesMetaInMiddle ? "text-pretty" : undefined,
              )}
              data-slot="page-context-description"
            >
              {description}
            </p>
          ) : null}
        </div>
        {meta && !placesMetaInMiddle ? (
          <div className="min-w-0 text-xs text-muted-foreground" data-slot="page-context-meta">
            {meta}
          </div>
        ) : null}
      </div>
      {meta && placesMetaInMiddle ? (
        <div
          className="flex min-w-0 flex-wrap items-center gap-2 lg:shrink-0 lg:justify-center"
          data-slot="page-context-meta"
        >
          {meta}
        </div>
      ) : null}
      {(status || actions) ? (
        <div
          className={cn(
            "flex min-w-0 flex-wrap items-center gap-2 sm:ml-3 sm:shrink-0 sm:justify-end",
            placesMetaInMiddle ? "lg:ml-3" : undefined,
          )}
          data-slot="page-context-actions"
        >
          {status ? <div className="min-w-0">{status}</div> : null}
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
