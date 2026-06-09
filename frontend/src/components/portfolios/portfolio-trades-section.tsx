import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";

import { formatCurrency, formatDateTime, formatDecimal } from "@/lib/format";
import type { BalanceRead } from "@/lib/types/balance";
import type { PositionRead } from "@/lib/types/position";
import type { TradingOperationRead } from "@/lib/types/trading";

import { ConsoleSection } from "@/components/shared/console-section";
import { DataTable } from "@/components/shared/data-table";
import { DataTableColumnHeader } from "@/components/shared/data-table-column-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { RecordTradingOperationDialog } from "./record-trading-operation-dialog";

type PortfolioTradesSectionProps = {
  portfolioId: number | string;
  balances: BalanceRead[];
  operations: TradingOperationRead[];
  hasPositions: boolean;
  positions: Pick<PositionRead, "name" | "symbol">[];
};

function describeOperation(operation: TradingOperationRead) {
  if (operation.side === "BUY" || operation.side === "SELL") {
    return `${formatDecimal(operation.quantity ?? 0, 4)} @ ${formatCurrency(operation.price ?? 0, operation.currency)}`;
  }

  if (operation.side === "DIVIDEND") {
    return formatCurrency(operation.dividendAmount ?? 0, operation.currency);
  }

  return `Ratio ${operation.splitRatio ?? "-"}`;
}

export function PortfolioTradesSection({
  portfolioId,
  balances,
  operations,
  hasPositions,
  positions,
}: PortfolioTradesSectionProps) {
  const [showForm, setShowForm] = useState(false);
  const depositBalances = useMemo(
    () => balances.filter((balance) => balance.operationType === "DEPOSIT"),
    [balances],
  );
  const sortedOperations = useMemo(
    () => [...operations].sort((left, right) => right.executedAt.localeCompare(left.executedAt)),
    [operations],
  );
  const columns = useMemo<ColumnDef<TradingOperationRead>[]>(
    () => [
      {
        accessorKey: "executedAt",
        cell: ({ row }) => formatDateTime(row.original.executedAt),
        header: ({ column }) => <DataTableColumnHeader column={column} title="Executed" />,
      },
      {
        accessorKey: "symbol",
        cell: ({ row }) => <span className="font-medium">{row.original.symbol}</span>,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Symbol" />,
      },
      {
        accessorKey: "side",
        cell: ({ row }) => <Badge variant="secondary">{row.original.side}</Badge>,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Side" />,
      },
      {
        accessorKey: "balanceLabel",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Balance" />,
      },
      {
        accessorFn: (row) => describeOperation(row),
        cell: ({ row }) => describeOperation(row.original),
        header: ({ column }) => <DataTableColumnHeader column={column} title="Details" />,
        id: "details",
      },
      {
        accessorFn: (row) => Number(row.commission),
        cell: ({ row }) => <span>{formatCurrency(row.original.commission, row.original.currency)}</span>,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Commission" />,
        id: "commission",
      },
    ],
    [],
  );

  return (
    <>
      <ConsoleSection
        actions={(
          <Button
            className="h-8 text-xs"
            disabled={depositBalances.length === 0 && !hasPositions}
            onClick={() => setShowForm(true)}
            size="sm"
          >
            <Plus data-icon="inline-start" /> Add Operation
          </Button>
        )}
        description="Executed operations stay append-only in history while new records use the existing trade form."
        title="Trading Operations"
      >
        <div className="flex flex-col gap-3">
          <DataTable
            columns={columns}
            data={sortedOperations}
            emptyMessage="No operations recorded yet."
            initialSorting={[{ desc: true, id: "executedAt" }]}
          />
        </div>
      </ConsoleSection>
      <RecordTradingOperationDialog
        balances={balances}
        open={showForm}
        onOpenChange={setShowForm}
        portfolioId={portfolioId}
        positions={positions}
      />
    </>
  );
}
