import type { ReactNode } from "react";

import {
  EmptyStatePanel,
  type EmptyStatePanelTone,
} from "@/components/shared/empty-state-panel";
import {
  ResourceStatusStrip,
  type ResourceStatusStripItem,
} from "@/components/shared/resource-status-strip";
import { cn } from "@/components/ui/utils";

type CanonicalErrorPageRootElement = "div" | "main" | "section";

export type CanonicalErrorPageProps = {
  action?: ReactNode;
  contentClassName?: string;
  contentTestId: string;
  description: ReactNode;
  descriptionTestId: string;
  icon?: ReactNode;
  meta: ReactNode;
  metaTestId: string;
  panelDescription?: ReactNode;
  panelTestId: string;
  panelTitle: ReactNode;
  rootClassName?: string;
  rootElement?: CanonicalErrorPageRootElement;
  statusItems: readonly ResourceStatusStripItem[];
  statusTestId: string;
  testId: string;
  title: ReactNode;
  tone?: EmptyStatePanelTone;
};

export function CanonicalErrorPage({
  action,
  contentClassName,
  contentTestId,
  description,
  descriptionTestId,
  icon,
  meta,
  metaTestId,
  panelDescription,
  panelTestId,
  panelTitle,
  rootClassName,
  rootElement: Root = "section",
  statusItems,
  statusTestId,
  testId,
  title,
  tone = "neutral",
}: CanonicalErrorPageProps) {
  return (
    <Root
      className={cn(
        "min-h-screen bg-background px-4 py-8 sm:px-6 sm:py-10 lg:px-8",
        rootClassName,
      )}
      data-testid={testId}
    >
      <div
        className={cn(
          "mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-6xl flex-col justify-center gap-6",
          contentClassName,
        )}
        data-testid={contentTestId}
      >
        <header className="flex w-full min-w-0 flex-col gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-[1.75rem]">
              {title}
            </h1>
            <p
              className="max-w-4xl text-sm leading-6 text-muted-foreground"
              data-testid={descriptionTestId}
            >
              {description}
            </p>
          </div>
          <div className="flex w-full min-w-0 flex-col gap-3">
            <div className="w-full min-w-0" data-testid={statusTestId}>
              <ResourceStatusStrip
                className="w-full max-w-none justify-start flex-wrap"
                items={statusItems}
              />
            </div>
            <div
              className="flex w-full min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground"
              data-testid={metaTestId}
            >
              {meta}
            </div>
          </div>
        </header>
        <EmptyStatePanel
          className="w-full max-w-none"
          action={action}
          description={panelDescription}
          icon={icon}
          testId={panelTestId}
          title={panelTitle}
          tone={tone}
        />
      </div>
    </Root>
  );
}
