import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudioAgentEditorPage } from "./editor";

const navigateMock = vi.fn();
const paramsMock: { agentKey?: string } = {};

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
  useStudioAgentSpecByKey: () =>
    paramsMock.agentKey
      ? {
          detailQuery: {
            data: {
              id: 8,
              key: paramsMock.agentKey,
              version: 1,
              origin: "seeded",
              status: "ACTIVE",
              name: "Seeded Agent",
              instructions: "Seeded instructions.",
              modelPolicy: {},
              finalOutputContract: null,
              defaultCapabilityBundleKeys: [],
              defaultPersonaProfileKeys: [],
              createdAt: "2026-04-14T10:00:00Z",
              updatedAt: "2026-04-14T10:00:00Z",
            },
            error: null,
            isError: false,
            isPending: false,
          },
          isMissing: false,
          matchedItem: { id: 8, key: paramsMock.agentKey },
        }
      : {
          detailQuery: {
            data: undefined,
            error: null,
            isError: false,
            isPending: false,
          },
          isMissing: false,
          matchedItem: undefined,
        },
  useCreateStudioAgentSpec: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
  useUpdateStudioAgentSpec: () => ({
    isPending: false,
    mutateAsync: vi.fn(),
  }),
}));

describe("StudioAgentEditorPage", () => {
  beforeEach(() => {
    paramsMock.agentKey = undefined;
    navigateMock.mockReset();
  });

  it("keeps the create route editable for managed Studio agents", () => {
    render(<StudioAgentEditorPage />);

    expect(screen.getByTestId("studio-agents-save")).toBeInTheDocument();
    expect(screen.getByLabelText(/agent key/i)).toBeEnabled();
    expect(screen.queryByTestId("studio-agents-readonly-banner")).not.toBeInTheDocument();
  });

  it("shows a read-only banner for seeded Studio agents", () => {
    paramsMock.agentKey = "seeded_agent";

    render(<StudioAgentEditorPage />);

    expect(screen.getByTestId("studio-agents-readonly-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("studio-agents-save")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/agent key/i)).toBeDisabled();
  });
});
