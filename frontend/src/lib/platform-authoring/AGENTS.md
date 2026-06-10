# FRONTEND PLATFORM AUTHORING LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/platform-authoring/` owns pure TypeScript authoring helpers for Workflow Package manifests and package-local resources: agents, output schemas, capability profiles, private MCP configs, workflow graphs, generated input values, resource refs, validation issues, local YAML diagnostics/formatting, manifest parsing, and JSON serialization. It is intentionally React-free and request-free.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## STRUCTURE
```text
platform-authoring/
├── common/              # resource refs, JSON serialization, field paths, issue helpers
├── schema/              # schema IR, JSON Schema codec, factories, validation, preview
├── values/              # generated-form value-entry model, codec, factories, validation
├── agents/              # package-local agent manifest parsing, formatting, outline, and validation
├── workflows/           # package-local workflow graph helpers and validation
└── workflow-packages/   # package manifest parser, serializer, resource assembly, and YAML workflow helpers
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Schema builder contract | `schema/types.ts`, `schema/codec.ts` | IR ↔ JSON Schema conversion and parser boundary |
| Schema defaults / preview | `schema/factories.ts`, `schema/preview.ts` | initial nodes and sample values for editors |
| Schema validation | `schema/validation.ts` | builder issue model used by package-local output schema, agent, and workflow panels |
| Value-entry helpers | `values/*.ts` | schema-driven form values and validation |
| Workflow Package manifests | `workflow-packages/manifest.ts` | package draft model, local parsing/serialization, private MCP transport helpers, and workflow YAML conversion |
| Package-local workflow authoring | `workflows/*.ts` | draft creation, wire bindings, path validation |
| Package-local agent authoring | `agents/manifest.ts` | manifest parsing, formatting, outline extraction, and editor diagnostics |
| Common helpers | `common/*.ts` | resource refs, field paths, issue text, safe serialization |
| Local coverage | `agents/manifest.test.ts`, `workflow-packages/manifest.test.ts` | manifest round-trips, YAML restrictions, and private MCP authoring fields |

## CONVENTIONS
- Keep this layer pure: no React state, hooks, routing, toasts, or network requests.
- Codecs translate between backend wire contracts and editor-friendly IR; pages/components should not reimplement parsing.
- Factories own default draft/node/value creation so editors start from consistent state.
- Validation returns structured issue lists that pages/components render; do not throw for normal authoring mistakes.
- Local manifest helpers are allowed to reject unsupported YAML features up front. Keep aliases, anchors, merge keys, and unsupported tags out of package/agent authoring flows.
- Private MCP authoring stays package-local: stdio drafts keep command/args text and HTTP drafts keep `url`, `headers`, and `query`; browser-visible manifest reads and exports omit secret-bearing `env`, `headers`, and `query` maps.
- Resource-ref parsing and formatting stay centralized in `common/resource-ref.ts`.

## ANTI-PATTERNS
- Do not import `src/hooks`, `src/lib/api`, or UI components into this tree.
- Do not fork schema, value, workflow, or manifest validation in routed pages.
- Do not store display-only labels in IR types when they do not belong to backend contracts.
- Do not silently widen the supported JSON Schema or manifest/YAML subset without updating tests and backend compiler/parser expectations.
- Do not move private MCP transport normalization into page components.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
