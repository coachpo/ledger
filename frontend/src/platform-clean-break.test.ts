import { describe, expect, it } from "vitest";

import { queryKeys } from "./lib/query-keys";

const retiredApiModules = import.meta.glob(
  "./lib/api/{agents,capabilities,mcp-servers,output-schemas,workflows}.ts",
);
const retiredHookModules = import.meta.glob(
  "./hooks/use-{agents,capabilities,mcp-servers,output-schemas,workflows}.ts",
);
const retiredPlatformNamespaces = [
  "agents",
  "capabilities",
  "mcpServers",
  "outputSchemas",
  "workflows",
] as const;

function platformNamespaceKeys() {
  return Object.keys(queryKeys.platform);
}

describe("platform clean break", () => {
  it("keeps retired global authoring API and hook modules deleted", () => {
    expect(Object.keys(retiredApiModules)).toEqual([]);
    expect(Object.keys(retiredHookModules)).toEqual([]);
  });

  it("keeps platform query keys on live package-first namespaces", () => {
    expect(platformNamespaceKeys()).toEqual(
      expect.arrayContaining([
        "extensions",
        "modelConnections",
        "runs",
        "tools",
        "workflowPackages",
      ]),
    );
    for (const namespace of retiredPlatformNamespaces) {
      expect(platformNamespaceKeys()).not.toContain(namespace);
    }
  });
});
