import { type ComponentProps, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { JsonPrimitive, SchemaIRArray, SchemaIRNode } from "@/lib/platform-authoring/schema/types";
import { valueEntryPathToString } from "@/lib/platform-authoring/values/codec";
import {
  createArrayValueEntry,
  createBooleanValueEntry,
  createIntegerValueEntry,
  createNullValueEntry,
  createNumberValueEntry,
  createObjectValueEntry,
  createStringValueEntry,
  createValueEntryArrayItem,
  createValueEntryObjectField,
} from "@/lib/platform-authoring/values/factories";
import type { ValueEntry, ValueEntryArray, ValueEntryPath } from "@/lib/platform-authoring/values/types";
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
import { cn } from "@/components/ui/utils";

export type ArrayFieldListRenderItemArgs = {
  index: number;
  item: ValueEntry;
  label: string;
  onChange: (nextValue: ValueEntry) => void;
};

export type ArrayFieldListProps = {
  addLabel?: string;
  description?: string;
  disabled?: boolean;
  emptyState?: string;
  itemLabelPrefix?: string;
  label: string;
  onChange: (nextValue: ValueEntryArray) => void;
  renderItem: (args: ArrayFieldListRenderItemArgs) => ReactNode;
  required?: boolean;
  schema: SchemaIRArray;
  value: ValueEntryArray;
} & Omit<ComponentProps<"div">, "children" | "onChange">;

function extendPath(pathTokens: ValueEntryPath, token: string): ValueEntryPath {
  return [...pathTokens, token];
}

function getFieldPathLabel(pathTokens: ValueEntryPath): string {
  return valueEntryPathToString(pathTokens) || "root";
}

function createPrimitiveValueEntry(value: JsonPrimitive | null, pathTokens: ValueEntryPath): ValueEntry {
  if (value === null) {
    return createNullValueEntry(pathTokens);
  }

  switch (typeof value) {
    case "boolean":
      return createBooleanValueEntry(value, pathTokens);
    case "number":
      return Number.isInteger(value)
        ? createIntegerValueEntry(value, pathTokens)
        : createNumberValueEntry(value, pathTokens);
    case "string":
      return createStringValueEntry(value, pathTokens);
  }
}

function createValueEntryForSchema(schema: SchemaIRNode, pathTokens: ValueEntryPath = []): ValueEntry {
  switch (schema.kind) {
    case "string":
      return createStringValueEntry("", pathTokens);
    case "integer":
      return createIntegerValueEntry(0, pathTokens);
    case "number":
      return createNumberValueEntry(0, pathTokens);
    case "boolean":
      return createBooleanValueEntry(false, pathTokens);
    case "enum":
      return createPrimitiveValueEntry(schema.values[0] ?? "", pathTokens);
    case "literal":
      return createPrimitiveValueEntry(schema.value, pathTokens);
    case "array":
      return createArrayValueEntry([], pathTokens);
    case "ref":
      return createStringValueEntry("", pathTokens);
    case "discriminated_union":
      return createValueEntryForSchema(schema.variants[0] ?? { kind: "object", fields: [] }, pathTokens);
    case "object":
    default:
      return createObjectValueEntry(
        (schema.fields ?? [])
          .filter((field) => field.required !== false)
          .map((field) => {
            const fieldPath = extendPath(pathTokens, field.name);
            return createValueEntryObjectField(field.name, createValueEntryForSchema(field.schema, fieldPath), fieldPath);
          }),
        pathTokens,
      );
  }
}

function rebaseValueEntryPaths(value: ValueEntry, pathTokens: ValueEntryPath): ValueEntry {
  switch (value.kind) {
    case "null":
    case "boolean":
    case "integer":
    case "number":
    case "string":
      return createPrimitiveValueEntry(value.value, pathTokens);
    case "array":
      return createArrayValueEntry(
        value.items.map((item, index) => {
          const itemPath = extendPath(pathTokens, String(index));
          return createValueEntryArrayItem(index, rebaseValueEntryPaths(item.value, itemPath), itemPath);
        }),
        pathTokens,
      );
    case "object":
      return createObjectValueEntry(
        value.fields.map((field) => {
          const fieldPath = extendPath(pathTokens, field.key);
          return createValueEntryObjectField(field.key, rebaseValueEntryPaths(field.value, fieldPath), fieldPath);
        }),
        pathTokens,
      );
  }
}

function updateArrayItems(value: ValueEntryArray, items: ValueEntry[]): ValueEntryArray {
  return createArrayValueEntry(
    items.map((item, index) => {
      const itemPath = extendPath(value.pathTokens, String(index));
      return createValueEntryArrayItem(index, rebaseValueEntryPaths(item, itemPath), itemPath);
    }),
    value.pathTokens,
  );
}

export function ArrayFieldList({
  addLabel = "Add Item",
  className,
  description,
  disabled = false,
  emptyState = "No items yet. Add one to start capturing repeated values.",
  itemLabelPrefix = "Item",
  label,
  onChange,
  renderItem,
  required,
  schema,
  value,
  ...props
}: ArrayFieldListProps) {
  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{label}</CardTitle>
          <Badge variant="outline">array</Badge>
          <Badge variant="secondary">{required === false ? "optional" : "required"}</Badge>
          <Badge variant="outline">{getFieldPathLabel(value.pathTokens)}</Badge>
        </div>
        <CardDescription>
          {description ?? schema.description ?? "Add, remove, and review repeated values while keeping indexed path tokens aligned."}
        </CardDescription>
        <CardAction>
          <Button
            disabled={disabled}
            size="sm"
            type="button"
            variant="outline"
            onClick={() => {
              const nextItem = createValueEntryForSchema(schema.items, extendPath(value.pathTokens, String(value.items.length)));
              onChange(updateArrayItems(value, [...value.items.map((item) => item.value), nextItem]));
            }}
          >
            <Plus data-icon="inline-start" />
            {addLabel}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {value.items.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
            {emptyState}
          </div>
        ) : null}
        {value.items.map((item, index) => {
          const itemLabel = `${itemLabelPrefix} ${index + 1}`;

          return (
            <div className="flex flex-col gap-3 rounded-lg border border-dashed p-4" key={`${label}-${index}-${item.pathTokens.join(".")}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{itemLabel}</span>
                    <Badge variant="outline">{getFieldPathLabel(item.pathTokens)}</Badge>
                  </div>
                </div>
                <Button
                  disabled={disabled}
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => onChange(updateArrayItems(value, value.items.filter((_, itemIndex) => itemIndex !== index).map((entry) => entry.value)))}
                >
                  <Trash2 data-icon="inline-start" />
                  Remove Item
                </Button>
              </div>
              {renderItem({
                index,
                item: item.value,
                label: itemLabel,
                onChange: (nextValue) => {
                  onChange(
                    updateArrayItems(
                      value,
                      value.items.map((entry, itemIndex) => (itemIndex === index ? nextValue : entry.value)),
                    ),
                  );
                },
              })}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}