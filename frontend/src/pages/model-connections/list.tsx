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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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

function renderLastTestBadge(connection: ModelConnectionListItemRead) {
  if (connection.lastTestOk === true) {
    return <Badge variant="secondary">Passed</Badge>;
  }

  if (connection.lastTestOk === false) {
    return <Badge variant="destructive">Failed</Badge>;
  }

  return <Badge variant="outline">Not tested</Badge>;
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
        <Card>
          <CardHeader>
            <CardTitle>Saved connections</CardTitle>
            <CardDescription>
              Active connections can be chosen by new saves, while archived ones remain visible for historical edits.
            </CardDescription>
          </CardHeader>
          <CardContent>
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
                      <dl className="grid min-w-0 gap-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
                        <div className="min-w-0 space-y-1 rounded-md border p-3">
                          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Base URL
                          </dt>
                          <dd className="break-all font-medium text-foreground">{connection.baseUrl}</dd>
                          <dd className="break-words text-muted-foreground">{organizationProject}</dd>
                        </div>
                        <div className="min-w-0 space-y-1 rounded-md border p-3">
                          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Reasoning
                          </dt>
                          <dd>
                            <Badge variant="outline">
                              {formatReasoningEffort(connection.reasoningEffort)}
                            </Badge>
                          </dd>
                          <dd className="break-words text-muted-foreground">
                            {API_STYLE_LABELS[connection.apiStyle]}
                          </dd>
                          <dd className="text-muted-foreground">{connection.timeoutSeconds}s timeout</dd>
                        </div>
                        <div className="min-w-0 space-y-1 rounded-md border p-3">
                          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            API Key
                          </dt>
                          <dd>
                            <Badge variant={connection.hasApiKey ? "secondary" : "outline"}>
                              {connection.hasApiKey ? "Configured" : "Missing"}
                            </Badge>
                          </dd>
                          <dd className="break-words text-muted-foreground">
                            {connection.apiKeyLast4
                              ? `Ending in ••••${connection.apiKeyLast4}`
                              : "No API key saved."}
                          </dd>
                        </div>
                        <div className="min-w-0 space-y-1 rounded-md border p-3 sm:col-span-2 xl:col-span-3">
                          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Last Test
                          </dt>
                          <dd>{renderLastTestBadge(connection)}</dd>
                          <dd className="break-words text-muted-foreground">
                            {connection.lastTestedAt
                              ? formatDateTime(connection.lastTestedAt)
                              : "No connection test recorded."}
                          </dd>
                          {connection.lastTestMessage ? (
                            <dd className="break-words text-muted-foreground">
                              {connection.lastTestMessage}
                            </dd>
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
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
