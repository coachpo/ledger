import { type ComponentProps, useId } from "react";

import {
  createBooleanValueEntry,
  createIntegerValueEntry,
  createNumberValueEntry,
  createStringValueEntry,
} from "@/lib/platform-authoring/values/factories";
import type {
  JsonPrimitive,
  SchemaIRBoolean,
  SchemaIREnum,
  SchemaIRInteger,
  SchemaIRLiteral,
  SchemaIRNode,
  SchemaIRNumber,
  SchemaIRString,
} from "@/lib/platform-authoring/schema/types";
import type { ValueEntryPath, ValueEntryScalar } from "@/lib/platform-authoring/values/types";
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

type ScalarSchema = Extract<
  SchemaIRNode,
  { kind: "string" | "integer" | "number" | "boolean" | "enum" | "literal" }
>;

type ScalarFieldValue = Extract<
  ValueEntryScalar,
  { kind: "boolean" | "integer" | "number" | "string" }
>;

type ScalarFieldProps = {
  description?: string;
  disabled?: boolean;
  label: string;
  onChange: (nextValue: ScalarFieldValue) => void;
  schema: ScalarSchema;
  value: ScalarFieldValue;
} & Omit<ComponentProps<"div">, "onChange">;

function createScalarValueEntry(value: JsonPrimitive, pathTokens: ValueEntryPath): ScalarFieldValue {
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

function getScalarPrimitiveValue(value: ScalarFieldValue): JsonPrimitive {
  return value.value;
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

function getScalarDescription(schema: ScalarSchema, description?: string): string {
  if (description) {
    return description;
  }

  if (schema.description) {
    return schema.description;
  }

  switch (schema.kind) {
    case "boolean":
      return "Toggle the boolean value.";
    case "enum":
      return "Select one of the supported schema values.";
    case "literal":
      return "Literal values are fixed by the schema and stay read-only.";
    case "integer":
      return "Enter a whole number that matches the schema.";
    case "number":
      return "Enter a numeric value that matches the schema.";
    case "string":
      return "Provide the text value that matches the schema.";
  }
}

function getEnumValue(schema: SchemaIREnum, value: ScalarFieldValue): string {
  const primitiveValue = getScalarPrimitiveValue(value);
  const resolvedValue = schema.values.some((option) => option === primitiveValue)
    ? primitiveValue
    : (schema.values[0] ?? "");

  return getPrimitiveOptionValue(resolvedValue);
}

export function ScalarField({
  className,
  description,
  disabled = false,
  label,
  onChange,
  schema,
  value,
  ...props
}: ScalarFieldProps) {
  const fieldId = useId();
  const fieldDescription = getScalarDescription(schema, description);

  if (schema.kind === "boolean") {
    return (
      <div className={cn("flex flex-col gap-3", className)} {...props}>
        <div className="flex items-center justify-between rounded-md border bg-background px-3 py-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor={fieldId}>{label}</Label>
            <p className="text-sm text-muted-foreground">{fieldDescription}</p>
          </div>
          <Switch
            checked={value.kind === "boolean" ? value.value : false}
            disabled={disabled}
            id={fieldId}
            onCheckedChange={(checked) => onChange(createBooleanValueEntry(checked, value.pathTokens))}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)} {...props}>
      <div className="flex flex-col gap-1">
        <Label htmlFor={fieldId}>{label}</Label>
        <p className="text-sm text-muted-foreground">{fieldDescription}</p>
      </div>

      {schema.kind === "string" ? (
        <Textarea
          disabled={disabled}
          id={fieldId}
          rows={3}
          value={value.kind === "string" ? value.value : ""}
          onChange={(event) => onChange(createStringValueEntry(event.target.value, value.pathTokens))}
        />
      ) : null}
      {schema.kind === "integer" ? (
        <Input
          disabled={disabled}
          id={fieldId}
          inputMode="numeric"
          type="number"
          value={value.kind === "integer" ? value.value : 0}
          onChange={(event) => onChange(createIntegerValueEntry(Number.parseInt(event.target.value || "0", 10), value.pathTokens))}
        />
      ) : null}
      {schema.kind === "number" ? (
        <Input
          disabled={disabled}
          id={fieldId}
          inputMode="decimal"
          type="number"
          value={value.kind === "number" || value.kind === "integer" ? value.value : 0}
          onChange={(event) => onChange(createNumberValueEntry(Number.parseFloat(event.target.value || "0"), value.pathTokens))}
        />
      ) : null}
      {schema.kind === "enum" ? (
        <Select
          disabled={disabled}
          value={getEnumValue(schema, value)}
          onValueChange={(nextValue) => onChange(createScalarValueEntry(parsePrimitiveOptionValue(nextValue), value.pathTokens))}
        >
          <SelectTrigger aria-label={`${label} enum value`} id={fieldId}>
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
        <Input disabled id={fieldId} readOnly value={String(schema.value)} />
      ) : null}
    </div>
  );
}

export type {
  ScalarFieldProps,
  ScalarFieldValue,
  ScalarSchema,
  SchemaIRBoolean,
  SchemaIREnum,
  SchemaIRInteger,
  SchemaIRLiteral,
  SchemaIRNumber,
  SchemaIRString,
};
