import { useMemo } from "react";
import { Pencil, Plus } from "lucide-react";
import { useNavigate } from "react-router";

import { useStudioWorkflowSpecs } from "@/hooks/use-studio";
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

export function StudioWorkflowsListPage() {
  const navigate = useNavigate();
  const workflowsQuery = useStudioWorkflowSpecs();
  const workflows = useMemo(
    () => sortByKey(workflowsQuery.data?.items ?? []),
    [workflowsQuery.data?.items],
  );

  return (
    <div className="space-y-4 p-4" data-testid="studio-workflows-list">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Studio Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Inspect workflow graph definitions and keep managed drafts editable from key-based Studio routes.
          </p>
        </div>
        <Button size="sm" onClick={() => navigate("/studio/workflows/new")}>
          <Plus className="mr-1 size-3.5" />
          New Workflow
        </Button>
      </div>

      {workflowsQuery.isPending ? <div className="p-4 text-sm text-muted-foreground">Loading workflow specs...</div> : null}
      {workflowsQuery.isError ? <div className="p-4 text-sm text-muted-foreground">{workflowsQuery.error instanceof Error ? workflowsQuery.error.message : "Failed to load Studio workflows."}</div> : null}

      {!workflowsQuery.isPending && !workflowsQuery.isError && workflows.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">No Studio workflows yet.</CardContent>
        </Card>
      ) : null}

      {!workflowsQuery.isPending && !workflowsQuery.isError ? (
        <div className="flex flex-col gap-3">
          {workflows.map((workflow) => {
            const isReadOnly = workflow.origin !== "managed";

            return (
              <Card key={workflow.id}>
                <CardHeader className="gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base font-semibold">{workflow.name}</CardTitle>
                    <StudioResourceBadges
                      origin={workflow.origin}
                      status={workflow.status}
                      version={workflow.version}
                      extra={isReadOnly ? <Badge variant="outline">Read-only</Badge> : <Badge variant="secondary">Editable</Badge>}
                    />
                  </div>
                  <CardDescription>{workflow.key}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">Entry agent: {workflow.entryAgentKey ?? "None"}</p>
                  <p className="text-xs text-muted-foreground">Updated {formatDateTime(workflow.updatedAt)}</p>
                  <div className="flex items-center justify-end gap-2">
                    <Button size="sm" variant={isReadOnly ? "outline" : "secondary"} onClick={() => navigate(`/studio/workflows/${workflow.key}/edit`)}>
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
