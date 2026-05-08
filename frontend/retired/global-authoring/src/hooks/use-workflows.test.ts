import { describe, expect, it } from "vitest";

import { queryKeys } from "@/lib/query-keys";

describe("useWorkflows clean-break removal", () => {
  it("does not expose global workflow authoring query keys", () => {
    expect(Reflect.has(queryKeys.platform, "workflows")).toBe(false);
  });
});
