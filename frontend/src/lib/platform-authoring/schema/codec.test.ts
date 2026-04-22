import { describe, expect, it } from "vitest";

import { parseSchemaJsonText, schemaBuilderToJsonSchema } from "./codec";

describe("schema codec", () => {
  it("converts an object builder into JSON Schema", () => {
    const builder = {
      kind: "object",
      allowAdditionalProperties: false,
      fields: [
        { name: "summary", required: true, schema: { kind: "string", title: "Summary" } },
        { name: "count", required: false, schema: { kind: "integer" } },
        { name: "shared", required: true, schema: { kind: "ref", schemaKey: "analysis_schema", schemaVersion: 2 } },
      ],
    } satisfies Parameters<typeof schemaBuilderToJsonSchema>[0];

    expect(schemaBuilderToJsonSchema(builder)).toEqual({
      type: "object",
      additionalProperties: false,
      properties: {
        summary: { type: "string", title: "Summary" },
        count: { type: "integer" },
        shared: { $ref: "registry://analysis_schema@2" },
      },
      required: ["summary", "shared"],
    });
  });

  it("parses supported JSON Schema text into builder nodes", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          type: "object",
          title: "Analysis",
          description: "Structured output.",
          properties: {
            summary: { type: "string", title: "Summary" },
            itemIds: { type: "array", items: { type: "integer" } },
            shared: { $ref: "registry://analysis_schema@2" },
          },
          required: ["summary", "shared"],
          additionalProperties: true,
        },
        null,
        2,
      ),
    );

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual({
      kind: "object",
      title: "Analysis",
      description: "Structured output.",
      allowAdditionalProperties: true,
      fields: [
        { name: "summary", required: true, schema: { kind: "string", title: "Summary", description: null } },
        {
          name: "itemIds",
          required: false,
          schema: {
            kind: "array",
            title: null,
            description: null,
            items: { kind: "integer", title: null, description: null },
          },
        },
        {
          name: "shared",
          required: true,
          schema: { kind: "ref", schemaKey: "analysis_schema", schemaVersion: 2, title: null, description: null },
        },
      ],
    });
  });

  it("reports unsupported keywords with the current parser wording", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          type: "object",
          properties: {},
          patternProperties: { "^x": { type: "string" } },
        },
        null,
        2,
      ),
    );

    expect(result.builder).toBeNull();
    expect(result.jsonSchema).toBeNull();
    expect(result.issues).toEqual([
      {
        field: "jsonSchema.patternProperties",
        issue: "patternProperties is not supported",
      },
    ]);
  });

  it("decodes registry refs into key and version fields", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          $ref: "registry://shared_schema@12",
        },
        null,
        2,
      ),
    );

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual({
      kind: "ref",
      schemaKey: "shared_schema",
      schemaVersion: 12,
      title: null,
      description: null,
    });
  });
});
