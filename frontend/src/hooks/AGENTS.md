# FRONTEND HOOKS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file only covers `src/hooks/`.

## OVERVIEW
`src/hooks/` wraps the `src/lib/api/*.ts` modules with TanStack Query hooks for portfolios, balances, positions, trading operations, market data, templates, reports, simulations, orchestration, runtime, Studio, Tryout, and one small UI debounce helper.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio list/detail mutations | `use-portfolios.ts` | list/detail hooks + portfolio invalidation |
| Balance flows | `use-balances.ts` | portfolio-scoped CRUD |
| Position + CSV flows | `use-positions.ts` | CRUD, symbol lookup, preview/commit imports |
| Trading operations | `use-trading-operations.ts` | list + create trading operations |
| Market data | `use-market-data.ts` | quotes/history with symbol guards |
| Template flows | `use-templates.ts` | list/detail CRUD, inline compile with runtime inputs, placeholder tree |
| Report flows | `use-reports.ts` | list/detail, compile with runtime inputs, upload, update, delete |
| Simulation flows | `use-simulations.ts` | list/detail, 5s running-state polling, create, cancel, delete |
| Orchestration flows | `use-orchestration.ts` | roles, characters, mention catalog, invalidation helpers |
| Runtime flows | `use-runtime.ts` | v2 runtime runs, artifacts, approvals, trace, cancel, and approval actions |
| Studio flows | `use-studio.ts` | v2 Studio runs plus agent/workflow/persona/capability list/detail and CRUD/status mutations |
| Tryout flows | `use-tryouts.ts` | v2 Tryout execute/read/persist hooks with runtime/Studio invalidation |
| Orchestration hook tests | `use-orchestration.test.ts` | orchestration write invalidation coverage |
| Generic timing helper | `use-debounce.ts` | small debounce helper used by the template editor |

## CONVENTIONS
- Portfolio-scoped query hooks accept `portfolioId | undefined`, derive a resolved id, and gate execution with `enabled`.
- Mutations invalidate either list/detail keys or `invalidatePortfolioScope()`; do not hand-roll cache clearing in components.
- Template hooks invalidate `queryKeys.templates.list()` and keep placeholder/detail query composition inside the hooks layer.
- Report hooks invalidate `queryKeys.reports.list()` for writes and additionally invalidate slug-scoped detail keys after content edits so the detail route refreshes without a redirect.
- `useSimulation()` owns the 5-second `refetchInterval` policy for `PENDING`, `RUNNING`, `AWAITING_CALLBACK`, and `PROCESSING_CALLBACK` rows, while create/cancel/delete invalidate both the list and the affected detail query.
- `useOrchestration*` hooks own role/character cache invalidation and also invalidate the orchestration mention catalog after writes so prompt-time target lists stay current.
- `useRuntime*` hooks own runtime/studio cache invalidation after run cancellation or approval actions so Tryout and Studio views stay in sync without page-local cache edits.
- `useStudio*` hooks own the v2 Studio query/mutation wiring for spec catalogs, runtime run inspection, and related invalidation.
- `useTryout*` hooks own Tryout execute/persist invalidation across Tryout, runtime, and Studio namespaces so the page only manages draft UI and toasts.
- `useCompileInline()` is a mutation because it represents explicit compile work rather than cached resource fetching; it accepts both template content and optional runtime inputs for `{{inputs...}}` preview resolution.
- `useCompileReport()` is a mutation because report generation is a write that creates a persisted snapshot from a template and may include runtime inputs.
- The template editor owns the 500 ms debounce for inline compile; hooks expose compile/query primitives but do not debounce internally.
- Hooks wrap `src/lib/api*.ts` only and keep server-state orchestration out of routed screens.
- Generic utility hooks such as `use-debounce.ts` should stay UI-focused and framework-agnostic.

## ANTI-PATTERNS
- Do not call `src/lib/api*.ts` directly from routed screens when a hook already exists.
- Do not invent inline query keys in components.
- Do not mutate cache state ad hoc when invalidation helpers already model the scope.
- Do not hide API errors in hooks; let the caller decide how to surface them.
- Do not special-case report uploads or downloads in pages when the hooks/API modules already own the request behavior.
- Do not reimplement simulation polling or terminal-state cleanup in pages when `use-simulations.ts` already models those transitions.
- Do not move route-local UI state into this layer just because a page is busy.
- Do not duplicate orchestration invalidation logic in page components.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES
- `invalidatePortfolioScope()` is the shared invalidation path for portfolio-scoped mutations.
- Template hooks keep cache policy intentionally simple: list invalidation on writes, page-level navigation/toasts in the callers.
- Report hooks keep the same pattern: list invalidation on writes, report-page navigation and toast actions in callers such as the reports list and template editor.
- Simulation hooks follow the same split: query orchestration and invalidation live here, while launch/cancel/delete toasts plus route transitions stay in the simulation pages.
- Orchestration hooks follow the same split too: cache policy and API wiring live here, while forms and navigation stay in the route family.
- Runtime, Studio, and Tryout hooks follow the same pattern: cache keys and cross-surface invalidation live here, while route-level pages own draft state, navigation, and toast feedback.
