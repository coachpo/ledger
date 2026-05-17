import type { UnknownRecord } from "@/lib/types/common";
import { parseJsonValue, stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { parseSchemaJsonObject, type SchemaCodecIssue } from "./codec";
import type { JsonValue, SchemaIRDiscriminatedUnion, SchemaIRField, SchemaIRNode, SchemaIRObject } from "./types";

export type LaunchParametersTemplate = {
  issues: SchemaCodecIssue[];
  parameters: UnknownRecord;
  reason: string | null;
  schemaSupported: boolean;
  text: string;
};

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOwnKey(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function hasSchemaDefault(schema: SchemaIRNode): boolean {
  return hasOwnKey(schema, "defaultValue");
}

function cloneJsonValue(value: JsonValue): JsonValue {
  return JSON.parse(JSON.stringify(value)) as JsonValue;
}
function sortedFields(fields: readonly SchemaIRField[] = []): SchemaIRField[] {
  return [...fields].sort((left, right) => left.name.localeCompare(right.name));
}

function defaultedUnionVariant(schema: SchemaIRDiscriminatedUnion, value: JsonValue): SchemaIRNode {
  if (isUnknownRecord(value)) {
    const selected = schema.variants.find((variant) => {
      if (variant.kind !== "object") {
        return false;
      }
      const discriminator = (variant.fields ?? []).find((field) => field.name === schema.discriminator);
      return discriminator?.schema.kind === "literal" && value[schema.discriminator] === discriminator.schema.value;
    });

    if (selected) {
      return selected;
    }
  }

  return schema.variants[0] ?? { fields: [], kind: "object" };
}

function templateObjectFromFields(fields: readonly SchemaIRField[], defaultValue?: UnknownRecord): UnknownRecord {
  return Object.fromEntries(
    sortedFields(fields)
      .filter((field) => field.required !== false || hasSchemaDefault(field.schema) || Boolean(defaultValue && hasOwnKey(defaultValue, field.name)))
      .map((field) => {
        if (defaultValue && hasOwnKey(defaultValue, field.name)) {
          return [field.name, templateValueFromDefault(field.schema, defaultValue[field.name] as JsonValue)];
        }
        return [field.name, templateValueFromSchema(field.schema)];
      }),
  );
}

function templateValueFromDefault(schema: SchemaIRNode, value: JsonValue): unknown {
  if (schema.kind === "object" && isUnknownRecord(value)) {
    return templateObjectFromFields(schema.fields ?? [], value);
  }

  if (schema.kind === "array" && Array.isArray(value)) {
    return value.map((item) => templateValueFromDefault(schema.items, item));
  }

  if (schema.kind === "discriminated_union") {
    return templateValueFromDefault(defaultedUnionVariant(schema, value), value);
  }

  if (schema.kind === "literal") {
    return schema.value;
  }

  return cloneJsonValue(value);
}

function templateValueFromSchema(schema: SchemaIRNode): unknown {
  if (hasSchemaDefault(schema)) {
    return templateValueFromDefault(schema, schema.defaultValue as JsonValue);
  }

  switch (schema.kind) {
    case "boolean":
      return false;
    case "integer":
    case "number":
      return 0;
    case "enum":
      return schema.values[0] ?? "";
    case "literal":
      return schema.value;
    case "array":
      return [];
    case "object":
      return templateObjectFromFields(schema.fields ?? []);
    case "discriminated_union":
      return templateValueFromSchema(schema.variants[0] ?? { fields: [], kind: "object" });
    case "ref":
    case "string":
    default:
      return "";
  }
}

function templateFromObjectSchema(schema: SchemaIRObject): UnknownRecord {
  const value = templateValueFromSchema(schema);
  return isUnknownRecord(value) ? value : {};
}

export function createLaunchParametersTemplate(inputSchema: unknown): LaunchParametersTemplate {
  const parsed = parseSchemaJsonObject(inputSchema);
  if (!parsed.builder) {
    const parameters = {};
    return {
      issues: parsed.issues,
      parameters,
      reason: "The workflow input schema could not be converted into the supported package schema template, so the raw JSON editor starts from an empty object.",
      schemaSupported: false,
      text: stringifyJson(parameters),
    };
  }

  if (parsed.builder.kind !== "object") {
    const parameters = {};
    return {
      issues: [],
      parameters,
      reason: "Workflow launch parameters must use an object input schema, so the raw JSON editor starts from an empty object.",
      schemaSupported: false,
      text: stringifyJson(parameters),
    };
  }

  const parameters = templateFromObjectSchema(parsed.builder);
  return {
    issues: [],
    parameters,
    reason: null,
    schemaSupported: true,
    text: stringifyJson(parameters),
  };
}

export function resetLaunchParametersTemplate(template: LaunchParametersTemplate): string {
  return template.text;
}

export function parseLaunchParametersJson(parametersText: string): UnknownRecord {
  const parsed = parseJsonValue<unknown>("Runtime inputs JSON", parametersText, {});
  if (!isUnknownRecord(parsed)) {
    throw new Error("Runtime inputs JSON must be a valid object.");
  }
  return parsed;
}
