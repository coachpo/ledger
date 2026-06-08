import { describe, expect, it } from "vitest";

import type { WorkflowPackageMetadataRead } from "./workflow-package";

describe("workflow package metadata types", () => {
  it("keeps apiVersion literal", () => {
    const metadata: WorkflowPackageMetadataRead = {
      apiVersion: "signaldeck.workflowPackage/v1",
      key: "research_package",
      name: "Research Package",
      description: "",
    };

    expect(metadata.apiVersion).toBe("signaldeck.workflowPackage/v1");
  });

  it("rejects unsupported apiVersion values", () => {
    const metadata: WorkflowPackageMetadataRead = {
      // @ts-expect-error unsupported workflow package apiVersion
      apiVersion: "signaldeck.workflowPackage/v2",
      key: "research_package",
      name: "Research Package",
      description: "",
    };

    expect(metadata.key).toBe("research_package");
  });
});
