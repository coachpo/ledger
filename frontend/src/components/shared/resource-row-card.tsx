import type { ReactNode } from "react";
import { Link } from "react-router";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type ResourceRowCardPrimaryAction = {
  kind: "link";
  label: string;
  to: string;
  testId?: string;
};

export type ResourceRowCardDensity = "compact" | "compactPlus";

type ListCardVariant = "entity" | "grouped";

export type EntityListCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  bodyAction?: ResourceRowCardPrimaryAction;
  className?: string;
  description?: ReactNode;
  evidence?: ReactNode;
  footer?: ReactNode;
  leading?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  provenance?: ReactNode;
  selected?: boolean;
  statusStrip?: ReactNode;
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

const subtitleClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "min-w-0 break-words text-[11px] text-muted-foreground",
  compactPlus: "min-w-0 break-words text-xs text-muted-foreground",
};

const descriptionClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "min-w-0 break-words text-[11px] text-muted-foreground",
  compactPlus: "min-w-0 break-words text-sm text-muted-foreground",
};

const metadataClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "min-w-0 break-words text-[11px] text-muted-foreground",
  compactPlus: "min-w-0 break-words text-xs text-muted-foreground",
};

const footerClassByDensity: Record<ResourceRowCardDensity, string> = {
  compact: "min-w-0 pt-1 text-[11px] text-muted-foreground",
  compactPlus: "min-w-0 pt-1 text-xs text-muted-foreground",
};

const titleActionLinkClassName =
  "rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function renderTitleAction(
  title: ReactNode,
  action?: ResourceRowCardPrimaryAction,
) {
  if (!action) {
    return title;
  }

  return (
    <Link
      aria-label={action.label}
      className={titleActionLinkClassName}
      data-testid={action.testId}
      to={action.to}
    >
      {title}
    </Link>
  );
}

type ListCardBodyProps = Pick<
  EntityListCardProps,
  | "badges"
  | "description"
  | "evidence"
  | "footer"
  | "metadata"
  | "provenance"
  | "statusStrip"
  | "subtitle"
  | "title"
> & {
  className?: string;
  titleAction?: ResourceRowCardPrimaryAction;
  variant: ListCardVariant;
};

function ListCardBody({
  badges,
  className,
  description,
  evidence,
  footer,
  metadata,
  provenance,
  statusStrip,
  subtitle,
  title,
  titleAction,
  variant,
}: ListCardBodyProps) {
  const descriptionClassName = descriptionClassByVariant[variant];

  return (
    <div className={cn("min-w-0 space-y-1", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className={titleClassByVariant[variant]}>
          {renderTitleAction(title, titleAction)}
        </div>
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
      {(statusStrip || provenance) ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {statusStrip}
          {provenance}
        </div>
      ) : null}
      {evidence ? <div className="min-w-0">{evidence}</div> : null}
      {footer ? <div className="min-w-0 text-xs text-muted-foreground">{footer}</div> : null}
    </div>
  );
}

function renderBody(props: EntityListCardProps, variant: ListCardVariant) {
  const action = props.bodyAction ?? props.primaryAction;

  return (
    <div className="min-w-0 flex-1 text-left">
      <ListCardBody {...props} titleAction={action} variant={variant} />
    </div>
  );
}

type ResourceRowCardBodyProps = Pick<
  ResourceRowCardProps,
  | "badges"
  | "description"
  | "evidence"
  | "footer"
  | "metadata"
  | "provenance"
  | "statusStrip"
  | "subtitle"
  | "title"
> & {
  className?: string;
  density: ResourceRowCardDensity;
  titleAction?: ResourceRowCardPrimaryAction;
};

function ResourceRowCardBody({
  badges,
  className,
  density,
  description,
  evidence,
  footer,
  metadata,
  provenance,
  statusStrip,
  subtitle,
  title,
  titleAction,
}: ResourceRowCardBodyProps) {
  return (
    <div className={cn("min-w-0 space-y-0.5", className)}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <div className="min-w-0 break-words text-sm font-medium leading-5 tracking-tight text-foreground">
          {renderTitleAction(title, titleAction)}
        </div>
        {badges ? (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {badges}
          </div>
        ) : null}
      </div>
      {subtitle ? <div className={subtitleClassByDensity[density]}>{subtitle}</div> : null}
      {description ? <div className={descriptionClassByDensity[density]}>{description}</div> : null}
      {metadata ? <div className={metadataClassByDensity[density]}>{metadata}</div> : null}
      {(statusStrip || provenance) ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2 pt-1">
          {statusStrip}
          {provenance}
        </div>
      ) : null}
      {evidence ? <div className="min-w-0 pt-1">{evidence}</div> : null}
      {footer ? <div className={footerClassByDensity[density]}>{footer}</div> : null}
    </div>
  );
}

function renderResourceRowBody(
  props: ResourceRowCardProps,
  density: ResourceRowCardDensity,
) {
  const action = props.bodyAction ?? props.primaryAction;

  return (
    <div className="min-w-0 flex-1 text-left">
      <ResourceRowCardBody {...props} density={density} titleAction={action} />
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
      <CardContent className={contentClassByDensity[density]}>
        <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
          {leading ? <div className="shrink-0 pt-0.5 sm:pt-0">{leading}</div> : null}
          {renderResourceRowBody(bodyProps, density)}
        </div>
        {actions ? (
          <div className={actionsClassByDensity[density]}>{actions}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}
