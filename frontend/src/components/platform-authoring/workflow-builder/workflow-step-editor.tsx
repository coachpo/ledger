import { type ComponentProps } from "react";
import { Plus, Trash2 } from "lucide-react";

import { createEmptyWorkflowAgent } from "@/lib/platform-authoring/workflows/draft";
import type {
  WorkflowDraft,
  WorkflowDraftAgent,
  WorkflowDraftStep,
} from "@/lib/platform-authoring/workflows/types";
import type { AgentRead } from "@/lib/types/agent";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

import { WorkflowAgentCard } from "./workflow-agent-card";

export type WorkflowStepEditorProps = {
  currentStepNumber: number;
  onChange: (nextStep: WorkflowDraftStep) => void;
  onRemove?: () => void;
  step: WorkflowDraftStep;
  workflowAgents: readonly AgentRead[];
  workflowDraft: WorkflowDraft;
} & Omit<ComponentProps<"div">, "onChange">;

export function WorkflowStepEditor({
  className,
  currentStepNumber,
  onChange,
  onRemove,
  step,
  workflowAgents,
  workflowDraft,
  ...props
}: WorkflowStepEditorProps) {
  const heading = `Step ${currentStepNumber}`;

  const updateAgents = (nextAgents: WorkflowDraftAgent[]) => {
    onChange({
      ...step,
      agents: nextAgents,
    });
  };

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <div className="flex flex-col gap-1">
          <CardTitle>{heading}</CardTitle>
          <CardDescription>
            Agents in the same step run together and publish their outputs to named slots.
          </CardDescription>
        </div>
        {onRemove ? (
          <CardAction>
            <Button size="sm" type="button" variant="outline" onClick={onRemove}>
              <Trash2 data-icon="inline-start" />
              Remove Step
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {step.agents.map((draftAgent, agentIndex) => (
          <WorkflowAgentCard
            currentStepNumber={currentStepNumber}
            draftAgent={draftAgent}
            heading={`${heading} Agent ${agentIndex + 1}`}
            key={`${step.id}-${agentIndex}`}
            onChange={(nextAgent) => {
              const nextDraftAgent = nextAgent as WorkflowDraftAgent;

              updateAgents(
                step.agents.map((currentAgent, currentAgentIndex) =>
                  currentAgentIndex === agentIndex ? nextDraftAgent : currentAgent,
                ),
              );
            }}
            onRemove={
              step.agents.length > 1
                ? () =>
                    updateAgents(
                      step.agents.filter(
                        (_, currentAgentIndex) => currentAgentIndex !== agentIndex,
                      ),
                    )
                : undefined
            }
            workflowAgents={workflowAgents}
            workflowDraft={workflowDraft}
          />
        ))}

        <Button
          className="w-fit"
          size="sm"
          type="button"
          variant="outline"
          onClick={() => updateAgents([...step.agents, createEmptyWorkflowAgent()])}
        >
          <Plus data-icon="inline-start" />
          Add Agent
        </Button>
      </CardContent>
    </Card>
  );
}
