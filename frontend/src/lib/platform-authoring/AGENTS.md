# FRONTEND PLATFORM AUTHORING LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/platform-authoring/` owns pure TypeScript authoring helpers for Workflow Package manifests and package-local resources: agents, output schemas, capability profiles, private MCP configs, workflow graphs, generated input values, resource refs, validation issues, local YAML diagnostics/formatting, manifest parsing, and JSON serialization. It is intentionally React-free and request-free.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

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

## CHILD DOCS
- `common/AGENTS.md` — resource refs, field paths, issue text, and safe serialization
- `schema/AGENTS.md` — schema IR, JSON Schema codec, preview, templates, launch input state, and validation
- `values/AGENTS.md` — generated-form value-entry model, codec, factories, and validation
- `agents/AGENTS.md` — package-local agent manifest parsing, formatting, outline, and diagnostics
- `workflows/AGENTS.md` — workflow graph drafts, manifest codec, wire bindings, and validation
- `workflow-packages/AGENTS.md` — package manifest parsing/serialization, runtime-input registry, secret bindings, and private MCP transport helpers

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Schema builder contract | `schema/types.ts`, `schema/codec.ts` | IR ↔ JSON Schema conversion and parser boundary |
| Schema defaults / preview | `schema/factories.ts`, `schema/preview.ts`, `schema/schema-template.ts` | initial nodes, sample values, and schema template defaults for editors |
| Launch input state | `schema/launch-input-state.ts` | workflow launch parameter form state and draft preservation helpers |
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
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
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
