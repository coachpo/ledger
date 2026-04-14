import { useMemo } from "react";
import { Pencil, Plus } from "lucide-react";
import { useNavigate } from "react-router";

import { useStudioAgentSpecs } from "@/hooks/use-studio";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { StudioResourceBadges } from "../shared";
import { sortByKey } from "../shared-utils";

export function StudioAgentsListPage() {
  const navigate = useNavigate();
  const agentsQuery = useStudioAgentSpecs();
  const agents = useMemo(() => sortByKey(agentsQuery.data?.items ?? []), [agentsQuery.data?.items]);

  return (
    <div className="space-y-4 p-4" data-testid="studio-agents-list">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Studio Agents</h1>
          <p className="text-sm text-muted-foreground">
            Managed agent specs stay editable in Studio while seeded rows remain inspectable but read-only.
          </p>
        </div>
        <Button data-testid="studio-agents-new" size="sm" onClick={() => navigate("/studio/agents/new")}>
          <Plus className="mr-1 size-3.5" />
          New Agent
        </Button>
      </div>

      {agentsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">Loading agent specs...</CardContent>
        </Card>
      ) : null}

      {agentsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {agentsQuery.error instanceof Error ? agentsQuery.error.message : "Failed to load Studio agents."}
          </CardContent>
        </Card>
      ) : null}

      {!agentsQuery.isPending && !agentsQuery.isError && agents.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">No Studio agents yet.</CardContent>
        </Card>
      ) : null}

      {!agentsQuery.isPending && !agentsQuery.isError ? (
        <div className="flex flex-col gap-3">
          {agents.map((agent) => {
            const isReadOnly = agent.origin !== "managed";

            return (
              <Card data-testid={`studio-agents-row-${agent.key}`} key={agent.id}>
                <CardHeader className="gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base font-semibold">{agent.name}</CardTitle>
                    <StudioResourceBadges
                      origin={agent.origin}
                      status={agent.status}
                      version={agent.version}
                      extra={isReadOnly ? <Badge variant="outline">Read-only</Badge> : <Badge variant="secondary">Editable</Badge>}
                    />
                  </div>
                  <CardDescription>{agent.key}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">{agent.instructions}</p>
                  <p className="text-xs text-muted-foreground">Updated {formatDateTime(agent.updatedAt)}</p>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      aria-label={`Open ${agent.name}`}
                      data-testid={`studio-agents-open-${agent.key}`}
                      size="sm"
                      variant={isReadOnly ? "outline" : "secondary"}
                      onClick={() => navigate(`/studio/agents/${agent.key}/edit`)}
                    >
                      <Pencil className="mr-1 size-3.5" />
                      {isReadOnly ? "Inspect" : "Edit"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
