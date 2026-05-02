import type { UnknownRecord } from "./common";

export type JsonPrimitive = boolean | number | string;
export type JsonValue = boolean | number | string | null | JsonValue[] | { [key: string]: JsonValue };
export type OutputSchemaStatus = "draft" | "published" | "deprecated" | "archived";
export type OutputSchemaKind = "standalone" | "shared";

interface OutputSchemaBuilderBase {
  title?: string | null;
  description?: string | null;
  defaultValue?: JsonValue;
}

export interface OutputSchemaBuilderString extends OutputSchemaBuilderBase {
  kind: "string";
}

export interface OutputSchemaBuilderInteger extends OutputSchemaBuilderBase {
  kind: "integer";
}

export interface OutputSchemaBuilderNumber extends OutputSchemaBuilderBase {
  kind: "number";
}

export interface OutputSchemaBuilderBoolean extends OutputSchemaBuilderBase {
  kind: "boolean";
}

export interface OutputSchemaBuilderEnum extends OutputSchemaBuilderBase {
  kind: "enum";
  values: JsonPrimitive[];
}

export interface OutputSchemaBuilderLiteral extends OutputSchemaBuilderBase {
  kind: "literal";
  value: JsonPrimitive;
}

export interface OutputSchemaBuilderField {
  name: string;
  required?: boolean;
  schema: OutputSchemaBuilderNode;
}

export interface OutputSchemaBuilderObject extends OutputSchemaBuilderBase {
  kind: "object";
  fields?: OutputSchemaBuilderField[];
  allowAdditionalProperties?: boolean;
}

export interface OutputSchemaBuilderArray extends OutputSchemaBuilderBase {
  kind: "array";
  items: OutputSchemaBuilderNode;
}

export interface OutputSchemaBuilderRef extends OutputSchemaBuilderBase {
  kind: "ref";
  schemaKey: string;
  schemaVersion?: number | null;
}

export interface OutputSchemaBuilderDiscriminatedUnion extends OutputSchemaBuilderBase {
  kind: "discriminated_union";
  discriminator: string;
  variants: OutputSchemaBuilderNode[];
}

export type OutputSchemaBuilderNode =
  | OutputSchemaBuilderString
  | OutputSchemaBuilderInteger
  | OutputSchemaBuilderNumber
  | OutputSchemaBuilderBoolean
  | OutputSchemaBuilderEnum
  | OutputSchemaBuilderLiteral
  | OutputSchemaBuilderObject
  | OutputSchemaBuilderArray
  | OutputSchemaBuilderRef
  | OutputSchemaBuilderDiscriminatedUnion;

export interface OutputSchemaCreateInput {
  key: string;
  kind?: OutputSchemaKind;
  name: string;
  description?: string;
  builder?: OutputSchemaBuilderNode;
  jsonSchema?: UnknownRecord | null;
}

export interface OutputSchemaUpdateInput {
  name?: string;
  description?: string;
  builder?: OutputSchemaBuilderNode;
  jsonSchema?: UnknownRecord;
}

export interface OutputSchemaRead {
  id: number;
  key: string;
  version: number;
  status: OutputSchemaStatus;
  kind: OutputSchemaKind;
  name: string;
  description: string;
  jsonSchema: UnknownRecord;
  builder: OutputSchemaBuilderNode;
  registryRefs: string[];
  createdAt: string;
  updatedAt: string;
}

export interface OutputSchemaListRead {
  items: OutputSchemaRead[];
}

export interface OutputSchemaListParams {
  status?: OutputSchemaStatus;
  kind?: OutputSchemaKind;
}
