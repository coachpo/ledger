import { type ComponentProps, useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";

import {
  formatResourceRef,
  type ResourceRef,
} from "@/lib/platform-authoring/common/resource-ref";
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
import { cn } from "@/components/ui/utils";

import {
  ResourceRefSelect,
  type ResourceRefSelectOption,
} from "./resource-ref-select";

type ResourceMultiRefSelectProps = {
  addLabel?: string;
  description?: string;
  disabled?: boolean;
  emptyDescription?: string;
  emptyTitle?: string;
  label?: string;
  onChange: (nextValue: ResourceRef[]) => void;
  options?: readonly ResourceRefSelectOption[];
  resourceLabel?: string;
  resourcePlaceholder?: string;
  searchPlaceholder?: string;
  value: readonly ResourceRef[];
  versionLabel?: string;
} & Omit<ComponentProps<"div">, "onChange">;

function compareResourceOptions(
  left: ResourceRefSelectOption,
  right: ResourceRefSelectOption,
): number {
  const keyComparison = left.key.localeCompare(right.key);

  if (keyComparison !== 0) {
    return keyComparison;
  }

  if (left.version === right.version) {
    return 0;
  }

  if (left.version == null) {
    return 1;
  }

  if (right.version == null) {
    return -1;
  }

  return right.version - left.version;
}

function getDefaultResourceRef(
  options: readonly ResourceRefSelectOption[],
  selectedRefs: readonly ResourceRef[],
): ResourceRef | null {
  const selectedValues = new Set(selectedRefs.map((ref) => formatResourceRef(ref)));
  const groupedDefaults = new Map<string, ResourceRef>();

  [...options].sort(compareResourceOptions).forEach((option) => {
    if (!groupedDefaults.has(option.key)) {
      groupedDefaults.set(option.key, { key: option.key, version: option.version });
    }
  });

  for (const option of groupedDefaults.values()) {
    if (!selectedValues.has(formatResourceRef(option))) {
      return option;
    }
  }

  return groupedDefaults.values().next().value ?? null;
}

function getDuplicateCountMap(value: readonly ResourceRef[]): Map<string, number> {
  return value.reduce((counts, ref) => {
    const formattedRef = formatResourceRef(ref);
    counts.set(formattedRef, (counts.get(formattedRef) ?? 0) + 1);
    return counts;
  }, new Map<string, number>());
}

export function ResourceMultiRefSelect({
  addLabel = "Add binding",
  className,
  description = "Manage multiple resource bindings with structured key and version selectors.",
  disabled = false,
  emptyDescription = "Add at least one binding to attach resources here.",
  emptyTitle = "No resource bindings configured",
  label = "Resource bindings",
  onChange,
  options = [],
  resourceLabel = "Resource",
  resourcePlaceholder = "Select resource",
  searchPlaceholder = "Search resources...",
  value,
  versionLabel = "Version",
  ...props
}: ResourceMultiRefSelectProps) {
  const duplicateCounts = useMemo(() => getDuplicateCountMap(value), [value]);
  const nextDefaultRef = useMemo(() => getDefaultResourceRef(options, value), [options, value]);

  const addBinding = () => {
    if (!nextDefaultRef) {
      return;
    }

    onChange([...value, nextDefaultRef]);
  };

  const updateBinding = (index: number, nextValue: ResourceRef | null) => {
    const nextBindings = [...value];

    if (nextValue) {
      nextBindings[index] = nextValue;
      onChange(nextBindings);
      return;
    }

    onChange(nextBindings.filter((_, currentIndex) => currentIndex !== index));
  };

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {value.length === 0 ? (
          <Alert>
            <AlertTitle>{emptyTitle}</AlertTitle>
            <AlertDescription>{emptyDescription}</AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed bg-muted/20 p-4">
          <Badge variant="outline">
            {value.length} binding{value.length === 1 ? "" : "s"}
          </Badge>
          <Badge variant="outline">
            {new Set(value.map((ref) => ref.key)).size} resource key
            {new Set(value.map((ref) => ref.key)).size === 1 ? "" : "s"}
          </Badge>
          <Button
            disabled={disabled || !nextDefaultRef}
            size="sm"
            type="button"
            variant="outline"
            onClick={addBinding}
          >
            <Plus data-icon="inline-start" />
            {addLabel}
          </Button>
        </div>

        {value.length > 0 ? (
          <div className="flex flex-col gap-4">
            {value.map((ref, index) => {
              const formattedRef = formatResourceRef(ref);
              const duplicateCount = duplicateCounts.get(formattedRef) ?? 0;

              return (
                <div className="flex flex-col gap-3" key={`${formattedRef}-${index}`}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">Binding {index + 1}</Badge>
                      <Badge variant="outline">{formattedRef}</Badge>
                      {duplicateCount > 1 ? (
                        <Badge variant="secondary">Duplicate selection</Badge>
                      ) : null}
                    </div>
                    <Button
                      disabled={disabled}
                      size="sm"
                      type="button"
                      variant="outline"
                      onClick={() => updateBinding(index, null)}
                    >
                      <Trash2 data-icon="inline-start" />
                      Remove
                    </Button>
                  </div>

                  <ResourceRefSelect
                    description=""
                    disabled={disabled}
                    label={`Binding ${index + 1}`}
                    options={options}
                    resourceLabel={resourceLabel}
                    resourcePlaceholder={resourcePlaceholder}
                    searchPlaceholder={searchPlaceholder}
                    value={ref}
                    versionLabel={versionLabel}
                    onChange={(nextValue) => updateBinding(index, nextValue)}
                  />
                </div>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
