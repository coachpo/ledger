import { describe, expect, it } from "vitest";

import { formatMarkdown } from "./markdown-format";

describe("formatMarkdown", () => {
  it("normalizes markdown list spacing and keeps template placeholders intact", async () => {
    const input = "# Report\n{{portfolios.demo}}\n\n-   first item\n-    second item\n";

    await expect(formatMarkdown(input)).resolves.toBe(
      "# Report\n\n{{portfolios.demo}}\n\n- first item\n- second item\n",
    );
  });
});
