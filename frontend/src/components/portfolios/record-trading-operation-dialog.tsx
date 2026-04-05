import { useMemo } from "react";
import { toast } from "sonner";

import { useCreateTradingOperation } from "@/hooks/use-trading-operations";
import type { BalanceRead } from "@/lib/types/balance";
import type { PositionRead } from "@/lib/types/position";
import type { TradingOperationInput } from "@/lib/types/trading";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { TradingOperationForm } from "./trading-operation-form";

type RecordTradingOperationDialogProps = {
  balances: BalanceRead[];
  initialSymbol?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  portfolioId: number | string;
  positions: Pick<PositionRead, "name" | "symbol">[];
};

export function RecordTradingOperationDialog({
  balances,
  initialSymbol,
  open,
  onOpenChange,
  portfolioId,
  positions,
}: RecordTradingOperationDialogProps) {
  const createMutation = useCreateTradingOperation(portfolioId);
  const depositBalances = useMemo(
    () => balances
      .filter((balance) => balance.operationType === "DEPOSIT")
      .sort((left, right) => Number(right.amount) - Number(left.amount)),
    [balances],
  );
  const symbolOptions = useMemo(
    () => {
      const seenSymbols = new Set<string>();

      return positions
        .map((position) => ({
          label: position.name
            ? `${position.symbol} (${position.name})`
            : position.symbol,
          symbol: position.symbol,
        }))
        .filter((option) => {
          if (seenSymbols.has(option.symbol)) {
            return false;
          }

          seenSymbols.add(option.symbol);
          return true;
        })
        .sort((left, right) => left.symbol.localeCompare(right.symbol));
    },
    [positions],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Record Trading Operation</DialogTitle>
        </DialogHeader>
        <TradingOperationForm
          key={initialSymbol ?? "new-operation"}
          balances={depositBalances}
          initialSymbol={initialSymbol}
          isPending={createMutation.isPending}
          onCancel={() => onOpenChange(false)}
          symbolOptions={symbolOptions}
          onSave={(data: TradingOperationInput) => {
            createMutation.mutate(data, {
              onError: (error) => toast.error(error instanceof Error ? error.message : "Failed to create operation"),
              onSuccess: () => {
                toast.success("Operation recorded");
                onOpenChange(false);
              },
            });
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
