import { type ReactNode } from "react";

import { ConsoleSection } from "@/components/shared/console-section";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/components/ui/utils";
import { type LucideIcon } from "lucide-react";

import { formatOptional } from "./shared-helpers";

export type DetailItem = {
  label: string;
  value: ReactNode;
};

export type RunDetailSectionBlockProps = {
  actions?: ReactNode;
  blockId: string;
  cardClassName?: string;
  cardTestId?: string;
  children: ReactNode;
  contentClassName?: string;
  description: ReactNode;
  icon: LucideIcon;
  title: ReactNode;
  tone?: "default" | "muted" | "warning" | "danger";
};

export function RunDetailSectionTitle({
  blockId,
  icon: Icon,
  title,
}: {
  blockId: string;
  icon: LucideIcon;
  title: ReactNode;
}) {
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span
        aria-hidden="true"
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border bg-muted/40 text-muted-foreground"
        data-testid={`runs-detail-section-icon-${blockId}`}
      >
        <Icon className="size-4" />
      </span>
      <span
        className="min-w-0 break-words text-sm font-semibold tracking-tight text-foreground"
        data-testid={`runs-detail-section-title-${blockId}`}
      >
        {title}
      </span>
    </span>
  );
}

export function RunDetailSectionDescription({
  blockId,
  children,
}: {
  blockId: string;
  children: ReactNode;
}) {
  return (
    <span
      className="block text-xs leading-5 text-muted-foreground"
      data-testid={`runs-detail-section-description-${blockId}`}
    >
      {children}
    </span>
  );
}

export function RunDetailSectionBlock({
  actions,
  blockId,
  cardClassName,
  cardTestId,
  children,
  contentClassName,
  description,
  icon,
  title,
  tone = "default",
}: RunDetailSectionBlockProps) {
  return (
    <Collapsible
      className="min-w-0"
      data-run-detail-section-block="true"
      data-testid={`runs-detail-section-${blockId}`}
      defaultOpen={false}
    >
      <ConsoleSection
        actions={
          <div className="flex min-w-0 flex-wrap justify-end gap-2">
            {actions}
            <CollapsibleTrigger asChild>
              <Button
                className="cursor-pointer"
                size="sm"
                type="button"
                variant="outline"
              >
                Toggle
              </Button>
            </CollapsibleTrigger>
          </div>
        }
        className={cardClassName}
        contentClassName={contentClassName}
        description={
          <RunDetailSectionDescription blockId={blockId}>
            {description}
          </RunDetailSectionDescription>
        }
        testId={cardTestId}
        title={
          <RunDetailSectionTitle blockId={blockId} icon={icon} title={title} />
        }
        tone={tone}
      >
        <CollapsibleContent
          className="grid min-w-0 gap-3 data-[state=closed]:hidden"
          forceMount
        >
          {children}
        </CollapsibleContent>
      </ConsoleSection>
    </Collapsible>
  );
}

export function RunDetailEmptyState({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return (
    <div
      className="rounded-md border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground"
      data-testid={testId}
    >
      {children}
    </div>
  );
}

export function RunDetailTableFrame({
  children,
  className,
  testId,
}: {
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 overflow-x-auto rounded-lg border bg-card",
        className,
      )}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

export function CollapsibleConsoleSection({
  blockId,
  children,
  description,
  icon,
  title,
}: {
  blockId: string;
  children: ReactNode;
  description: ReactNode;
  icon: LucideIcon;
  title: ReactNode;
}) {
  return (
    <RunDetailSectionBlock
      blockId={blockId}
      description={description}
      icon={icon}
      title={title}
    >
      {children}
    </RunDetailSectionBlock>
  );
}

export function CollapsibleDetailPanel({
  children,
  description,
  testId,
  title,
}: {
  children: ReactNode;
  description: ReactNode;
  testId: string;
  title: ReactNode;
}) {
  return (
    <Collapsible className="min-w-0" data-testid={testId} defaultOpen={false}>
      <ConsoleSection
        actions={
          <CollapsibleTrigger asChild>
            <Button
              className="cursor-pointer"
              size="sm"
              type="button"
              variant="outline"
            >
              Toggle
            </Button>
          </CollapsibleTrigger>
        }
        description={description}
        title={title}
      >
        <CollapsibleContent
          className="grid min-w-0 gap-3 data-[state=closed]:hidden"
          forceMount
        >
          {children}
        </CollapsibleContent>
      </ConsoleSection>
    </Collapsible>
  );
}

export function DetailGrid({ items }: { items: DetailItem[] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div className="min-w-0 space-y-1" key={item.label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {item.label}
          </dt>
          <dd className="break-words text-foreground">
            {formatOptional(item.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function CompactModeEmptyState({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return <RunDetailEmptyState testId={testId}>{children}</RunDetailEmptyState>;
}
