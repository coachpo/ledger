import { type ComponentProps, useId } from "react";

import type { WireBinding } from "@/lib/platform-authoring/workflows/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

import type { WorkflowWireBindingSlotOption } from "./wire-binding-editor";

const NONE_OPTION = "__none__";

export type WorkflowSlotPickerValue = Pick<WireBinding, "slot" | "stepIndex">;

export type WorkflowSlotPickerProps = {
  description?: string;
  disabled?: boolean;
  emptyDescription?: string;
  emptyTitle?: string;
  label?: string;
  onChange: (nextValue: WorkflowSlotPickerValue) => void;
  slotLabel?: string;
  slotOptions?: readonly WorkflowWireBindingSlotOption[];
  stepLabel?: string;
  value: WorkflowSlotPickerValue;
} & ComponentProps<"div">;

function getWorkflowSlotStepOptions(
  slotOptions: readonly WorkflowWireBindingSlotOption[],
): number[] {
  return Array.from(new Set(slotOptions.map((option) => option.stepIndex))).sort(
    (left, right) => left - right,
  );
}

function getWorkflowSlotsForStep(
  slotOptions: readonly WorkflowWireBindingSlotOption[],
  stepIndex: number | null,
): WorkflowWireBindingSlotOption[] {
  if (stepIndex == null) {
    return [];
  }

  return slotOptions.filter((option) => option.stepIndex === stepIndex);
}

function findSelectedWorkflowSlotOption(
  value: WorkflowSlotPickerValue,
  slotOptions: readonly WorkflowWireBindingSlotOption[],
): WorkflowWireBindingSlotOption | undefined {
  if (value.stepIndex == null || !value.slot) {
    return undefined;
  }

  return slotOptions.find(
    (option) => option.stepIndex === value.stepIndex && option.slot === value.slot,
  );
}

export function WorkflowSlotPicker({
  className,
  description = "Choose a slot from an earlier workflow step.",
  disabled = false,
  emptyDescription =
    "Add at least one named slot on a prior step before wiring this selection.",
  emptyTitle = "No prior step slots available",
  label = "Prior step slot",
  onChange,
  slotLabel = "Slot",
  slotOptions = [],

  stepLabel = "Step",
  value,
  ...props
}: WorkflowSlotPickerProps) {
  const stepFieldId = useId();
  const slotFieldId = useId();
  const stepOptions = getWorkflowSlotStepOptions(slotOptions);
  const hasSlotOptions = slotOptions.length > 0;
  const hasSelectedStep = value.stepIndex != null && stepOptions.includes(value.stepIndex);
  const slotChoices = getWorkflowSlotsForStep(slotOptions, hasSelectedStep ? value.stepIndex : null);
  const selectedSlotOption = findSelectedWorkflowSlotOption(
    hasSelectedStep ? value : { slot: null, stepIndex: null },
    slotChoices,
  );
  const hasStaleSelection =
    (value.stepIndex != null && !hasSelectedStep) ||
    (Boolean(value.slot) && value.stepIndex != null && !selectedSlotOption);

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!hasSlotOptions ? (
          <Alert>
            <AlertTitle>{emptyTitle}</AlertTitle>

            <AlertDescription>{emptyDescription}</AlertDescription>
          </Alert>
        ) : null}

        {hasStaleSelection ? (
          <Alert>
            <AlertTitle>Current selection is unavailable</AlertTitle>
            <AlertDescription>
              The saved step or slot no longer exists in the available prior-step options.
              Pick a different slot to continue.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor={stepFieldId}>{stepLabel}</Label>
            <Select
              disabled={disabled || !hasSlotOptions}
              value={hasSelectedStep ? String(value.stepIndex) : NONE_OPTION}
              onValueChange={(nextValue) =>
                onChange({
                  slot: null,
                  stepIndex: nextValue === NONE_OPTION ? null : Number.parseInt(nextValue, 10),
                })
              }
            >
              <SelectTrigger aria-label={stepLabel} id={stepFieldId}>
                <SelectValue placeholder="Select step" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select step</SelectItem>
                  {stepOptions.map((stepIndex) => {
                    const stepSlotCount = getWorkflowSlotsForStep(slotOptions, stepIndex).length;

                    return (
                      <SelectItem key={`${stepFieldId}-${stepIndex}`} value={String(stepIndex)}>
                        {`Step ${stepIndex} · ${stepSlotCount} slot${stepSlotCount === 1 ? "" : "s"}`}
                      </SelectItem>
                    );
                  })}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor={slotFieldId}>{slotLabel}</Label>
            <Select
              disabled={disabled || !hasSelectedStep || slotChoices.length === 0}
              value={selectedSlotOption?.slot ?? NONE_OPTION}
              onValueChange={(nextValue) =>
                onChange({
                  slot: nextValue === NONE_OPTION ? null : nextValue,
                  stepIndex: hasSelectedStep ? value.stepIndex : null,
                })
              }
            >
              <SelectTrigger aria-label={slotLabel} id={slotFieldId}>
                <SelectValue placeholder="Select slot" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value={NONE_OPTION}>Select slot</SelectItem>
                  {slotChoices.map((option) => (
                    <SelectItem
                      key={`${slotFieldId}-${option.stepIndex}-${option.slot}`}
                      value={option.slot}
                    >
                      {option.slot}
                      {option.optional ? " (optional)" : ""}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
        </div>

        <Separator />

        <div className="flex flex-col gap-3 rounded-lg border border-border/70 bg-card/70 p-4 shadow-ui-xs">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {hasSelectedStep ? `Step ${value.stepIndex}` : "No step selected"}
            </Badge>
            <Badge variant="outline">{selectedSlotOption?.slot ?? "Slot pending"}</Badge>
            {selectedSlotOption?.optional ? <Badge variant="secondary">Optional slot</Badge> : null}
            {selectedSlotOption?.schema ? <Badge variant="secondary">Schema available</Badge> : null}
          </div>

          <p className="text-sm text-muted-foreground">
            {selectedSlotOption
              ? "The selected slot stays aligned with the shared workflow binding model, including its optional metadata and any resolved schema."
              : hasSlotOptions
                ? "Pick a prior step first, then choose one of that step's exposed slots."
                : "Prior-step slot choices will appear here once an earlier agent exposes a slot name."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
