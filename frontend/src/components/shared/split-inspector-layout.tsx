import type { ReactNode } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/components/ui/utils";

export type SplitInspectorLayoutDirection = "horizontal" | "vertical";

export type SplitInspectorPanelSize = {
  defaultSize?: number;
  maxSize?: number;
  minSize?: number;
};

export type SplitInspectorLayoutTab<TTab extends string = string> = {
  content: ReactNode;
  disabled?: boolean;
  label: ReactNode;
  value: TTab;
};

export type SplitInspectorLayoutProps<TTab extends string = string> = {
  activeTab?: TTab;
  className?: string;
  direction?: SplitInspectorLayoutDirection;
  emptyInspector: ReactNode;
  inspectorActions?: ReactNode;
  inspectorAriaLabel?: string;
  inspectorOpen?: boolean;
  inspectorTitle?: ReactNode;
  leftPane: ReactNode;
  leftPaneAriaLabel?: string;
  leftPanel?: SplitInspectorPanelSize;
  onActiveTabChange?: (tab: TTab) => void;
  rightPane?: ReactNode;
  rightPanel?: SplitInspectorPanelSize;
  tabs?: readonly SplitInspectorLayoutTab<TTab>[];
  testId?: string;
};

export type SheetInspectorLayoutProps<TTab extends string = string> = Omit<
  SplitInspectorLayoutProps<TTab>,
  "direction" | "leftPanel" | "rightPanel"
> & {
  onInspectorOpenChange?: (open: boolean) => void;
  sheetDescription?: ReactNode;
};

const defaultLeftPanel: Required<SplitInspectorPanelSize> = {
  defaultSize: 34,
  maxSize: 55,
  minSize: 20,
};

const defaultRightPanel: Required<SplitInspectorPanelSize> = {
  defaultSize: 66,
  maxSize: 80,
  minSize: 35,
};

function panelSize(
  defaults: Required<SplitInspectorPanelSize>,
  override?: SplitInspectorPanelSize,
): Required<SplitInspectorPanelSize> {
  return {
    defaultSize: override?.defaultSize ?? defaults.defaultSize,
    maxSize: override?.maxSize ?? defaults.maxSize,
    minSize: override?.minSize ?? defaults.minSize,
  };
}

function InspectorHeader({
  actions,
  title,
}: {
  actions?: ReactNode;
  title?: ReactNode;
}) {
  if (!actions && !title) {
    return null;
  }

  return (
    <div className="flex min-w-0 items-start justify-between gap-3">
      {title ? (
        <div className="min-w-0 break-words text-sm font-semibold tracking-tight">
          {title}
        </div>
      ) : (
        <span aria-hidden="true" />
      )}
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : null}
    </div>
  );
}

function renderPlainInspector({
  actions,
  content,
  title,
}: {
  actions?: ReactNode;
  content: ReactNode;
  title?: ReactNode;
}) {
  const hasHeader = Boolean(actions || title);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      {hasHeader ? (
        <div className="shrink-0 border-b border-border/70 bg-ui-surface-chrome px-4 py-3 backdrop-blur-xl">
          <InspectorHeader actions={actions} title={title} />
        </div>
      ) : null}
      <div className="min-h-0 min-w-0 flex-1 overflow-auto p-4">
        {content}
      </div>
    </div>
  );
}

function renderEmptyInspector(content: ReactNode) {
  return (
    <div
      className="flex h-full min-h-0 min-w-0 flex-col overflow-auto p-4"
      data-testid="split-inspector-empty"
    >
      {content}
    </div>
  );
}

type InspectorContentProps<TTab extends string> = Pick<
  SplitInspectorLayoutProps<TTab>,
  | "activeTab"
  | "emptyInspector"
  | "inspectorActions"
  | "inspectorOpen"
  | "inspectorTitle"
  | "onActiveTabChange"
  | "rightPane"
  | "tabs"
>;

function renderInspectorContent<TTab extends string = string>({
  activeTab,
  emptyInspector,
  inspectorActions,
  inspectorOpen = true,
  inspectorTitle,
  onActiveTabChange,
  rightPane,
  tabs,
}: InspectorContentProps<TTab>) {
  const selectedTab = activeTab ?? tabs?.[0]?.value;

  if (!inspectorOpen) {
    return renderEmptyInspector(emptyInspector);
  }

  if (tabs && tabs.length > 0 && selectedTab) {
    return (
      <Tabs
        className="flex h-full min-h-0 min-w-0 flex-col gap-0"
        onValueChange={(value) => onActiveTabChange?.(value as TTab)}
        value={selectedTab}
      >
        <div className="flex shrink-0 flex-col gap-3 border-b border-border/70 bg-ui-surface-chrome px-4 py-3 backdrop-blur-xl">
          <InspectorHeader actions={inspectorActions} title={inspectorTitle} />
          <TabsList className="h-8 max-w-full justify-start overflow-x-auto">
            {tabs.map((tab) => (
              <TabsTrigger
                className="px-3 text-xs"
                disabled={tab.disabled}
                key={tab.value}
                value={tab.value}
              >
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {tabs.map((tab) => (
          <TabsContent
            className="m-0 min-h-0 flex-1 overflow-auto p-4 data-[state=inactive]:hidden"
            key={tab.value}
            value={tab.value}
          >
            {tab.content}
          </TabsContent>
        ))}
      </Tabs>
    );
  }

  return renderPlainInspector({
    actions: inspectorActions,
    content: rightPane ?? emptyInspector,
    title: inspectorTitle,
  });
}

export function SplitInspectorLayout<TTab extends string = string>({
  activeTab,
  className,
  direction = "horizontal",
  emptyInspector,
  inspectorActions,
  inspectorAriaLabel = "Inspector panel",
  inspectorOpen = true,
  inspectorTitle,
  leftPane,
  leftPaneAriaLabel = "Inspector source panel",
  leftPanel,
  onActiveTabChange,
  rightPane,
  rightPanel,
  tabs,
  testId = "split-inspector-layout",
}: SplitInspectorLayoutProps<TTab>) {
  const leftSize = panelSize(defaultLeftPanel, leftPanel);
  const rightSize = panelSize(defaultRightPanel, rightPanel);
  const inspectorContent = renderInspectorContent({
    activeTab,
    emptyInspector,
    inspectorActions,
    inspectorOpen,
    inspectorTitle,
    onActiveTabChange,
    rightPane,
    tabs,
  });

  return (
    <ResizablePanelGroup
      className={cn(
        "h-full min-h-0 min-w-0 overflow-hidden rounded-xl border border-border/70 bg-card/95 shadow-ui-xs",
        className,
      )}
      data-inspector-state={inspectorOpen ? "open" : "closed"}
      data-testid={testId}
      direction={direction}
    >
      <ResizablePanel className="min-h-0 min-w-0" {...leftSize}>
        <section
          aria-label={leftPaneAriaLabel}
          className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
          data-testid="split-inspector-left-pane"
        >
          {leftPane}
        </section>
      </ResizablePanel>
      <ResizableHandle
        className="bg-border/70"
        data-testid="split-inspector-resize-handle"
        withHandle
      />
      <ResizablePanel className="min-h-0 min-w-0" {...rightSize}>
        <aside
          aria-label={inspectorAriaLabel}
          className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-ui-surface-grouped/50"
          data-testid="split-inspector-right-pane"
        >
          {inspectorContent}
        </aside>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

export function SheetInspectorLayout<TTab extends string = string>({
  activeTab,
  className,
  emptyInspector,
  inspectorActions,
  inspectorAriaLabel = "Inspector sheet",
  inspectorOpen = true,
  inspectorTitle,
  leftPane,
  leftPaneAriaLabel = "Inspector source panel",
  onActiveTabChange,
  onInspectorOpenChange,
  rightPane,
  sheetDescription,
  tabs,
  testId = "sheet-inspector-layout",
}: SheetInspectorLayoutProps<TTab>) {
  const inspectorContent = renderInspectorContent({
    activeTab,
    emptyInspector,
    inspectorActions,
    inspectorOpen,
    inspectorTitle,
    onActiveTabChange,
    rightPane,
    tabs,
  });

  return (
    <div
      className={cn(
        "h-full min-h-0 min-w-0 overflow-hidden rounded-xl border border-border/70 bg-card/95 shadow-ui-xs",
        className,
      )}
      data-inspector-mode="sheet"
      data-inspector-state={inspectorOpen ? "open" : "closed"}
      data-testid={testId}
    >
      <section
        aria-label={leftPaneAriaLabel}
        className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden"
        data-testid="split-inspector-left-pane"
      >
        {leftPane}
      </section>
      <Sheet onOpenChange={onInspectorOpenChange} open={inspectorOpen}>
        <SheetContent
          aria-label={inspectorAriaLabel}
          className="w-full gap-0 p-0 sm:max-w-md"
          data-testid="split-inspector-sheet"
        >
          <SheetHeader className="sr-only">
            <SheetTitle>{inspectorTitle ?? "Inspector panel"}</SheetTitle>
            {sheetDescription ? (
              <SheetDescription>{sheetDescription}</SheetDescription>
            ) : null}
          </SheetHeader>
          <div
            className="min-h-0 flex-1 overflow-hidden"
            data-testid="split-inspector-sheet-body"
          >
            {inspectorContent}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
