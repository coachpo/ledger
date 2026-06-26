import type { DataTableColumnInstance } from "./data-table";
import { useId } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/utils";

export type DataTableColumnHeaderDensity = "comfortable" | "compact";

type DataTableColumnHeaderProps = {
  className?: string;
  column: DataTableColumnInstance;
  density?: DataTableColumnHeaderDensity;
  title: string;
};

const headerClassByDensity: Record<DataTableColumnHeaderDensity, string> = {
  comfortable: "-ml-3 h-8 px-3",
  compact: "-ml-2 h-8 px-2 text-xs font-medium",
};

export function DataTableColumnHeader({
  className,
  column,
  density = "comfortable",
  title,
}: DataTableColumnHeaderProps) {
  const titleId = useId();

  if (!column.getCanSort()) {
    return <div className={cn(className)}>{title}</div>;
  }

  const sorted = column.getIsSorted();
  const Icon =
    sorted === "asc" ? ArrowUp : sorted === "desc" ? ArrowDown : ArrowUpDown;
  const sortLabel = sorted
    ? `Sort column (${sorted === "asc" ? "ascending" : "descending"})`
    : "Sort column";
  const sortTitle = sorted
    ? `Sort by ${title} (${sorted === "asc" ? "ascending" : "descending"})`
    : `Sort by ${title}`;

  return (
    <Button
      aria-describedby={titleId}
      aria-label={sortLabel}
      className={cn(headerClassByDensity[density], className)}
      onClick={() => column.toggleSorting(sorted === "asc")}
      size="sm"
      title={sortTitle}
      type="button"
      variant="ghost"
    >
      <span id={titleId}>{title}</span>
      <Icon aria-hidden="true" />
    </Button>
  );
}
