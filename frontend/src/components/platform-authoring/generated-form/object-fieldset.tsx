import { type ComponentProps, type ReactNode } from "react";
import { AlertCircle, Plus, Trash2 } from "lucide-react";

import type { JsonPrimitive, SchemaIRNode, SchemaIRObject } from "@/lib/platform-authoring/schema/types";
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
import type {
  ValueEntry,
  ValueEntryObject,
  ValueEntryObjectField,
  ValueEntryPath,
} from "@/lib/platform-authoring/values/types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
      return createValueEntryForSchema(
        schema.variants[0] ?? { kind: "object", fields: [] },
        pathTokens,
      );
    case "object":
    default:
      return createObjectValueEntry(
        (schema.fields ?? [])
          .filter((field) => field.required !== false)
          .map((field) => {
            const fieldPath = extendPath(pathTokens, field.name);
            return createValueEntryObjectField(
              field.name,
              createValueEntryForSchema(field.schema, fieldPath),
              fieldPath,
            );
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

function normalizeObjectValue(schema: SchemaIRObject, value: ValueEntryObject): ValueEntryObject {
  const definedFields = schema.fields ?? [];
  const definedFieldNames = new Set(definedFields.map((field) => field.name));
  const existingFields = new Map(value.fields.map((field) => [field.key, field]));

  const nextFields = definedFields
    .filter((field) => field.required !== false || existingFields.has(field.name))
    .map((field) => {
      const fieldPath = extendPath(value.pathTokens, field.name);
      const existingField = existingFields.get(field.name);

      return createValueEntryObjectField(
        field.name,
        existingField
          ? rebaseValueEntryPaths(existingField.value, fieldPath)
          : createValueEntryForSchema(field.schema, fieldPath),
        fieldPath,
      );
    });

  const extraFields = value.fields
    .filter((field) => !definedFieldNames.has(field.key))
    .map((field) => {
      const fieldPath = extendPath(value.pathTokens, field.key);
      return createValueEntryObjectField(field.key, rebaseValueEntryPaths(field.value, fieldPath), fieldPath);
    });

  return createObjectValueEntry([...nextFields, ...extraFields], value.pathTokens);
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
        ? rebaseValueEntryPaths(field.value, fieldPath)
        : rebaseValueEntryPaths(field.value, fieldPath),
      fieldPath,
    );
  });

  return createObjectValueEntry(
    nextFields.filter((field) => definedFieldNames.has(field.key) || schema.allowAdditionalProperties),
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
  const extraFields = resolvedValue.fields.filter((field) => !definedFields.some((item) => item.name === field.key));

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
        {schema.allowAdditionalProperties ? (
          <Badge className="w-fit" variant="outline">
            Allows additional properties
          </Badge>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {definedFields.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
            {emptyState}
          </div>
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

        {extraFields.length > 0 ? (
          <Alert>
            <AlertCircle />
            <AlertTitle>Additional properties preserved</AlertTitle>
            <AlertDescription className="flex flex-wrap gap-2">
              {extraFields.map((field) => (
                <Badge key={field.key} variant="secondary">
                  {field.key}
                </Badge>
              ))}
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
