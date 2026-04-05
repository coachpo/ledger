import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";

import { formatCurrency, formatDateTime, formatDecimal } from "@/lib/format";
import type { BalanceRead } from "@/lib/types/balance";
import type { PositionRead } from "@/lib/types/position";
import type { TradingOperationRead } from "@/lib/types/trading";

import { DataTableColumnHeader } from "@/components/shared/data-table-column-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { PortfolioTableSection } from "./portfolio-table-section";
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
    <PortfolioTableSection
      action={(
        <Button onClick={() => setShowForm(true)} disabled={depositBalances.length === 0 && !hasPositions}>
          <Plus className="mr-1 size-4" /> Add Operation
        </Button>
      )}
      columns={columns}
      contentTop={depositBalances.length === 0 ? (
        <div className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
          {hasPositions
            ? "Add a deposit balance for BUY, SELL, or DIVIDEND operations. SPLIT remains available for existing positions."
            : "Add a deposit balance before recording BUY, SELL, or DIVIDEND operations. SPLIT requires an existing position."}
        </div>
      ) : null}
      data={sortedOperations}
      emptyMessage="No operations recorded yet."
      initialSorting={[{ desc: true, id: "executedAt" }]}
      title="Trading Operations"
    >
      <RecordTradingOperationDialog
        balances={balances}
        open={showForm}
        onOpenChange={setShowForm}
        portfolioId={portfolioId}
        positions={positions}
      />
    </PortfolioTableSection>
  );
}
