# FRONTEND PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers routed page components in `src/pages/`.

## CHILD DOCS
- `backtests/AGENTS.md` — backtest list/config/detail orchestration and running-state polling rules
- `orchestration/AGENTS.md` — orchestration index, role, and character route family
- `portfolios/AGENTS.md` — portfolio list/detail route orchestration and quote-enriched workspace rules
- `templates/AGENTS.md` — template list/editor orchestration, debounce preview, and placeholder rules
- `reports/AGENTS.md` — report list/detail routes, markdown rendering, upload/generate/download behavior

## OVERVIEW
`src/pages/` contains the top-level routed screen components that map directly to routes defined in `src/routes.ts`. Each page composes hooks, shared components, or feature UI to deliver a complete user-facing workflow.

## STRUCTURE
```text
src/pages/
├── dashboard.tsx           # home route summary
├── backtests/
│   ├── list.tsx            # backtest inventory and terminal delete flow
│   ├── config.tsx          # simulation launch form with portfolio/template options
│   └── detail.tsx          # running-state progress plus completed results
├── studio/
│   ├── index.tsx           # Studio landing page for v2 catalog and run entry points
│   ├── agents/             # agent spec list/editor routes
│   ├── workflows/          # workflow spec list/editor routes
│   ├── personas/           # persona profile list/editor-style inspection routes
│   ├── capabilities/       # capability registry list/editor routes
│   └── runs/
│       └── detail.tsx      # Studio runtime run detail route
├── tryout/
│   └── index.tsx           # Tryout execute/inspect/persist/approval route
├── orchestration/
│   ├── index.tsx           # orchestration landing page
│   ├── roles/
│   │   ├── list.tsx        # role inventory and CRUD entry points
│   │   └── editor.tsx      # role create/edit form
│   └── characters/
│       ├── list.tsx        # character inventory and CRUD entry points
│       └── editor.tsx      # character create/edit form
├── portfolios/
│   ├── list.tsx            # portfolio workspace landing
│   └── detail.tsx          # portfolio detail with balances/positions/trades
├── reports/
│   ├── list.tsx            # report inventory with generate/upload/delete flows
│   └── detail.tsx          # markdown report read/edit/download route
└── templates/
    ├── list.tsx            # stored-template list and delete flow
    └── editor.tsx          # full-height editor, inline compile preview, placeholder browser
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Dashboard landing | `dashboard.tsx` | home route summary and retry state |
| Backtest routes | `backtests/AGENTS.md` | list/config/detail, 5s polling, charts, and cleanup |
| Studio routes | `studio/**/*`, `../components/layout.tsx`, `../routes.ts` | `/studio` catalog plus agent/workflow/persona/capability CRUD and run detail routes |
| Tryout route | `tryout/index.tsx`, `../routes.ts` | `/tryout` execute/inspect/persist flow using runtime and Studio data |
| Orchestration routes | `orchestration/AGENTS.md` | orchestration landing plus role and character CRUD |
| Portfolio workspace | `portfolios/AGENTS.md` | portfolio list and detail workspace |
| Report routes | `reports/AGENTS.md` | list/detail, upload/generate, markdown view/edit/download |
| Template list/editor | `templates/AGENTS.md` | stored-template CRUD, inline compile preview, placeholder insertion |

## CONVENTIONS
- Each page component maps to exactly one route in `src/routes.ts`.
- `src/routes.ts` owns the actual route table, while `src/components/layout.tsx` owns the shell, breadcrumbs, and sidebar labels.
- Pages compose hooks from `src/hooks/`, shared components from `src/components/shared/`, and feature components from the relevant feature folders.
- Pages handle top-level data fetching, mutation feedback (toasts), and route-level error states.
- Pages should not contain business logic; delegate to hooks or feature-specific components.
- Backtest pages keep polling, chart wiring, report-link extraction, and launch-form state at the route level while leaving request details to hooks and API modules.
- The template editor page uses `useDebounce()`, `useCompileInline()`, and `usePlaceholders()` to keep preview and placeholder browsing responsive without moving that orchestration into the component library.
- Report pages use `use-reports.ts` for server state, render markdown in read mode, and keep edit-mode textareas local to the route component.
- Studio pages use the v2 Studio hooks and route params to keep spec CRUD, runtime run inspection, and sidebar/breadcrumb ownership inside the routed page layer.
- The Tryout page composes `use-tryouts.ts`, `use-runtime.ts`, and `use-studio.ts` for execute/persist/approval flows while keeping request details and cache invalidation in hooks.
- Orchestration pages use `use-orchestration.ts` plus shared role/character form schemas and keep route transitions/toasts in the page layer.
- Portfolio detail pages compose portfolio, balance, position, trade, and market-data hooks together; quote enrichment and allocation math stay in shared analytics helpers instead of the page body.

## ANTI-PATTERNS
- Do not put business rules or complex state management directly in page components.
- Do not duplicate feature-specific logic here when a feature folder or hook already owns it.
- Do not call `fetch` directly; use hooks from `src/hooks/` instead.
- Do not create ad-hoc query keys in pages; use canonical keys from `src/lib/query-keys.ts`.
- Do not bypass the layout shell, error boundary, or template-editor full-height layout rules when adding a new page.
- Do not duplicate report request logic in page components when `use-reports.ts` and the template editor already own the server-side workflow.
- Do not move orchestration route logic into generic component folders.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm test:e2e
```

## NOTES
- Pages are thin orchestration layers; the real complexity lives in hooks, shared components, and feature folders.
- Portfolio detail pages are routable but not exposed separately in the sidebar.
- Studio and Tryout are first-class routed surfaces wired through `src/routes.ts` and `src/components/layout.tsx`; Studio exposes the v2 catalog/run workspace, while Tryout exposes the v2 execution/persist/approval flow.
- Orchestration is a first-class sidebar route group, and its landing page links out to roles and characters.
