import { MoreHorizontal, Plus, SquarePen, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { useInventoryViewState } from "@/hooks/use-inventory-view-state";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";
import {
  PROTOCOL_PROFILE_DESCRIPTIONS,
  PROTOCOL_PROFILE_LABELS,
  formatCapabilityDetails,
  formatCapabilitySummary,
  formatRuntimePolicyEvidence,
  getModelConnectionEvidenceItems,
  getModelConnectionStatusItems,
} from "./model-connection-ui";

type ModelConnectionSelectionHandlers = {
  onDelete: (connection: ModelConnectionListItemRead) => void;
  onSelect: (
    connectionsToUpdate: readonly ModelConnectionListItemRead[],
    selected: boolean,
  ) => void;
};

function sortConnections(items: readonly ModelConnectionListItemRead[]) {
  return [...items].sort((left, right) => {
    const byName = left.name.localeCompare(right.name);
    return byName !== 0 ? byName : left.modelId.localeCompare(right.modelId);
  });
}

function filterConnections(
  items: readonly ModelConnectionListItemRead[],
  search: string,
) {
  const query = search.trim().toLowerCase();
  if (!query) {
    return items;
  }

  return items.filter((connection) =>
    [
      connection.name,
      connection.key,
      connection.modelId,
      connection.description,
      connection.baseUrl,
      connection.protocolProfile,
      PROTOCOL_PROFILE_LABELS[connection.protocolProfile],
      PROTOCOL_PROFILE_DESCRIPTIONS[connection.protocolProfile],
      formatCapabilitySummary(connection.capabilities),
      formatCapabilityDetails(connection),
      formatRuntimePolicyEvidence(connection),
      connection.lastTestMessage ?? "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
}

function ModelConnectionEvidence({
  connection,
  labels,
  layout = "grid",
}: {
  connection: ModelConnectionListItemRead;
  labels?: readonly string[];
  layout?: "grid" | "list" | "inline";
}) {
  const items = getModelConnectionEvidenceItems(connection).filter((item) =>
    labels ? labels.includes(String(item.label)) : true,
  );

  return <EvidenceCluster items={items} layout={layout} />;
}

function ModelConnectionsPageActions() {
  return (
    <Button asChild data-testid="model-connections-new" size="sm">
      <Link to="/model-connections/new">
        <Plus data-icon="inline-start" />
        New Model Connection
      </Link>
    </Button>
  );
}

function ModelConnectionsStateCards({
  error,
  isError,
  isPending,
  filteredCount,
  search,
}: {
  error: unknown;
  isError: boolean;
  isPending: boolean;
  filteredCount: number;
  search: string;
}) {
  if (isPending) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Loading model connections...
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card role="alert" aria-live="polite">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          {error instanceof Error
            ? error.message
            : "Failed to load model connections."}
        </CardContent>
      </Card>
    );
  }

  if (filteredCount > 0) {
    return null;
  }

  return (
    <Card>
      <CardContent className="space-y-1 py-8 text-center text-sm text-muted-foreground">
        <p className="font-medium text-foreground">
          {search.trim()
            ? "No model connections match this search."
            : "No model connections exist yet."}
        </p>
        <p className="text-xs">
          {search.trim()
            ? "Refine the search by connection name, stable key, model, or base URL."
            : "Create a saved endpoint before launching workflow packages that need model access."}
        </p>
      </CardContent>
    </Card>
  );
}

function ModelConnectionsCards({
  connections,
  deletePending,
  onDelete,
}: {
  connections: readonly ModelConnectionListItemRead[];
  deletePending: boolean;
  onDelete: (connection: ModelConnectionListItemRead) => void;
}) {
  return (
    <PlatformResourceList>
      {connections.map((connection) => (
        <PlatformResourceCard
          key={connection.id}
          density="compactPlus"
          testId={`model-connections-row-${connection.id}`}
          title={connection.name}
          subtitle={connection.modelId}
          description={connection.description || "No description provided."}
          provenance={
            <ProvenanceBadge label="Stable key" detail={connection.key} />
          }
          statusStrip={
            <ResourceStatusStrip
              items={getModelConnectionStatusItems(connection)}
            />
          }
          evidence={<ModelConnectionEvidence connection={connection} />}
          actions={
            <ModelConnectionActions
              connection={connection}
              deletePending={deletePending}
              onDelete={onDelete}
            />
          }
        />
      ))}
    </PlatformResourceList>
  );
}

function ModelConnectionActions({
  connection,
  deletePending,
  onDelete,
}: {
  connection: ModelConnectionListItemRead;
  deletePending: boolean;
  onDelete: (connection: ModelConnectionListItemRead) => void;
}) {
  return (
    <>
      <Button asChild size="sm">
        <Link
          aria-label={`Edit model connection ${connection.name}`}
          data-testid={`model-connections-open-${connection.id}`}
          to={`/model-connections/${connection.id}/edit`}
        >
          <SquarePen data-icon="inline-start" />
          Edit
        </Link>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={`Open actions for model connection ${connection.name}`}
            className="cursor-pointer"
            size="icon"
            type="button"
            variant="ghost"
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            data-testid={`model-connections-delete-${connection.id}`}
            disabled={deletePending}
            onSelect={() => onDelete(connection)}
            variant="destructive"
          >
            <Trash2 className="size-3.5" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}

function ModelConnectionsTable({
  allFilteredSelected,
  connections,
  deletePending,
  selectedConnectionIds,
  someFilteredSelected,
  onDelete,
  onSelect,
}: {
  allFilteredSelected: boolean;
  connections: readonly ModelConnectionListItemRead[];
  deletePending: boolean;
  selectedConnectionIds: ReadonlySet<ModelConnectionListItemRead["id"]>;
  someFilteredSelected: boolean;
} & ModelConnectionSelectionHandlers) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="w-9">
            <Checkbox
              aria-label="Select all shown model connections"
              checked={
                allFilteredSelected
                  ? true
                  : someFilteredSelected
                    ? "indeterminate"
                    : false
              }
              onCheckedChange={(checked) =>
                onSelect(connections, checked === true)
              }
            />
          </TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Stable key</TableHead>
          <TableHead>Model ID</TableHead>
          <TableHead>Protocol profile</TableHead>
          <TableHead>Capability summary</TableHead>
          <TableHead>Test state</TableHead>
          <TableHead>Runtime policy</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {connections.map((connection) => {
          const isSelected = selectedConnectionIds.has(connection.id);

          return (
            <TableRow
              key={connection.id}
              data-state={isSelected ? "selected" : undefined}
              data-testid={`model-connections-row-${connection.id}`}
            >
              <TableCell>
                <Checkbox
                  aria-label={`Select model connection ${connection.name}`}
                  checked={isSelected}
                  onCheckedChange={(checked) =>
                    onSelect([connection], checked === true)
                  }
                />
              </TableCell>
              <TableCell className="min-w-56 whitespace-normal">
                <div className="flex flex-col gap-1">
                  <p className="font-medium text-foreground">
                    {connection.name}
                  </p>
                  <p className="line-clamp-2 text-xs text-muted-foreground">
                    {connection.description || "No description provided."}
                  </p>
                </div>
              </TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">
                {connection.key}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {connection.modelId}
              </TableCell>
              <TableCell className="min-w-64 whitespace-normal text-xs text-muted-foreground">
                <ModelConnectionEvidence
                  connection={connection}
                  labels={["Protocol profile"]}
                  layout="list"
                />
              </TableCell>
              <TableCell className="min-w-64 whitespace-normal text-xs text-muted-foreground">
                {formatCapabilitySummary(connection.capabilities)}
              </TableCell>
              <TableCell className="min-w-64 whitespace-normal text-xs text-muted-foreground">
                <ModelConnectionEvidence
                  connection={connection}
                  labels={["Test state", "Reachability"]}
                  layout="list"
                />
              </TableCell>
              <TableCell className="min-w-72 whitespace-normal text-xs text-muted-foreground">
                {formatRuntimePolicyEvidence(connection)}
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-2">
                  <Button asChild size="sm" variant="outline">
                    <Link
                      aria-label={`Edit model connection ${connection.name}`}
                      data-testid={`model-connections-open-${connection.id}`}
                      to={`/model-connections/${connection.id}/edit`}
                    >
                      <SquarePen data-icon="inline-start" />
                      Edit
                    </Link>
                  </Button>
                  <Button
                    data-testid={`model-connections-delete-${connection.id}`}
                    disabled={deletePending}
                    size="sm"
                    variant="outline"
                    onClick={() => onDelete(connection)}
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
  );
}

function ModelConnectionsBulkActions({
  filteredCount,
  isPending,
  selectedCount,
  onClear,
  onDeleteSelected,
}: {
  filteredCount: number;
  isPending: boolean;
  selectedCount: number;
  onClear: () => void;
  onDeleteSelected: () => void;
}) {
  if (selectedCount === 0) {
    return null;
  }

  return (
    <div
      data-testid="model-connections-bulk-actions"
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
    >
      <span className="text-xs text-muted-foreground">
        {selectedCount} of {filteredCount} model connections selected
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="destructive"
          disabled={isPending}
          onClick={onDeleteSelected}
        >
          <Trash2 className="size-3.5" /> Delete selected
        </Button>
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}

export function ModelConnectionsListPage() {
  const connectionsQuery = useModelConnections();
  const deleteMutation = useDeleteModelConnection();
  const deleteConnectionsMutation = useDeleteModelConnections();
  const connections = useMemo(
    () => sortConnections(connectionsQuery.data?.items ?? []),
    [connectionsQuery.data?.items],
  );
  const [search, setSearch] = useState("");
  const [selectedConnectionIds, setSelectedConnectionIds] = useState<
    Set<ModelConnectionListItemRead["id"]>
  >(new Set());
  const { viewMode, onViewModeChange } = useInventoryViewState({
    initialViewMode: "table",
    onCardsMode: () => setSelectedConnectionIds(new Set()),
  });
  const [deleting, setDeleting] = useState<ModelConnectionListItemRead | null>(
    null,
  );
  const filteredConnections = useMemo(
    () => filterConnections(connections, search),
    [connections, search],
  );
  const selectedConnections = useMemo(
    () =>
      filteredConnections.filter((connection) =>
        selectedConnectionIds.has(connection.id),
      ),
    [filteredConnections, selectedConnectionIds],
  );
  const selectedCount = selectedConnections.length;
  const allFilteredSelected =
    filteredConnections.length > 0 &&
    filteredConnections.every((connection) =>
      selectedConnectionIds.has(connection.id),
    );
  const someFilteredSelected = filteredConnections.some((connection) =>
    selectedConnectionIds.has(connection.id),
  );

  const deletePending =
    deleteMutation.isPending || deleteConnectionsMutation.isPending;
  const showCards =
    !connectionsQuery.isPending &&
    !connectionsQuery.isError &&
    filteredConnections.length > 0 &&
    viewMode === "cards";
  const showTable =
    !connectionsQuery.isPending &&
    !connectionsQuery.isError &&
    filteredConnections.length > 0 &&
    viewMode === "table";

  const setConnectionsSelected = (
    connectionsToUpdate: readonly ModelConnectionListItemRead[],
    selected: boolean,
  ) => {
    setSelectedConnectionIds((previous) => {
      const next = new Set(previous);
      connectionsToUpdate.forEach((connection) => {
        if (selected) {
          next.add(connection.id);
        } else {
          next.delete(connection.id);
        }
      });
      return next;
    });
  };

  const handleDelete = async () => {
    if (!deleting) {
      return;
    }

    const modelConnectionId = deleting.id;

    try {
      await deleteMutation.mutateAsync(modelConnectionId);
      toast.success("Model connection deleted");
      setSelectedConnectionIds((previous) => {
        const next = new Set(previous);
        next.delete(modelConnectionId);
        return next;
      });
      setDeleting(null);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to delete model connection",
      );
    }
  };

  const handleDeleteSelected = () => {
    if (selectedConnections.length === 0) {
      return;
    }

    const connectionIds = selectedConnections.map(
      (connection) => connection.id,
    );
    const count = selectedConnections.length;
    deleteConnectionsMutation.mutate(connectionIds, {
      onError: (error) =>
        toast.error(
          error instanceof Error
            ? error.message
            : "Failed to delete model connections.",
        ),
      onSuccess: () => {
        toast.success(
          `${count} ${count === 1 ? "model connection" : "model connections"} deleted`,
        );
        setSelectedConnectionIds(new Set());
      },
    });
  };

  return (
    <InventoryPageShell
      pageContext={{
        actions: <ModelConnectionsPageActions />,
        description:
          "Manage live model endpoints, credentials, protocol profiles, and backend-derived compatibility evidence by stable key.",
        title: "Model Connections",
      }}
      testId="platform-model-connections-page"
      toolbar={{
        resultSummary: `${filteredConnections.length} of ${connections.length} model connections shown`,
        search: {
          id: "model-connections-search",
          label: "Search model connections",
          placeholder:
            "Search by name, key, model, protocol, or compatibility evidence...",
          value: search,
          onChange: setSearch,
        },
        viewMode,
        onViewModeChange,
      }}
    >
      <ModelConnectionsStateCards
        error={connectionsQuery.error}
        filteredCount={filteredConnections.length}
        isError={connectionsQuery.isError}
        isPending={connectionsQuery.isPending}
        search={search}
      />
      {showCards ? (
        <ModelConnectionsCards
          connections={filteredConnections}
          deletePending={deletePending}
          onDelete={setDeleting}
        />
      ) : null}
      {showTable ? (
        <ModelConnectionsTable
          allFilteredSelected={allFilteredSelected}
          connections={filteredConnections}
          deletePending={deletePending}
          selectedConnectionIds={selectedConnectionIds}
          someFilteredSelected={someFilteredSelected}
          onDelete={setDeleting}
          onSelect={setConnectionsSelected}
        />
      ) : null}
      {viewMode === "table" ? (
        <ModelConnectionsBulkActions
          filteredCount={filteredConnections.length}
          isPending={deleteConnectionsMutation.isPending}
          selectedCount={selectedCount}
          onClear={() => setSelectedConnectionIds(new Set())}
          onDeleteSelected={handleDeleteSelected}
        />
      ) : null}
      <ConfirmDeleteDialog
        open={deleting !== null}
        title="Delete model connection"
        description={`Delete ${deleting?.name ?? "this model connection"}? Deletion is blocked while current workflow packages reference its stable key. This cannot be undone.`}
        confirmLabel="Delete connection"
        isPending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        onConfirm={handleDelete}
      />
    </InventoryPageShell>
  );
}
