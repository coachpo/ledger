import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudioPersonaEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { personaKey?: string } = {};

function buildPersona(
  overrides: Partial<{
    key: string;
    origin: "managed" | "imported" | "seeded";
    status: "DRAFT" | "ACTIVE" | "DEPRECATED" | "ARCHIVED";
  }> = {},
) {
  return {
    id: 7,
    key: overrides.key ?? "managed.persona.alpha",
    version: 2,
    origin: overrides.origin ?? "managed",
    status: overrides.status ?? "DRAFT",
    kind: "managed_persona",
    displayName: "Managed Persona Alpha",
    enabled: true,
    handle: null,
    canonicalTargetId: `persona:${overrides.key ?? "managed.persona.alpha"}`,
    parentProfileKey: null,
    parentProfileVersion: null,
    legacySourceVersion: null,
    systemPromptFragment: "System instructions.",
    promptAppendFragment: "Append instructions.",
    defaultCapabilityBundleKeys: [],
    createdAt: "2026-04-14T10:00:00Z",
    updatedAt: "2026-04-14T10:00:00Z",
  };
}

vi.mock("react-router", () => ({
  useNavigate: () => navigateMock,
  useParams: () => paramsMock,
}));

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}));

vi.mock("@/hooks/use-studio", () => ({
  useStudioPersonaByKey: () => {
    if (!paramsMock.personaKey) {
      return {
        detailQuery: {
          data: undefined,
          error: null,
          isError: false,
          isPending: false,
        },
        isMissing: false,
      };
    }

    if (paramsMock.personaKey === "imported.character.analyst") {
      return {
        detailQuery: {
          data: buildPersona({
            key: "imported.character.analyst",
            origin: "imported",
            status: "ACTIVE",
          }),
          error: null,
          isError: false,
          isPending: false,
        },
        isMissing: false,
      };
    }

    if (paramsMock.personaKey === "managed.persona.active") {
      return {
        detailQuery: {
          data: buildPersona({ key: "managed.persona.active", status: "ACTIVE" }),
          error: null,
          isError: false,
          isPending: false,
        },
        isMissing: false,
      };
    }

    return {
      detailQuery: {
        data: buildPersona({ key: paramsMock.personaKey }),
        error: null,
        isError: false,
        isPending: false,
      },
      isMissing: false,
    };
  },
  useStudioPersonaVersions: () => ({
    data: { items: [{ version: 2, status: "DRAFT", origin: "managed", createdAt: "2026-04-14T10:00:00Z" }] },
    isPending: false,
  }),
  useCreateStudioPersona: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateStudioPersona: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useActivateStudioPersona: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeprecateStudioPersona: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useArchiveStudioPersona: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

describe("StudioPersonaEditorPage", () => {
  beforeEach(() => {
    paramsMock.personaKey = undefined;
    navigateMock.mockReset();
  });

  it("keeps the create route editable for managed personas", () => {
    render(<StudioPersonaEditorPage />);

    expect(screen.getByTestId("studio-personas-save")).toBeInTheDocument();
    expect(screen.getByLabelText(/persona key/i)).toBeEnabled();
    expect(screen.queryByTestId("studio-personas-readonly-banner")).not.toBeInTheDocument();
  });

  it("shows a read-only banner for imported personas", () => {
    paramsMock.personaKey = "imported.character.analyst";

    render(<StudioPersonaEditorPage />);

    expect(screen.getByTestId("studio-personas-readonly-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("studio-personas-save")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/persona handle/i)).toBeDisabled();
  });

  it("offers draft creation for managed active personas instead of inline editing", () => {
    paramsMock.personaKey = "managed.persona.active";

    render(<StudioPersonaEditorPage />);

    expect(screen.getByTestId("studio-personas-readonly-banner")).toBeInTheDocument();
    expect(screen.getByTestId("studio-personas-create-draft")).toBeInTheDocument();
    expect(screen.getByTestId("studio-personas-deprecate")).toBeInTheDocument();
    expect(screen.queryByTestId("studio-personas-save")).not.toBeInTheDocument();
  });
});
