# FRONTEND OUTPUT SCHEMAS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/output-schemas/` contains the routed output schema inventory and the builder-first editor. The editor keeps the builder tree, raw JSON Schema tab, and preview tab in sync through shared helpers in `shared.ts`.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Output schema inventory | `list.tsx` | list query, edit, and summary badges |
| Output schema editor | `editor.tsx` | create/update, activation, builder, JSON Schema, and preview tabs |
| Builder helpers | `shared.ts` | builder-to-schema conversion, preview generation, parsing, and validation |
| Output schema hooks | `../../hooks/use-output-schemas.ts` | list/detail CRUD and activation |
| Output schema types | `../../lib/types/output-schema.ts` | builder node shapes, write payloads, and schema read models |

## CONVENTIONS
- The builder is the primary editing surface, and the JSON Schema tab reflects the builder state.
- Preview values are derived from the builder helpers, not hand-written in the page.
- Activation is a post-create workflow, so saved records can move from draft to active.
- `shared.ts` owns the reusable parse and conversion rules for the page family.
- Hooks own cache invalidation, while the page owns tab state, editor state, and validation feedback.

## ANTI-PATTERNS
- Do not let the JSON Schema tab diverge from the builder state.
- Do not duplicate preview generation or schema conversion inside the editor component.
- Do not bypass the hook layer for activation or CRUD.
- Do not add builder kinds without updating the shared helpers and the editor together.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
