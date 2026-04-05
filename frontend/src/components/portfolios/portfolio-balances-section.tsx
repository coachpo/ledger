import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { useCreateBalance, useDeleteBalance, useUpdateBalance } from "@/hooks/use-balances";
import { formatCurrency, formatDateTime } from "@/lib/format";
import { getSignedBalanceAmount } from "@/lib/portfolio-analytics";
import type { BalanceRead, BalanceUpdateInput, BalanceWriteInput } from "@/lib/types/balance";

import { DataTableColumnHeader } from "@/components/shared/data-table-column-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { BalanceFormDialog } from "./balance-form-dialog";
import { ConfirmDeleteDialog } from "./confirm-delete-dialog";
import { PortfolioTableSection } from "./portfolio-table-section";

type PortfolioBalancesSectionProps = {
  portfolioId: number | string;
  balances: BalanceRead[];
};

export function PortfolioBalancesSection({
  portfolioId,
  balances,
}: PortfolioBalancesSectionProps) {
  const createMutation = useCreateBalance(portfolioId);
  const updateMutation = useUpdateBalance(portfolioId);
  const deleteMutation = useDeleteBalance(portfolioId);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<BalanceRead | null>(null);
  const [deleting, setDeleting] = useState<BalanceRead | null>(null);

  const sortedBalances = useMemo(
    () => [...balances].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt)),
    [balances],
  );
  const columns = useMemo<ColumnDef<BalanceRead>[]>(
    () => [
      {
        accessorKey: "label",
        cell: ({ row }) => <span className="font-medium">{row.original.label}</span>,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Label" />,
      },
      {
        accessorKey: "operationType",
        cell: ({ row }) => <Badge variant="secondary">{row.original.operationType}</Badge>,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
      },
      {
        accessorFn: (row) => getSignedBalanceAmount(row) ?? Number.NEGATIVE_INFINITY,
        cell: ({ row }) => {
          const amount = getSignedBalanceAmount(row.original);

          return <span>{amount === null ? "--" : formatCurrency(amount, row.original.currency)}</span>;
        },
        header: ({ column }) => <DataTableColumnHeader column={column} title="Amount" />,
        id: "amount",
      },
      {
        accessorKey: "currency",
        header: ({ column }) => <DataTableColumnHeader column={column} title="Currency" />,
      },
      {
        accessorKey: "updatedAt",
        cell: ({ row }) => formatDateTime(row.original.updatedAt),
        header: ({ column }) => <DataTableColumnHeader column={column} title="Updated" />,
      },
      {
        cell: ({ row }) => (
          <div className="flex">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button aria-label={`Open actions for ${row.original.label}`} size="icon" variant="ghost">
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem
                  onSelect={() => {
                    setEditing(row.original);
                    setShowForm(true);
                  }}
                >
                  <Pencil className="size-4" />
                  Edit balance
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setDeleting(row.original)} variant="destructive">
                  <Trash2 className="size-4" />
                  Delete balance
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
        enableSorting: false,
        id: "actions",
      },
    ],
    [],
  );

  return (
    <PortfolioTableSection
      action={(
        <Button onClick={() => { setEditing(null); setShowForm(true); }}>
          <Plus className="mr-1 size-4" /> Add Balance
        </Button>
      )}
      columns={columns}
      data={sortedBalances}
      emptyMessage="No balances yet."
      initialSorting={[{ desc: true, id: "updatedAt" }]}
      title="Balances"
    >

      <BalanceFormDialog
        open={showForm}
        initial={editing ?? undefined}
        isPending={createMutation.isPending || updateMutation.isPending}
        onOpenChange={(open) => {
          setShowForm(open);
          if (!open) {
            setEditing(null);
          }
        }}
        onSave={(data) => {
          if (editing) {
            updateMutation.mutate(
              { balanceId: editing.id, data: data as BalanceUpdateInput },
              {
                onError: (error) => toast.error(error instanceof Error ? error.message : "Failed to update balance"),
                onSuccess: () => {
                  toast.success("Balance updated");
                  setShowForm(false);
                  setEditing(null);
                },
              },
            );
            return;
          }

          createMutation.mutate(data as BalanceWriteInput, {
            onError: (error) => toast.error(error instanceof Error ? error.message : "Failed to create balance"),
            onSuccess: () => {
              toast.success("Balance created");
              setShowForm(false);
            },
          });
        }}
      />

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        title="Delete balance"
        description={`Delete ${deleting?.label ?? "this balance"}? Existing trading operations remain in history.`}
        isPending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        onConfirm={() => {
          if (!deleting) {
            return;
          }

          deleteMutation.mutate(deleting.id, {
            onError: (error) => toast.error(error instanceof Error ? error.message : "Failed to delete balance"),
            onSuccess: () => {
              toast.success("Balance deleted");
              setDeleting(null);
            },
          });
        }}
      />
    </PortfolioTableSection>
  );
}
