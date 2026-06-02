import { type ComponentProps, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { SchemaIRNode, SchemaIRObject } from "@/lib/platform-authoring/schema/types";
import { valueEntryPathToString } from "@/lib/platform-authoring/values/codec";
import {
  coerceValueEntryForSchema,
  createObjectValueEntry,
  createValueEntryForSchema,
  createValueEntryObjectField,
  rebaseValueEntryPaths,
} from "@/lib/platform-authoring/values/factories";
import type {
  ValueEntry,
  ValueEntryObject,
  ValueEntryObjectField,
  ValueEntryPath,
} from "@/lib/platform-authoring/values/types";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/components/ui/utils";

export type ObjectFieldsetRenderFieldArgs = {
  field: ValueEntryObjectField;
  label: string;
  onChange: (nextValue: ValueEntry) => void;
  required: boolean;
  schema: SchemaIRNode;
};

export type ObjectFieldsetProps = {
  description?: string;
  disabled?: boolean;
  emptyState?: string;
  label: string;
  onChange: (nextValue: ValueEntryObject) => void;
  renderField: (args: ObjectFieldsetRenderFieldArgs) => ReactNode;
  required?: boolean;
  schema: SchemaIRObject;
  value: ValueEntryObject;
} & Omit<ComponentProps<"div">, "children" | "onChange">;

function extendPath(pathTokens: ValueEntryPath, token: string): ValueEntryPath {
  return [...pathTokens, token];
}

function getFieldPathLabel(pathTokens: ValueEntryPath): string {
  return valueEntryPathToString(pathTokens) || "root";
}

function normalizeObjectValue(schema: SchemaIRObject, value: ValueEntryObject): ValueEntryObject {
  const coercedValue = coerceValueEntryForSchema(schema, value, value.pathTokens);
  return coercedValue.kind === "object" ? coercedValue : createObjectValueEntry([], value.pathTokens);
}

function updateObjectFields(
  schema: SchemaIRObject,
  value: ValueEntryObject,
  fields: ValueEntryObject["fields"],
): ValueEntryObject {
  const definedFieldNames = new Set((schema.fields ?? []).map((field) => field.name));

  const nextFields = fields.map((field) => {
    const fieldPath = extendPath(value.pathTokens, field.key);
    const schemaField = (schema.fields ?? []).find((item) => item.name === field.key);

    return createValueEntryObjectField(
      field.key,
      schemaField
        ? coerceValueEntryForSchema(schemaField.schema, field.value, fieldPath)
        : rebaseValueEntryPaths(field.value, fieldPath),
      fieldPath,
    );
  });

  return createObjectValueEntry(
    nextFields.filter((field) => definedFieldNames.has(field.key)),
    value.pathTokens,
  );
}

export function ObjectFieldset({
  className,
  description,
  disabled = false,
  emptyState = "This object schema does not define any editable fields yet.",
  label,
  onChange,
  renderField,
  required,
  schema,
  value,
  ...props
}: ObjectFieldsetProps) {
  const resolvedValue = normalizeObjectValue(schema, value);
  const definedFields = schema.fields ?? [];
  const renderedFieldNames = new Set(resolvedValue.fields.map((field) => field.key));

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{label}</CardTitle>
          <Badge variant="outline">object</Badge>
          <Badge variant="secondary">{required === false ? "optional" : "required"}</Badge>
          <Badge variant="outline">{getFieldPathLabel(resolvedValue.pathTokens)}</Badge>
        </div>
        <CardDescription>
          {description ?? schema.description ?? "Capture object fields without dropping the shared value-entry structure."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {definedFields.length === 0 ? (
          <InlineStatePanel description={emptyState} />
        ) : null}
        {definedFields.map((field) => {
          const existingField = resolvedValue.fields.find((item) => item.key === field.name);

          if (!existingField && field.required === false) {
            return (
              <div
                className="flex items-center justify-between rounded-md border border-dashed bg-muted/20 p-3"
                key={field.name}
              >
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{field.name}</span>
                    <Badge variant="outline">{field.schema.kind.replaceAll("_", " ")}</Badge>
                    <Badge variant="secondary">optional</Badge>
                    <Badge variant="outline">
                      {getFieldPathLabel(extendPath(resolvedValue.pathTokens, field.name))}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Optional field. Add it when you need to capture this value.
                  </p>
                </div>
                <Button
                  disabled={disabled}
                  size="sm"
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const fieldPath = extendPath(resolvedValue.pathTokens, field.name);
                    onChange(
                      updateObjectFields(schema, resolvedValue, [
                        ...resolvedValue.fields,
                        createValueEntryObjectField(
                          field.name,
                          createValueEntryForSchema(field.schema, fieldPath),
                          fieldPath,
                        ),
                      ]),
                    );
                  }}
                >
                  <Plus data-icon="inline-start" />
                  Add Field
                </Button>
              </div>
            );
          }

          if (!existingField) {
            return null;
          }

          return (
            <div className="flex flex-col gap-3" key={field.name}>
              <div className="flex justify-end">
                {field.required === false && renderedFieldNames.has(field.name) ? (
                  <Button
                    disabled={disabled}
                    size="sm"
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      onChange(
                        updateObjectFields(
                          schema,
                          resolvedValue,
                          resolvedValue.fields.filter((item) => item.key !== field.name),
                        ),
                      )
                    }
                  >
                    <Trash2 data-icon="inline-start" />
                    Remove Optional Field
                  </Button>
                ) : null}
              </div>
              {renderField({
                field: existingField,
                label: field.name,
                onChange: (nextValue) => {
                  onChange(
                    updateObjectFields(
                      schema,
                      resolvedValue,
                      resolvedValue.fields.map((item) =>
                        item.key === field.name
                          ? createValueEntryObjectField(item.key, nextValue, item.pathTokens)
                          : item,
                      ),
                    ),
                  );
                },
                required: field.required !== false,
                schema: field.schema,
              })}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
