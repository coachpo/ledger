import { ChevronDown, ChevronRight, Plus, SquarePen, Trash2 } from "lucide-react";
import { Fragment, type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { useInventoryViewState } from "@/hooks/use-inventory-view-state";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/components/ui/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  PROTOCOL_PROFILE_SHORT_LABELS,
  formatCapabilityDetails,
  formatCapabilitySummary,
  formatCompactCapabilitySummary,
  formatCompactLastTestedAt,
  formatLastTestStatus,
  formatReasoningEffort,
  formatRuntimePolicyEvidence,
  getCompactRuntimePolicyItems,
  getModelConnectionEvidenceItems,
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

type ModelConnectionEvidenceItem = ReturnType<
  typeof getModelConnectionEvidenceItems
>[number];

function compactBadgeToneFromEvidence(
  tone: ModelConnectionEvidenceItem["tone"],
): CompactBadgeTone {
  if (tone === "verified") {
    return "success";
  }

  if (tone === "danger") {
    return "danger";
  }

  if (tone === "warning") {
    return "warning";
  }

  return "neutral";
}

function getNamedEvidenceItem(
  connection: ModelConnectionListItemRead,
  label: string,
) {
  return getModelConnectionEvidenceItems(connection).find(
    (item) => String(item.label) === label,
  );
}

function ModelConnectionCardEvidenceChips({
  connection,
}: {
  connection: ModelConnectionListItemRead;
}) {
  const credentialItem = getNamedEvidenceItem(connection, "Credential state");

  if (!credentialItem) {
    return null;
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      <CompactMetadataBadge
        detail={String(credentialItem.description ?? credentialItem.value)}
        label={String(credentialItem.value)}
        tone={compactBadgeToneFromEvidence(credentialItem.tone)}
      />
    </div>
  );
}

function ModelConnectionCard({
  connection,
  deletePending,
  onDelete,
}: {
  connection: ModelConnectionListItemRead;
  deletePending: boolean;
  onDelete: (connection: ModelConnectionListItemRead) => void;
}) {
  return (
    <PlatformResourceCard
      actions={
        <ModelConnectionActions
          connection={connection}
          deletePending={deletePending}
          onDelete={onDelete}
        />
      }
      density="compactPlus"
      description={connection.description || "No description provided."}
      factsGrid={<ModelConnectionCardDetails connection={connection} />}
      testId={`model-connections-row-${connection.id}`}
      title={connection.name}
    />
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
        <ModelConnectionCard
          connection={connection}
          deletePending={deletePending}
          key={connection.id}
          onDelete={onDelete}
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
      <Button asChild className="h-8 px-2" size="sm" variant="outline">
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
    </>
  );
}

type CompactBadgeTone = "neutral" | "success" | "warning" | "danger";

const compactBadgeVariantByTone: Record<
  CompactBadgeTone,
  "secondary" | "outline" | "destructive"
> = {
  danger: "destructive",
  neutral: "outline",
  success: "secondary",
  warning: "outline",
};

function CompactMetadataBadge({
  accessibleDetail,
  detail,
  emphasized = false,
  label,
  tone = "neutral",
}: {
  accessibleDetail?: string;
  detail: ReactNode;
  emphasized?: boolean;
  label: string;
  tone?: CompactBadgeTone;
}) {
  const derivedAccessibleDetail =
    accessibleDetail ?? (typeof detail === "string" ? detail : undefined);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          aria-label={derivedAccessibleDetail ? `${label}: ${derivedAccessibleDetail}` : label}
          className="inline-flex max-w-full rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          tabIndex={0}
        >
          <Badge
            className={cn(
              "max-w-full px-1.5 py-0 text-xs leading-5",
              emphasized
                ? "border-ring/30 bg-accent/40 text-accent-foreground shadow-sm"
                : null,
            )}
            data-emphasized={emphasized ? "true" : undefined}
            data-tone={tone}
            variant={compactBadgeVariantByTone[tone]}
          >
            <span className="truncate">{label}</span>
          </Badge>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-left">{detail}</TooltipContent>
    </Tooltip>
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
  className,
  connection,
}: {
  className?: string;
  connection: ModelConnectionListItemRead;
}) {
  return (
    <div
      className={cn(
        "grid min-w-0 gap-x-6 gap-y-2 md:grid-cols-2 xl:grid-cols-4",
        className,
      )}
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

function ModelConnectionCardDetails({
  connection,
}: {
  connection: ModelConnectionListItemRead;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <ModelConnectionCardEvidenceChips connection={connection} />
      <ModelConnectionDetailSections
        className="rounded-lg border bg-muted/15 p-3"
        connection={connection}
      />
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
        <div
          aria-label={`Expanded details for ${connection.name}`}
          className="flex min-w-0 flex-col gap-2 rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
          role="group"
        >
          <div className="min-w-0">
            <p className="text-xs font-medium text-foreground">
              Connection detail
            </p>
            <p className="mt-0.5 break-words leading-5">
              {connection.description || "No description provided."}
            </p>
          </div>
          <ModelConnectionDetailSections
            className="border-t pt-2"
            connection={connection}
          />
        </div>
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
    <Table className="table-fixed text-xs">
      <TableHeader>
        <TableRow className="bg-muted/30 hover:bg-muted/30">
          <TableHead className="w-9 px-2 py-1.5">
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
                  <Checkbox
                    aria-label={`Select model connection ${connection.name}`}
                    checked={isSelected}
                    onCheckedChange={(checked) =>
                      onSelect([connection], checked === true)
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
