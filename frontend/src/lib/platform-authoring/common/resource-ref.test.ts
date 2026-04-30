import { describe, expect, it } from "vitest";

import {
  formatResourceRef,
  parseResourceRef,
  parseVersionedRef,
  parseVersionedRefs,
  toVersionedRefValue,
  validateResourceRef,
  validateResourceRefs,
} from "./resource-ref";

describe("resource-ref", () => {
  it("parses key-only refs into typed ResourceRefs", () => {
    expect(parseResourceRef("Output schema", "summary_schema")).toEqual({
      key: "summary_schema",
      version: null,
    });
  });

  it("parses key+version refs and formats them back", () => {
    const ref = parseVersionedRef("Output schema", "summary_schema@5");

    expect(ref).toEqual({ key: "summary_schema", version: 5 });
    expect(formatResourceRef(ref)).toBe("summary_schema@5");
    expect(toVersionedRefValue(ref.key, ref.version)).toBe("summary_schema@5");
  });

  it("rejects invalid versions with current caller-facing wording", () => {
    expect(() => parseVersionedRef("Capability", "summarize@beta")).toThrowError(
      "Capability entries must use key or key@version.",
    );
  });

  it("rejects blank input and exposes validation issues for shared callers", () => {
    expect(() => parseResourceRef("Output schema", "  ")).toThrowError(
      "Output schema is required.",
    );
    expect(validateResourceRef("Output schema", "  ")).toEqual([
      {
        field: "Output schema",
        issue: "Output schema is required.",
      },
    ]);
  });

  it("parses line-delimited refs and tracks indexed validation paths", () => {
    expect(parseVersionedRefs("Capability", "summarize@3\nquotes")).toEqual([
      { key: "summarize", version: 3 },
      { key: "quotes", version: null },
    ]);
    expect(validateResourceRefs("Capability", "summarize@3\nbroken@beta")).toEqual([
      {
        field: "Capability[1]",
        issue: "Capability entries must use key or key@version.",
      },
    ]);
  });
});
