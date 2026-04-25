# FRONTEND PLATFORM AUTHORING LIB GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/platform-authoring/` owns pure TypeScript authoring helpers for platform agents, output schemas, workflow wiring, generated input values, resource refs, validation issues, and JSON serialization. It is intentionally React-free and request-free.

## STRUCTURE
```text
platform-authoring/
├── common/      # resource refs, JSON serialization, field paths, issue helpers
├── schema/      # schema IR, JSON Schema codec, factories, validation, preview
├── values/      # generated-form value-entry model, codec, factories, validation
├── agents/      # agent editor draft, binding refs, validation
└── workflows/   # workflow draft, wire-binding codec, validation
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Schema builder contract | `schema/types.ts`, `schema/codec.ts` | IR ↔ JSON Schema conversion and parser boundary |
| Schema defaults / preview | `schema/factories.ts`, `schema/preview.ts` | initial nodes and sample values for editors |
| Schema validation | `schema/validation.ts` | builder issue model used by output-schema, agent, and workflow pages |
| Value-entry helpers | `values/*.ts` | schema-driven form values and validation |
| Workflow authoring | `workflows/*.ts` | draft creation, wire bindings, path validation |
| Agent authoring | `agents/*.ts` | draft state, binding refs, agent validation |
| Common helpers | `common/*.ts` | versioned resource refs, field paths, issue text, safe serialization |

## CONVENTIONS
- Keep this layer pure: no React state, hooks, routing, toasts, or network requests.
- Codecs translate between backend wire contracts and editor-friendly IR; pages/components should not reimplement parsing.
- Factories own default draft/node/value creation so editors start from consistent state.
- Validation returns structured issue lists that pages/components render; do not throw for normal authoring mistakes.
- Resource-ref parsing and formatting stay centralized in `common/resource-ref.ts`.

## ANTI-PATTERNS
- Do not import `src/hooks`, `src/lib/api`, or UI components into this tree.
- Do not fork schema, value, or workflow validation in routed pages.
- Do not store display-only labels in IR types when they do not belong to backend contracts.
- Do not silently widen the supported JSON Schema subset without updating tests and backend output-schema compiler expectations.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
