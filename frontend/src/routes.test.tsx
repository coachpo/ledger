import { matchRoutes } from "react-router";
import { describe, expect, it } from "vitest";

import { router } from "./routes";

describe("router", () => {
  it("does not register removed legacy route families", () => {
    expect(matchRoutes(router.routes, "/tryout")).toBeNull();
    expect(matchRoutes(router.routes, "/studio")).toBeNull();
    expect(matchRoutes(router.routes, "/studio/agents")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/roles")).toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/characters")).toBeNull();
  });

  it("does not register the removed backtests route family", () => {
    expect(matchRoutes(router.routes, "/backtests")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/new")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/123")).toBeNull();
  });
});
