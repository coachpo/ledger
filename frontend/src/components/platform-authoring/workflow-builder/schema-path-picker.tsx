import { Plus, Trash2 } from "lucide-react";
import { type ComponentProps, useId } from "react";

import { workflowPathTokensToPath } from "@/lib/platform-authoring/workflows/codec";
import { getObjectProperties } from "@/lib/platform-authoring/workflows/validation";
import type { WorkflowBindingPath } from "@/lib/platform-authoring/workflows/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
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
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

const NONE_OPTION = "__none__";
const CUSTOM_OPTION = "__custom__";

export type WorkflowSchemaPathPickerValue = WorkflowBindingPath;

export type WorkflowSchemaPathPickerProps = {
  description?: string;
  disabled?: boolean;
  emptyPathDescription?: string;
  label?: string;
  noSchemaDescription?: string;
  onChange: (nextValue: WorkflowSchemaPathPickerValue) => void;
  schema?: unknown;
  value: WorkflowSchemaPathPickerValue;
} & ComponentProps<"div">;

function normalizePathTokens(pathTokens: readonly string[]): string[] {
  return pathTokens.map((token) => token.trim()).filter(Boolean);
}

function getAvailableKeys(
  schema: unknown,
  pathTokens: readonly string[],
): string[] {
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

function findInvalidTokenIndex(
  schema: unknown,
  pathTokens: readonly string[],
): number | null {
  let currentSchema = schema;

  for (const [index, token] of pathTokens.entries()) {
    const nextSchema = getObjectProperties(currentSchema)[token];
    if (!nextSchema) {
      return index;
    }
    currentSchema = nextSchema;
  }

  return null;
}

function getSegmentOptions(
  schema: unknown,
  pathTokens: readonly string[],
  index: number,
): string[] {
  return getAvailableKeys(schema, pathTokens.slice(0, index));
}

export function WorkflowSchemaPathPicker({
  className,
  description = "Select schema path segments as tokens instead of editing a dotted path string.",
  disabled = false,
  emptyPathDescription = "Empty path selects the full schema value.",
  label = "Schema path",
  noSchemaDescription = "Schema-aware suggestions appear when a JSON schema is available for this binding source.",
  onChange,
  schema,
  value,
  ...props
}: WorkflowSchemaPathPickerProps) {
  const id = useId();
  const normalizedValue = normalizePathTokens(value);
  const pathPreview = workflowPathTokensToPath(normalizedValue);
  const hasSchema = typeof schema !== "undefined";
  const invalidTokenIndex = hasSchema
    ? findInvalidTokenIndex(schema, normalizedValue)
    : null;
  const availableNextKeys = hasSchema
    ? getAvailableKeys(schema, normalizedValue)
    : [];

  const updatePathTokens = (nextValue: readonly string[]) => {
    onChange(normalizePathTokens(nextValue));
  };

  const replaceToken = (index: number, nextToken: string) => {
    const nextValue = [...normalizedValue];
    nextValue[index] = nextToken;
    updatePathTokens(nextValue);
  };

  const removeToken = (index: number) => {
    updatePathTokens(
      normalizedValue.filter((_, currentIndex) => currentIndex !== index),
    );
  };

  const addToken = (nextToken: string) => {
    updatePathTokens([...normalizedValue, nextToken]);
  };

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {!hasSchema ? (
          <Alert>
            <AlertTitle>Schema suggestions unavailable</AlertTitle>
            <AlertDescription>{noSchemaDescription}</AlertDescription>
          </Alert>
        ) : null}

        {invalidTokenIndex != null ? (
          <Alert>
            <AlertTitle>Current path no longer matches the schema</AlertTitle>
            <AlertDescription>
              Segment {invalidTokenIndex + 1} (
              <code>{normalizedValue[invalidTokenIndex]}</code>) is not
              available at this level anymore. You can keep editing the
              tokenized path manually or replace it with one of the current
              schema keys.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-col gap-3 rounded-md border border-dashed bg-muted/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{pathPreview ?? "No path selected"}</Badge>
            <Badge variant="outline">
              {normalizedValue.length} segment
              {normalizedValue.length === 1 ? "" : "s"}
            </Badge>
            <Badge variant="secondary">
              {hasSchema ? "Schema-aware" : "Manual editing"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {normalizedValue.length > 0
              ? "Each path segment stays tokenized in the workflow draft model so later codec and validation layers can keep dotted-path conversion at the boundary only."
              : emptyPathDescription}
          </p>
        </div>

        {normalizedValue.length > 0 ? <Separator /> : null}

        <div className="flex flex-col gap-4">
          {normalizedValue.map((token, index) => {
            const segmentOptions = hasSchema
              ? getSegmentOptions(schema, normalizedValue, index)
              : [];
            const hasSegmentOptions = segmentOptions.length > 0;
            const isCustomToken = hasSegmentOptions
              ? !segmentOptions.includes(token)
              : true;
            const selectValue = hasSegmentOptions
              ? isCustomToken
                ? CUSTOM_OPTION
                : token
              : NONE_OPTION;
            const segmentFieldId = `${id}-segment-${index}`;
            const customFieldId = `${segmentFieldId}-custom`;
            const gridClassName =
              hasSegmentOptions && isCustomToken
                ? "md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
                : "md:grid-cols-[minmax(0,1fr)_auto]";

            return (
              <div
                className={cn("grid gap-3", gridClassName)}
                key={`${segmentFieldId}-${token}`}
              >
                <div className="flex flex-col gap-2">
                  <Label htmlFor={segmentFieldId}>Segment {index + 1}</Label>
                  {hasSegmentOptions ? (
                    <Select
                      disabled={disabled}
                      value={selectValue}
                      onValueChange={(nextValue) => {
                        if (nextValue === CUSTOM_OPTION) {
                          replaceToken(
                            index,
                            isCustomToken ? token : `field_${index + 1}`,
                          );
                          return;
                        }

                        if (nextValue === NONE_OPTION) {
                          replaceToken(index, "");
                          return;
                        }

                        replaceToken(index, nextValue);
                      }}
                    >
                      <SelectTrigger
                        aria-label={`Segment ${index + 1}`}
                        id={segmentFieldId}
                      >
                        <SelectValue
                          placeholder={`Select segment ${index + 1}`}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value={CUSTOM_OPTION}>
                            Custom value
                          </SelectItem>
                          {segmentOptions.map((option) => (
                            <SelectItem
                              key={`${segmentFieldId}-${option}`}
                              value={option}
                            >
                              {option}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      aria-label={`Segment ${index + 1}`}
                      disabled={disabled}
                      id={segmentFieldId}
                      placeholder={`Segment ${index + 1}`}
                      value={token}
                      onChange={(event) =>
                        replaceToken(index, event.target.value)
                      }
                    />
                  )}
                </div>

                {hasSegmentOptions && isCustomToken ? (
                  <div className="flex flex-col gap-2">
                    <Label htmlFor={customFieldId}>Custom segment</Label>
                    <Input
                      aria-label={`Custom segment ${index + 1}`}
                      disabled={disabled}
                      id={customFieldId}
                      placeholder={`Segment ${index + 1}`}
                      value={token}
                      onChange={(event) =>
                        replaceToken(index, event.target.value)
                      }
                    />
                  </div>
                ) : null}

                <div className="flex items-end">
                  <Button
                    aria-label={`Remove segment ${index + 1}`}
                    disabled={disabled}
                    size="icon"
                    type="button"
                    variant="outline"
                    onClick={() => removeToken(index)}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>

        <Separator />

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={disabled}
              size="sm"
              type="button"
              variant="outline"
              onClick={() => addToken(`field_${normalizedValue.length + 1}`)}
            >
              <Plus data-icon="inline-start" />
              Add custom segment
            </Button>
            {availableNextKeys.map((key) => (
              <Button
                disabled={disabled}
                key={`${id}-next-${key}`}
                size="sm"
                type="button"
                variant="outline"
                onClick={() => addToken(key)}
              >
                {key}
              </Button>
            ))}
          </div>

          <p className="text-sm text-muted-foreground">
            {availableNextKeys.length > 0
              ? "Choose the next segment from the current schema branch or add a custom token when the schema is incomplete."
              : hasSchema
                ? "No deeper object properties are available at the current path. Add a custom token only if the schema is intentionally incomplete."
                : "Without schema metadata this picker falls back to direct token editing while keeping the workflow path model tokenized."}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
