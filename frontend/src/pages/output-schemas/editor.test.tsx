import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OutputSchemasEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { schemaId?: string } = {};
const createOutputSchemaMock = vi.fn();
const updateOutputSchemaMock = vi.fn();
const activateOutputSchemaMock = vi.fn();
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();

const existingSchema = {
  id: 7,
  key: "analysis_schema",
  version: 3,
  status: "draft",
  kind: "standalone",
  name: "Analysis Schema",
  description: "Structured analysis output.",
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
} as const;

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}));

vi.mock("@/hooks/use-output-schemas", () => ({
  useOutputSchema: (schemaId?: string) =>
    schemaId
      ? { data: existingSchema, error: null, isError: false, isPending: false }
      : { data: undefined, error: null, isError: false, isPending: false },
  useCreateOutputSchema: () => ({ isPending: false, mutateAsync: createOutputSchemaMock }),
  useUpdateOutputSchema: () => ({ isPending: false, mutateAsync: updateOutputSchemaMock }),
  useActivateOutputSchema: () => ({ isPending: false, mutateAsync: activateOutputSchemaMock }),
}));

describe("OutputSchemasEditorPage", () => {
  beforeEach(() => {
    paramsMock.schemaId = undefined;
    navigateMock.mockReset();
    createOutputSchemaMock.mockReset();
    updateOutputSchemaMock.mockReset();
    activateOutputSchemaMock.mockReset();
    toastErrorMock.mockReset();
    toastSuccessMock.mockReset();
  });

  it("shows builder, JSON Schema, and Preview tabs and keeps builder changes synchronized", async () => {
    render(<OutputSchemasEditorPage />);

    expect(screen.getByRole("tab", { name: /builder/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /json schema/i })).toBeVisible();
    expect(screen.getByRole("tab", { name: /preview/i })).toBeVisible();

    fireEvent.click(screen.getByTestId("output-schema-add-field"));
    fireEvent.change(screen.getByDisplayValue("field_1"), { target: { value: "answer" } });

    fireEvent.click(screen.getByRole("tab", { name: /json schema/i }));
    await waitFor(() => {
      expect((screen.getByTestId("output-schema-json-editor") as HTMLTextAreaElement).value).toContain('"answer":');
    });

    fireEvent.click(screen.getByRole("tab", { name: /preview/i }));
    expect(screen.getByTestId("output-schema-preview")).toHaveTextContent('"answer"');
  });

  it("surfaces unsupported keyword validation feedback and blocks save", async () => {
    render(<OutputSchemasEditorPage />);

    fireEvent.click(screen.getByRole("tab", { name: /json schema/i }));
    fireEvent.change(screen.getByTestId("output-schema-json-editor"), {
      target: {
        value: JSON.stringify(
          {
            type: "object",
            properties: {},
            patternProperties: { "^x": { type: "string" } },
          },
          null,
          2,
        ),
      },
    });

    expect(await screen.findByTestId("output-schema-validation-feedback")).toHaveTextContent(
      "patternProperties is not supported",
    );

    fireEvent.click(screen.getByTestId("output-schemas-save"));

    await waitFor(() => {
      expect(createOutputSchemaMock).not.toHaveBeenCalled();
      expect(toastErrorMock).toHaveBeenCalledWith("Resolve JSON Schema validation issues before saving.");
    });
  });

  it("hydrates edit mode, saves through the update hook, and navigates to the new version", async () => {
    paramsMock.schemaId = "7";
    updateOutputSchemaMock.mockResolvedValue({ id: 12 });

    render(<OutputSchemasEditorPage />);

    expect(screen.getByLabelText("Key")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Analysis Schema Updated" } });
    fireEvent.click(screen.getByTestId("output-schemas-save"));

    await waitFor(() => expect(updateOutputSchemaMock).toHaveBeenCalledTimes(1));
    expect(updateOutputSchemaMock).toHaveBeenCalledWith({
      schemaId: "7",
      payload: expect.objectContaining({
        builder: existingSchema.builder,
        name: "Analysis Schema Updated",
      }),
    });
    expect(navigateMock).toHaveBeenCalledWith("/output-schemas/12/edit");
  });
});
