import { describe, expect, it } from "vitest";

import { queryKeys } from "@/lib/query-keys";

describe("useAgents clean-break removal", () => {
  it("does not expose global agent authoring query keys", () => {
    expect(Reflect.has(queryKeys.platform, "agents")).toBe(false);
  });
});
