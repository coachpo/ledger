import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LegacySkillsEditRedirect,
  LegacySkillsListRedirect,
  LegacySkillsNewRedirect,
} from "./legacy-redirect";

const { navigateProps, paramsMock } = vi.hoisted(() => ({
  navigateProps: [] as Array<{ replace?: boolean; to: string }>,
  paramsMock: { skillId: "" },
}));

vi.mock("react-router", () => ({
  Navigate: (props: { replace?: boolean; to: string }) => {
    navigateProps.push(props);
    return null;
  },
  useParams: () => paramsMock,
}));

describe("legacy skill route redirects", () => {
  beforeEach(() => {
    navigateProps.length = 0;
    paramsMock.skillId = "";
  });

  it("redirects the legacy list route to canonical capabilities with replace", () => {
    render(<LegacySkillsListRedirect />);

    expect(navigateProps).toEqual([{ replace: true, to: "/capabilities" }]);
  });

  it("redirects the legacy create route to canonical capabilities with replace", () => {
    render(<LegacySkillsNewRedirect />);

    expect(navigateProps).toEqual([{ replace: true, to: "/capabilities/new" }]);
  });

  it("redirects the legacy edit route to the matching canonical capability route with replace", () => {
    paramsMock.skillId = "42";

    render(<LegacySkillsEditRedirect />);

    expect(navigateProps).toEqual([{ replace: true, to: "/capabilities/42/edit" }]);
  });
});
