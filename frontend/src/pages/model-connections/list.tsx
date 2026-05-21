import {
  LayoutGrid,
  List,
  Plus,
  Search,
  SquarePen,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useDeleteModelConnections,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { formatDateTime } from "@/lib/format";
import type {
  ModelConnectionApiStyle,
  ModelConnectionListItemRead,
} from "@/lib/types/model-connection";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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

const API_STYLE_LABELS: Record<ModelConnectionApiStyle, string> = {
  chat_completions: "Chat Completions API - legacy / OpenAI-compatible",
  responses: "Responses API",
};

type ViewMode = "cards" | "table";

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

function ModelConnectionMetadata({
  connection,
}: {
  connection: ModelConnectionListItemRead;
}) {
  return (
    <div className="grid min-w-0 gap-x-5 gap-y-2 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-3">
      <div className="min-w-0">
        <span className="font-medium text-foreground">Base URL:</span>{" "}
        <span className="break-all">{connection.baseUrl}</span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Reasoning:</span>{" "}
        <span>{formatReasoningEffort(connection.reasoningEffort)}</span>{" "}
        <span aria-hidden="true">·</span>{" "}
        <span className="break-words">
          {API_STYLE_LABELS[connection.apiStyle]}
        </span>{" "}
        <span aria-hidden="true">·</span>{" "}
        <span>{connection.timeoutSeconds}s timeout</span>
      </div>
      <div className="min-w-0">
        <span className="font-medium text-foreground">Last Test:</span>{" "}
        <span>{formatLastTestStatus(connection)}</span>{" "}
        <span className="break-words">
          ·{" "}
          {connection.lastTestedAt
            ? formatDateTime(connection.lastTestedAt)
            : "No connection test recorded."}
        </span>
        {connection.lastTestMessage ? (
          <span className="break-words"> · {connection.lastTestMessage}</span>
        ) : null}
      </div>
    </div>
  );
}

export function ModelConnectionsListPage() {
  const navigate = useNavigate();
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

  const handleDelete = async (modelConnectionId: number) => {
    try {
      await deleteMutation.mutateAsync(modelConnectionId);
      toast.success("Model connection deleted");
      setSelectedConnectionIds((previous) => {
        const next = new Set(previous);
        next.delete(modelConnectionId);
        return next;
      });
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
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="model-connections-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            Model Connections
          </h1>
          <p className="text-sm text-muted-foreground">
            Manage live model endpoints, credentials, and runtime defaults that
            workflow packages reference by stable key.
          </p>
        </div>
        <Button
          className="cursor-pointer"
          data-testid="model-connections-new"
          size="sm"
          onClick={() => navigate("/model-connections/new")}
        >
          <Plus data-icon="inline-start" />
          New Model Connection
        </Button>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1" role="search">
          <Search
            className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            aria-label="Search model connections"
            className="h-8 pl-8 text-xs"
            placeholder="Search connections by name, key, model, or URL..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(value) => {
            if (!value) return;
            setViewMode(value as ViewMode);
            if (value === "cards") setSelectedConnectionIds(new Set());
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

      {connectionsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading model connections...
          </CardContent>
        </Card>
      ) : null}

      {connectionsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {connectionsQuery.error instanceof Error
              ? connectionsQuery.error.message
              : "Failed to load model connections."}
          </CardContent>
        </Card>
      ) : null}

      {!connectionsQuery.isPending &&
      !connectionsQuery.isError &&
      filteredConnections.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {search.trim()
              ? "No model connections match this search."
              : "No model connections exist yet."}
          </CardContent>
        </Card>
      ) : null}

      {!connectionsQuery.isPending &&
      !connectionsQuery.isError &&
      filteredConnections.length > 0 &&
      viewMode === "cards" ? (
        <PlatformResourceList>
          {filteredConnections.map((connection) => {
            return (
              <PlatformResourceCard
                key={connection.id}
                density="compactPlus"
                primaryAction={{
                  kind: "link",
                  label: `Open model connection ${connection.name}`,
                  to: `/model-connections/${connection.id}/edit`,
                }}
                testId={`model-connections-row-${connection.id}`}
                title={connection.name}
                subtitle={connection.modelId}
                description={connection.description}
                metadata={<ModelConnectionMetadata connection={connection} />}
                actions={
                  <>
                    <Button
                      data-testid={`model-connections-open-${connection.id}`}
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        navigate(`/model-connections/${connection.id}/edit`)
                      }
                    >
                      <SquarePen data-icon="inline-start" />
                      Edit
                    </Button>
                    <Button
                      data-testid={`model-connections-delete-${connection.id}`}
                      disabled={
                        deleteMutation.isPending ||
                        deleteConnectionsMutation.isPending
                      }
                      size="sm"
                      variant="outline"
                      onClick={() => void handleDelete(connection.id)}
                    >
                      <Trash2 data-icon="inline-start" />
                      Delete
                    </Button>
                  </>
                }
              />
            );
          })}
        </PlatformResourceList>
      ) : null}

      {!connectionsQuery.isPending &&
      !connectionsQuery.isError &&
      filteredConnections.length > 0 &&
      viewMode === "table" ? (
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
                    setConnectionsSelected(
                      filteredConnections,
                      checked === true,
                    )
                  }
                />
              </TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Base URL</TableHead>
              <TableHead>Runtime Defaults</TableHead>
              <TableHead>Last Test</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredConnections.map((connection) => {
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
                        setConnectionsSelected([connection], checked === true)
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
                    <span>
                      {formatReasoningEffort(connection.reasoningEffort)}
                    </span>{" "}
                    <span aria-hidden="true">·</span>{" "}
                    <span>{API_STYLE_LABELS[connection.apiStyle]}</span>{" "}
                    <span aria-hidden="true">·</span>{" "}
                    <span>{connection.timeoutSeconds}s timeout</span>
                  </TableCell>
                  <TableCell className="min-w-56 whitespace-normal text-xs text-muted-foreground">
                    <span>{formatLastTestStatus(connection)}</span>{" "}
                    <span>
                      ·{" "}
                      {connection.lastTestedAt
                        ? formatDateTime(connection.lastTestedAt)
                        : "No connection test recorded."}
                    </span>
                    {connection.lastTestMessage ? (
                      <span> · {connection.lastTestMessage}</span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        data-testid={`model-connections-open-${connection.id}`}
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          navigate(`/model-connections/${connection.id}/edit`)
                        }
                      >
                        <SquarePen data-icon="inline-start" />
                        Edit
                      </Button>
                      <Button
                        data-testid={`model-connections-delete-${connection.id}`}
                        disabled={
                          deleteMutation.isPending ||
                          deleteConnectionsMutation.isPending
                        }
                        size="sm"
                        variant="outline"
                        onClick={() => void handleDelete(connection.id)}
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
      ) : null}
      {viewMode === "table" && selectedCount > 0 ? (
        <div
          data-testid="model-connections-bulk-actions"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2"
        >
          <span className="text-xs text-muted-foreground">
            {selectedCount} of {filteredConnections.length} model connections
            selected
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="destructive"
              disabled={deleteConnectionsMutation.isPending}
              onClick={handleDeleteSelected}
            >
              <Trash2 className="size-3.5" /> Delete selected
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedConnectionIds(new Set())}
            >
              Clear
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
