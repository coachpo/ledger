import { type ReactNode } from "react";

import { ConsoleSection } from "@/components/shared/console-section";
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
    <div
      className="min-w-0"
      data-run-detail-section-block="true"
      data-testid={`runs-detail-section-${blockId}`}
    >
      <ConsoleSection
        actions={
          actions ? (
            <div className="flex min-w-0 flex-wrap justify-end gap-2">
              {actions}
            </div>
          ) : undefined
        }
        className={cardClassName}
        contentClassName={cn("grid min-w-0 gap-3", contentClassName)}
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
        {children}
      </ConsoleSection>
    </div>
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

export function RunDetailContentSection({
  children,
  className,
  contentClassName,
  description,
  sectionId,
  testId,
  title,
}: {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  description?: ReactNode;
  sectionId?: string;
  testId?: string;
  title: ReactNode;
}) {
  const headingId = sectionId
    ? `runs-detail-content-section-title-${sectionId}`
    : undefined;

  return (
    <section
      aria-labelledby={headingId}
      className={cn("min-w-0 space-y-3", className)}
      data-testid={testId}
    >
      <div className="space-y-1">
        <h3
          className="text-sm font-semibold tracking-tight text-foreground"
          id={headingId}
        >
          {title}
        </h3>
        {description ? (
          <div className="text-xs leading-5 text-muted-foreground">
            {description}
          </div>
        ) : null}
      </div>
      <div className={cn("grid min-w-0 gap-3", contentClassName)}>
        {children}
      </div>
    </section>
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
