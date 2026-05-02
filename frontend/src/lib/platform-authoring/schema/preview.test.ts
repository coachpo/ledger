import { describe, expect, it } from "vitest";

import type { SchemaIRNode } from "./types";
import { buildPreviewValue, buildRunInputDefaultValue } from "./preview";

describe("schema preview values", () => {
  const metadataRichSchema: SchemaIRNode = {
    kind: "object",
    allowAdditionalProperties: false,
    fields: [
      {
        name: "ticker",
        required: true,
        schema: { kind: "string", title: "Ticker Symbol", description: "Exchange ticker." },
      },
      {
        name: "dryRun",
        required: false,
        schema: { kind: "boolean", title: "Dry Run", description: "Skip side effects." },
      },
    ],
  };

  it("keeps titles out of synthesized string samples", () => {
    expect(buildPreviewValue(metadataRichSchema)).toEqual({ ticker: "example", dryRun: true });
  });

  it("builds initial run input values from required fields only", () => {
    expect(buildRunInputDefaultValue(metadataRichSchema)).toEqual({ ticker: "example" });
  });
});
