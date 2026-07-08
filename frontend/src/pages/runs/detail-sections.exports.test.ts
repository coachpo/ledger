import { describe, expect, it } from "vitest";

describe("runs detail-sections barrel", () => {
  it("re-exports run detail sections for RunsDetailPage", async () => {
    const detailSections = await import("./detail-sections");

    expect(detailSections).toHaveProperty("RunDetailSectionStack");
  });
});
