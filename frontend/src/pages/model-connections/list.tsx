import { Archive, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useArchiveModelConnection,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { formatDateTime } from "@/lib/format";
import type {
  ModelConnectionApiStyle,
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
  const archiveMutation = useArchiveModelConnection();
  const connections = sortConnections(connectionsQuery.data?.items ?? []);

  const handleArchive = async (modelConnectionId: number) => {
    try {
      await archiveMutation.mutateAsync(modelConnectionId);
      toast.success("Model connection archived");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive model connection");
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
            Manage saved model endpoints, credentials, and runtime defaults that agents will reference.
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
            const organizationProject =
              [connection.organization, connection.project].filter(Boolean).join(" • ") ||
              "No organization or project override.";

            return (
              <PlatformResourceCard
                key={connection.id}
                testId={`model-connections-row-${connection.id}`}
                title={connection.name}
                subtitle={connection.modelId}
                description={connection.description || "No description provided."}
                badges={
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge
                      variant={connection.status === "active" ? "secondary" : "outline"}
                      className="capitalize"
                    >
                      {connection.status}
                    </Badge>
                  </div>
                }
                metadata={
                  <dl className="flex min-w-0 flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
                    <div className="min-w-0 shrink grow basis-full sm:basis-[calc(50%-0.625rem)] xl:basis-0">
                      <dt className="inline font-medium text-foreground">Base URL:</dt>{" "}
                      <dd className="inline break-all">{connection.baseUrl}</dd>{" "}
                      <dd className="inline break-words">· {organizationProject}</dd>
                    </div>
                    <div className="min-w-0 shrink grow basis-full sm:basis-[calc(50%-0.625rem)] xl:basis-0">
                      <dt className="inline font-medium text-foreground">Reasoning:</dt>{" "}
                      <dd className="inline">{formatReasoningEffort(connection.reasoningEffort)}</dd>{" "}
                      <dd className="inline break-words">· {API_STYLE_LABELS[connection.apiStyle]}</dd>{" "}
                      <dd className="inline">· {connection.timeoutSeconds}s timeout</dd>
                    </div>
                    <div className="min-w-0 shrink grow basis-full sm:basis-[calc(50%-0.625rem)] xl:basis-0">
                      <dt className="inline font-medium text-foreground">API Key:</dt>{" "}
                      <dd className="inline">{connection.hasApiKey ? "Configured" : "Missing"}</dd>{" "}
                      <dd className="inline break-words">
                        ·{" "}
                        {connection.apiKeyLast4
                          ? `Ending in ••••${connection.apiKeyLast4}`
                          : "No API key saved."}
                      </dd>
                    </div>
                    <div className="min-w-0 shrink grow basis-full sm:basis-[calc(50%-0.625rem)] xl:basis-0">
                      <dt className="inline font-medium text-foreground">Last Test:</dt>{" "}
                      <dd className="inline">{formatLastTestStatus(connection)}</dd>{" "}
                      <dd className="inline break-words">
                        ·{" "}
                        {connection.lastTestedAt
                          ? formatDateTime(connection.lastTestedAt)
                          : "No connection test recorded."}
                      </dd>
                      {connection.lastTestMessage ? (
                        <dd className="inline break-words"> · {connection.lastTestMessage}</dd>
                      ) : null}
                    </div>
                  </dl>
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
                    {connection.status !== "archived" ? (
                      <Button
                        data-testid={`model-connections-archive-${connection.id}`}
                        disabled={archiveMutation.isPending}
                        size="sm"
                        variant="outline"
                        onClick={() => void handleArchive(connection.id)}
                      >
                        <Archive data-icon="inline-start" />
                        Archive
                      </Button>
                    ) : null}
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
