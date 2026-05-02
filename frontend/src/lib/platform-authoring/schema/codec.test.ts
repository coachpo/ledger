import { describe, expect, it } from "vitest";

import { parseSchemaJsonText, schemaBuilderToJsonSchema } from "./codec";

type SchemaBuilderInput = Parameters<typeof schemaBuilderToJsonSchema>[0];

const metadataRichBuilder = {
  kind: "object",
  title: "Run Input",
  description: "Fields collected before launching the run.",
  allowAdditionalProperties: false,
  fields: [
    {
      name: "summary",
      required: true,
      schema: { kind: "string", title: "Summary", description: "Short text entered by the operator." },
    },
    {
      name: "approved",
      required: false,
      schema: { kind: "boolean", title: "Approved", description: "Whether the run may proceed." },
    },
    {
      name: "score",
      required: true,
      schema: { kind: "number", title: "Score", description: "Confidence score for the run." },
    },
    {
      name: "count",
      required: true,
      schema: { kind: "integer", title: "Count", description: "Number of positions to review." },
    },
    {
      name: "itemIds",
      required: true,
      schema: {
        kind: "array",
        title: "Item IDs",
        description: "Identifiers selected for the run.",
        items: { kind: "integer", title: "Item ID", description: "Single identifier." },
      },
    },
    {
      name: "rating",
      required: true,
      schema: { kind: "enum", values: ["low", "high"], title: "Rating", description: "Allowed rating values." },
    },
    {
      name: "status",
      required: true,
      schema: { kind: "literal", value: "ready", title: "Status", description: "Fixed status marker." },
    },
    {
      name: "shared",
      required: true,
      schema: {
        kind: "ref",
        schemaKey: "analysis_schema",
        schemaVersion: 2,
        title: "Shared Schema",
        description: "Registry-backed shared schema.",
      },
    },
    {
      name: "event",
      required: true,
      schema: {
        kind: "discriminated_union",
        title: "Event",
        description: "Event-specific input payload.",
        discriminator: "kind",
        variants: [
          {
            kind: "object",
            title: "Buy Event",
            description: "Branch for buy orders.",
            allowAdditionalProperties: false,
            fields: [
              {
                name: "kind",
                required: true,
                schema: { kind: "literal", value: "buy", title: "Event Kind", description: "Discriminator value." },
              },
              {
                name: "confidence",
                required: true,
                schema: { kind: "number", title: "Confidence", description: "Branch confidence value." },
              },
            ],
          },
          {
            kind: "object",
            title: "Sell Event",
            description: "Branch for sell orders.",
            allowAdditionalProperties: false,
            fields: [
              {
                name: "kind",
                required: true,
                schema: { kind: "literal", value: "sell", title: "Event Kind", description: "Discriminator value." },
              },
              {
                name: "reason",
                required: true,
                schema: { kind: "string", title: "Reason", description: "Branch reason text." },
              },
            ],
          },
        ],
      },
    },
  ],
} satisfies SchemaBuilderInput;

const metadataRichJsonSchema = {
  additionalProperties: false,
  properties: {
    summary: { type: "string", title: "Summary", description: "Short text entered by the operator." },
    approved: { type: "boolean", title: "Approved", description: "Whether the run may proceed." },
    score: { type: "number", title: "Score", description: "Confidence score for the run." },
    count: { type: "integer", title: "Count", description: "Number of positions to review." },
    itemIds: {
      items: { type: "integer", title: "Item ID", description: "Single identifier." },
      type: "array",
      title: "Item IDs",
      description: "Identifiers selected for the run.",
    },
    rating: { enum: ["low", "high"], type: "string", title: "Rating", description: "Allowed rating values." },
    status: { const: "ready", type: "string", title: "Status", description: "Fixed status marker." },
    shared: {
      $ref: "registry://analysis_schema@2",
      title: "Shared Schema",
      description: "Registry-backed shared schema.",
    },
    event: {
      anyOf: [
        {
          additionalProperties: false,
          properties: {
            kind: { const: "buy", type: "string", title: "Event Kind", description: "Discriminator value." },
            confidence: { type: "number", title: "Confidence", description: "Branch confidence value." },
          },
          required: ["kind", "confidence"],
          type: "object",
          title: "Buy Event",
          description: "Branch for buy orders.",
        },
        {
          additionalProperties: false,
          properties: {
            kind: { const: "sell", type: "string", title: "Event Kind", description: "Discriminator value." },
            reason: { type: "string", title: "Reason", description: "Branch reason text." },
          },
          required: ["kind", "reason"],
          type: "object",
          title: "Sell Event",
          description: "Branch for sell orders.",
        },
      ],
      discriminator: { propertyName: "kind" },
      title: "Event",
      description: "Event-specific input payload.",
    },
  },
  required: ["summary", "score", "count", "itemIds", "rating", "status", "shared", "event"],
  type: "object",
  title: "Run Input",
  description: "Fields collected before launching the run.",
};

describe("schema codec", () => {
  it("writes title and description metadata for supported builder nodes", () => {
    expect(schemaBuilderToJsonSchema(metadataRichBuilder)).toEqual(metadataRichJsonSchema);
  });

  it("reads title and description metadata from supported JSON Schema nodes", () => {
    const result = parseSchemaJsonText(JSON.stringify(metadataRichJsonSchema, null, 2));

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual(metadataRichBuilder);
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
