import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/components/ui/utils";

export type DataTableDensity = "comfortable" | "compact";

type DataTableSortDirection = "asc" | "desc";

export type DataTableSortingState = {
  desc: boolean;
  id: string;
}[];

export type DataTableRow<TData> = {
  index: number;
  original: TData;
};

export type DataTableHeaderContext = {
  column: DataTableColumnInstance;
};

export type DataTableCellContext<TData> = {
  getValue: () => unknown;
  row: DataTableRow<TData>;
  value: unknown;
};

export type DataTableColumn<TData> = {
  accessorFn?: (row: TData) => unknown;
  accessorKey?: keyof TData & string;
  cell?: (context: DataTableCellContext<TData>) => ReactNode;
  enableSorting?: boolean;
  header?:
    | ReactNode
    | ((context: DataTableHeaderContext) => ReactNode)
    | string;
  id?: string;
};

export type DataTableColumnInstance = {
  getCanSort: () => boolean;
  getIsSorted: () => false | DataTableSortDirection;
  id: string;
  toggleSorting: (desc?: boolean) => void;
};

type ResolvedColumn<TData> = {
  id: string;
  original: DataTableColumn<TData>;
  canSort: boolean;
  resolver: (row: TData) => unknown;
};

type DataTableProps<TData> = {
  className?: string;
  columns: DataTableColumn<TData>[];
  data: TData[];
  density?: DataTableDensity;
  emptyMessage: string;
  getRowTestId?: (row: DataTableRow<TData>) => string | undefined;
  initialSorting?: DataTableSortingState;
  tableLabel?: string;
};

const tableContainerClassByDensity: Record<DataTableDensity, string> = {
  comfortable:
    "overflow-x-auto rounded-xl border border-border/70 bg-card/95 shadow-ui-xs",
  compact:
    "min-w-0 max-w-full overflow-x-auto rounded-xl border border-border/70 bg-card/95 shadow-ui-xs",
};

const tableCellClassByDensity: Record<DataTableDensity, string> = {
  comfortable: "",
  compact: "py-2 text-xs",
};

export function DataTable<TData>({
  className,
  columns,
  data,
  density = "comfortable",
  emptyMessage,
  getRowTestId,
  initialSorting = [],
  tableLabel,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<DataTableSortingState>(initialSorting);

  const resolvedColumns = useMemo<ResolvedColumn<TData>[]>(() => {
    return columns.map((column, index) => {
      const accessorKey = column.accessorKey;

      return {
        canSort: column.enableSorting !== false && Boolean(accessorKey || column.accessorFn),
        id: column.id ?? String(accessorKey ?? `column-${index}`),
        original: column,
        resolver: column.accessorFn
          ? column.accessorFn
          : accessorKey
            ? (row: TData) => (row as Record<string, unknown>)[accessorKey]
            : () => undefined,
      };
    });
  }, [columns]);

  const sortColumnInstance = (column: ResolvedColumn<TData>): DataTableColumnInstance => ({
    getCanSort: () => column.canSort,
    getIsSorted: () => {
      if (!sorting.length || sorting[0].id !== column.id) {
        return false;
      }

      return sorting[0].desc ? "desc" : "asc";
    },
    id: column.id,
    toggleSorting: (desc = false) => {
      setSorting((current) => {
        if (!current.length || current[0].id !== column.id) {
          return [{ desc, id: column.id }];
        }

        if (current[0].desc === desc) {
          return [{ ...current[0], desc: !current[0].desc }];
        }

        return [{ ...current[0], desc }];
      });
    },
  });

  const sortedData = useMemo(() => {
    const activeSorting = sorting[0];
    if (!activeSorting) {
      return data;
    }

    const activeColumn = resolvedColumns.find((column) => column.id === activeSorting.id);
    if (!activeColumn || !activeColumn.canSort) {
      return data;
    }

    const direction = activeSorting.desc ? -1 : 1;

    return [...data].sort((left, right) => {
      const leftValue = activeColumn.resolver(left);
      const rightValue = activeColumn.resolver(right);

      if (leftValue === rightValue) {
        return 0;
      }
      if (leftValue == null) {
        return 1 * direction;
      }
      if (rightValue == null) {
        return -1 * direction;
      }

      if (typeof leftValue === "number" && typeof rightValue === "number") {
        if (Number.isNaN(leftValue) && Number.isNaN(rightValue)) {
          return 0;
        }
        if (Number.isNaN(leftValue)) {
          return 1 * direction;
        }
        if (Number.isNaN(rightValue)) {
          return -1 * direction;
        }

        return leftValue < rightValue ? -1 * direction : 1 * direction;
      }

      return String(leftValue).localeCompare(String(rightValue)) * direction;
    });
  }, [data, resolvedColumns, sorting]);
  const rows = useMemo(
    () =>
      sortedData.map((rowData, rowIndex) => {
        const row: DataTableRow<TData> = {
          index: rowIndex,
          original: rowData,
        };

        return (
          <TableRow key={rowIndex} data-state={undefined} data-testid={getRowTestId?.(row)}>
            {resolvedColumns.map((column) => {
              const value = column.resolver(rowData);
              const cell =
                column.original.cell == null
                  ? (value as ReactNode)
                  : column.original.cell({
                      getValue: () => value,
                      row,
                      value,
                    });

              return (
                <TableCell
                  className={tableCellClassByDensity[density]}
                  key={`${column.id}-${rowIndex}`}
                >
                  {cell}
                </TableCell>
              );
            })}
          </TableRow>
        );
      }),
    [resolvedColumns, sortedData, density, getRowTestId],
  );

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div className={tableContainerClassByDensity[density]}>
        <Table aria-label={tableLabel}>
          <TableHeader>
            <TableRow>
              {resolvedColumns.map((column) => (
                <TableHead key={column.id}>
                  {typeof column.original.header === "function"
                    ? column.original.header({ column: sortColumnInstance(column) })
                    : column.original.header ?? null}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length ? rows : (
              <TableRow>
                <TableCell
                  className="h-28 text-center text-muted-foreground"
                  colSpan={resolvedColumns.length}
                >
                  {emptyMessage}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
