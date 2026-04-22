import type { UnknownRecord } from "@/lib/types/common";
import type { JsonPrimitive, SchemaIRNode, SchemaIRRef } from "./types";
import { createDefaultSchemaNode } from "./factories";
import {
  createSchemaValidationIssue,
  getUnsupportedSchemaKeywordMessage,
  joinSchemaPath,
  type SchemaValidationIssue,
} from "./validation";

export type SchemaCodecIssue = SchemaValidationIssue;

export type SchemaCodecParseSuccess = {
  builder: ReturnType<typeof jsonSchemaToSchemaBuilder>;
  jsonSchema: UnknownRecord;
  issues: [];
};

export type SchemaCodecParseFailure = {
  builder: null;
  jsonSchema: null;
  issues: SchemaCodecIssue[];
};

export type SchemaCodecParseResult = SchemaCodecParseSuccess | SchemaCodecParseFailure;

type PrimitiveKind = "boolean" | "integer" | "number" | "string";

type SchemaNodeContext = {
  issues: SchemaCodecIssue[];
  path: string;
};

const PRIMITIVE_TYPES = new Set(["string", "integer", "number", "boolean"]);
const REGISTRY_REF_RE = /^registry:\/\/(?<key>[a-z][a-z0-9_]{0,119})(?:@(?<version>[1-9][0-9]*))?$/;

function addIssue(issues: SchemaCodecIssue[], field: string, issue: string) {
  issues.push(createSchemaValidationIssue(field, issue));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function toOptionalText(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function primitiveKindForValue(value: JsonPrimitive): PrimitiveKind {
  if (typeof value === "boolean") {
    return "boolean";
  }

  if (typeof value === "string") {
    return "string";
  }

  return Number.isInteger(value) ? "integer" : "number";
}

function primitiveValueToInput(value: JsonPrimitive): string {
  return typeof value === "string" ? value : String(value);
}

export function parsePrimitiveInput(value: string, kind: PrimitiveKind): JsonPrimitive {
  if (kind === "boolean") {
    return value.trim().toLowerCase() === "true";
  }

  if (kind === "integer") {
    return Number.parseInt(value.trim() || "0", 10);
  }

  if (kind === "number") {
    return Number.parseFloat(value.trim() || "0");
  }

  return value;
}

function parseLinePrimitive(value: string): JsonPrimitive {
  const trimmed = value.trim();

  if (trimmed === "true") {
    return true;
  }

  if (trimmed === "false") {
    return false;
  }

  if (/^-?\d+$/.test(trimmed)) {
    return Number.parseInt(trimmed, 10);
  }

  if (/^-?(?:\d+\.\d+|\d+\.\d*|\d*\.\d+)$/.test(trimmed)) {
    return Number.parseFloat(trimmed);
  }

  return trimmed;
}

export function formatPrimitiveList(values: JsonPrimitive[]) {
  return values.map(primitiveValueToInput).join("\n");
}

export function parsePrimitiveList(value: string): JsonPrimitive[] {
  return value
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map(parseLinePrimitive);
}

function withMetadata<T extends SchemaIRNode>(
  node: T,
  title?: string,
  description?: string,
): T {
  return {
    ...node,
    description: toOptionalText(description) ?? null,
    title: toOptionalText(title) ?? null,
  };
}

function withJsonMetadata(payload: UnknownRecord, node: { description?: string | null; title?: string | null }) {
  const nextPayload = { ...payload };

  if (toOptionalText(node.title ?? undefined)) {
    nextPayload.title = node.title;
  }

  if (toOptionalText(node.description ?? undefined)) {
    nextPayload.description = node.description;
  }

  return nextPayload;
}

export function schemaBuilderToJsonSchema(node: SchemaIRNode): UnknownRecord {
  switch (node.kind) {
    case "string":
    case "integer":
    case "number":
    case "boolean": {
      return withJsonMetadata({ type: node.kind }, node);
    }
    case "enum": {
      const firstValue = node.values[0] ?? "value";
      return withJsonMetadata({ enum: node.values, type: primitiveKindForValue(firstValue) }, node);
    }
    case "literal": {
      return withJsonMetadata({ const: node.value, type: primitiveKindForValue(node.value) }, node);
    }
    case "array":
      return withJsonMetadata({ items: schemaBuilderToJsonSchema(node.items), type: "array" }, node);
    case "ref":
      return withJsonMetadata(
        { $ref: `registry://${node.schemaKey}${node.schemaVersion ? `@${node.schemaVersion}` : ""}` },
        node,
      );
    case "discriminated_union":
      return withJsonMetadata(
        {
          anyOf: node.variants.map((variant) => schemaBuilderToJsonSchema(variant)),
          discriminator: { propertyName: node.discriminator },
        },
        node,
      );
    case "object":
    default: {
      const fields = node.fields ?? [];
      return withJsonMetadata(
        {
          additionalProperties: Boolean(node.allowAdditionalProperties),
          properties: Object.fromEntries(fields.map((field) => [field.name, schemaBuilderToJsonSchema(field.schema)])),
          required: fields.filter((field) => field.required !== false).map((field) => field.name),
          type: "object",
        },
        node,
      );
    }
  }
}

export function parseSchemaJsonText(value: string): SchemaCodecParseResult {
  const trimmed = value.trim();
  if (!trimmed) {
    return {
      builder: null,
      jsonSchema: null,
      issues: [createSchemaValidationIssue("jsonSchema", "A schema definition is required")],
    };
  }

  try {
    const jsonSchema = JSON.parse(trimmed) as unknown;
    const issues: SchemaCodecIssue[] = [];
    const builder = jsonSchemaToSchemaBuilder(jsonSchema, { issues, path: "jsonSchema" });
    if (issues.length > 0) {
      return { builder: null, jsonSchema: null, issues };
    }

    return { builder, jsonSchema: jsonSchema as UnknownRecord, issues: [] };
  } catch {
    return {
      builder: null,
      jsonSchema: null,
      issues: [createSchemaValidationIssue("jsonSchema", "JSON Schema must be valid JSON.")],
    };
  }
}

function jsonSchemaToSchemaBuilder(schema: unknown, context: SchemaNodeContext): SchemaIRNode {
  if (!isRecord(schema)) {
    addIssue(context.issues, context.path, "Schema nodes must be objects");
    return createDefaultSchemaNode("string");
  }

  const title = readOptionalString(schema.title, joinSchemaPath(context.path as never, "title"), context.issues);
  const description = readOptionalString(
    schema.description,
    joinSchemaPath(context.path as never, "description"),
    context.issues,
  );

  for (const key of ["allOf", "if", "then", "else", "not", "oneOf"] as const) {
    if (key in schema) {
      addIssue(context.issues, joinSchemaPath(context.path as never, key), getUnsupportedSchemaKeywordMessage(key));
    }
  }

  if ("$ref" in schema) {
    validateAllowedKeys(schema, new Set(["$ref", "title", "description"]), context);
    return withMetadata(parseRefBuilder(schema.$ref, context), title, description);
  }

  if ("anyOf" in schema) {
    validateAllowedKeys(schema, new Set(["anyOf", "discriminator", "title", "description"]), context);
    const anyOf = schema.anyOf;
    if (!Array.isArray(anyOf) || anyOf.length < 2) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "anyOf"),
        "Discriminated unions must include at least two variants",
      );
      return withMetadata(createDefaultSchemaNode("discriminated_union"), title, description);
    }

    if (!("discriminator" in schema)) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "anyOf"),
        "Undiscriminated unions are not supported",
      );
    }

    const discriminator = parseDiscriminator(
      schema.discriminator,
      joinSchemaPath(context.path as never, "discriminator"),
      context.issues,
    );

    return withMetadata(
      {
        kind: "discriminated_union",
        discriminator,
        variants: anyOf.map((variant, index) =>
          jsonSchemaToSchemaBuilder(variant, {
            issues: context.issues,
            path: joinSchemaPath(context.path as never, `anyOf[${index}]`),
          }),
        ),
      },
      title,
      description,
    );
  }

  if ("const" in schema) {
    validateAllowedKeys(schema, new Set(["const", "type", "title", "description"]), context);
    const literal = parseJsonPrimitive(schema.const, joinSchemaPath(context.path as never, "const"), context.issues);
    validateDeclaredPrimitiveType(schema.type, literal ? primitiveKindForValue(literal) : undefined, context);
    return withMetadata({ kind: "literal", value: literal ?? "value" }, title, description);
  }

  if ("enum" in schema) {
    validateAllowedKeys(schema, new Set(["enum", "type", "title", "description"]), context);
    if (!Array.isArray(schema.enum) || schema.enum.length === 0) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "enum"), "Enum values must be a non-empty array");
      return withMetadata(createDefaultSchemaNode("enum"), title, description);
    }

    const values = schema.enum
      .map((entry, index) => parseJsonPrimitive(entry, joinSchemaPath(context.path as never, `enum[${index}]`), context.issues))
      .filter((entry): entry is JsonPrimitive => entry !== null);

    if (values.length > 0 && new Set(values.map((entry) => primitiveKindForValue(entry))).size > 1) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "enum"), "Enum values must all use the same primitive type");
    }

    validateDeclaredPrimitiveType(schema.type, values[0] ? primitiveKindForValue(values[0]) : undefined, context);
    return withMetadata({ kind: "enum", values: values.length > 0 ? values : ["value"] }, title, description);
  }

  if (typeof schema.type !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "type"), "Schema type is required");
    return withMetadata(createDefaultSchemaNode("string"), title, description);
  }

  if (PRIMITIVE_TYPES.has(schema.type)) {
    validateAllowedKeys(schema, new Set(["type", "title", "description"]), context);
    return withMetadata({ kind: schema.type as PrimitiveKind }, title, description);
  }

  if (schema.type === "array") {
    validateAllowedKeys(schema, new Set(["type", "items", "title", "description"]), context);
    if (Array.isArray(schema.items)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "items"), "Tuple arrays are not supported");
      return withMetadata(createDefaultSchemaNode("array"), title, description);
    }

    if (schema.items === undefined) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "items"), "Array items are required");
      return withMetadata(createDefaultSchemaNode("array"), title, description);
    }

    return withMetadata(
      {
        kind: "array",
        items: jsonSchemaToSchemaBuilder(schema.items, { issues: context.issues, path: joinSchemaPath(context.path as never, "items") }),
      },
      title,
      description,
    );
  }

  if (schema.type === "object") {
    validateAllowedKeys(
      schema,
      new Set(["type", "properties", "required", "additionalProperties", "title", "description"]),
      context,
    );

    const properties = schema.properties ?? {};
    if (!isRecord(properties)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "properties"), "Object properties must be an object");
      return withMetadata(createDefaultSchemaNode("object"), title, description);
    }

    const rawRequired = Array.isArray(schema.required) ? schema.required : [];
    if (schema.required !== undefined && !Array.isArray(schema.required)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "required"), "Required fields must be an array");
    }

    const requiredSet = new Set<string>();
    rawRequired.forEach((entry, index) => {
      if (typeof entry !== "string" || !entry.trim()) {
        addIssue(
          context.issues,
          joinSchemaPath(context.path as never, `required[${index}]`),
          "Required field names must be non-empty strings",
        );
        return;
      }

      requiredSet.add(entry);
    });

    let allowAdditionalProperties = false;
    if (isRecord(schema.additionalProperties)) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "additionalProperties"),
        "Schema-valued additionalProperties is not supported",
      );
    } else if (typeof schema.additionalProperties === "boolean") {
      allowAdditionalProperties = schema.additionalProperties;
    } else if (schema.additionalProperties !== undefined) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "additionalProperties"),
        "additionalProperties must be a boolean",
      );
    }

    const fields = Object.entries(properties).map(([name, childSchema]) => ({
      name,
      required: requiredSet.has(name),
      schema: jsonSchemaToSchemaBuilder(childSchema, {
        issues: context.issues,
        path: joinSchemaPath(context.path as never, `properties.${name}`),
      }),
    }));

    for (const requiredField of [...requiredSet].filter((name) => !(name in properties))) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "required"),
        `Required field ${JSON.stringify(requiredField)} is not defined in properties`,
      );
    }

    return withMetadata(
      {
        kind: "object",
        allowAdditionalProperties,
        fields,
      },
      title,
      description,
    );
  }

  addIssue(context.issues, joinSchemaPath(context.path as never, "type"), `Schema type ${JSON.stringify(schema.type)} is not supported`);
  return withMetadata(createDefaultSchemaNode("string"), title, description);
}

function validateAllowedKeys(schema: Record<string, unknown>, allowedKeys: Set<string>, context: SchemaNodeContext) {
  for (const key of Object.keys(schema).sort()) {
    if (allowedKeys.has(key)) {
      continue;
    }

    addIssue(context.issues, joinSchemaPath(context.path as never, key), getUnsupportedSchemaKeywordMessage(key));
  }
}

function readOptionalString(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (value === undefined || value === null) {
    return undefined;
  }

  if (typeof value !== "string") {
    addIssue(issues, path, `${path.endsWith("title") ? "title" : "description"} must be a string`);
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function parseJsonPrimitive(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (typeof value === "boolean" || typeof value === "string" || typeof value === "number") {
    return value as JsonPrimitive;
  }

  addIssue(issues, path, "Values must be JSON primitives");
  return null;
}

function validateDeclaredPrimitiveType(
  declaredType: unknown,
  expectedType: PrimitiveKind | undefined,
  context: SchemaNodeContext,
) {
  if (declaredType === undefined || expectedType === undefined) {
    return;
  }

  if (typeof declaredType !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "type"), "Schema type must be a string");
    return;
  }

  if (declaredType !== expectedType) {
    addIssue(
      context.issues,
      joinSchemaPath(context.path as never, "type"),
      `Declared type ${JSON.stringify(declaredType)} does not match the literal or enum values`,
    );
  }
}

function parseDiscriminator(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }

  if (isRecord(value) && typeof value.propertyName === "string" && value.propertyName.trim()) {
    return value.propertyName.trim();
  }

  addIssue(issues, path, "Discriminator must define propertyName");
  return "kind";
}

function parseRefBuilder(value: unknown, context: SchemaNodeContext): SchemaIRRef {
  if (typeof value !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "$ref"), "Registry refs must be strings");
    return { kind: "ref", schemaKey: "shared_schema" } as const;
  }

  const match = REGISTRY_REF_RE.exec(value.trim());
  if (!match?.groups?.key) {
    addIssue(
      context.issues,
      joinSchemaPath(context.path as never, "$ref"),
      "Registry refs must use registry://<key> or registry://<key>@<version>",
    );
    return { kind: "ref", schemaKey: "shared_schema" } as const;
  }

  return {
    kind: "ref",
    schemaKey: match.groups.key,
    schemaVersion: match.groups.version ? Number.parseInt(match.groups.version, 10) : undefined,
  } as const;
}

