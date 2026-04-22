import type {
  JsonPrimitive,
  OutputSchemaBuilderArray,
  OutputSchemaBuilderBoolean,
  OutputSchemaBuilderDiscriminatedUnion,
  OutputSchemaBuilderEnum,
  OutputSchemaBuilderField,
  OutputSchemaBuilderInteger,
  OutputSchemaBuilderLiteral,
  OutputSchemaBuilderNode,
  OutputSchemaBuilderNumber,
  OutputSchemaBuilderObject,
  OutputSchemaBuilderRef,
  OutputSchemaBuilderString,
  OutputSchemaCreateInput,
  OutputSchemaKind,
  OutputSchemaListParams,
  OutputSchemaListRead,
  OutputSchemaRead,
  OutputSchemaStatus,
  OutputSchemaUpdateInput,
} from "@/lib/types/output-schema";

export type { JsonPrimitive, OutputSchemaKind, OutputSchemaStatus };
export type { OutputSchemaCreateInput, OutputSchemaListParams, OutputSchemaListRead, OutputSchemaRead, OutputSchemaUpdateInput };

export type SchemaIRNode = OutputSchemaBuilderNode;
export type SchemaIRString = OutputSchemaBuilderString;
export type SchemaIRInteger = OutputSchemaBuilderInteger;
export type SchemaIRNumber = OutputSchemaBuilderNumber;
export type SchemaIRBoolean = OutputSchemaBuilderBoolean;
export type SchemaIREnum = OutputSchemaBuilderEnum;
export type SchemaIRLiteral = OutputSchemaBuilderLiteral;
export type SchemaIRObject = OutputSchemaBuilderObject;
export type SchemaIRArray = OutputSchemaBuilderArray;
export type SchemaIRRef = OutputSchemaBuilderRef;
export type SchemaIRDiscriminatedUnion = OutputSchemaBuilderDiscriminatedUnion;
export type SchemaIRField = OutputSchemaBuilderField;

export type SchemaIRBuilderInput = OutputSchemaBuilderNode;
export type SchemaIRRead = OutputSchemaRead;
export type SchemaIRCreateInput = OutputSchemaCreateInput;
export type SchemaIRUpdateInput = OutputSchemaUpdateInput;
export type SchemaIRListRead = OutputSchemaListRead;
export type SchemaIRListParams = OutputSchemaListParams;

export type SchemaIR = SchemaIRNode;
export type SchemaIRVariant = SchemaIRNode;
export type SchemaIRPrimitive = JsonPrimitive;
