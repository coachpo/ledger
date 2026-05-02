import { type ComponentProps, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { SchemaIRArray } from "@/lib/platform-authoring/schema/types";
import { valueEntryPathToString } from "@/lib/platform-authoring/values/codec";
import {
  coerceValueEntryForSchema,
  createArrayValueEntry,
  createValueEntryArrayItem,
  createValueEntryForSchema,
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

function updateArrayItems(schema: SchemaIRArray, value: ValueEntryArray, items: ValueEntry[]): ValueEntryArray {
  return createArrayValueEntry(
    items.map((item, index) => {
      const itemPath = extendPath(value.pathTokens, String(index));
      return createValueEntryArrayItem(index, coerceValueEntryForSchema(schema.items, item, itemPath), itemPath);
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
              onChange(updateArrayItems(schema, value, [...value.items.map((item) => item.value), nextItem]));
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
                  onClick={() => onChange(updateArrayItems(schema, value, value.items.filter((_, itemIndex) => itemIndex !== index).map((entry) => entry.value)))}
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
                      schema,
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