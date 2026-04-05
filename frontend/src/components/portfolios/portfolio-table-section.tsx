import type { ReactNode } from "react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";

import { DataTable } from "@/components/shared/data-table";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type PortfolioTableSectionProps<TData, TValue> = {
  action?: ReactNode;
  children?: ReactNode;
  columns: ColumnDef<TData, TValue>[];
  contentTop?: ReactNode;
  data: TData[];
  emptyMessage: string;
  headerContent?: ReactNode;
  initialPageSize?: number;
  initialSorting?: SortingState;
  title: string;
};

export function PortfolioTableSection<TData, TValue>({
  action,
  children,
  columns,
  contentTop,
  data,
  emptyMessage,
  headerContent,
  initialPageSize = 10,
  initialSorting = [],
  title,
}: PortfolioTableSectionProps<TData, TValue>) {
  return (
    <>
      <Card>
        <CardHeader>
          <div className="space-y-2">
            <CardTitle>{title}</CardTitle>
            {headerContent}
          </div>
          {action ? <CardAction>{action}</CardAction> : null}
        </CardHeader>
        <CardContent className={contentTop ? "space-y-4" : undefined}>
          {contentTop}
          <DataTable
            columns={columns}
            data={data}
            emptyMessage={emptyMessage}
            initialPageSize={initialPageSize}
            initialSorting={initialSorting}
          />
        </CardContent>
      </Card>
      {children}
    </>
  );
}
