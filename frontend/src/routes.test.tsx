import { matchRoutes } from "react-router";
import { describe, expect, it } from "vitest";

import { router } from "./routes";

describe("router", () => {
  it("registers a discoverable orchestration hub route", () => {
    expect(matchRoutes(router.routes, "/orchestration")).not.toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/roles")).not.toBeNull();
    expect(matchRoutes(router.routes, "/orchestration/characters")).not.toBeNull();
  });

  it("does not register the removed backtests route family", () => {
    expect(matchRoutes(router.routes, "/backtests")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/new")).toBeNull();
    expect(matchRoutes(router.routes, "/backtests/123")).toBeNull();
  });
});
