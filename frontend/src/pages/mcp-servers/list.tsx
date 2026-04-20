import { Archive, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { useArchiveMcpServer, useMcpServers } from "@/hooks/use-mcp-servers";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

export function McpServersListPage() {
  const navigate = useNavigate();
  const serversQuery = useMcpServers();
  const archiveMutation = useArchiveMcpServer();
  const servers = sortByKey(serversQuery.data?.items ?? []);

  const handleArchive = async (serverId: number) => {
    try {
      await archiveMutation.mutateAsync(serverId);
      toast.success("MCP server archived");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive MCP server");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="platform-mcp-servers-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="mcp-servers-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground">
            Manage external MCP server definitions and validate their connection settings.
          </p>
        </div>
        <Button data-testid="mcp-servers-new" size="sm" onClick={() => navigate("/mcp-servers/new")}>
          <Plus data-icon="inline-start" />
          New MCP Server
        </Button>
      </div>

      {serversQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading MCP servers...
          </CardContent>
        </Card>
      ) : null}

      {serversQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {serversQuery.error instanceof Error ? serversQuery.error.message : "Failed to load MCP servers."}
          </CardContent>
        </Card>
      ) : null}

      {!serversQuery.isPending && !serversQuery.isError && servers.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No MCP servers exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!serversQuery.isPending && !serversQuery.isError && servers.length > 0 ? (
        <div className="grid gap-3">
          {servers.map((server) => (
            <Card key={server.id} data-testid={`mcp-servers-row-${server.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{server.name}</CardTitle>
                    <CardDescription>{server.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges
                    status={server.status}
                    version={server.version}
                    extra={
                      <>
                        <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                          {server.transport}
                        </span>
                        <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                          {server.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </>
                    }
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`mcp-servers-open-${server.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/mcp-servers/${server.id}/edit`)}
                  >
                    <SquarePen data-icon="inline-start" />
                    Edit
                  </Button>
                  {server.status !== "archived" ? (
                    <Button
                      data-testid={`mcp-servers-archive-${server.key}`}
                      disabled={archiveMutation.isPending}
                      size="sm"
                      variant="outline"
                      onClick={() => void handleArchive(server.id)}
                    >
                      <Archive data-icon="inline-start" />
                      Archive
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{server.description || "No description provided."}</p>
                <p>
                  {server.transport === "stdio" ? server.command || "No command configured." : server.url || "No URL configured."}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
