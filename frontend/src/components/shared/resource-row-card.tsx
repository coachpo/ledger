import type { ReactNode } from "react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type ResourceRowCardPrimaryAction =
  | { kind: "button"; label: string; onClick: () => void; testId?: string }
  | { kind: "link"; label: string; to: string; testId?: string };

export type ResourceRowCardDensity = "compact" | "compactPlus";

export type ResourceRowCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  className?: string;
  density?: ResourceRowCardDensity;
  description?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  subtitle?: ReactNode;
  testId?: string;
  title: ReactNode;
};

const contentClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "flex items-center justify-between gap-3 px-4 py-3",
  compactPlus:
    "flex min-w-0 flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4",
};

const actionsClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "flex shrink-0 items-center gap-1.5",
  compactPlus:
    "flex w-full flex-wrap gap-2 sm:w-auto sm:shrink-0 sm:justify-end [&_button]:cursor-pointer",
};

type ResourceRowCardBodyProps = Pick<
  ResourceRowCardProps,
  "badges" | "description" | "metadata" | "subtitle" | "title"
> & {
  className?: string;
};

function ResourceRowCardBody({
  badges,
  className,
  description,
  metadata,
  subtitle,
  title,
}: ResourceRowCardBodyProps) {
  return (
    <div className={cn("min-w-0 space-y-0.5", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="min-w-0 break-words text-sm font-medium leading-5 tracking-tight text-foreground">
          {title}
        </div>
        {badges ? <div className="flex min-w-0 flex-wrap items-center gap-1.5">{badges}</div> : null}
      </div>
      {subtitle ? (
        <div className="min-w-0 break-words text-[11px] text-muted-foreground">
          {subtitle}
        </div>
      ) : null}
      {description ? (
        <div className="min-w-0 break-words text-[11px] text-muted-foreground">
          {description}
        </div>
      ) : null}
      {metadata ? (
        <div className="min-w-0 break-words text-[11px] text-muted-foreground">
          {metadata}
        </div>
      ) : null}
    </div>
  );
}

function renderPrimaryBody(props: ResourceRowCardProps) {
  const bodyClassName = "min-w-0 flex-1 text-left";

  if (props.primaryAction?.kind === "link") {
    return (
      <Link
        aria-label={props.primaryAction.label}
        className={bodyClassName}
        data-testid={props.primaryAction.testId}
        to={props.primaryAction.to}
      >
        <ResourceRowCardBody {...props} />
      </Link>
    );
  }

  if (props.primaryAction?.kind === "button") {
    return (
      <div className={cn("relative", bodyClassName)}>
        <div className="[&_a]:relative [&_a]:z-10 [&_button]:relative [&_button]:z-10">
          <ResourceRowCardBody {...props} />
        </div>
        <button
          aria-label={props.primaryAction.label}
          className="absolute inset-0 cursor-pointer text-left"
          data-testid={props.primaryAction.testId}
          onClick={props.primaryAction.onClick}
          type="button"
        />
      </div>
    );
  }

  return (
    <div className={bodyClassName}>
      <ResourceRowCardBody {...props} />
    </div>
  );
}
export function ResourceRowCard({
  actions,
  className,
  density = "compact",
  testId,
  ...bodyProps
}: ResourceRowCardProps) {
  return (
    <Card
      className={cn("overflow-hidden transition-colors hover:bg-accent/50", className)}
      data-testid={testId}
    >
      <CardContent className={contentClassByDensity[density]}>
        {renderPrimaryBody({ ...bodyProps, density })}
        {actions ? <div className={actionsClassByDensity[density]}>{actions}</div> : null}
      </CardContent>
    </Card>
  );
}
