import { Archive, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import {
  useArchiveModelConnection,
  useModelConnections,
} from "@/hooks/use-model-connections";
import { formatDateTime } from "@/lib/format";
import type { ModelConnectionListItemRead } from "@/lib/types/model-connection";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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
          <CardContent className="px-0 pb-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Base URL</TableHead>
                  <TableHead>Reasoning</TableHead>
                  <TableHead>API Key</TableHead>
                  <TableHead>Last Test</TableHead>
                  <TableHead className="pr-6 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connections.map((connection) => (
                  <TableRow key={connection.id} data-testid={`model-connections-row-${connection.id}`}>
                    <TableCell className="pl-6 align-top whitespace-normal">
                      <div className="space-y-1">
                        <p className="font-medium text-foreground">{connection.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {connection.description || "No description provided."}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="align-top">
                      <Badge
                        variant={connection.status === "active" ? "secondary" : "outline"}
                        className="capitalize"
                      >
                        {connection.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="align-top">{connection.modelId}</TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <div className="space-y-1 text-sm text-muted-foreground">
                        <p className="font-medium text-foreground">{connection.baseUrl}</p>
                        <p>
                          {[connection.organization, connection.project].filter(Boolean).join(" • ") ||
                            "No organization or project override."}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <div className="space-y-1 text-sm text-muted-foreground">
                        <Badge variant="outline" className="capitalize">
                          {connection.reasoningEffort}
                        </Badge>
                        <p>{connection.timeoutSeconds}s timeout</p>
                      </div>
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <div className="space-y-1 text-sm text-muted-foreground">
                        <Badge variant={connection.hasApiKey ? "secondary" : "outline"}>
                          {connection.hasApiKey ? "Configured" : "Missing"}
                        </Badge>
                        <p>
                          {connection.apiKeyLast4
                            ? `Ending in ••••${connection.apiKeyLast4}`
                            : "No API key saved."}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell className="align-top whitespace-normal">
                      <div className="space-y-1 text-sm text-muted-foreground">
                        {renderLastTestBadge(connection)}
                        <p>
                          {connection.lastTestedAt
                            ? formatDateTime(connection.lastTestedAt)
                            : "No connection test recorded."}
                        </p>
                        {connection.lastTestMessage ? <p>{connection.lastTestMessage}</p> : null}
                      </div>
                    </TableCell>
                    <TableCell className="pr-6 align-top">
                      <div className="flex justify-end gap-2">
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
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
