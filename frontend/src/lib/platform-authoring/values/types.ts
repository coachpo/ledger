export type ValueEntryKind = "null" | "boolean" | "integer" | "number" | "string" | "array" | "object";

type ValueEntryPathToken = string;
export type ValueEntryPath = ValueEntryPathToken[];

interface ValueEntryBase {
  kind: ValueEntryKind;
  pathTokens: ValueEntryPath;
}

export interface ValueEntryNull extends ValueEntryBase {
  kind: "null";
  value: null;
}

export interface ValueEntryBoolean extends ValueEntryBase {
  kind: "boolean";
  value: boolean;
}

export interface ValueEntryInteger extends ValueEntryBase {
  kind: "integer";
  value: number;
}

export interface ValueEntryNumber extends ValueEntryBase {
  kind: "number";
  value: number;
}

export interface ValueEntryString extends ValueEntryBase {
  kind: "string";
  value: string;
}

export interface ValueEntryArrayItem {
  index: number;
  pathTokens: ValueEntryPath;
  value: ValueEntry;
}

export interface ValueEntryArray extends ValueEntryBase {
  kind: "array";
  items: ValueEntryArrayItem[];
}

export interface ValueEntryObjectField {
  key: string;
  pathTokens: ValueEntryPath;
  value: ValueEntry;
}

export interface ValueEntryObject extends ValueEntryBase {
  kind: "object";
  fields: ValueEntryObjectField[];
}

export type ValueEntryScalar = ValueEntryNull | ValueEntryBoolean | ValueEntryInteger | ValueEntryNumber | ValueEntryString;
export type ValueEntry = ValueEntryScalar | ValueEntryArray | ValueEntryObject;
