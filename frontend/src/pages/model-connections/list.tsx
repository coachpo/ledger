import { Plus, SquarePen, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useDeleteModelConnection,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { formatDateTime } from "@/lib/format";
import type {
  ModelConnectionApiStyle,
  ModelConnectionKind,
  ModelConnectionListItemRead,
} from "@/lib/types/model-connection";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { PlatformResourceCard, PlatformResourceList } from "../platform-resource-shared";

const API_STYLE_LABELS: Record<ModelConnectionApiStyle, string> = {
  chat_completions: "Chat Completions API - legacy / OpenAI-compatible",
  responses: "Responses API",
};

const CONNECTION_KIND_LABELS: Record<ModelConnectionKind, string> = {
  deterministic_smoke: "Deterministic smoke",
  provider: "Provider-backed",
};

function sortConnections(items: readonly ModelConnectionListItemRead[]) {
  return [...items].sort((left, right) => {
    const byName = left.name.localeCompare(right.name);
    return byName !== 0 ? byName : left.modelId.localeCompare(right.modelId);
  });
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

function formatReasoningEffort(value: ModelConnectionListItemRead["reasoningEffort"]): string {
  return value ?? "Omitted";
}

export function ModelConnectionsListPage() {
  const navigate = useNavigate();
  const connectionsQuery = useModelConnections();
  const deleteMutation = useDeleteModelConnection();
  const connections = sortConnections(connectionsQuery.data?.items ?? []);

  const handleDelete = async (modelConnectionId: number) => {
    try {
      await deleteMutation.mutateAsync(modelConnectionId);
      toast.success("Model connection deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete model connection");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="platform-model-connections-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="model-connections-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Model Connections</h1>
          <p className="text-sm text-muted-foreground">
            Manage live model endpoints, credentials, and runtime defaults that workflow packages reference by stable key.
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

      {!connectionsQuery.isPending && !connectionsQuery.isError && connections.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No model connections exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!connectionsQuery.isPending && !connectionsQuery.isError && connections.length > 0 ? (
        <PlatformResourceList>
          {connections.map((connection) => {
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
                badges={
                  <Badge variant={connection.connectionKind === "deterministic_smoke" ? "secondary" : "outline"}>
                    {CONNECTION_KIND_LABELS[connection.connectionKind]}
                  </Badge>
                }
                description={connection.description}
                metadata={
                  <div className="grid min-w-0 gap-x-5 gap-y-2 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-3">
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">Base URL:</span>{" "}
                      <span className="break-all">{connection.baseUrl}</span>
                    </div>
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">Reasoning:</span>{" "}
                      <span>{formatReasoningEffort(connection.reasoningEffort)}</span>{" "}
                      <span aria-hidden="true">·</span>{" "}
                      <span className="break-words">{API_STYLE_LABELS[connection.apiStyle]}</span>{" "}
                      <span aria-hidden="true">·</span>{" "}
                      <span>{connection.timeoutSeconds}s timeout</span>
                    </div>
                    <div className="min-w-0">
                      <span className="font-medium text-foreground">Mode:</span>{" "}
                      <span>{CONNECTION_KIND_LABELS[connection.connectionKind]}</span>
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
                }
                actions={
                  <>
                    <Button
                      data-testid={`model-connections-open-${connection.id}`}
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(`/model-connections/${connection.id}/edit`)}
                    >
                      <SquarePen data-icon="inline-start" />
                      Edit
                    </Button>
                    <Button
                      data-testid={`model-connections-delete-${connection.id}`}
                      disabled={deleteMutation.isPending}
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
    </div>
  );
}
