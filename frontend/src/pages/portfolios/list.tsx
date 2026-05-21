import { useMemo, useState } from "react";
import {
  LayoutGrid,
  List,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

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

import { EntityListCard } from "@/components/shared/resource-row-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { PortfolioFormDialog } from "@/components/forms/portfolio-form-dialog";

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
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");
  const [selectedPortfolioIds, setSelectedPortfolioIds] = useState<
    Set<PortfolioRead["id"]>
  >(new Set());

  const portfolios = useMemo(
    () =>
      [...(portfoliosQuery.data ?? [])].sort((left, right) =>
        right.updatedAt.localeCompare(left.updatedAt),
      ),
    [portfoliosQuery.data],
  );
  const filteredPortfolios = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return portfolios;
    }

    return portfolios.filter((portfolio) =>
      [
        portfolio.name,
        portfolio.description,
        portfolio.baseCurrency,
        String(portfolio.positionCount),
        String(portfolio.balanceCount),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [portfolios, search]);
  const selectedPortfolios = useMemo(
    () =>
      filteredPortfolios.filter((portfolio) =>
        selectedPortfolioIds.has(portfolio.id),
      ),
    [filteredPortfolios, selectedPortfolioIds],
  );
  const selectedCount = selectedPortfolios.length;
  const allFilteredSelected =
    filteredPortfolios.length > 0 &&
    filteredPortfolios.every((portfolio) =>
      selectedPortfolioIds.has(portfolio.id),
    );
  const someFilteredSelected = filteredPortfolios.some((portfolio) =>
    selectedPortfolioIds.has(portfolio.id),
  );

  const setPortfoliosSelected = (
    portfoliosToUpdate: readonly PortfolioRead[],
    selected: boolean,
  ) => {
    setSelectedPortfolioIds((previous) => {
      const next = new Set(previous);
      portfoliosToUpdate.forEach((portfolio) => {
        if (selected) {
          next.add(portfolio.id);
        } else {
          next.delete(portfolio.id);
        }
      });
      return next;
    });
  };

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
        setSelectedPortfolioIds(new Set());
      },
    });
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Portfolios</h1>
          <p className="text-sm text-muted-foreground">
            Manage live portfolio records and jump into detailed position,
            balance, and trade views.
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
        >
          <Plus data-icon="inline-start" /> New Portfolio
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1" role="search">
          <Label htmlFor="portfolio-search" className="sr-only">
            Search portfolios
          </Label>
          <Search
            className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="portfolio-search"
            name="portfolioSearch"
            placeholder="Search portfolios by name, currency, or holdings..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(value) => {
            if (!value) return;
            setViewMode(value as "cards" | "table");
            if (value === "cards") setSelectedPortfolioIds(new Set());
          }}
        >
          <ToggleGroupItem
            value="cards"
            aria-label="Cards view"
            className="h-8 w-8 px-0"
          >
            <LayoutGrid className="size-3.5" />
          </ToggleGroupItem>
          <ToggleGroupItem
            value="table"
            aria-label="Table view"
            className="h-8 w-8 px-0"
          >
            <List className="size-3.5" />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div className="grid gap-2 sm:gap-3">
        {portfoliosQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              Loading portfolios...
            </CardContent>
          </Card>
        ) : null}
        {portfoliosQuery.isError ? (
          <Card role="alert">
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              {portfoliosQuery.error instanceof Error
                ? portfoliosQuery.error.message
                : "Failed to load portfolios."}
            </CardContent>
          </Card>
        ) : null}
        {!portfoliosQuery.isPending &&
        !portfoliosQuery.isError &&
        portfolios.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No portfolios yet.
            </CardContent>
          </Card>
        ) : null}
        {!portfoliosQuery.isPending &&
        !portfoliosQuery.isError &&
        portfolios.length > 0 &&
        filteredPortfolios.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No portfolios match your search.
            </CardContent>
          </Card>
        ) : null}
        {viewMode === "cards"
          ? filteredPortfolios.map((portfolio) => (
              <EntityListCard
                key={portfolio.id}
                title={portfolio.name}
                badges={
                  <>
                    <Badge variant="outline">{portfolio.baseCurrency}</Badge>
                    <Badge variant="outline">
                      {portfolio.positionCount} pos
                    </Badge>
                    <Badge variant="outline">
                      {portfolio.balanceCount} bal
                    </Badge>
                  </>
                }
                description={portfolio.description || "No description"}
                metadata={<>Updated {formatDateTime(portfolio.updatedAt)}</>}
                primaryAction={{
                  kind: "link",
                  label: `Open portfolio ${portfolio.name}`,
                  to: `/portfolios/${portfolio.id}`,
                }}
                actions={
                  <>
                    <Button asChild size="sm">
                      <Link to={`/portfolios/${portfolio.id}`}>Open</Link>
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          aria-label={`Open actions for ${portfolio.name}`}
                          size="icon"
                          type="button"
                          variant="ghost"
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => {
                            setEditing(portfolio);
                            setShowForm(true);
                          }}
                        >
                          <Pencil className="size-3.5" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={() => setDeleting(portfolio)}
                          variant="destructive"
                        >
                          <Trash2 className="size-3.5" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </>
                }
              />
            ))
          : null}
        {viewMode === "table" && filteredPortfolios.length > 0 ? (
          <div className="rounded-md border">
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
                        setPortfoliosSelected(
                          filteredPortfolios,
                          checked === true,
                        )
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
                  const isSelected = selectedPortfolioIds.has(portfolio.id);

                  return (
                    <TableRow
                      key={portfolio.id}
                      data-state={isSelected ? "selected" : undefined}
                    >
                      <TableCell>
                        <Checkbox
                          aria-label={`Select portfolio ${portfolio.name}`}
                          checked={isSelected}
                          onCheckedChange={(checked) =>
                            setPortfoliosSelected([portfolio], checked === true)
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
          </div>
        ) : null}
      </div>

      {viewMode === "table" && selectedCount > 0 ? (
        <div
          data-testid="portfolios-bulk-actions"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
        >
          <span className="text-xs text-muted-foreground">
            {selectedCount} of {filteredPortfolios.length} portfolios selected
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="destructive"
              disabled={deletePortfoliosMutation.isPending}
              onClick={handleDeleteSelected}
            >
              <Trash2 className="size-3.5" /> Delete selected
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedPortfolioIds(new Set())}
            >
              Clear
            </Button>
          </div>
        </div>
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
              setSelectedPortfolioIds((previous) => {
                const next = new Set(previous);
                next.delete(deleting.id);
                return next;
              });
            },
          });
        }}
      />
    </div>
  );
}
