import type { WorkflowSection } from "@/lib/platform-authoring/workflows/types";

export const WORKFLOW_BUILDER_WIZARD_SECTIONS = [
  {
    description:
      "Set the workflow identity and define the request schema that step wiring can reference.",
    title: "Input",
    value: "input",
  },
  {
    description: "Arrange parallel steps and map pinned agents into named slots.",
    title: "Steps",
    value: "steps",
  },
  {
    description: "Choose the final output slot or synthesized output agent.",
    title: "Output",
    value: "output",
  },
  {
    description: "Review validation, payload structure, and run readiness.",
    title: "Review",
    value: "review",
  },
] as const satisfies readonly {
  description: string;
  title: string;
  value: WorkflowSection;
}[];

export function workflowBuilderSectionForIssue(field: string): WorkflowSection {
  if (field === "key" || field === "name" || field.startsWith("inputSchema")) {
    return "input";
  }

  if (field.startsWith("steps")) {
    return "steps";
  }

  if (field.startsWith("outputSpec")) {
    return "output";
  }

  return "review";
}
