import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OutputSchemasListPage } from "./list";

const navigateMock = vi.fn();

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
}));

vi.mock("@/hooks/use-output-schemas", () => ({
  useOutputSchemas: () => ({
    data: {
      items: [
        {
          id: 5,
          key: "decision_schema",
          version: 2,
          status: "draft",
          kind: "standalone",
          name: "Decision Schema",
          description: "Structured decision output.",
          jsonSchema: {
            type: "object",
            properties: { summary: { type: "string" } },
            required: ["summary"],
            additionalProperties: false,
          },
          builder: {
            kind: "object",
            allowAdditionalProperties: false,
            fields: [{ name: "summary", required: true, schema: { kind: "string" } }],
          },
          registryRefs: [],
          createdAt: "2026-04-20T10:00:00Z",
          updatedAt: "2026-04-20T10:00:00Z",
        },
      ],
    },
    error: null,
    isError: false,
    isPending: false,
  }),
}));

describe("OutputSchemasListPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("renders schemas and navigates to create and edit routes", () => {
    render(<OutputSchemasListPage />);

    expect(screen.getByTestId("platform-output-schemas-page")).toBeVisible();
    expect(screen.getByText("Decision Schema")).toBeVisible();
    expect(screen.getByText("decision_schema")).toBeVisible();

    fireEvent.click(screen.getByTestId("output-schemas-new"));
    expect(navigateMock).toHaveBeenCalledWith("/output-schemas/new");

    fireEvent.click(screen.getByTestId("output-schemas-open-decision_schema"));
    expect(navigateMock).toHaveBeenCalledWith("/output-schemas/5/edit");
  });
});
