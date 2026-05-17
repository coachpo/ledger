import type {
  SchemaIRArray,
  SchemaIRBoolean,
  SchemaIRDiscriminatedUnion,
  SchemaIREnum,
  SchemaIRField,
  SchemaIRLiteral,
  SchemaIRNode,
  SchemaIRObject,
  SchemaIRRef,
  SchemaIRString,
} from "./types";

export function createDefaultSchemaNode(kind: SchemaIRNode["kind"] = "object"): SchemaIRNode {
  switch (kind) {
    case "string":
      return { kind: "string" } satisfies SchemaIRString;
    case "integer":
      return { kind: "integer" };
    case "number":
      return { kind: "number" };
    case "boolean":
      return { kind: "boolean" } satisfies SchemaIRBoolean;
    case "enum":
      return { kind: "enum", values: ["value"] } satisfies SchemaIREnum;
    case "literal":
      return { kind: "literal", value: "value" } satisfies SchemaIRLiteral;
    case "array":
      return { kind: "array", items: createDefaultSchemaNode("string") } satisfies SchemaIRArray;
    case "ref":
      return { kind: "ref", schemaKey: "shared_schema" } satisfies SchemaIRRef;
    case "discriminated_union":
      return {
        kind: "discriminated_union",
        discriminator: "kind",
        variants: [createDefaultVariantObject("first"), createDefaultVariantObject("second")],
      } satisfies SchemaIRDiscriminatedUnion;
    case "object":
    default:
      return {
        kind: "object",
        fields: [],
      } satisfies SchemaIRObject;
  }
}

export function createDefaultSchemaField(name = "field"): SchemaIRField {
  return { name, required: true, schema: createDefaultSchemaNode("string") };
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
