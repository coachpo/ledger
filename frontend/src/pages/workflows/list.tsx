import { PlayCircle, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";

import { useWorkflows } from "@/hooks/use-workflows";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges } from "../platform-resource-shared";

export function WorkflowsListPage() {
  const navigate = useNavigate();
  const workflowsQuery = useWorkflows();
  const workflows = workflowsQuery.data?.items ?? [];

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="workflows-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold tracking-tight">Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Author multi-step agent workflows with pinned versions, explicit slot wiring,
            and a review-first path into the new runs monitor.
          </p>
        </div>
        <Button data-testid="workflows-new" size="sm" onClick={() => navigate("/workflows/new")}>
          <Plus data-icon="inline-start" />
          New Workflow
        </Button>
      </div>

      {workflowsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading workflows...
          </CardContent>
        </Card>
      ) : null}

      {workflowsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {workflowsQuery.error instanceof Error
              ? workflowsQuery.error.message
              : "Failed to load workflows."}
          </CardContent>
        </Card>
      ) : null}

      {!workflowsQuery.isPending && !workflowsQuery.isError && workflows.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No workflows exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!workflowsQuery.isPending && !workflowsQuery.isError && workflows.length > 0 ? (
        <div className="grid gap-3">
          {workflows.map((workflow) => (
            <Card key={workflow.id} data-testid={`workflows-row-${workflow.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-col gap-1">
                    <CardTitle className="text-base">{workflow.name}</CardTitle>
                    <CardDescription>{workflow.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges status={workflow.status} version={workflow.version} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`workflows-open-${workflow.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/workflows/${workflow.id}/edit`)}
                  >
                    <SquarePen data-icon="inline-start" />
                    Edit
                  </Button>
                  <Button
                    data-testid={`workflows-run-${workflow.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/workflows/${workflow.id}/run`)}
                  >
                    <PlayCircle data-icon="inline-start" />
                    Run Now
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
                <p>{workflow.description || "No description provided."}</p>
                <p>
                  {workflow.steps.length} step(s) · Aggregate budget {workflow.aggregateBudgetUsd}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
