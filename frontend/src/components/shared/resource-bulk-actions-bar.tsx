import type { ReactNode } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";

import { ResourceFilterBar } from "./resource-filter-bar";

export type ResourceBulkActionsBarProps = {
  clearLabel?: ReactNode;
  deleteLabel?: ReactNode;
  deletePending?: boolean;
  resourceLabel: string;
  selectedCount: number;
  summary?: ReactNode;
  testId?: string;
  totalCount: number;
  onClear: () => void;
  onDeleteSelected: () => void;
};

export function ResourceBulkActionsBar({
  clearLabel = "Clear",
  deleteLabel = "Delete selected",
  deletePending = false,
  resourceLabel,
  selectedCount,
  summary,
  testId,
  totalCount,
  onClear,
  onDeleteSelected,
}: ResourceBulkActionsBarProps) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <ResourceFilterBar
      actions={
        <>
          <Button
            disabled={deletePending}
            size="sm"
            type="button"
            variant="destructive"
            onClick={onDeleteSelected}
          >
            <Trash2 data-icon="inline-start" />
            {deleteLabel}
          </Button>
          <Button size="sm" type="button" variant="ghost" onClick={onClear}>
            {clearLabel}
          </Button>
        </>
      }
      summary={
        summary ?? `${selectedCount} of ${totalCount} ${resourceLabel} selected`
      }
      testId={testId}
    />
  );
}
