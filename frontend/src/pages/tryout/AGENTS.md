# TRYOUT PAGE GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/tryout/` owns the v2 Tryout flow: select one workflow spec or one single-agent spec, execute it, inspect the active run, resolve approvals, and optionally persist the result.

## STRUCTURE
```text
src/pages/tryout/
├── index.tsx               # main Tryout route
├── approval-card.tsx       # approval UI tied to the active runtime run
├── shared.ts               # validation, formatting, and runtime-input helpers
├── use-tryout-draft.ts     # local draft-state helper
└── index.test.tsx          # route-level coverage
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Main route | `index.tsx` | execute, inspect, persist, and approval flow anchored to the active run id |
| Draft behavior | `use-tryout-draft.ts` | local form state and runtime-input row behavior |
| Local helpers | `shared.ts` | validation messages, runtime-input map building, target summaries, formatting |
| Approval UI | `approval-card.tsx` | approval actions shown for the active run |
| Hook wiring | `../../hooks/use-tryouts.ts`, `../../hooks/use-runtime.ts`, `../../hooks/use-studio.ts` | Tryout create/persist, runtime reads, and Studio catalog selection |
| API/types | `../../lib/api/tryouts.ts`, `../../lib/api/runtime.ts`, `../../lib/types/tryout.ts`, `../../lib/types/runtime.ts` | v2 request helpers and wire contracts |

## CONVENTIONS
- The Tryout draft stays local until execution begins; keep transient form state in `use-tryout-draft.ts`, not in global hooks.
- `index.tsx` pins all inspect/persist/approval behavior to the active run id after a successful execute call.
- Workflow-spec and single-agent selection comes from active Studio catalogs via `use-studio.ts`; do not duplicate catalog-fetching logic locally.
- Runtime inputs are assembled through the helpers in `shared.ts`; keep JSON/string formatting there instead of in JSX branches.
- Persist is a separate explicit action after execution, and approval handling stays attached to the active runtime run.

## ANTI-PATTERNS
- Do not call v2 API helpers directly from JSX handlers when the corresponding hooks already exist.
- Do not invent page-local cache invalidation outside `use-tryouts.ts` and `use-runtime.ts`.
- Do not move Tryout draft state into the generic hooks layer just because the page is large.
- Do not hand-build runtime input maps or approval payloads in multiple places.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES
- Tryout is the browser-facing execution surface for a single workflow or single-agent run.
- The page intentionally combines execution, inspection, persist, and approval actions so a user can stay in one route while iterating on a run.
- `use-tryouts.ts` invalidates Tryout, runtime, and Studio scopes together so the active run stays coherent across route families.
