import { type ComponentProps, useId } from "react";
import { AlertCircle, Trash2 } from "lucide-react";

import { createEmptyWireBindingDraft } from "@/lib/platform-authoring/workflows/codec";
import {
  findAgentByKey,
  getSchemaFieldNames,
} from "@/lib/platform-authoring/workflows/validation";
import type { WorkflowDraft, WorkflowDraftAgent } from "@/lib/platform-authoring/workflows/types";
import type { AgentRead } from "@/lib/types/agent";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/components/ui/utils";

import {
  WireBindingEditor,
  type WorkflowWireBindingSlotOption,
} from "./wire-binding-editor";

const NONE_OPTION = "__none__";

function collectPreviousStepSlotOptions(
  workflowDraft: WorkflowDraft,
  workflowAgents: readonly AgentRead[],
  currentStepNumber: number,
): WorkflowWireBindingSlotOption[] {
  return workflowDraft.steps
    .slice(0, Math.max(0, currentStepNumber - 1))
    .flatMap((step, stepIndex) =>
      step.agents.flatMap((draftAgent) => {
        const slot = draftAgent.slot.trim();
        const resolvedAgent = findAgentByKey(workflowAgents, draftAgent.agentKey);

        if (!slot || !resolvedAgent) {
          return [];
        }

        return [
          {
            optional: draftAgent.optional,
            schema: resolvedAgent.outputSchema.jsonSchema,
            slot,
            stepIndex: stepIndex + 1,
          },
        ];
      }),
    );
}

export type WorkflowAgentCardProps = {
  currentStepNumber: number;
  draftAgent: WorkflowDraftAgent;
  heading: string;
  onChange: (nextAgent: WorkflowDraftAgent) => void;
  onRemove?: () => void;
  workflowAgents: readonly AgentRead[];
  workflowDraft: WorkflowDraft;
} & ComponentProps<"div">;

export function WorkflowAgentCard({
  className,
  currentStepNumber,
  draftAgent,
  heading,
  onChange,
  onRemove,
  workflowAgents,
  workflowDraft,
  ...props
}: WorkflowAgentCardProps) {
  const agentFieldId = useId();
  const versionFieldId = useId();
  const slotFieldId = useId();
  const optionalFieldId = useId();
  const resolvedAgent = findAgentByKey(workflowAgents, draftAgent.agentKey);
  const fieldNames = getSchemaFieldNames(resolvedAgent?.inputSchema, draftAgent.wiring);
  const slotOptions = collectPreviousStepSlotOptions(workflowDraft, workflowAgents, currentStepNumber);

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <div className="flex flex-col gap-1">
          <CardTitle className="text-base">{heading}</CardTitle>
          <CardDescription>
            Pin an agent version, assign its slot name, and map every required input field.
          </CardDescription>
        </div>
        {onRemove ? (
          <CardAction>
            <Button size="sm" type="button" variant="outline" onClick={onRemove}>
              <Trash2 data-icon="inline-start" />
              Remove Agent
            </Button>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-4">
          <div className="flex flex-col gap-2 md:col-span-2">
            <Label htmlFor={agentFieldId}>Agent</Label>
            <Select
              value={draftAgent.agentKey || NONE_OPTION}
              onValueChange={(value) =>
                onChange({
                  ...draftAgent,
                  agentKey: value === NONE_OPTION ? "" : value,
                })
              }
            >
              <SelectTrigger aria-label={`${heading} agent`} id={agentFieldId}>
                <SelectValue placeholder="Select agent" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select agent</SelectItem>
                  {workflowAgents.map((agent) => (
                    <SelectItem key={agent.id} value={agent.key}>
                      {agent.name} ({agent.key}@{agent.version})
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor={versionFieldId}>Pinned version</Label>
            <Input
              id={versionFieldId}
              aria-label={`${heading} version`}
              placeholder={resolvedAgent ? String(resolvedAgent.version) : "1"}
              value={draftAgent.agentVersion}
              onChange={(event) => onChange({ ...draftAgent, agentVersion: event.target.value })}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor={slotFieldId}>Slot</Label>
            <Input
              id={slotFieldId}
              aria-label={`${heading} slot`}
              placeholder="analysis"
              value={draftAgent.slot}
              onChange={(event) => onChange({ ...draftAgent, slot: event.target.value })}
            />
          </div>
        </div>

        <div className="flex items-center justify-between rounded-md border p-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor={optionalFieldId}>Optional slot</Label>
            <p className="text-sm text-muted-foreground">
              Optional agents may fail and provide a null slot for downstream wiring.
            </p>
          </div>
          <Switch
            id={optionalFieldId}
            checked={draftAgent.optional}
            onCheckedChange={(checked) => onChange({ ...draftAgent, optional: checked })}
          />
        </div>

        {!resolvedAgent && draftAgent.agentKey.trim() ? (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Agent not found</AlertTitle>
            <AlertDescription>
              The saved workflow references `{draftAgent.agentKey}`, but that agent is not in the
              current latest-version catalog.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-col gap-1">
              <h3 className="text-sm font-medium">Slot wiring</h3>
              <p className="text-sm text-muted-foreground">
                Map each agent input field from the workflow input or an earlier slot.
              </p>
            </div>
            {resolvedAgent ? <Badge variant="outline">{fieldNames.length} mapped field(s)</Badge> : null}
          </div>

          {fieldNames.length === 0 ? (
            <div className="rounded-lg border border-border/70 bg-card/70 p-4 text-sm text-muted-foreground shadow-ui-xs">
              Select an agent with an object input schema to configure slot wiring controls.
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {fieldNames.map((fieldName) => (
                <WireBindingEditor
                  binding={draftAgent.wiring[fieldName] ?? createEmptyWireBindingDraft()}
                  fieldName={fieldName}
                  inputSchema={resolvedAgent?.inputSchema}
                  key={`${heading}-${fieldName}`}
                  onChange={(nextBinding) =>
                    onChange({
                      ...draftAgent,
                      wiring: { ...draftAgent.wiring, [fieldName]: nextBinding },
                    })
                  }
                  slotOptions={slotOptions}
                />
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
