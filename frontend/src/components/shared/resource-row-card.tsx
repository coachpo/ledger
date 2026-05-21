import type { ReactNode } from "react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type ResourceRowCardPrimaryAction =
  | { kind: "button"; label: string; onClick: () => void; testId?: string }
  | { kind: "link"; label: string; to: string; testId?: string };

export type ResourceRowCardDensity = "compact" | "compactPlus";

type ListCardVariant = "entity" | "grouped";

export type EntityListCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  bodyAction?: ResourceRowCardPrimaryAction;
  className?: string;
  description?: ReactNode;
  leading?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  selected?: boolean;
  subtitle?: ReactNode;
  testId?: string;
  title: ReactNode;
};

export type GroupedListCardProps = EntityListCardProps;

export type ResourceRowCardProps = EntityListCardProps & {
  density?: ResourceRowCardDensity;
};

const contentClassByVariant: Record<ListCardVariant, string> = {
  entity:
    "flex min-w-0 flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between",
  grouped: "flex items-center justify-between gap-3 px-4 py-3",
};

const bodyWrapperClassByVariant: Record<ListCardVariant, string> = {
  entity: "flex min-w-0 flex-1 items-start gap-3",
  grouped: "flex min-w-0 flex-1 items-start gap-3 sm:items-center",
};

const actionsClassByVariant: Record<ListCardVariant, string> = {
  entity:
    "flex w-full flex-wrap gap-2 sm:w-auto sm:shrink-0 sm:justify-end [&_button]:cursor-pointer",
  grouped: "flex shrink-0 items-center gap-1.5 [&_button]:cursor-pointer",
};

const titleClassByVariant: Record<ListCardVariant, string> = {
  entity:
    "min-w-0 break-words text-base font-semibold leading-5 tracking-tight text-foreground",
  grouped:
    "min-w-0 break-words text-sm font-medium leading-5 tracking-tight text-foreground",
};

const descriptionClassByVariant: Record<ListCardVariant, string> = {
  entity: "min-w-0 break-words text-sm text-muted-foreground",
  grouped: "min-w-0 break-words text-xs text-muted-foreground",
};

const legacyContentClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "flex items-center justify-between gap-3 px-4 py-3",
  compactPlus:
    "flex min-w-0 flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between sm:p-4",
};

const legacyActionsClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "flex shrink-0 items-center gap-1.5",
  compactPlus:
    "flex w-full flex-wrap gap-2 sm:w-auto sm:shrink-0 sm:justify-end [&_button]:cursor-pointer",
};

type ListCardBodyProps = Pick<
  EntityListCardProps,
  "badges" | "description" | "metadata" | "subtitle" | "title"
> & {
  className?: string;
  variant: ListCardVariant;
};

function ListCardBody({
  badges,
  className,
  description,
  metadata,
  subtitle,
  title,
  variant,
}: ListCardBodyProps) {
  const descriptionClassName = descriptionClassByVariant[variant];

  return (
    <div className={cn("min-w-0 space-y-1", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className={titleClassByVariant[variant]}>{title}</div>
        {badges ? (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {badges}
          </div>
        ) : null}
      </div>
      {subtitle ? (
        <div className="min-w-0 break-words text-xs text-muted-foreground">
          {subtitle}
        </div>
      ) : null}
      {description ? (
        <div className={descriptionClassName}>{description}</div>
      ) : null}
      {metadata ? (
        <div className="min-w-0 break-words text-xs text-muted-foreground">
          {metadata}
        </div>
      ) : null}
    </div>
  );
}

function renderBody(props: EntityListCardProps, variant: ListCardVariant) {
  const bodyClassName = "min-w-0 flex-1 text-left";
  const action = props.bodyAction ?? props.primaryAction;

  if (action?.kind === "link") {
    return (
      <Link
        aria-label={action.label}
        className={bodyClassName}
        data-testid={action.testId}
        to={action.to}
      >
        <ListCardBody {...props} variant={variant} />
      </Link>
    );
  }

  if (action?.kind === "button") {
    return (
      <div className={cn("relative", bodyClassName)}>
        <div className="[&_a]:relative [&_a]:z-10 [&_button]:relative [&_button]:z-10">
          <ListCardBody {...props} variant={variant} />
        </div>
        <button
          aria-label={action.label}
          className="absolute inset-0 cursor-pointer text-left"
          data-testid={action.testId}
          onClick={action.onClick}
          type="button"
        />
      </div>
    );
  }

  return (
    <div className={bodyClassName}>
      <ListCardBody {...props} variant={variant} />
    </div>
  );
}

type LegacyResourceRowCardBodyProps = Pick<
  ResourceRowCardProps,
  "badges" | "description" | "metadata" | "subtitle" | "title"
> & {
  className?: string;
};

function LegacyResourceRowCardBody({
  badges,
  className,
  description,
  metadata,
  subtitle,
  title,
}: LegacyResourceRowCardBodyProps) {
  return (
    <div className={cn("min-w-0 space-y-0.5", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="min-w-0 break-words text-sm font-medium leading-5 tracking-tight text-foreground">
          {title}
        </div>
        {badges ? (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {badges}
          </div>
        ) : null}
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

function renderLegacyBody(props: ResourceRowCardProps) {
  const bodyClassName = "min-w-0 flex-1 text-left";
  const action = props.bodyAction ?? props.primaryAction;

  if (action?.kind === "link") {
    return (
      <Link
        aria-label={action.label}
        className={bodyClassName}
        data-testid={action.testId}
        to={action.to}
      >
        <LegacyResourceRowCardBody {...props} />
      </Link>
    );
  }

  if (action?.kind === "button") {
    return (
      <div className={cn("relative", bodyClassName)}>
        <div className="[&_a]:relative [&_a]:z-10 [&_button]:relative [&_button]:z-10">
          <LegacyResourceRowCardBody {...props} />
        </div>
        <button
          aria-label={action.label}
          className="absolute inset-0 cursor-pointer text-left"
          data-testid={action.testId}
          onClick={action.onClick}
          type="button"
        />
      </div>
    );
  }

  return (
    <div className={bodyClassName}>
      <LegacyResourceRowCardBody {...props} />
    </div>
  );
}

function BaseListCard({
  actions,
  className,
  leading,
  selected = false,
  testId,
  variant,
  ...bodyProps
}: EntityListCardProps & { variant: ListCardVariant }) {
  return (
    <Card
      className={cn(
        "overflow-hidden transition-colors hover:bg-accent/50 data-[state=selected]:bg-muted",
        className,
      )}
      data-state={selected ? "selected" : undefined}
      data-testid={testId}
    >
      <CardContent className={contentClassByVariant[variant]}>
        <div className={bodyWrapperClassByVariant[variant]}>
          {leading ? <div className="shrink-0 pt-0.5">{leading}</div> : null}
          {renderBody(bodyProps, variant)}
        </div>
        {actions ? (
          <div className={actionsClassByVariant[variant]}>{actions}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function EntityListCard(props: EntityListCardProps) {
  return <BaseListCard {...props} variant="entity" />;
}

export function GroupedListCard(props: GroupedListCardProps) {
  return <BaseListCard {...props} variant="grouped" />;
}

export function ResourceRowCard({
  actions,
  className,
  density = "compact",
  leading,
  selected = false,
  testId,
  ...bodyProps
}: ResourceRowCardProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden transition-colors hover:bg-accent/50 data-[state=selected]:bg-muted",
        className,
      )}
      data-state={selected ? "selected" : undefined}
      data-testid={testId}
    >
      <CardContent className={legacyContentClassByDensity[density]}>
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
          {leading ? <div className="shrink-0 pt-0.5 sm:pt-0">{leading}</div> : null}
          {renderLegacyBody(bodyProps)}
        </div>
        {actions ? (
          <div className={legacyActionsClassByDensity[density]}>{actions}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}
