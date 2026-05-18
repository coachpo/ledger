import { describe, expect, it } from "vitest";

const sourceFiles = import.meta.glob("./**/*.{ts,tsx}", {
  eager: true,
  import: "default",
  query: "?raw",
});

const staleTokens = [
  ["@/lib/api/", "agents"].join(""),
  ["@/lib/api/", "capabilities"].join(""),
  ["@/lib/api/", "mcp-servers"].join(""),
  ["@/lib/api/", "output-schemas"].join(""),
  ["@/lib/api/", "workflows"].join(""),
  ["./api/", "agents"].join(""),
  ["./api/", "capabilities"].join(""),
  ["./api/", "mcp-servers"].join(""),
  ["./api/", "output-schemas"].join(""),
  ["./api/", "workflows"].join(""),
  ["queryKeys.platform.", "agents"].join(""),
  ["queryKeys.platform.", "workflows"].join(""),
  ["queryKeys.platform.", "capabilities"].join(""),
  ["queryKeys.platform.", "mcpServers"].join(""),
  ["queryKeys.platform.", "outputSchemas"].join(""),
  ["use", "Agents"].join(""),
  ["use", "Capabilities"].join(""),
  ["use", "McpServers"].join(""),
  ["use", "OutputSchemas"].join(""),
  ["use", "Workflows"].join(""),
  ["agents", "Api"].join(""),
  ["workflows", "Api"].join(""),
  ["capabilities", "Api"].join(""),
  ["mcpServers", "Api"].join(""),
  ["outputSchemas", "Api"].join(""),
  ["@/hooks/use-", "agents"].join(""),
  ["@/hooks/use-", "capabilities"].join(""),
  ["@/hooks/use-", "output-schemas"].join(""),
  ["@/hooks/use-", "mcp-servers"].join(""),
];

describe("platform clean break", () => {
  it("keeps retired global authoring hooks and clients out of shipped source", () => {
    const matches = Object.entries(sourceFiles).flatMap(([fileName, source]) =>
      staleTokens.filter((token) => String(source).includes(token)).map((token) => `${fileName}: ${token}`),
    );

    expect(matches).toEqual([]);
  });
});
