import type { ReactNode } from "react";

import {
  ResourceRowCard,
  type ResourceRowCardDensity,
  type ResourceRowCardPrimaryAction,
} from "@/components/shared/resource-row-card";
import { Badge } from "@/components/ui/badge";

import { formatStatusLabel } from "./platform-resource-helpers";

type PlatformResourceListProps = {
  children: ReactNode;
};

type PlatformResourceCardProps = {
  actions?: ReactNode;
  badges?: ReactNode;
  density?: ResourceRowCardDensity;
  description?: ReactNode;
  evidence?: ReactNode;
  evidenceChips?: ReactNode;
  factsGrid?: ReactNode;
  footer?: ReactNode;
  leading?: ReactNode;
  metadata?: ReactNode;
  primaryAction?: ResourceRowCardPrimaryAction;
  provenance?: ReactNode;
  selected?: boolean;
  statusStrip?: ReactNode;
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
    density = "compactPlus",
    description,
    evidence,
    evidenceChips,
    factsGrid,
    footer,
    leading,
    metadata,
    primaryAction,
    provenance,
    selected = false,
    statusStrip,
    subtitle,
    testId,
    title,
  } = props;

  return (
    <ResourceRowCard
      actions={actions}
      badges={badges}
      bodyAction={primaryAction}
      density={density}
      description={description}
      evidence={evidence}
      evidenceChips={evidenceChips}
      factsGrid={factsGrid}
      footer={footer}
      leading={leading}
      metadata={metadata}
      provenance={provenance}
      selected={selected}
      statusStrip={statusStrip}
      subtitle={subtitle}
      testId={testId}
      title={title}
    />
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
      {typeof version === "number" ? (
        <Badge variant="outline">v{version}</Badge>
      ) : null}
      <Badge variant="secondary" className="capitalize">
        {formatStatusLabel(status)}
      </Badge>
      {extra}
    </div>
  );
}
