import type { ReactNode } from "react";

import {
  ResourceRowCard,
  type ResourceRowCardPrimaryAction,
} from "@/components/shared/resource-row-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

import { formatStatusLabel } from "./platform-resource-helpers";

type PlatformResourceListProps = {
  children: ReactNode;
};

type PlatformResourceCardDensity = "legacy" | "compact" | "compactPlus";

type PlatformResourceCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  density?: PlatformResourceCardDensity;
  description?: ReactNode;
  leading?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  selected?: boolean;
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
    leading,
    metadata,
    primaryAction,
    selected = false,
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
        leading={leading}
        metadata={metadata}
        primaryAction={primaryAction}
        selected={selected}
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
