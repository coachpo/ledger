import { useMemo, useState } from "react";

import { formatCurrency, formatDate, formatDecimal } from "@/lib/format";
import type { BacktestTradeLogEntry } from "@/lib/types/backtest";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type SortField = "cycleDate" | "symbol" | "side" | "quantity" | "price" | "status";

export function TradeLogTable({ trades }: { trades: BacktestTradeLogEntry[] }) {
  const [sortField, setSortField] = useState<SortField>("cycleDate");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  const sortedTrades = useMemo(() => {
    const getComparableValue = (trade: BacktestTradeLogEntry) => {
      switch (sortField) {
        case "symbol":
          return trade.symbol;
        case "side":
          return trade.side;
        case "quantity":
          return Number(trade.quantity ?? 0);
        case "price":
          return Number(trade.executedPrice ?? trade.requestedPrice ?? 0);
        case "status":
          return trade.executed ? "Executed" : trade.failureReason ?? "Failed";
        case "cycleDate":
        default:
          return trade.cycleDate;
      }
    };

    return [...trades].sort((left, right) => {
      const leftValue = getComparableValue(left);
      const rightValue = getComparableValue(right);
      const comparison =
        typeof leftValue === "number" && typeof rightValue === "number"
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue));
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [sortDirection, sortField, trades]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDirection("asc");
  };

  const sortLabel = (field: SortField, label: string) =>
    sortField === field ? `${label} ${sortDirection === "asc" ? "↑" : "↓"}` : label;

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>
              <button type="button" onClick={() => handleSort("cycleDate")}>{sortLabel("cycleDate", "Date")}</button>
            </TableHead>
            <TableHead>
              <button type="button" onClick={() => handleSort("symbol")}>{sortLabel("symbol", "Symbol")}</button>
            </TableHead>
            <TableHead>
              <button type="button" onClick={() => handleSort("side")}>{sortLabel("side", "Action")}</button>
            </TableHead>
            <TableHead>
              <button type="button" onClick={() => handleSort("quantity")}>{sortLabel("quantity", "Qty")}</button>
            </TableHead>
            <TableHead>
              <button type="button" onClick={() => handleSort("price")}>{sortLabel("price", "Price")}</button>
            </TableHead>
            <TableHead>
              <button type="button" onClick={() => handleSort("status")}>{sortLabel("status", "Status")}</button>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sortedTrades.map((trade) => (
            <TableRow key={`${trade.cycleDate}-${trade.symbol}-${trade.side}`}>
              <TableCell>{formatDate(trade.cycleDate)}</TableCell>
              <TableCell>{trade.symbol}</TableCell>
              <TableCell>{trade.side}</TableCell>
              <TableCell>
                {trade.quantity ? formatDecimal(trade.quantity, 0) : "-"}
              </TableCell>
              <TableCell>
                {trade.executedPrice
                  ? formatCurrency(trade.executedPrice)
                  : trade.requestedPrice
                    ? formatCurrency(trade.requestedPrice)
                    : "-"}
              </TableCell>
              <TableCell>
                {trade.executed ? "Executed" : trade.failureReason ?? "Failed"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
