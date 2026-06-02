import { Plus, Trash2 } from "lucide-react";

import {
  createEmptyWireBindingDraft,
  workflowPathTokensToPath,
} from "@/lib/platform-authoring/workflows/codec";
import { getObjectProperties } from "@/lib/platform-authoring/workflows/validation";
import type { WireBinding } from "@/lib/platform-authoring/workflows/types";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

const NONE_OPTION = "__none__";

export type WorkflowWireBindingSlotOption = {
  optional: boolean;
  schema?: unknown;
  slot: string;
  stepIndex: number;
};

export type WireBindingEditorProps = {
  binding: WireBinding;
  fieldName: string;
  inputSchema?: unknown;
  label?: string;
  onChange: (nextBinding: WireBinding) => void;
  slotOptions?: readonly WorkflowWireBindingSlotOption[];
};

function tokenizeFieldName(fieldName: string): string[] {
  return fieldName
    .split(".")
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function getAvailableKeys(schema: unknown, pathTokens: readonly string[]): string[] {
  let currentSchema = schema;

  for (const token of pathTokens) {
    const nextSchema = getObjectProperties(currentSchema)[token];
    if (!nextSchema) {
      return [];
    }
    currentSchema = nextSchema;
  }

  return Object.keys(getObjectProperties(currentSchema)).sort((left, right) =>
    left.localeCompare(right),
  );
}

function getLatestStepIndex(slotOptions: readonly WorkflowWireBindingSlotOption[]): number | null {
  if (slotOptions.length === 0) {
    return null;
  }

  return Math.max(...slotOptions.map((option) => option.stepIndex));
}

function getSlotSchema(
  binding: WireBinding,
  slotOptions: readonly WorkflowWireBindingSlotOption[],
): unknown {
  if (binding.source !== "step" || binding.stepIndex == null || !binding.slot) {
    return undefined;
  }

  return slotOptions.find(
    (option) => option.stepIndex === binding.stepIndex && option.slot === binding.slot,
  )?.schema;
}

type BindingPathEditorProps = {
  binding: WireBinding;
  fieldName: string;
  label: string;
  onChange: (nextBinding: WireBinding) => void;
  schema?: unknown;
};

function BindingPathEditor({
  binding,
  fieldName,
  label,
  onChange,
  schema,
}: BindingPathEditorProps) {
  const availableKeys = getAvailableKeys(schema, binding.pathTokens);
  const pathPreview = workflowPathTokensToPath(binding.pathTokens);

  const updateTokens = (nextTokens: string[]) => {
    onChange({
      ...binding,
      pathTokens: nextTokens.map((token) => token.trim()).filter(Boolean),
    });
  };

  return (
    <div className="flex flex-col gap-3 rounded-md border border-dashed bg-muted/20 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <Label>{label}</Label>
          <p className="text-sm text-muted-foreground">
            Edit the path as individual segments instead of a dotted string.
          </p>
        </div>
        <Badge variant="outline">{pathPreview ?? fieldName}</Badge>
      </div>

      {binding.pathTokens.length === 0 ? (
        <div className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
          {binding.source === "input"
            ? `No explicit path selected. This will fall back to "${fieldName}".`
            : "No nested path selected. The full slot payload will be used."}
        </div>
      ) : null}

      {binding.pathTokens.map((token, index) => (
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" key={`${label}-${index}`}>
          <Input
            aria-label={`${label} segment ${index + 1}`}
            placeholder={`Segment ${index + 1}`}
            value={token}
            onChange={(event) => {
              const nextTokens = [...binding.pathTokens];
              nextTokens[index] = event.target.value;
              updateTokens(nextTokens);
            }}
          />
          <Button
            aria-label={`Remove ${label} segment ${index + 1}`}
            size="icon"
            type="button"
            variant="outline"
            onClick={() =>
              updateTokens(binding.pathTokens.filter((_, currentIndex) => currentIndex !== index))
            }
          >
            <Trash2 />
          </Button>
        </div>
      ))}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          type="button"
          variant="outline"
          onClick={() =>
            updateTokens([...binding.pathTokens, `field_${binding.pathTokens.length + 1}`])
          }
        >
          <Plus data-icon="inline-start" />
          Add Segment
        </Button>
        {availableKeys.map((key) => (
          <Button
            key={`${label}-${key}`}
            size="sm"
            type="button"
            variant="outline"
            onClick={() => updateTokens([...binding.pathTokens, key])}
          >
            {key}
          </Button>
        ))}
      </div>
    </div>
  );
}

export function WireBindingEditor({
  binding,
  fieldName,
  inputSchema,
  label = fieldName,
  onChange,
  slotOptions = [],
}: WireBindingEditorProps) {
  const stepOptions = Array.from(new Set(slotOptions.map((option) => option.stepIndex))).sort(
    (left, right) => left - right,
  );
  const slotChoices =
    binding.source === "step" && binding.stepIndex != null
      ? slotOptions.filter((option) => option.stepIndex === binding.stepIndex)
      : [];
  const activeSchema =
    binding.source === "input" ? inputSchema : getSlotSchema(binding, slotOptions);

  return (
    <div className="flex flex-col gap-4 rounded-md border p-4">
      <div className="grid gap-4 md:grid-cols-4">
        <div className="flex flex-col gap-2">
          <Label>{label}</Label>
          <Select
            value={binding.source}
            onValueChange={(value: WireBinding["source"]) => {
              if (value === "none") {
                onChange(createEmptyWireBindingDraft());
                return;
              }

              if (value === "input") {
                onChange({
                  ...createEmptyWireBindingDraft(),
                  source: "input",
                  pathTokens: tokenizeFieldName(fieldName),
                });
                return;
              }

              onChange({
                ...createEmptyWireBindingDraft(),
                source: "step",
                stepIndex: getLatestStepIndex(slotOptions),
              });
            }}
          >
            <SelectTrigger aria-label={`${label} source`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="none">Not wired</SelectItem>
                <SelectItem value="input">Workflow input</SelectItem>
                <SelectItem value="step">Previous step slot</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {binding.source === "step" ? (
          <>
            <div className="flex flex-col gap-2">
              <Label>Step</Label>
              <Select
                value={binding.stepIndex != null ? String(binding.stepIndex) : NONE_OPTION}
                onValueChange={(value) =>
                  onChange({
                    ...binding,
                    slot: null,
                    stepIndex: value === NONE_OPTION ? null : Number.parseInt(value, 10),
                  })
                }
              >
                <SelectTrigger aria-label={`${label} step`}>
                  <SelectValue placeholder="Select step" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE_OPTION}>Select step</SelectItem>
                    {stepOptions.map((stepIndex) => (
                      <SelectItem key={`${label}-step-${stepIndex}`} value={String(stepIndex)}>
                        Step {stepIndex}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label>Slot</Label>
              <Select
                value={binding.slot ?? NONE_OPTION}
                onValueChange={(value) =>
                  onChange({ ...binding, slot: value === NONE_OPTION ? null : value })
                }
              >
                <SelectTrigger aria-label={`${label} slot`}>
                  <SelectValue placeholder="Select slot" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE_OPTION}>Select slot</SelectItem>
                    {slotChoices.map((option) => (
                      <SelectItem
                        key={`${label}-slot-${option.stepIndex}-${option.slot}`}
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

            <div className="flex items-end">
              <Badge className="h-fit" variant="outline">
                {binding.slot ? `Step ${binding.stepIndex} · ${binding.slot}` : "Slot pending"}
              </Badge>
            </div>
          </>
        ) : null}
      </div>

      {binding.source === "none" ? (
        <InlineStatePanel description="Leave this unwired to skip the source entirely." />
      ) : null}

      {binding.source !== "none" ? (
        <BindingPathEditor
          binding={binding}
          fieldName={fieldName}
          label={binding.source === "input" ? "Input path" : "Slot path"}
          onChange={onChange}
          schema={activeSchema}
        />
      ) : null}
    </div>
  );
}
