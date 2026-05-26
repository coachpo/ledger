# FRONTEND HOOKS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file only covers `src/hooks/`.

## OVERVIEW
`src/hooks/` wraps the current `src/lib/api/*.ts` modules with TanStack Query hooks for portfolios, balances, positions, trading operations, market data, templates, reports, Extensions, Workflow Packages, extension-filtered read-only Tools metadata for package authoring, Model Connections, Memory, Runs, plus lightweight route-shell UI state helpers for inventory view mode, filters, selection, split-inspector panes, and one small debounce helper.

Extension model: statically resident extension state flows.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio list/detail mutations | `use-portfolios.ts` | list/detail hooks plus portfolio invalidation |
| Balance flows | `use-balances.ts` | portfolio-scoped CRUD |
| Position + CSV flows | `use-positions.ts` | CRUD, symbol lookup, preview/commit imports |
| Trading operations | `use-trading-operations.ts` | list plus create trading operations |
| Market data | `use-market-data.ts` | quotes/history with symbol guards |
| Template flows | `use-templates.ts` | list/detail CRUD, inline compile with runtime inputs, placeholder tree |
| Report flows | `use-reports.ts` | list/detail, compile with runtime inputs, upload, update, delete |
| Extension state flows | `use-extensions.ts` | `/api/extensions` list/toggle state, finance cache invalidation, route/tool visibility support |
| Workflow Package flows | `use-workflow-packages.ts` | package list/detail, manifest CRUD, import, export, secret bindings, runtime-input registry, validation, preflight, launch, and extension-filtered tool reads |
| Model connection flows | `use-model-connections.ts` | saved endpoint CRUD, delete, connection-test helpers |
| Memory flows | `use-memory.ts` | explicit-scope memory list/detail/revision/event reads with caller-owned access-context gating |
| Run flows | `use-runs.ts` | run list/detail reads with package provenance, backend progress/queue payloads, active queued/running polling, plus rerun/fork drafts and create mutations |
| Inventory view state | `use-inventory-view-state.ts` | cards/table mode state shared by inventory routes |
| Resource filter state | `use-resource-filter-state.ts` | labeled search/filter text and derived filter helpers for shared inventory shells |
| Resource selection state | `use-resource-selection-state.ts` | table-only selection, select-all, clear, and scoped bulk-action state |
| Split inspector state | `use-split-inspector-state.ts` | workspace/run-detail inspector open state for shared split-pane layouts |
| Hook test hotspots | `use-workflow-packages.test.ts`, `use-model-connections.test.ts`, `use-runs.test.ts`, `use-inventory-view-state.test.ts`, `use-resource-filter-state.test.ts`, `use-resource-selection-state.test.ts`, `use-split-inspector-state.test.ts` | focused cache, mutation, and shared route-shell state coverage |
| Generic timing helper | `use-debounce.ts` | small debounce helper used by the template editor |

## CONVENTIONS
- Portfolio-scoped query hooks accept `portfolioId | undefined`, derive a resolved id, and gate execution with `enabled`.
- Mutations invalidate either list/detail keys or `invalidatePortfolioScope()`; do not hand-roll cache clearing in components.
- Template hooks invalidate `queryKeys.templates.list()` and keep placeholder/detail query composition inside the hooks layer.
- Report hooks invalidate `queryKeys.reports.list()` for writes and additionally invalidate slug-scoped detail keys after content edits so the detail route refreshes without a redirect.
- `useTools()` composes `/api/tools` with `useExtensions()` and returns extension-filtered read-only tool metadata for package capability-profile pickers.
- Package-first platform hooks invalidate `queryKeys.platform.*` namespaces. Package mutations also refresh launch, preflight, manifest/detail, and runtime-input-registry scopes so saved-input and run-creation surfaces converge after edits/imports/deletes.
- Memory hooks read through `queryKeys.platform.memory.*`; pages must pass explicit access context payloads and use `enabled` to avoid calling `/api/memory` before a package context and private scope exist.
- Model-connection connection tests invalidate persisted last-test metadata after save/test flows.
- `useToggleExtension()` invalidates extension state plus finance workspace caches so routes, nav, and package tool filters converge after enable/disable changes.
- UI state hooks such as `useInventoryViewState()`, `useResourceFilterState()`, `useResourceSelectionState()`, and `useSplitInspectorState()` stay presentational and page-local; they coordinate shared shells but never fetch or invalidate server data.
- `useCompileInline()` is a mutation because it represents explicit compile work rather than cached resource fetching; it accepts both template content and optional runtime inputs for `{{inputs...}}` preview resolution.
- `useCompileReport()` is a mutation because report generation is a write that creates a persisted snapshot from a template and may include runtime inputs.
- The template editor owns the 500 ms debounce for inline compile; hooks expose compile/query primitives but do not debounce internally.
- Hooks wrap `src/lib/api*.ts` only and keep server-state request logic out of routed screens.
- Generic utility hooks such as `use-debounce.ts` should stay UI-focused and framework-agnostic.

## ANTI-PATTERNS
- Do not call `src/lib/api*.ts` directly from routed screens when a hook already exists.
- Do not invent inline query keys in components; keys must include every variable used by the query function.
- Do not mutate cache state ad hoc when invalidation helpers already model the scope.
- Do not hide API errors in hooks; let the caller decide how to surface them.
- Do not special-case report uploads or downloads in pages when the hooks/API modules already own the request behavior.
- Do not bypass `use-extensions.ts` or `useTools()` for extension state and tool visibility in package flows.
- Do not move route-local UI state into this layer just because a page is busy.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES
- `invalidatePortfolioScope()` is the shared invalidation path for portfolio-scoped mutations.
- Template and report hooks keep cache policy intentionally simple: list/detail invalidation in hooks, navigation and toasts in callers.
- `invalidateWorkflowPackageScope()` and `invalidateWorkflowPackageRuntimeInputRegistryScope()` are the central package-side invalidation helpers; keep route surfaces aligned with them instead of inventing page-local refresh rules.
- Package-first platform hooks follow the same split: cache policy, extension-state filtering, explicit Memory access payloads, and API wiring live here, while routed pages own draft UI, navigation, and feedback.
- The route-shell state hooks are reusable across finance inventories and platform workspace/console pages; current cross-route usage varies by hook, so keep cards/table/filter/selection/inspector behavior aligned here instead of cloning page-local implementations.
