import { describe, expect, it } from "vitest";

describe("runs detail-sections barrel", () => {
  it("re-exports RunForkDialog for RunsDetailPage", async () => {
    const detailSections = await import("./detail-sections");

    expect(detailSections).toHaveProperty("RunDetailSectionStack");
    expect(detailSections).toHaveProperty("RunForkDialog");
  });
});
