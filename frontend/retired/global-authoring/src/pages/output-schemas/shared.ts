export {
  formatPrimitiveList,
  parsePrimitiveInput,
  parsePrimitiveList,
  parseSchemaJsonText as parseJsonSchemaText,
  schemaBuilderToJsonSchema as builderToJsonSchema,
  type SchemaCodecParseFailure as JsonSchemaParseFailure,
  type SchemaCodecParseResult as JsonSchemaParseResult,
  type SchemaCodecParseSuccess as JsonSchemaParseSuccess,
} from "@/lib/platform-authoring/schema/codec";
export {
  createDefaultSchemaField as createDefaultField,
  createDefaultSchemaNode as createDefaultBuilderNode,
} from "@/lib/platform-authoring/schema/factories";
export { createLiteralValueDraft, createPreviewJson } from "@/lib/platform-authoring/schema/preview";
export type { SchemaValidationIssue as OutputSchemaValidationIssue } from "@/lib/platform-authoring/schema/validation";

export function stringifyJsonSchema(value: unknown) {
  return JSON.stringify(value, null, 2);
}
