import type { ReactNode } from "react";

import {
  PageContextBar,
  type PageContextBarProps,
} from "@/components/shared/page-context-bar";
import {
  ResourceFilterBar,
  type ResourceFilterBarProps,
} from "@/components/shared/resource-filter-bar";
import {
  ResourceToolbar,
  type ResourceToolbarProps,
} from "@/components/shared/resource-toolbar";
import { cn } from "@/components/ui/utils";

export type InventoryPageShellProps = {
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  filterBar?: ResourceFilterBarProps | null;
  pageContext: PageContextBarProps;
  renderContent?: boolean;
  testId?: string;
  toolbar?: ResourceToolbarProps | null;
};
export function InventoryPageShell({
  children,
  className,
  contentClassName,
  filterBar,
  pageContext,
  renderContent = true,
  testId,
  toolbar,
}: InventoryPageShellProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-4 p-[var(--ui-layout-page-padding)]",
        className,
      )}
      data-testid={testId}
    >
      <div data-inventory-shell-region="context">
        <PageContextBar {...pageContext} />
      </div>
      {toolbar ? (
        <div data-inventory-shell-region="toolbar">
          <ResourceToolbar {...toolbar} />
        </div>
      ) : null}
      {filterBar ? (
        <div data-inventory-shell-region="filters">
          <ResourceFilterBar {...filterBar} />
        </div>
      ) : null}
      {renderContent ? (
        <div
          className={cn("min-w-0", contentClassName)}
          data-inventory-shell-region="content"
          data-slot="inventory-page-shell-content"
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
