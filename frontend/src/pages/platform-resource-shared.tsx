import type { ReactNode } from "react";

import {
  ResourceRowCard,
  type ResourceRowCardPrimaryAction,
} from "@/components/shared/resource-row-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

export {
  parseJsonValue,
  parseLineList,
  stringifyJson,
  toLineList,
} from "@/lib/platform-authoring/common/serialization";
export {
  parseVersionedRef,
  parseVersionedRefs,
  toVersionedRefValue,
  type ResourceRef,
} from "@/lib/platform-authoring/common/resource-ref";

type PlatformResourceListProps = {
  children: ReactNode;
};

type PlatformResourceCardDensity = "legacy" | "compact" | "compactPlus";

type PlatformResourceCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  density?: PlatformResourceCardDensity;
  description?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  subtitle?: ReactNode;
  testId: string;
  title: ReactNode;
};

export function PlatformResourceList(props: PlatformResourceListProps) {
  const { children } = props;

  return <div className="grid gap-2 sm:gap-3">{children}</div>;
}

export function PlatformResourceCard(props: PlatformResourceCardProps) {
  const {
    actions,
    badges,
    density = "legacy",
    description,
    metadata,
    primaryAction,
    subtitle,
    testId,
    title,
  } = props;

  if (density !== "legacy") {
    return (
      <ResourceRowCard
        actions={actions}
        badges={badges}
        density={density}
        description={description}
        metadata={metadata}
        primaryAction={primaryAction}
        subtitle={subtitle}
        testId={testId}
        title={title}
      />
    );
  }

  return (
    <Card data-testid={testId} className="overflow-hidden">
      <CardContent className="p-3 sm:p-4">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="space-y-1">
              <div className="flex min-w-0 items-center gap-1.5">
                <div className="min-w-0 truncate text-base font-medium text-foreground">{title}</div>
                {badges ? <div className="shrink-0">{badges}</div> : null}
              </div>
              {subtitle ? (
                <div className="break-all text-sm text-muted-foreground">{subtitle}</div>
              ) : null}
            </div>
            {description ? (
              <p className="break-words text-sm text-muted-foreground">{description}</p>
            ) : null}
            {metadata ? <div>{metadata}</div> : null}
          </div>
          {actions ? (
            <div className="flex w-full flex-wrap gap-2 lg:w-auto lg:shrink-0 lg:justify-end [&_button]:cursor-pointer">
              {actions}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function sortByKey<T extends { key: string }>(items: readonly T[]): T[] {
  return [...items].sort((left, right) => left.key.localeCompare(right.key));
}

export function parseRequiredText(label: string, value: string): string {
  const trimmed = value.trim();

  if (!trimmed) {
    throw new Error(`${label} is required.`);
  }

  return trimmed;
}

export function parseOptionalNumber(
  label: string,
  value: string,
  options: { integer?: boolean; min?: number } = {},
): number | undefined {
  const trimmed = value.trim();

  if (!trimmed) {
    return undefined;
  }

  const parsed = Number(trimmed);

  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} must be a number.`);
  }

  if (options.integer && !Number.isInteger(parsed)) {
    throw new Error(`${label} must be a whole number.`);
  }

  if (options.min !== undefined && parsed < options.min) {
    throw new Error(`${label} must be at least ${options.min}.`);
  }

  return parsed;
}

export function formatStatusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export function PlatformResourceBadges(props: {
  extra?: ReactNode;
  status: string;
  version?: number;
}) {
  const { extra, status, version } = props;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {typeof version === "number" ? <Badge variant="outline">v{version}</Badge> : null}
      <Badge variant="secondary" className="capitalize">
        {formatStatusLabel(status)}
      </Badge>
      {extra}
    </div>
  );
}
