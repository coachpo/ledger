import { type ComponentProps, useMemo } from "react";
import { AlertCircle, Plus, Trash2 } from "lucide-react";

import type {
  JsonPrimitive,
  SchemaIRDiscriminatedUnion,
  SchemaIRNode,
  SchemaIRObject,
} from "@/lib/platform-authoring/schema/types";
import { valueEntryPathToString } from "@/lib/platform-authoring/values/codec";
import {
  coerceValueEntryForSchema,
  createArrayValueEntry,
  createBooleanValueEntry,
  createIntegerValueEntry,
  createNumberValueEntry,
  createObjectValueEntry,
  createPrimitiveValueEntry,
  createStringValueEntry,
  createValueEntryArrayItem,
  createValueEntryForSchema,
  createValueEntryObjectField,
  getPrimitiveValue,
  rebaseValueEntryPaths,
} from "@/lib/platform-authoring/values/factories";
import { validateValueEntryNode, type ValueEntryValidationIssue } from "@/lib/platform-authoring/values/validation";
import type {
  ValueEntry,
  ValueEntryArray,
  ValueEntryObject,
  ValueEntryPath,
} from "@/lib/platform-authoring/values/types";
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
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";

const NONE_OPTION = "__none__";

export type SchemaValueEntryFormProps = {
  disabled?: boolean;
  label?: string;
  onChange: (nextValue: ValueEntry) => void;
  schema: SchemaIRNode;
  value?: ValueEntry | null;
} & Omit<ComponentProps<"div">, "onChange">;

type SchemaFormProps = SchemaValueEntryFormProps & {
  description?: string;
};

type SchemaNodeEditorProps = {
  depth: number;
  disabled: boolean;
  label: string;
  onChange: (nextValue: ValueEntry) => void;
  required?: boolean;
  schema: SchemaIRNode;
  value: ValueEntry;
};

type DiscriminatedUnionOption = {
  discriminatorValue: JsonPrimitive | null;
  index: number;
  label: string;
  schema: SchemaIRNode;
};

function extendPath(pathTokens: ValueEntryPath, token: string): ValueEntryPath {
  return [...pathTokens, token];
}

function getDiscriminatedUnionOptions(schema: SchemaIRDiscriminatedUnion): DiscriminatedUnionOption[] {
  return schema.variants.map((variant, index) => {
    if (variant.kind === "object") {
      const discriminatorField = (variant.fields ?? []).find((field) => field.name === schema.discriminator);
      if (discriminatorField?.schema.kind === "literal") {
        return {
          discriminatorValue: discriminatorField.schema.value,
          index,
          label: getSchemaDisplayLabel(variant, String(discriminatorField.schema.value)),
          schema: variant,
        } satisfies DiscriminatedUnionOption;
      }
    }

    return {
      discriminatorValue: null,
      index,
      label: getSchemaDisplayLabel(variant, `Variant ${index + 1}`),
      schema: variant,
    } satisfies DiscriminatedUnionOption;
  });
}

function getSelectedDiscriminatedUnionIndex(schema: SchemaIRDiscriminatedUnion, value: ValueEntry | null | undefined): number {
  if (!value || value.kind !== "object") {
    return 0;
  }

  const discriminatorField = value.fields.find((field) => field.key === schema.discriminator);
  const discriminatorValue = discriminatorField ? getPrimitiveValue(discriminatorField.value) : undefined;
  if (discriminatorValue == null) {
    return 0;
  }

  return getDiscriminatedUnionOptions(schema).find((option) => option.discriminatorValue === discriminatorValue)?.index ?? 0;
}

function getFieldPathLabel(pathTokens: ValueEntryPath): string {
  return valueEntryPathToString(pathTokens) || "root";
}

function getSchemaDisplayLabel(schema: SchemaIRNode, fallbackLabel: string): string {
  return schema.title ?? fallbackLabel;
}

function getPrimitiveOptionValue(value: JsonPrimitive): string {
  return `${typeof value}:${JSON.stringify(value)}`;
}

function parsePrimitiveOptionValue(value: string): JsonPrimitive {
  const separatorIndex = value.indexOf(":");
  const type = value.slice(0, separatorIndex);
  const payload = value.slice(separatorIndex + 1);
  const parsed = JSON.parse(payload) as JsonPrimitive;

  if (type === "number" || type === "boolean" || type === "string") {
    return parsed;
  }

  return String(parsed);
}

function updateArrayItems(schema: SchemaIRNode, value: ValueEntryArray, items: ValueEntry[]): ValueEntryArray {
  return createArrayValueEntry(
    items.map((item, index) => {
      const itemPath = extendPath(value.pathTokens, String(index));
      return createValueEntryArrayItem(index, coerceValueEntryForSchema(schema, item, itemPath), itemPath);
    }),
    value.pathTokens,
  );
}

function updateObjectFields(schema: SchemaIRObject, value: ValueEntryObject, fields: ValueEntryObject["fields"]): ValueEntryObject {
  const knownFieldNames = new Set((schema.fields ?? []).map((field) => field.name));
  const nextFields = fields.map((field) => {
    const fieldPath = extendPath(value.pathTokens, field.key);
    const schemaField = (schema.fields ?? []).find((item) => item.name === field.key);

    return createValueEntryObjectField(
      field.key,
      schemaField ? coerceValueEntryForSchema(schemaField.schema, field.value, fieldPath) : rebaseValueEntryPaths(field.value, fieldPath),
      fieldPath,
    );
  });

  return createObjectValueEntry(
    nextFields.filter((field) => knownFieldNames.has(field.key)),
    value.pathTokens,
  );
}

function SchemaEditorHeader({
  label,
  pathTokens,
  required,
  schema,
}: {
  label: string;
  pathTokens: ValueEntryPath;
  required?: boolean;
  schema: SchemaIRNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium text-foreground">{label}</span>

      <Badge variant="outline" className="capitalize">
        {schema.kind.replaceAll("_", " ")}
      </Badge>
      <Badge variant="secondary">{required === false ? "optional" : "required"}</Badge>
      <Badge variant="outline">{getFieldPathLabel(pathTokens)}</Badge>
    </div>
  );
}

function ValidationIssuesAlert({ issues }: { issues: readonly ValueEntryValidationIssue[] }) {
  if (issues.length === 0) {
    return null;
  }

  return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>Value entry needs cleanup</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-4">
          {issues.slice(0, 5).map((issue) => (
            <li key={`${issue.field}-${issue.issue}`}>
              <span className="font-medium">{issue.field}</span>: {issue.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function SchemaNodeEditor({ depth, disabled, label, onChange, required, schema, value }: SchemaNodeEditorProps) {
  const displayLabel = getSchemaDisplayLabel(schema, label);

  if (schema.kind === "object") {
    const objectValue = value.kind === "object" ? value : createObjectValueEntry([], value.pathTokens);
    const definedFields = schema.fields ?? [];
    const renderedFieldNames = new Set(objectValue.fields.map((field) => field.key));

    return (
      <Card className={cn(depth > 0 && "border-dashed")}>
        <CardHeader>
          <SchemaEditorHeader label={displayLabel} pathTokens={objectValue.pathTokens} required={required} schema={schema} />
          <CardDescription>
            {schema.description ?? "Capture object fields without dropping the shared value-entry structure."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {definedFields.length === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
              This object schema does not define any editable fields yet.
            </div>
          ) : null}
          {definedFields.map((field) => {
            const fieldLabel = getSchemaDisplayLabel(field.schema, field.name);
            const existingField = objectValue.fields.find((item) => item.key === field.name);
            if (!existingField && field.required === false) {
              return (
                <div className="flex items-center justify-between rounded-md border border-dashed bg-muted/20 p-3" key={field.name}>
                  <div className="flex flex-col gap-1">
                    <SchemaEditorHeader label={fieldLabel} pathTokens={extendPath(objectValue.pathTokens, field.name)} required={false} schema={field.schema} />
                    <p className="text-sm text-muted-foreground">
                      {field.schema.description ?? "Optional field. Add it when you need to capture this value."}
                    </p>
                  </div>
                  <Button
                    disabled={disabled}
                    size="sm"
                    type="button"
                    variant="outline"
                    onClick={() => {
                      const fieldPath = extendPath(objectValue.pathTokens, field.name);
                      onChange(
                        updateObjectFields(schema, objectValue, [
                          ...objectValue.fields,
                          createValueEntryObjectField(field.name, createValueEntryForSchema(field.schema, fieldPath), fieldPath),
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

            const nextField = existingField ?? createValueEntryObjectField(field.name, createValueEntryForSchema(field.schema, extendPath(objectValue.pathTokens, field.name)), extendPath(objectValue.pathTokens, field.name));
            return (
              <div className="flex flex-col gap-3" key={field.name}>
                <div className="flex justify-end">
                  {field.required === false && renderedFieldNames.has(field.name) ? (
                    <Button
                      disabled={disabled}
                      size="sm"
                      type="button"
                      variant="ghost"
                      onClick={() => onChange(updateObjectFields(schema, objectValue, objectValue.fields.filter((item) => item.key !== field.name)))}
                    >
                      <Trash2 data-icon="inline-start" />
                      Remove Optional Field
                    </Button>
                  ) : null}
                </div>
                <SchemaNodeEditor
                  depth={depth + 1}
                  disabled={disabled}
                  label={fieldLabel}
                  onChange={(nextValue) => onChange(updateObjectFields(schema, objectValue, objectValue.fields.map((item) => item.key === field.name ? createValueEntryObjectField(item.key, nextValue, item.pathTokens) : item)))}
                  required={field.required !== false}
                  schema={field.schema}
                  value={nextField.value}
                />
              </div>
            );
          })}
        </CardContent>
      </Card>
    );
  }

  if (schema.kind === "array") {
    const arrayValue = value.kind === "array" ? value : createArrayValueEntry([], value.pathTokens);

    return (
      <Card className={cn(depth > 0 && "border-dashed")}>
        <CardHeader>
          <SchemaEditorHeader label={displayLabel} pathTokens={arrayValue.pathTokens} required={required} schema={schema} />
          <CardDescription>
            {schema.description ?? "Add, remove, and reorder repeated values while keeping indexed path tokens aligned."}
          </CardDescription>
          <CardAction>
            <Button
              disabled={disabled}
              size="sm"
              type="button"
              variant="outline"
              onClick={() => onChange(updateArrayItems(schema.items, arrayValue, [...arrayValue.items.map((item) => item.value), createValueEntryForSchema(schema.items, extendPath(arrayValue.pathTokens, String(arrayValue.items.length)))]))}
            >
              <Plus data-icon="inline-start" />
              Add Item
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {arrayValue.items.length === 0 ? (
            <div className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
              No items yet. Add one to start capturing repeated values.
            </div>
          ) : null}
          {arrayValue.items.map((item, index) => (
            <div className="flex flex-col gap-3 rounded-lg border border-dashed p-4" key={`${label}-${index}`}>
              <div className="flex justify-end">
                <Button
                  disabled={disabled}
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => onChange(updateArrayItems(schema.items, arrayValue, arrayValue.items.filter((_, itemIndex) => itemIndex !== index).map((entry) => entry.value)))}
                >
                  <Trash2 data-icon="inline-start" />
                  Remove Item
                </Button>
              </div>
              <SchemaNodeEditor
                depth={depth + 1}
                disabled={disabled}
                label={`Item ${index + 1}`}
                onChange={(nextValue) => onChange(updateArrayItems(schema.items, arrayValue, arrayValue.items.map((entry, itemIndex) => itemIndex === index ? nextValue : entry.value)))}
                schema={schema.items}
                value={item.value}
              />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (schema.kind === "discriminated_union") {
    const options = getDiscriminatedUnionOptions(schema);
    const selectedIndex = getSelectedDiscriminatedUnionIndex(schema, value);
    const selectedOption = options[selectedIndex] ?? options[0];

    return (
      <Card className={cn(depth > 0 && "border-dashed")}>
        <CardHeader>
          <SchemaEditorHeader label={displayLabel} pathTokens={value.pathTokens} required={required} schema={schema} />
          <CardDescription>
            {schema.description ?? `Pick a ${schema.discriminator} variant before filling the matching object shape.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label>Variant</Label>
            <Select
              disabled={disabled}
              value={selectedOption ? String(selectedOption.index) : NONE_OPTION}
              onValueChange={(nextValue) => {
                const nextOption = options.find((option) => String(option.index) === nextValue);
                if (nextOption) {
                  onChange(createValueEntryForSchema(nextOption.schema, value.pathTokens));
                }
              }}
            >
              <SelectTrigger aria-label={`${displayLabel} variant`}>
                <SelectValue placeholder="Select variant" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {options.map((option) => (
                    <SelectItem key={`${label}-${option.index}`} value={String(option.index)}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          {selectedOption ? (
            <SchemaNodeEditor
              depth={depth + 1}
              disabled={disabled}
              label={selectedOption.label}
              onChange={onChange}
              schema={selectedOption.schema}
              value={coerceValueEntryForSchema(selectedOption.schema, value, value.pathTokens)}
            />
          ) : null}
        </CardContent>
      </Card>
    );
  }

  if (schema.kind === "ref") {
    return (
      <Alert>
        <AlertCircle />
        <AlertTitle>{displayLabel}</AlertTitle>
        <AlertDescription className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">ref</Badge>
            <Badge variant="secondary">registry://{schema.schemaKey}{schema.schemaVersion ? `@${schema.schemaVersion}` : ""}</Badge>
            <Badge variant="outline">{getFieldPathLabel(value.pathTokens)}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {schema.description ?? "Referenced schemas are preserved in the shared value model, but this first generated-form surface cannot expand registry refs yet."}
          </p>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border/70 bg-muted/20 p-4">
      <SchemaEditorHeader label={displayLabel} pathTokens={value.pathTokens} required={required} schema={schema} />
      <p className="text-sm text-muted-foreground">{schema.description ?? "Provide a value that matches the selected schema branch."}</p>
      {schema.kind === "string" ? (
        <Textarea aria-label={displayLabel} disabled={disabled} rows={3} value={value.kind === "string" ? value.value : ""} onChange={(event) => onChange(createStringValueEntry(event.target.value, value.pathTokens))} />
      ) : null}
      {schema.kind === "integer" ? (
        <Input aria-label={displayLabel} disabled={disabled} inputMode="numeric" type="number" value={value.kind === "integer" ? value.value : 0} onChange={(event) => onChange(createIntegerValueEntry(Number.parseInt(event.target.value || "0", 10), value.pathTokens))} />
      ) : null}
      {schema.kind === "number" ? (
        <Input aria-label={displayLabel} disabled={disabled} inputMode="decimal" type="number" value={value.kind === "number" ? value.value : 0} onChange={(event) => onChange(createNumberValueEntry(Number.parseFloat(event.target.value || "0"), value.pathTokens))} />
      ) : null}
      {schema.kind === "boolean" ? (
        <div className="flex items-center justify-between rounded-md border bg-background px-3 py-2">
          <span className="text-sm text-foreground">Toggle the boolean value.</span>
          <Switch aria-label={displayLabel} checked={value.kind === "boolean" ? value.value : false} disabled={disabled} onCheckedChange={(checked) => onChange(createBooleanValueEntry(checked, value.pathTokens))} />
        </div>
      ) : null}
      {schema.kind === "enum" ? (
        <Select disabled={disabled} value={getPrimitiveOptionValue((getPrimitiveValue(value) as JsonPrimitive | undefined) ?? schema.values[0] ?? "")} onValueChange={(nextValue) => onChange(createPrimitiveValueEntry(parsePrimitiveOptionValue(nextValue), value.pathTokens))}>
          <SelectTrigger aria-label={`${displayLabel} enum value`}>
            <SelectValue placeholder="Select value" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {schema.values.map((option) => (
                <SelectItem key={getPrimitiveOptionValue(option)} value={getPrimitiveOptionValue(option)}>
                  {String(option)}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      ) : null}
      {schema.kind === "literal" ? (
        <Input aria-label={displayLabel} disabled readOnly value={String(schema.value)} />
      ) : null}
    </div>
  );
}

export function SchemaValueEntryForm({
  className,
  disabled = false,
  label = "Schema form",
  onChange,
  schema,
  value,
  ...props
}: SchemaValueEntryFormProps) {
  const resolvedValue = useMemo(() => coerceValueEntryForSchema(schema, value), [schema, value]);
  const validationIssues = useMemo(() => validateValueEntryNode(resolvedValue), [resolvedValue]);

  return (
    <div className={cn("flex flex-col gap-4", className)} {...props}>
      <ValidationIssuesAlert issues={validationIssues} />
      <SchemaNodeEditor depth={0} disabled={disabled} label={schema.title ?? label} onChange={onChange} schema={schema} value={resolvedValue} />
    </div>
  );
}

export function SchemaForm({
  className,
  description,
  disabled = false,
  label = "Schema form",
  onChange,
  schema,
  value,
  ...props
}: SchemaFormProps) {
  return (
    <div className={cn("flex flex-col gap-4", className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle>{label}</CardTitle>
          <CardDescription>
            {description ?? schema.description ?? "Enter structured values directly from the shared schema and value-entry foundations."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <SchemaValueEntryForm disabled={disabled} label={label} onChange={onChange} schema={schema} value={value} />
        </CardContent>
      </Card>
    </div>
  );
}
