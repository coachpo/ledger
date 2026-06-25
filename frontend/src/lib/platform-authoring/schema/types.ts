export type JsonPrimitive = boolean | number | string;
export type JsonValue = boolean | number | string | null | JsonValue[] | { [key: string]: JsonValue };

interface SchemaIRBase {
  title?: string | null;
  description?: string | null;
  defaultValue?: JsonValue;
}

export interface SchemaIRString extends SchemaIRBase {
  kind: "string";
}

export interface SchemaIRInteger extends SchemaIRBase {
  kind: "integer";
}

export interface SchemaIRNumber extends SchemaIRBase {
  kind: "number";
}

export interface SchemaIRBoolean extends SchemaIRBase {
  kind: "boolean";
}

export interface SchemaIREnum extends SchemaIRBase {
  kind: "enum";
  values: JsonPrimitive[];
}

export interface SchemaIRLiteral extends SchemaIRBase {
  kind: "literal";
  value: JsonPrimitive;
}

export interface SchemaIRField {
  name: string;
  required?: boolean;
  schema: SchemaIRNode;
}

export interface SchemaIRObject extends SchemaIRBase {
  kind: "object";
  fields?: SchemaIRField[];
}

export interface SchemaIRArray extends SchemaIRBase {
  kind: "array";
  items: SchemaIRNode;
}

export interface SchemaIRRef extends SchemaIRBase {
  kind: "ref";
  schemaKey: string;
  schemaVersion?: number | null;
}

export interface SchemaIRDiscriminatedUnion extends SchemaIRBase {
  kind: "discriminated_union";
  discriminator: string;
  variants: SchemaIRNode[];
}

export type SchemaIRNode =
  | SchemaIRString
  | SchemaIRInteger
  | SchemaIRNumber
  | SchemaIRBoolean
  | SchemaIREnum
  | SchemaIRLiteral
  | SchemaIRObject
  | SchemaIRArray
  | SchemaIRRef
  | SchemaIRDiscriminatedUnion;

export type SchemaIRBuilderInput = SchemaIRNode;

export type SchemaIR = SchemaIRNode;
export type SchemaIRVariant = SchemaIRNode;
export type SchemaIRPrimitive = JsonPrimitive;
