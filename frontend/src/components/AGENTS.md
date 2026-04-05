# FRONTEND COMPONENTS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers shared components, feature-specific components, and UI primitives in `src/components/`.

## OVERVIEW
`src/components/` contains the layout shell, theme system, shared component library, cross-route form/dialog surfaces, template-editor support components, portfolio-specific UI folders, backtest result widgets, and shadcn/ui primitives. Routed page components live in `src/pages/` and map to routes in `src/routes.ts`, including the report and backtest flows that reuse the shared shell and dialogs.

## STRUCTURE
```text
src/components/
├── layout.tsx              # sidebar shell, breadcrumbs, route framing
├── theme-provider.tsx      # localStorage + system theme sync
├── theme-toggle.tsx        # header control for light/dark/system
├── theme.ts                # theme context types
├── shared/                 # reusable components across features
├── forms/                  # cross-feature dialog forms
│   └── AGENTS.md
├── templates/              # template-editor support components and placeholder/runtime-input UI
│   └── AGENTS.md
├── backtests/              # backtest result widgets and status display
├── portfolios/             # portfolio feature-specific components
│   └── AGENTS.md
└── ui/                     # shadcn/ui primitives and helpers
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App shell / navigation | `layout.tsx`, `shared/error-boundary.tsx` | sidebar shell, portfolio/template/report nav, top-level error boundary |
| Theme behavior | `theme-provider.tsx`, `theme-toggle.tsx`, `theme.ts` | persisted theme state and system-sync logic |
| Shared components | `shared/AGENTS.md` | reusable data tables, metrics, field schemas, and error boundaries |
| Form components | `forms/AGENTS.md` | shared dialog forms that do not belong in a feature folder |
| Template-editor support UI | `templates/AGENTS.md` | placeholder reference and runtime-input surfaces used by template routes |
| Backtest feature UI | `backtests/AGENTS.md` | status badges, KPI cards, charts, and trade log tables |
| Portfolio feature UI | `portfolios/AGENTS.md` | sections, dialogs, trading form, feature-specific logic |
| Pure UI primitives | `ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |

## CHILD DOCS
- `shared/AGENTS.md` — reusable cross-feature components and schema helpers
- `forms/AGENTS.md` — cross-route dialog forms such as portfolio and report-generation dialogs
- `templates/AGENTS.md` — template-editor support components such as placeholder reference and runtime-input sections
- `backtests/AGENTS.md` — backtest charts, metrics, badges, and trade log tables
- `portfolios/AGENTS.md` — portfolio feature sections, dialogs, and trades UI
- `ui/AGENTS.md` — presentational shadcn/ui wrappers, sidebar context, and shared style helpers

## CONVENTIONS
- Routed page components live in `src/pages/` and are thin orchestration layers.
- Shared components in `shared/` are reusable across multiple features and should not contain portfolio-specific request logic.
- `shared/` is where the app keeps reusable data tables, metric cards, field schemas, and error boundaries; if a component only makes sense inside one feature route, keep it out of this folder.
- `forms/` is reserved for small cross-feature form surfaces such as portfolio creation/editing and shared report-generation dialogs.
- `templates/` is reserved for template-editor support widgets such as placeholder browsing and runtime-input row controls.
- Backtest result widgets stay in `backtests/` because they share a single wire contract, chart stack, and result vocabulary, even when they reuse shared cards or tables.
- Feature-specific components in `portfolios/` own their domain logic and should not be reused outside that feature without a clear abstraction.
- Report routes currently stay page-centric and reuse shared components such as `ConfirmDeleteDialog` instead of maintaining a dedicated `components/reports/` feature folder.
- Theme state lives in `theme-provider.tsx`; leaf components should consume the existing context instead of creating new theme state.
- `ui/` stays presentational; application state and request logic should stay in pages, shared, forms, or feature folders.

## ANTI-PATTERNS
- Do not put business rules or raw request code in `ui/` components.
- Do not put feature-specific logic in `shared/` components.
- Do not duplicate portfolio feature rules in shared components when the portfolio folder already owns them.
- Do not move backtest charts or trade-log widgets into `shared/` until another feature genuinely reuses the same result contract.
- Do not move feature-rich components into `ui/` just because they render cards or forms.
- Do not create one-off forms in feature folders when they should live in `forms/` or a shared dialog component.
- Do not move template-editor-only support widgets into `shared/` just because they render generic inputs or lists.
- Do not create a `components/reports/` folder just to wrap page-local report markup unless report UI genuinely becomes reusable across routes.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- `Layout` switches between the usual scroll container and a full-height outlet for template editor routes.
- `Layout` owns the Reports sidebar entry and breadcrumb labels for both `/reports` and `/reports/:slug`.
- `layout.tsx` owns route labels and nav composition; `ui/sidebar.tsx` and `ui/sidebar-context.ts` stay generic primitives.
- Page components stay thin; the real complexity lives in hooks, shared components, forms, and portfolio feature folders.
