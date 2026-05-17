import type { JsonPrimitive, SchemaIRLiteral, SchemaIRNode, SchemaIRObject } from "./types";

type PrimitiveKind = "boolean" | "integer" | "number" | "string";

function primitiveValueToInput(value: JsonPrimitive): string {
  return typeof value === "string" ? value : String(value);
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

function createDefaultVariantObject(tag: string): SchemaIRObject {
  return {
    kind: "object",
    fields: [
      { name: "kind", required: true, schema: { kind: "literal", value: tag } },
      { name: "value", required: true, schema: { kind: "string" } },
    ],
  };
}

function buildSampleValue(node: SchemaIRNode, options: { includeOptionalFields: boolean }): unknown {
  switch (node.kind) {
    case "string":
      return "example";
    case "integer":
      return 1;
    case "number":
      return 1.5;
    case "boolean":
      return true;
    case "enum":
      return node.values[0] ?? null;
    case "literal":
      return node.value;
    case "array":
      return [buildSampleValue(node.items, options)];
    case "ref":
      return `registry://${node.schemaKey}${node.schemaVersion ? `@${node.schemaVersion}` : ""}`;
    case "discriminated_union":
      return buildSampleValue(node.variants[0] ?? createDefaultVariantObject("variant"), options);
    case "object":
    default:
      return Object.fromEntries(
        (node.fields ?? [])
          .filter((field) => options.includeOptionalFields || field.required !== false)
          .map((field) => [field.name, buildSampleValue(field.schema, options)]),
      );
  }
}

export function buildPreviewValue(node: SchemaIRNode): unknown {
  return buildSampleValue(node, { includeOptionalFields: true });
}

export function buildRunInputDefaultValue(node: SchemaIRNode): unknown {
  return buildSampleValue(node, { includeOptionalFields: false });
}

export function stringifyPreviewJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function createPreviewJson(builder: SchemaIRNode) {
  return stringifyPreviewJson(buildPreviewValue(builder));
}

export function createLiteralValueDraft(node: SchemaIRLiteral) {
  const kind = primitiveKindForValue(node.value);
  return {
    kind,
    value: primitiveValueToInput(node.value),
  };
}
