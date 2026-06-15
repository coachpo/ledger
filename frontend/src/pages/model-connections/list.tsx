import { ChevronDown, ChevronRight, Plus, SquarePen, Trash2 } from "lucide-react";
import { Fragment, type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { useResourceSelectionState } from "@/hooks/use-resource-selection-state";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceBulkActionsBar } from "@/components/shared/resource-bulk-actions-bar";
import { ResourceSelectionCheckbox } from "@/components/shared/resource-selection-checkbox";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/components/ui/utils";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  PROTOCOL_PROFILE_DESCRIPTIONS,
  PROTOCOL_PROFILE_LABELS,
  PROTOCOL_PROFILE_SHORT_LABELS,
  formatCapabilityDetails,
  formatCapabilitySummary,
  formatCompactCapabilitySummary,
  formatCompactLastTestedAt,
  formatLastTestStatus,
  formatReasoningEffort,
  formatRuntimePolicyEvidence,
  getCompactRuntimePolicyItems,
} from "./model-connection-ui";

type ModelConnectionSelectionHandlers = {
  onDelete: (connection: ModelConnectionListItemRead) => void;
  onSelect: (
    connectionsToUpdate: readonly ModelConnectionListItemRead[],
    selected: boolean,
  ) => void;
};

function getModelConnectionId(connection: ModelConnectionListItemRead) {
  return connection.id;
}

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
      PROTOCOL_PROFILE_SHORT_LABELS[connection.protocolProfile],
      PROTOCOL_PROFILE_DESCRIPTIONS[connection.protocolProfile],
      formatCapabilitySummary(connection.capabilities),
      formatCompactCapabilitySummary(connection.capabilities),
      formatCapabilityDetails(connection),
      formatLastTestStatus(connection),
      formatCompactLastTestedAt(connection),
      formatRuntimePolicyEvidence(connection),
      getCompactRuntimePolicyItems(connection)
        .map((item) => `${item.label} ${item.detail}`)
        .join(" "),
      connection.lastTestMessage ?? "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
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
    return <InventoryStatePanel title="Loading model connections..." />;
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "Failed to load model connections.";

    return <InventoryStatePanel title={message} tone="danger" />;
  }

  if (filteredCount > 0) {
    return null;
  }

  return (
    <InventoryStatePanel
      description={
        search.trim()
          ? "Refine the search by connection name, stable key, model, or base URL."
          : "Create a saved endpoint before launching workflow packages that need model access."
      }
      title={
        search.trim()
          ? "No model connections match this search."
          : "No model connections exist yet."
      }
    />
  );
}

function MonospaceTruncate({ label, value }: { label: string; value: string }) {
  return (
    <span
      aria-label={`${label}: ${value}`}
      className="block max-w-full truncate font-mono text-xs text-muted-foreground"
      title={value}
    >
      {value}
    </span>
  );
}

function ModelConnectionNameCell({
  className,
  connection,
}: {
  className?: string;
  connection: ModelConnectionListItemRead;
}) {
  return (
    <span
      className={cn(
        "block min-w-0 truncate text-sm font-medium leading-5 text-foreground",
        className,
      )}
      title={connection.name}
    >
      {connection.name}
    </span>
  );
}

function ProtocolProfileCell({
  connection,
}: {
  connection: ModelConnectionListItemRead;
}) {
  const label = PROTOCOL_PROFILE_SHORT_LABELS[connection.protocolProfile];

  return (
    <Badge
      aria-label={`Profile: ${PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}`}
      variant="outline"
    >
      {label}
    </Badge>
  );
}

function CompactDetailField({
  children,
  label,
  mono = false,
}: {
  children: ReactNode;
  label: string;
  mono?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-start sm:gap-2">
      <dt className="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground sm:w-24">
        {label}
      </dt>
      <dd
        className={cn(
          "min-w-0 break-words text-xs leading-5 text-foreground",
          mono ? "break-all font-mono" : null,
        )}
      >
        {children}
      </dd>
    </div>
  );
}

function CompactDetailGroup({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="min-w-0">
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-foreground">
        {title}
      </h4>
      <dl className="flex min-w-0 flex-col gap-1.5">{children}</dl>
    </section>
  );
}

function ModelConnectionDetailSections({
  ariaLabel,
  className,
  connection,
  role,
}: {
  ariaLabel?: string;
  className?: string;
  connection: ModelConnectionListItemRead;
  role?: "group";
}) {
  return (
    <div
      aria-label={ariaLabel}
      className={cn(
        "grid min-w-0 gap-x-6 gap-y-2 md:grid-cols-2 xl:grid-cols-4",
        className,
      )}
      role={role}
    >
      <CompactDetailGroup title="Endpoint">
        <CompactDetailField label="Profile">
          {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
        </CompactDetailField>
        <CompactDetailField label="Stable key" mono>
          {connection.key}
        </CompactDetailField>
        <CompactDetailField label="Model ID" mono>
          {connection.modelId}
        </CompactDetailField>
        <CompactDetailField label="Base URL" mono>
          {connection.baseUrl}
        </CompactDetailField>
        <CompactDetailField label="Timeout">
          {connection.timeoutSeconds}s
        </CompactDetailField>
      </CompactDetailGroup>
      <CompactDetailGroup title="Capability support">
        <CompactDetailField label="Summary">
          {formatCapabilitySummary(connection.capabilities)}
        </CompactDetailField>
        <CompactDetailField label="Detail">
          {formatCapabilityDetails(connection)}
        </CompactDetailField>
      </CompactDetailGroup>
      <CompactDetailGroup title="Test and reachability">
        <CompactDetailField label="Last test">
          {formatLastTestStatus(connection)}
        </CompactDetailField>
        <CompactDetailField label="Tested at">
          {formatCompactLastTestedAt(connection)}
        </CompactDetailField>
        <CompactDetailField label="Message">
          {connection.lastTestMessage ??
            "Backend connection test has not reported a provider message."}
        </CompactDetailField>
      </CompactDetailGroup>
      <CompactDetailGroup title="Runtime policy">
        <CompactDetailField label="Policy">
          {formatRuntimePolicyEvidence(connection)}
        </CompactDetailField>
        <CompactDetailField label="Reasoning">
          {formatReasoningEffort(connection.reasoningEffort)}
        </CompactDetailField>
      </CompactDetailGroup>
    </div>
  );
}

function ModelConnectionDetailsRow({
  connection,
  detailsId,
}: {
  connection: ModelConnectionListItemRead;
  detailsId: string;
}) {
  return (
    <TableRow className="bg-muted/20 hover:bg-muted/20" id={detailsId}>
      <TableCell colSpan={6} className="whitespace-normal px-3 py-2">
        <ModelConnectionDetailSections
          ariaLabel={`Expanded details for ${connection.name}`}
          className="rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
          connection={connection}
          role="group"
        />
      </TableCell>
    </TableRow>
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
  const [expandedConnectionIds, setExpandedConnectionIds] = useState<
    Set<ModelConnectionListItemRead["id"]>
  >(new Set());

  const toggleDetails = (connectionId: ModelConnectionListItemRead["id"]) => {
    setExpandedConnectionIds((previous) => {
      const next = new Set(previous);
      if (next.has(connectionId)) {
        next.delete(connectionId);
      } else {
        next.add(connectionId);
      }
      return next;
    });
  };

  return (
    <ResourceTableFrame>
      <Table className="table-fixed text-xs">
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-9 px-2 py-1.5">
              <ResourceSelectionCheckbox
                ariaLabel="Select all shown model connections"
                indeterminate={someFilteredSelected}
                selected={allFilteredSelected}
                onSelectedChange={(selected) =>
                  onSelect(connections, selected)
                }
              />
            </TableHead>
            <TableHead className="w-[28%] px-2 py-1.5">Name</TableHead>
            <TableHead className="w-[20%] px-2 py-1.5">Stable key</TableHead>
            <TableHead className="w-[24%] px-2 py-1.5">Model ID</TableHead>
            <TableHead className="w-[12%] px-2 py-1.5">Profile</TableHead>
            <TableHead className="w-[280px] px-2 py-1.5 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {connections.map((connection) => {
            const isSelected = selectedConnectionIds.has(connection.id);
            const isExpanded = expandedConnectionIds.has(connection.id);
            const detailsId = `model-connection-details-${connection.id}`;

            return (
              <Fragment key={connection.id}>
                <TableRow
                  data-state={isSelected ? "selected" : undefined}
                  data-testid={`model-connections-row-${connection.id}`}
                >
                  <TableCell className="px-2 py-1.5">
                    <ResourceSelectionCheckbox
                      ariaLabel={`Select model connection ${connection.name}`}
                      selected={isSelected}
                      onSelectedChange={(selected) =>
                        onSelect([connection], selected)
                      }
                    />
                  </TableCell>
                  <TableCell className="min-w-0 px-2 py-1.5">
                    <ModelConnectionNameCell connection={connection} />
                  </TableCell>
                  <TableCell className="min-w-0 px-2 py-1.5">
                    <MonospaceTruncate
                      label="Stable key"
                      value={connection.key}
                    />
                  </TableCell>
                  <TableCell className="min-w-0 px-2 py-1.5">
                    <MonospaceTruncate
                      label="Model ID"
                      value={connection.modelId}
                    />
                  </TableCell>
                  <TableCell className="min-w-0 px-2 py-1.5">
                    <ProtocolProfileCell connection={connection} />
                  </TableCell>
                  <TableCell className="px-2 py-1.5">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <Button
                        aria-controls={detailsId}
                        aria-expanded={isExpanded}
                        className="h-8 px-2 cursor-pointer"
                        data-testid={`model-connections-details-${connection.id}`}
                        onClick={() => toggleDetails(connection.id)}
                        size="sm"
                        type="button"
                        variant="ghost"
                      >
                        {isExpanded ? (
                          <ChevronDown data-icon="inline-start" />
                        ) : (
                          <ChevronRight data-icon="inline-start" />
                        )}
                        {isExpanded ? "Hide details" : "Show details"}
                      </Button>
                      <Button
                        asChild
                        className="h-8 px-2"
                        size="sm"
                        variant="outline"
                      >
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
                        aria-label={`Delete model connection ${connection.name}`}
                        className="h-8 px-2 cursor-pointer"
                        data-testid={`model-connections-delete-${connection.id}`}
                        disabled={deletePending}
                        onClick={() => onDelete(connection)}
                        size="sm"
                        type="button"
                        variant="destructive"
                      >
                        <Trash2 data-icon="inline-start" />
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                {isExpanded ? (
                  <ModelConnectionDetailsRow
                    connection={connection}
                    detailsId={detailsId}
                  />
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </ResourceTableFrame>
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
  const [deleting, setDeleting] = useState<ModelConnectionListItemRead | null>(
    null,
  );
  const filteredConnections = useMemo(
    () => filterConnections(connections, search),
    [connections, search],
  );
  const activeSearch = search.trim();
  const connectionSelection = useResourceSelectionState({
    getId: getModelConnectionId,
    items: filteredConnections,
  });
  const selectedConnections = connectionSelection.selectedItems;
  const selectedCount = connectionSelection.selectedCount;
  const allFilteredSelected = connectionSelection.allSelected;
  const someFilteredSelected = connectionSelection.someSelected;

  const deletePending =
    deleteMutation.isPending || deleteConnectionsMutation.isPending;
  const showTable =
    !connectionsQuery.isPending &&
    !connectionsQuery.isError &&
    filteredConnections.length > 0;

  const handleDelete = async () => {
    if (!deleting) {
      return;
    }

    const modelConnectionId = deleting.id;

    try {
      await deleteMutation.mutateAsync(modelConnectionId);
      toast.success("Model connection deleted");
      connectionSelection.setIdsSelected([modelConnectionId], false);
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
        connectionSelection.clearSelection();
      },
    });
  };

  return (
    <InventoryPageShell
      filterBar={
        activeSearch
          ? {
              items: [
                {
                  active: true,
                  clearLabel: "Clear model connection search",
                  id: "search",
                  label: "Search",
                  value: activeSearch,
                  onClear: () => setSearch(""),
                },
              ],
              onClearAll: () => setSearch(""),
              testId: "model-connections-active-filters",
            }
          : null
      }
      pageContext={{
        actions: <ModelConnectionsPageActions />,
        description: "Manage model connections.",
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
      }}
    >
      <ModelConnectionsStateCards
        error={connectionsQuery.error}
        filteredCount={filteredConnections.length}
        isError={connectionsQuery.isError}
        isPending={connectionsQuery.isPending}
        search={search}
      />
      {showTable ? (
        <ModelConnectionsTable
          allFilteredSelected={allFilteredSelected}
          connections={filteredConnections}
          deletePending={deletePending}
          selectedConnectionIds={connectionSelection.selectedIds}
          someFilteredSelected={someFilteredSelected}
          onDelete={setDeleting}
          onSelect={connectionSelection.setItemsSelected}
        />
      ) : null}
      <ResourceBulkActionsBar
        deletePending={deleteConnectionsMutation.isPending}
        resourceLabel="model connections"
        selectedCount={selectedCount}
        testId="model-connections-bulk-actions"
        totalCount={filteredConnections.length}
        onClear={connectionSelection.clearSelection}
        onDeleteSelected={handleDeleteSelected}
      />
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
