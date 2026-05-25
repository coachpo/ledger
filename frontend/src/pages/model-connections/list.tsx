import {
  LayoutGrid,
  List,
  MoreHorizontal,
  Plus,
  Search,
  SquarePen,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { formatDateTime } from "@/lib/format";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";
import {
  CAPABILITY_LABEL_BY_KEY,
  CAPABILITY_STATUS_LABELS,
  OUTPUT_STRATEGY_POLICY_LABELS,
  PARALLEL_TOOL_CALLS_POLICY_LABELS,
  PROTOCOL_PROFILE_DESCRIPTIONS,
  PROTOCOL_PROFILE_LABELS,
  REASONING_POLICY_LABELS,
  STREAMING_POLICY_LABELS,
  SUMMARY_CAPABILITY_KEYS,
  formatCapabilitySummary,
} from "./model-connection-ui";

type ViewMode = "cards" | "table";

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

function formatLastTestStatus(connection: ModelConnectionListItemRead): string {
  if (connection.lastTestOk === true) {
    return "Passed";
  }

  if (connection.lastTestOk === false) {
    return "Failed";
  }

  return "Not tested";
}

function formatReasoningEffort(
  value: ModelConnectionListItemRead["reasoningEffort"],
): string {
  return value ?? "Omitted";
}

function formatRuntimePolicyEvidence(connection: ModelConnectionListItemRead): string {
  return [
    OUTPUT_STRATEGY_POLICY_LABELS[connection.outputStrategyPolicy],
    PARALLEL_TOOL_CALLS_POLICY_LABELS[connection.parallelToolCallsPolicy],
    REASONING_POLICY_LABELS[connection.reasoningPolicy],
    STREAMING_POLICY_LABELS[connection.streamingPolicy],
  ].join(" · ");
}

function formatCapabilityDetails(
  connection: ModelConnectionListItemRead,
): string {
  return SUMMARY_CAPABILITY_KEYS.map((capabilityKey) => {
    const capability = connection.capabilities[capabilityKey];
    return `${CAPABILITY_LABEL_BY_KEY[capabilityKey]}: ${
      CAPABILITY_STATUS_LABELS[capability.status]
    }`;
  }).join(" · ");
}

function ModelConnectionMetadata({
  connection,
}: {
  connection: ModelConnectionListItemRead;
}) {
  return (
    <div className="grid min-w-0 gap-x-5 gap-y-1.5 text-xs text-muted-foreground sm:grid-cols-2 xl:grid-cols-3">
      <div className="min-w-0">
        <span className="font-medium text-foreground">Protocol profile:</span>{" "}
        <span className="break-words">
          {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
        </span>{" "}
        <span aria-hidden="true">·</span>{" "}
        <span>{connection.timeoutSeconds}s timeout</span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Base URL:</span>{" "}
        <span className="break-all">{connection.baseUrl}</span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Reasoning:</span>{" "}
        <span>{formatReasoningEffort(connection.reasoningEffort)}</span>
      </div>
      <div className="min-w-0 sm:col-span-2 xl:col-span-1">
        <span className="font-medium text-foreground">Compatibility evidence:</span>{" "}
        <span className="break-words">{formatCapabilityDetails(connection)}</span>
      </div>
      <div className="min-w-0 sm:col-span-2 xl:col-span-1">
        <span className="font-medium text-foreground">Runtime policy evidence:</span>{" "}
        <span className="break-words">
          {formatRuntimePolicyEvidence(connection)}
        </span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Reachability:</span>{" "}
        <span>{formatLastTestStatus(connection)}</span>{" "}
        <span className="break-words">
          ·{" "}
          {connection.lastTestedAt
            ? formatDateTime(connection.lastTestedAt)
            : "No reachability test recorded."}
        </span>
        {connection.lastTestMessage ? (
          <span className="break-words"> · {connection.lastTestMessage}</span>
        ) : null}
      </div>
    </div>
  );
}

function ModelConnectionsHeader() {
  return (
    <div
      className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
      data-testid="model-connections-list"
    >
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">
          Model Connections
        </h1>
        <p className="text-sm text-muted-foreground">
          Manage live model endpoints, credentials, protocol profiles, and
          backend-derived compatibility evidence by stable key.
        </p>
      </div>
      <Button asChild data-testid="model-connections-new" size="sm">
        <Link to="/model-connections/new">
          <Plus data-icon="inline-start" />
          New Model Connection
        </Link>
      </Button>
    </div>
  );
}

function ModelConnectionsToolbar({
  search,
  viewMode,
  onSearchChange,
  onViewModeChange,
}: {
  search: string;
  viewMode: ViewMode;
  onSearchChange: (value: string) => void;
  onViewModeChange: (value: ViewMode) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative max-w-sm flex-1" role="search">
        <Search
          className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          aria-label="Search model connections"
          className="h-8 pl-8 text-xs"
          placeholder="Search by name, key, model, protocol, or compatibility evidence..."
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
      <ToggleGroup
        type="single"
        value={viewMode}
        onValueChange={(value) => {
          if (value) {
            onViewModeChange(value as ViewMode);
          }
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
          badges={
            <>
              <Badge variant="secondary">
                {formatLastTestStatus(connection)}
              </Badge>
              <Badge variant="outline">
                {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
              </Badge>
              <Badge variant="outline">
                {formatCapabilitySummary(connection.capabilities)}
              </Badge>
            </>
          }
          description={connection.description}
          metadata={<ModelConnectionMetadata connection={connection} />}
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
          <TableHead>Model</TableHead>
          <TableHead>Base URL</TableHead>
          <TableHead>Protocol Profile</TableHead>
          <TableHead>Compatibility Evidence</TableHead>
          <TableHead>Runtime Policy Evidence</TableHead>
          <TableHead>Reachability Test</TableHead>
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
                <div className="space-y-1">
                  <p className="font-medium text-foreground">
                    {connection.name}
                  </p>
                  <p className="line-clamp-2 text-xs text-muted-foreground">
                    {connection.description || "No description provided."}
                  </p>
                </div>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {connection.modelId}
              </TableCell>
              <TableCell className="max-w-72 whitespace-normal break-all text-xs text-muted-foreground">
                {connection.baseUrl}
              </TableCell>
              <TableCell className="min-w-64 whitespace-normal text-xs text-muted-foreground">
                <span>{PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}</span>{" "}
                <span aria-hidden="true">·</span>{" "}
                <span>Reasoning {formatReasoningEffort(connection.reasoningEffort)}</span>{" "}
                <span aria-hidden="true">·</span>{" "}
                <span>{connection.timeoutSeconds}s timeout</span>
              </TableCell>
              <TableCell className="min-w-72 whitespace-normal text-xs text-muted-foreground">
                <span>{formatCapabilitySummary(connection.capabilities)}</span>
                <span className="block break-words">
                  {formatCapabilityDetails(connection)}
                </span>
              </TableCell>
              <TableCell className="min-w-72 whitespace-normal text-xs text-muted-foreground">
                {formatRuntimePolicyEvidence(connection)}
              </TableCell>
              <TableCell className="min-w-56 whitespace-normal text-xs text-muted-foreground">
                <span>{formatLastTestStatus(connection)}</span>{" "}
                <span>
                  ·{" "}
                  {connection.lastTestedAt
                    ? formatDateTime(connection.lastTestedAt)
                    : "No reachability test recorded."}
                </span>
                {connection.lastTestMessage ? (
                  <span> · {connection.lastTestMessage}</span>
                ) : null}
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
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [selectedConnectionIds, setSelectedConnectionIds] = useState<
    Set<ModelConnectionListItemRead["id"]>
  >(new Set());
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

  const handleViewModeChange = (value: ViewMode) => {
    setViewMode(value);
    if (value === "cards") {
      setSelectedConnectionIds(new Set());
    }
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
    <div
      className="space-y-4 p-4"
      data-testid="platform-model-connections-page"
    >
      <ModelConnectionsHeader />
      <ModelConnectionsToolbar
        search={search}
        viewMode={viewMode}
        onSearchChange={setSearch}
        onViewModeChange={handleViewModeChange}
      />
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
    </div>
  );
}
