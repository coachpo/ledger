import { type ComponentProps, type ReactNode, useMemo } from "react";
import { AlertCircle, ArrowLeft, ArrowRight, Plus } from "lucide-react";

import { createEmptyWorkflowStep } from "@/lib/platform-authoring/workflows/draft";
import type {
  WorkflowDraft,
  WorkflowSection,
  WorkflowValidationIssue,
} from "@/lib/platform-authoring/workflows/types";
import type { AgentRead } from "@/lib/types/agent";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/components/ui/utils";

import { WorkflowStepEditor } from "./workflow-step-editor";

export const WORKFLOW_BUILDER_WIZARD_SECTIONS = [
  {
    description:
      "Set the workflow identity and define the request schema that step wiring can reference.",
    title: "Input",
    value: "input",
  },
  {
    description: "Arrange parallel steps and map pinned agents into named slots.",
    title: "Steps",
    value: "steps",
  },
  {
    description: "Choose the final output slot or synthesized output agent.",
    title: "Output",
    value: "output",
  },
  {
    description: "Review validation, payload structure, and run readiness.",
    title: "Review",
    value: "review",
  },
] as const satisfies readonly {
  description: string;
  title: string;
  value: WorkflowSection;
}[];

export function workflowBuilderSectionForIssue(field: string): WorkflowSection {
  if (field === "key" || field === "name" || field.startsWith("inputSchema")) {
    return "input";
  }

  if (field.startsWith("steps")) {
    return "steps";
  }

  if (field.startsWith("outputSpec")) {
    return "output";
  }

  return "review";
}

export type WorkflowBuilderWizardProps = {
  activeSection: WorkflowSection;
  inputSection: ReactNode;
  onActiveSectionChange: (nextSection: WorkflowSection) => void;
  onDraftChange: (nextDraft: WorkflowDraft) => void;
  outputSection: ReactNode;
  reviewActions?: ReactNode;
  reviewSection: ReactNode;
  stepAddLabel?: string;
  validationIssues?: readonly WorkflowValidationIssue[];
  workflowAgents: readonly AgentRead[];
  workflowDraft: WorkflowDraft;
} & Omit<ComponentProps<"div">, "onChange">;

function updateStepAtIndex(
  draft: WorkflowDraft,
  stepIndex: number,
  updater: (currentStep: WorkflowDraft["steps"][number]) => WorkflowDraft["steps"][number],
): WorkflowDraft {
  return {
    ...draft,
    steps: draft.steps.map((step, currentStepIndex) =>
      currentStepIndex === stepIndex ? updater(step) : step,
    ),
  };
}

export function WorkflowBuilderWizard({
  activeSection,
  className,
  inputSection,
  onActiveSectionChange,
  onDraftChange,
  outputSection,
  reviewActions,
  reviewSection,
  stepAddLabel = "Add Step",
  validationIssues = [],
  workflowAgents,
  workflowDraft,
  ...props
}: WorkflowBuilderWizardProps) {
  const activeIndex = Math.max(
    0,
    WORKFLOW_BUILDER_WIZARD_SECTIONS.findIndex((section) => section.value === activeSection),
  );
  const progressValue =
    ((activeIndex + 1) / WORKFLOW_BUILDER_WIZARD_SECTIONS.length) * 100;
  const canGoBack = activeIndex > 0;
  const canGoNext = activeSection !== "review";
  const activeSectionMeta = WORKFLOW_BUILDER_WIZARD_SECTIONS[activeIndex];

  const stepsSection = useMemo(
    () => (
      <div className="flex flex-col gap-4">
        {workflowDraft.steps.map((step, stepIndex) => (
          <WorkflowStepEditor
            currentStepNumber={stepIndex + 1}
            key={step.id}
            onChange={(nextStep) =>
              onDraftChange(updateStepAtIndex(workflowDraft, stepIndex, () => nextStep))
            }
            onRemove={
              workflowDraft.steps.length > 1
                ? () =>
                    onDraftChange({
                      ...workflowDraft,
                      steps: workflowDraft.steps.filter((_, currentIndex) => currentIndex !== stepIndex),
                    })
                : undefined
            }
            step={step}
            workflowAgents={workflowAgents}
            workflowDraft={workflowDraft}
          />
        ))}

        <Button
          className="w-fit"
          size="sm"
          type="button"
          variant="outline"
          onClick={() =>
            onDraftChange({
              ...workflowDraft,
              steps: [...workflowDraft.steps, createEmptyWorkflowStep()],
            })
          }
        >
          <Plus data-icon="inline-start" />
          {stepAddLabel}
        </Button>
      </div>
    ),
    [onDraftChange, stepAddLabel, workflowAgents, workflowDraft],
  );

  return (
    <div className={cn("flex flex-col gap-4", className)} {...props}>
      {validationIssues.length > 0 ? (
        <Alert data-testid="workflow-builder-validation-feedback" variant="destructive">
          <AlertCircle />
          <AlertTitle>Workflow validation needs attention</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {validationIssues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>{`${issue.field}: ${issue.issue}`}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="flex flex-col gap-4 pt-6">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                Step {activeIndex + 1} of {WORKFLOW_BUILDER_WIZARD_SECTIONS.length}
              </span>
              <span>{activeSectionMeta?.title}</span>
            </div>
            <Progress value={progressValue} />
          </div>

          <Tabs value={activeSection} onValueChange={(value) => onActiveSectionChange(value as WorkflowSection)}>
            <TabsList className="w-full justify-start">
              {WORKFLOW_BUILDER_WIZARD_SECTIONS.map((section) => (
                <TabsTrigger key={section.value} value={section.value}>
                  {section.title}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent forceMount value="input">
              {inputSection}
            </TabsContent>

            <TabsContent forceMount value="steps">
              {stepsSection}
            </TabsContent>

            <TabsContent forceMount value="output">
              {outputSection}
            </TabsContent>

            <TabsContent forceMount value="review">
              {reviewSection}
            </TabsContent>
          </Tabs>

          <Separator />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Button
              disabled={!canGoBack}
              size="sm"
              type="button"
              variant="outline"
              onClick={() =>
                onActiveSectionChange(
                  WORKFLOW_BUILDER_WIZARD_SECTIONS[Math.max(0, activeIndex - 1)].value,
                )
              }
            >
              <ArrowLeft data-icon="inline-start" />
              Back
            </Button>

            {canGoNext ? (
              <Button
                data-testid="workflow-builder-wizard-next"
                size="sm"
                type="button"
                onClick={() =>
                  onActiveSectionChange(
                    WORKFLOW_BUILDER_WIZARD_SECTIONS[
                      Math.min(WORKFLOW_BUILDER_WIZARD_SECTIONS.length - 1, activeIndex + 1)
                    ].value,
                  )
                }
              >
                Next
                <ArrowRight data-icon="inline-end" />
              </Button>
            ) : (
              <div className="flex flex-wrap gap-2">{reviewActions}</div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
