import { useCallback, useMemo, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { PortfolioFormDialog } from "@/components/forms/portfolio-form-dialog";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ResourceFilterBar } from "@/components/shared/resource-filter-bar";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResourceFilterState } from "@/hooks/use-resource-filter-state";
import { useResourceSelectionState } from "@/hooks/use-resource-selection-state";
import {
  useCreatePortfolio,
  useDeletePortfolio,
  useDeletePortfolios,
  usePortfolios,
  useUpdatePortfolio,
} from "@/hooks/use-portfolios";
import { formatDateTime } from "@/lib/format";
import type {
  PortfolioRead,
  PortfolioUpdateInput,
  PortfolioWriteInput,
} from "@/lib/types/portfolio";

export function PortfolioListPage() {
  const navigate = useNavigate();
  const portfoliosQuery = usePortfolios();
  const createMutation = useCreatePortfolio();
  const updateMutation = useUpdatePortfolio();
  const deleteMutation = useDeletePortfolio();
  const deletePortfoliosMutation = useDeletePortfolios();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PortfolioRead | null>(null);
  const [deleting, setDeleting] = useState<PortfolioRead | null>(null);

  const portfolios = useMemo(
    () =>
      [...(portfoliosQuery.data ?? [])].sort((left, right) =>
        right.updatedAt.localeCompare(left.updatedAt),
      ),
    [portfoliosQuery.data],
  );
  const portfolioSearchText = useCallback(
    (portfolio: PortfolioRead) =>
      [
        portfolio.name,
        portfolio.description,
        portfolio.baseCurrency,
        String(portfolio.positionCount),
        String(portfolio.balanceCount),
      ].join(" "),
    [],
  );
  const {
    filteredItems: filteredPortfolios,
    hasActiveFilters,
    search,
    resetAll: resetPortfolioFilters,
    setSearch,
  } = useResourceFilterState<PortfolioRead>({
    items: portfolios,
    searchText: portfolioSearchText,
  });
  const getPortfolioId = useCallback(
    (portfolio: PortfolioRead) => portfolio.id,
    [],
  );
  const {
    allSelected: allFilteredSelected,
    selectedCount,
    selectedItems: selectedPortfolios,
    someSelected: someFilteredSelected,
    clearSelection,
    isSelected,
    setIdsSelected,
    setItemsSelected,
  } = useResourceSelectionState<PortfolioRead, PortfolioRead["id"]>({
    getId: getPortfolioId,
    items: filteredPortfolios,
  });

  const openCreateDialog = useCallback(() => {
    setEditing(null);
    setShowForm(true);
  }, []);

  const handleDeleteSelected = () => {
    if (selectedPortfolios.length === 0) {
      return;
    }

    const portfolioIds = selectedPortfolios.map((portfolio) => portfolio.id);
    const count = selectedPortfolios.length;
    deletePortfoliosMutation.mutate(portfolioIds, {
      onError: (error) =>
        toast.error(
          error instanceof Error
            ? error.message
            : "Failed to delete portfolios",
        ),
      onSuccess: () => {
        toast.success(
          `${count} ${count === 1 ? "portfolio" : "portfolios"} deleted`,
        );
        clearSelection();
      },
    });
  };

  return (
    <InventoryPageShell
      filterBar={
        hasActiveFilters
          ? {
              testId: "portfolios-active-filters",
              items: [
                {
                  active: true,
                  clearLabel: "Clear portfolio search",
                  id: "search",
                  label: "Search",
                  value: search.trim(),
                  onClear: resetPortfolioFilters,
                },
              ],
              onClearAll: resetPortfolioFilters,
            }
          : null
      }
      pageContext={{
        actions: (
          <Button size="sm" type="button" onClick={openCreateDialog}>
            <Plus data-icon="inline-start" /> New Portfolio
          </Button>
        ),
        description: "Manage portfolios.",
        title: "Portfolios",
      }}
      testId="portfolios-list-page"
      toolbar={{
        resultSummary:
          portfoliosQuery.isPending || portfoliosQuery.isError
            ? undefined
            : `${filteredPortfolios.length} of ${portfolios.length} portfolios shown`,
        search: {
          id: "portfolio-search",
          label: "Search portfolios",
          name: "portfolioSearch",
          placeholder: "Search portfolios by name, currency, or holdings...",
          value: search,
          onChange: setSearch,
        },
      }}
    >
      <section
        aria-label="Portfolio inventory"
        className="grid gap-2 sm:gap-3"
        data-testid="portfolios-inventory"
      >
        {portfoliosQuery.isPending ? (
          <InventoryStatePanel
            description="Fetching the latest portfolio records."
            testId="portfolios-loading-state"
            title="Loading portfolios..."
          />
        ) : null}
        {portfoliosQuery.isError ? (
          <InventoryStatePanel
            description={
              portfoliosQuery.error instanceof Error
                ? portfoliosQuery.error.message
                : "Failed to load portfolios."
            }
            testId="portfolios-error-state"
            title="Failed to load portfolios."
            tone="danger"
          />
        ) : null}
        {!portfoliosQuery.isPending &&
        !portfoliosQuery.isError &&
        portfolios.length === 0 ? (
          <InventoryStatePanel
            action={
              <Button size="sm" type="button" onClick={openCreateDialog}>
                <Plus data-icon="inline-start" /> New Portfolio
              </Button>
            }
            description="Create a portfolio to start tracking positions, balances, and trades."
            testId="portfolios-empty-state"
            title="No portfolios yet."
          />
        ) : null}
        {!portfoliosQuery.isPending &&
        !portfoliosQuery.isError &&
        portfolios.length > 0 &&
        filteredPortfolios.length === 0 ? (
          <InventoryStatePanel
            action={
              <Button
                size="sm"
                type="button"
                variant="outline"
                onClick={resetPortfolioFilters}
              >
                Clear search
              </Button>
            }
            description="Clear the search to return to the full portfolio inventory."
            testId="portfolios-filtered-empty-state"
            title="No portfolios match your search."
          />
        ) : null}
        {filteredPortfolios.length > 0 ? (
          <ResourceTableFrame>
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="w-9">
                    <Checkbox
                      aria-label="Select all shown portfolios"
                      checked={
                        allFilteredSelected
                          ? true
                          : someFilteredSelected
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={(checked) =>
                        setItemsSelected(filteredPortfolios, checked === true)
                      }
                    />
                  </TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Currency</TableHead>
                  <TableHead>Holdings</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredPortfolios.map((portfolio) => {
                  const isPortfolioSelected = isSelected(portfolio.id);

                  return (
                    <TableRow
                      key={portfolio.id}
                      data-state={isPortfolioSelected ? "selected" : undefined}
                    >
                      <TableCell>
                        <Checkbox
                          aria-label={`Select portfolio ${portfolio.name}`}
                          checked={isPortfolioSelected}
                          onCheckedChange={(checked) =>
                            setItemsSelected([portfolio], checked === true)
                          }
                        />
                      </TableCell>
                      <TableCell className="min-w-56 whitespace-normal">
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">
                            {portfolio.name}
                          </p>
                          <p className="line-clamp-2 text-xs text-muted-foreground">
                            {portfolio.description || "No description"}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {portfolio.baseCurrency}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {portfolio.positionCount} positions ·{" "}
                        {portfolio.balanceCount} balances
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(portfolio.updatedAt)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1.5">
                          <Button asChild size="sm">
                            <Link
                              aria-label={`Open portfolio ${portfolio.name}`}
                              to={`/portfolios/${portfolio.id}`}
                            >
                              Open
                            </Link>
                          </Button>
                          <Button
                            aria-label={`Edit portfolio ${portfolio.name}`}
                            size="sm"
                            type="button"
                            variant="outline"
                            onClick={() => {
                              setEditing(portfolio);
                              setShowForm(true);
                            }}
                          >
                            <Pencil data-icon="inline-start" />
                            Edit
                          </Button>
                          <Button
                            aria-label={`Delete portfolio ${portfolio.name}`}
                            size="sm"
                            type="button"
                            variant="destructive"
                            onClick={() => setDeleting(portfolio)}
                          >
                            <Trash2 data-icon="inline-start" />
                            Delete
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ResourceTableFrame>
        ) : null}
      </section>

      {selectedCount > 0 ? (
        <ResourceFilterBar
          actions={
            <>
              <Button
                size="sm"
                type="button"
                variant="destructive"
                disabled={deletePortfoliosMutation.isPending}
                onClick={handleDeleteSelected}
              >
                <Trash2 data-icon="inline-start" /> Delete selected
              </Button>
              <Button
                size="sm"
                type="button"
                variant="ghost"
                onClick={clearSelection}
              >
                Clear
              </Button>
            </>
          }
          summary={`${selectedCount} of ${filteredPortfolios.length} portfolios selected`}
          testId="portfolios-bulk-actions"
        />
      ) : null}

      <PortfolioFormDialog
        open={showForm}
        initial={editing ?? undefined}
        isPending={createMutation.isPending || updateMutation.isPending}
        onOpenChange={(open) => {
          setShowForm(open);
          if (!open) {
            setEditing(null);
          }
        }}
        onSave={async (data) => {
          if (editing) {
            updateMutation.mutate(
              { portfolioId: editing.id, data: data as PortfolioUpdateInput },
              {
                onError: (error) =>
                  toast.error(
                    error instanceof Error
                      ? error.message
                      : "Failed to update portfolio",
                  ),
                onSuccess: () => {
                  toast.success("Portfolio updated");
                  setShowForm(false);
                  setEditing(null);
                },
              },
            );
            return;
          }

          try {
            const portfolio = await createMutation.mutateAsync(
              data as PortfolioWriteInput,
            );
            toast.success("Portfolio created");
            setShowForm(false);
            navigate(`/portfolios/${portfolio.id}`);
          } catch (error) {
            toast.error(
              error instanceof Error
                ? error.message
                : "Failed to create portfolio",
            );
          }
        }}
      />

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        title="Delete portfolio"
        description={`Delete ${deleting?.name ?? "this portfolio"}? This cannot be undone.`}
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
            onError: (error) =>
              toast.error(
                error instanceof Error
                  ? error.message
                  : "Failed to delete portfolio",
              ),
            onSuccess: () => {
              toast.success("Portfolio deleted");
              setDeleting(null);
              setIdsSelected([deleting.id], false);
            },
          });
        }}
      />
    </InventoryPageShell>
  );
}
