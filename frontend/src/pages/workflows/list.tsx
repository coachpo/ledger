import { Eye, PlayCircle, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";

import { useWorkflows } from "@/hooks/use-workflows";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import {
  PlatformResourceBadges,
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

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
        <Button
          className="cursor-pointer"
          data-testid="workflows-new"
          size="sm"
          onClick={() => navigate("/workflows/new")}
        >
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
        <PlatformResourceList>
          {workflows.map((workflow) => (
            <PlatformResourceCard
              key={workflow.id}
              actions={
                <>
                  <Button
                    data-testid={`workflows-detail-${workflow.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/workflows/${workflow.id}`)}
                  >
                    <Eye data-icon="inline-start" />
                    Detail
                  </Button>
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
                </>
              }
              badges={<PlatformResourceBadges status={workflow.status} version={workflow.version} />}
              description={workflow.description || "No description provided."}
              metadata={
                <p className="text-sm text-muted-foreground">
                  {workflow.steps.length} step(s) · Aggregate budget {workflow.aggregateBudgetUsd}
                </p>
              }
              subtitle={workflow.key}
              testId={`workflows-row-${workflow.key}`}
              title={workflow.name}
            />
          ))}
        </PlatformResourceList>
      ) : null}
    </div>
  );
}
