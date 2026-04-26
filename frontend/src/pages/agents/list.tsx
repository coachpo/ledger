import { Archive, Copy, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { useAgents, useArchiveAgent } from "@/hooks/use-agents";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

export function AgentsListPage() {
  const navigate = useNavigate();
  const agentsQuery = useAgents();
  const archiveMutation = useArchiveAgent();
  const agents = sortByKey(agentsQuery.data?.items ?? []);

  const handleArchive = async (agentId: number) => {
    try {
      await archiveMutation.mutateAsync(agentId);
      toast.success("Agent archived");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive agent");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="platform-agents-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="agents-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Create and update primary workspace agents, including saved model connections,
            output schema bindings, attached skill or MCP references, and editor-ready run-launch inputs.
          </p>
        </div>
        <Button data-testid="agents-new" size="sm" onClick={() => navigate("/agents/new")}>
          <Plus data-icon="inline-start" />
          New Agent
        </Button>
      </div>

      {agentsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading agents...
          </CardContent>
        </Card>
      ) : null}

      {agentsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {agentsQuery.error instanceof Error ? agentsQuery.error.message : "Failed to load agents."}
          </CardContent>
        </Card>
      ) : null}

      {!agentsQuery.isPending && !agentsQuery.isError && agents.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No agents exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!agentsQuery.isPending && !agentsQuery.isError && agents.length > 0 ? (
        <div className="grid gap-3">
          {agents.map((agent) => (
            <Card key={agent.id} data-testid={`agents-row-${agent.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{agent.name}</CardTitle>
                    <CardDescription>{agent.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges
                    status={agent.status}
                    version={agent.version}
                    extra={
                      <>
                        <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                          {agent.modelConnection.modelId}
                        </span>
                      </>
                    }
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`agents-duplicate-${agent.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/agents/new?duplicateFrom=${agent.id}`)}
                  >
                    <Copy data-icon="inline-start" />
                    Duplicate
                  </Button>
                  <Button
                    data-testid={`agents-open-${agent.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/agents/${agent.id}/edit`)}
                  >
                    <SquarePen data-icon="inline-start" />
                    Edit
                  </Button>
                  {agent.status !== "archived" ? (
                    <Button
                      data-testid={`agents-archive-${agent.key}`}
                      disabled={archiveMutation.isPending}
                      size="sm"
                      variant="outline"
                      onClick={() => void handleArchive(agent.id)}
                    >
                      <Archive data-icon="inline-start" />
                      Archive
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{agent.description || "No description provided."}</p>
                <p>
                  Output schema: {agent.outputSchema.key} · Skills: {agent.skills.length} · MCP servers: {agent.mcpServers.length}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
