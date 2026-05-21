import { useMemo, useState } from "react";
import { MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useCreatePortfolio,
  useDeletePortfolio,
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { PortfolioFormDialog } from "@/components/forms/portfolio-form-dialog";

export function PortfolioListPage() {
  const navigate = useNavigate();
  const portfoliosQuery = usePortfolios();
  const createMutation = useCreatePortfolio();
  const updateMutation = useUpdatePortfolio();
  const deleteMutation = useDeletePortfolio();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PortfolioRead | null>(null);
  const [deleting, setDeleting] = useState<PortfolioRead | null>(null);
  const [search, setSearch] = useState("");

  const portfolios = useMemo(
    () =>
      [...(portfoliosQuery.data ?? [])].sort((left, right) =>
        right.updatedAt.localeCompare(left.updatedAt),
      ),
    [portfoliosQuery.data],
  );
  const query = search.trim().toLowerCase();
  const filteredPortfolios = !query
    ? portfolios
    : portfolios.filter((portfolio) =>
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
        {filteredPortfolios.map((portfolio) => (
          <EntityListCard
            key={portfolio.id}
            title={portfolio.name}
            badges={
              <>
                <Badge variant="outline">{portfolio.baseCurrency}</Badge>
                <Badge variant="outline">{portfolio.positionCount} pos</Badge>
                <Badge variant="outline">{portfolio.balanceCount} bal</Badge>
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
        ))}
      </div>

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
            },
          });
        }}
      />
    </div>
  );
}
