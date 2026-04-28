import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { schemaBuilderToJsonSchema } from "@/lib/platform-authoring/schema/codec";
import type { OutputSchemaRead } from "@/lib/types/output-schema";

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
} satisfies OutputSchemaRead;

const unsupportedSchema = {
  ...existingSchema,
  id: 8,
  key: "legacy_schema",
  name: "Legacy Schema",
  jsonSchema: {
    type: "object",
    properties: {},
    patternProperties: { "^x": { type: "string" } },
  },
} satisfies OutputSchemaRead;

const schemaRecords: Record<string, OutputSchemaRead> = {
  "7": existingSchema,
  "8": unsupportedSchema,
};

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
      ? { data: schemaRecords[schemaId], error: null, isError: false, isPending: false }
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

  it("shows builder, exact raw schema JSON, and sample preview together from shared builder state", async () => {
    render(<OutputSchemasEditorPage />);

    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.getByText("Schema builder")).toBeVisible();
    expect(screen.getByTestId("output-schema-raw-json")).toBeVisible();
    expect(screen.getByTestId("output-schema-preview")).toBeVisible();

    fireEvent.click(screen.getByTestId("output-schema-add-field"));
    fireEvent.change(screen.getByDisplayValue("field_1"), { target: { value: "answer" } });

    await waitFor(() => {
      expect(
        within(screen.getByTestId("output-schema-preview")).getByRole("textbox", {
          name: /derived sample output/i,
        }),
      ).toHaveValue(stringifyJson({ answer: "example" }));
    });

    const rawJsonTextbox = within(screen.getByTestId("output-schema-raw-json")).getByRole("textbox", {
      name: /exact raw schema json/i,
    });

    expect(rawJsonTextbox).toHaveValue(
      stringifyJson(
        schemaBuilderToJsonSchema({
          kind: "object",
          allowAdditionalProperties: false,
          fields: [{ name: "answer", required: true, schema: { kind: "string" } }],
        }),
      ),
    );
    expect(rawJsonTextbox).toHaveAttribute("readonly");

    const previewTextbox = within(screen.getByTestId("output-schema-preview")).getByRole("textbox", {
      name: /derived sample output/i,
    });

    expect(previewTextbox).toHaveValue(stringifyJson({ answer: "example" }));
    expect(previewTextbox).toHaveAttribute("readonly");
  });

  it("creates a schema from the builder-only flow", async () => {
    createOutputSchemaMock.mockResolvedValue({ id: 11 });

    render(<OutputSchemasEditorPage />);

    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "analysis_schema" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Analysis Schema" } });
    fireEvent.click(screen.getByTestId("output-schema-add-field"));
    fireEvent.change(screen.getByDisplayValue("field_1"), { target: { value: "answer" } });
    fireEvent.click(screen.getByTestId("output-schemas-save"));

    await waitFor(() => expect(createOutputSchemaMock).toHaveBeenCalledTimes(1));
    expect(createOutputSchemaMock).toHaveBeenCalledWith({
      key: "analysis_schema",
      kind: "standalone",
      name: "Analysis Schema",
      description: undefined,
      builder: {
        kind: "object",
        allowAdditionalProperties: false,
        fields: [{ name: "answer", required: true, schema: { kind: "string" } }],
      },
      jsonSchema: schemaBuilderToJsonSchema({
        kind: "object",
        allowAdditionalProperties: false,
        fields: [{ name: "answer", required: true, schema: { kind: "string" } }],
      }),
    });
    expect(navigateMock).toHaveBeenCalledWith("/output-schemas/11/edit");
  });

  it("hydrates edit mode and saves through the update hook", async () => {
    paramsMock.schemaId = "7";
    updateOutputSchemaMock.mockResolvedValue({ id: 12 });

    render(<OutputSchemasEditorPage />);

    expect(screen.getByLabelText("Key")).toBeDisabled();
    expect(screen.getByTestId("output-schema-raw-json")).toBeVisible();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Analysis Schema Updated" } });
    fireEvent.click(screen.getByTestId("output-schemas-save"));

    await waitFor(() => expect(updateOutputSchemaMock).toHaveBeenCalledTimes(1));
    expect(updateOutputSchemaMock).toHaveBeenCalledWith({
      schemaId: "7",
      payload: expect.objectContaining({
        name: "Analysis Schema Updated",
        description: existingSchema.description,
        jsonSchema: existingSchema.jsonSchema,
        builder: expect.objectContaining({
          kind: "object",
          allowAdditionalProperties: false,
          fields: expect.arrayContaining([
            expect.objectContaining({
              name: "summary",
              required: true,
              schema: expect.objectContaining({ kind: "string" }),
            }),
          ]),
        }),
      }),
    });
    expect(navigateMock).toHaveBeenCalledWith("/output-schemas/12/edit");
  });

  it("shows an explicit blocker for unsupported persisted records and disables save", () => {
    paramsMock.schemaId = "8";

    render(<OutputSchemasEditorPage />);

    expect(screen.getByTestId("output-schema-unsupported-record")).toHaveTextContent("Unsupported retired schema shape");
    expect(screen.getByTestId("output-schema-unsupported-record")).toHaveTextContent("patternProperties is not supported");
    expect(screen.getByTestId("output-schemas-save")).toBeDisabled();
    expect(screen.queryByRole("tab", { name: /builder/i })).not.toBeInTheDocument();
    expect(updateOutputSchemaMock).not.toHaveBeenCalled();
  });
});
